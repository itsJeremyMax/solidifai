use crate::manifest::{EntryKind, FileEntry, Manifest};
use crate::verify::verify_tree;
use std::collections::BTreeMap;
use std::path::Path;

/// Write the whole tree under `root` as a zstd-compressed tar to `out`.
/// Entries are added in manifest (sorted) order with normalized mtimes so the
/// archive is reproducible for identical inputs.
pub fn write_full(root: &Path, manifest: &Manifest, out: &Path) -> anyhow::Result<()> {
    let f = std::fs::File::create(out)?;
    let enc = zstd::Encoder::new(f, 19)?.auto_finish();
    let mut builder = tar::Builder::new(enc);
    builder.follow_symlinks(false);
    for entry in &manifest.files {
        append_entry(&mut builder, root, entry)?;
    }
    builder.finish()?;
    Ok(())
}

fn append_entry<W: std::io::Write>(
    builder: &mut tar::Builder<W>,
    root: &Path,
    entry: &FileEntry,
) -> anyhow::Result<()> {
    let src = root.join(&entry.path);
    match entry.kind {
        EntryKind::File => {
            let mut header = tar::Header::new_gnu();
            let data = std::fs::read(&src)?;
            header.set_size(data.len() as u64);
            let mode = u32::from_str_radix(entry.mode.as_deref().unwrap_or("0644"), 8)?;
            header.set_mode(mode);
            header.set_mtime(0);
            header.set_cksum();
            builder.append_data(&mut header, &entry.path, &data[..])?;
        }
        EntryKind::Symlink => {
            let mut header = tar::Header::new_gnu();
            header.set_entry_type(tar::EntryType::Symlink);
            header.set_size(0);
            header.set_mtime(0);
            builder.append_link(
                &mut header,
                &entry.path,
                entry.target.as_deref().unwrap_or(""),
            )?;
        }
    }
    Ok(())
}

/// Extract a zstd-compressed tar (full or pack) into `dest`, returning the set
/// of relative paths it contained. Restores modes and symlinks.
pub fn extract(archive: &Path, dest: &Path) -> anyhow::Result<BTreeMap<String, ()>> {
    let f = std::fs::File::open(archive)?;
    let dec = zstd::Decoder::new(f)?;
    let mut ar = tar::Archive::new(dec);
    ar.set_preserve_permissions(true);
    ar.set_unpack_xattrs(false);
    let mut present = BTreeMap::new();
    for entry in ar.entries()? {
        let mut entry = entry?;
        let path = entry.path()?.to_string_lossy().replace('\\', "/");
        entry.unpack_in(dest)?;
        present.insert(path, ());
    }
    Ok(present)
}

/// Pack the files the client can't reconstruct from its base. Diff by (path, hash):
/// assemble sources unchanged files by path, so a moved file (same bytes, new path)
/// must still ship. Symlinks always included.
pub fn write_pack(
    root: &Path,
    manifest: &Manifest,
    prev: &Manifest,
    out: &Path,
) -> anyhow::Result<usize> {
    let prev_by_path: BTreeMap<&str, &str> = prev
        .files
        .iter()
        .filter_map(|f| Some((f.path.as_str(), f.sha256.as_deref()?)))
        .collect();

    let f = std::fs::File::create(out)?;
    let enc = zstd::Encoder::new(f, 19)?.auto_finish();
    let mut builder = tar::Builder::new(enc);
    builder.follow_symlinks(false);
    let mut written = 0;
    for entry in &manifest.files {
        let include = match entry.kind {
            EntryKind::Symlink => true,
            EntryKind::File => match entry.sha256.as_deref() {
                Some(h) => prev_by_path.get(entry.path.as_str()) != Some(&h),
                None => true,
            },
        };
        if include {
            append_entry(&mut builder, root, entry)?;
            written += 1;
        }
    }
    builder.finish()?;
    Ok(written)
}

/// Reconstruct the tree described by `manifest` into `dest`, sourcing each file
/// from the extracted `pack` when present, else by copying from `base` (the
/// client's existing engine) matched by relative path. After assembly the whole
/// tree is verified against the manifest; on any failure the caller discards
/// `dest`. `base` may be None (full-archive path: pack must contain everything).
pub fn assemble(
    base: Option<&Path>,
    pack: &Path,
    manifest: &Manifest,
    dest: &Path,
) -> anyhow::Result<()> {
    std::fs::create_dir_all(dest)?;
    // 1. lay down everything the pack carries
    let from_pack = extract(pack, dest)?;
    // 2. fill the rest from base by path
    for entry in &manifest.files {
        if from_pack.contains_key(&entry.path) {
            continue;
        }
        let base =
            base.ok_or_else(|| anyhow::anyhow!("file {} not in pack and no base", entry.path))?;
        let src = base.join(&entry.path);
        let dst = dest.join(&entry.path);
        if let Some(parent) = dst.parent() {
            std::fs::create_dir_all(parent)?;
        }
        match entry.kind {
            EntryKind::Symlink => {
                let _ = std::fs::remove_file(&dst);
                #[cfg(unix)]
                std::os::unix::fs::symlink(entry.target.as_deref().unwrap_or(""), &dst)?;
                // Windows engine trees record no symlinks, so nothing to recreate.
            }
            EntryKind::File => {
                std::fs::copy(&src, &dst)
                    .map_err(|e| anyhow::anyhow!("copy base file {}: {e}", entry.path))?;
            }
        }
    }
    // 3. verify the whole reconstructed tree
    verify_tree(dest, manifest)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hash::sha256_file;
    use std::os::unix::fs::PermissionsExt;

    fn fixture(root: &Path) {
        use std::os::unix::fs::symlink;
        std::fs::create_dir_all(root.join("bin")).unwrap();
        std::fs::write(root.join("bin/python3"), b"#!/fake\n").unwrap();
        std::fs::set_permissions(
            root.join("bin/python3"),
            std::fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        std::fs::write(root.join("data.txt"), b"payload").unwrap();
        symlink("python3", root.join("bin/python")).unwrap();
    }

    #[test]
    fn full_archive_round_trips_bytes_modes_symlinks() {
        let src = tempfile::tempdir().unwrap();
        fixture(src.path());
        let m = Manifest::build_from_dir(src.path(), "r", "p").unwrap();
        let arch = src.path().join("../full.tar.zst");
        write_full(src.path(), &m, &arch).unwrap();

        let dest = tempfile::tempdir().unwrap();
        extract(&arch, dest.path()).unwrap();

        // bytes identical
        assert_eq!(
            sha256_file(&dest.path().join("bin/python3")).unwrap(),
            sha256_file(&src.path().join("bin/python3")).unwrap()
        );
        // mode preserved
        let mode = std::fs::metadata(dest.path().join("bin/python3"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o755);
        // symlink preserved
        assert!(std::fs::symlink_metadata(dest.path().join("bin/python"))
            .unwrap()
            .file_type()
            .is_symlink());

        // the rebuilt manifest matches
        let m2 = Manifest::build_from_dir(dest.path(), "r", "p").unwrap();
        assert_eq!(m.manifest_hash, m2.manifest_hash);
    }

    #[test]
    fn pack_only_contains_changed_files() {
        // tree1
        let t1 = tempfile::tempdir().unwrap();
        std::fs::write(t1.path().join("big.so"), vec![0u8; 4096]).unwrap();
        std::fs::write(t1.path().join("code.py"), b"v1").unwrap();
        let m1 = Manifest::build_from_dir(t1.path(), "r1", "p").unwrap();

        // tree2: big.so unchanged, code.py changed, new.py added
        let t2 = tempfile::tempdir().unwrap();
        std::fs::write(t2.path().join("big.so"), vec![0u8; 4096]).unwrap();
        std::fs::write(t2.path().join("code.py"), b"v2-different").unwrap();
        std::fs::write(t2.path().join("new.py"), b"new").unwrap();
        let m2 = Manifest::build_from_dir(t2.path(), "r2", "p").unwrap();

        let pack = t2.path().join("../d.pack.tar.zst");
        let n = write_pack(t2.path(), &m2, &m1, &pack).unwrap();
        assert_eq!(n, 2, "only code.py + new.py, not the unchanged big.so");

        let dest = tempfile::tempdir().unwrap();
        let present = extract(&pack, dest.path()).unwrap();
        assert!(present.contains_key("code.py"));
        assert!(present.contains_key("new.py"));
        assert!(!present.contains_key("big.so"));
    }
}
