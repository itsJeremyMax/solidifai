use crate::hash::{sha256_bytes, sha256_file};
use serde::{Deserialize, Serialize};
use std::path::Path;
use walkdir::WalkDir;

#[cfg(unix)]
fn file_mode(md: &std::fs::Metadata) -> Option<String> {
    use std::os::unix::fs::PermissionsExt;
    Some(format!("{:04o}", md.permissions().mode() & 0o7777))
}
#[cfg(not(unix))]
fn file_mode(_md: &std::fs::Metadata) -> Option<String> {
    None // Windows has no exec bit; engine trees there are files-only
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EntryKind {
    File,
    Symlink,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FileEntry {
    /// Forward-slash relative path from the engine root.
    pub path: String,
    #[serde(rename = "type")]
    pub kind: EntryKind,
    /// Unix mode bits as octal string (e.g. "0755"); None for symlinks.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub mode: Option<String>,
    /// SHA-256 of file contents; None for symlinks.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub sha256: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub size: Option<u64>,
    /// Symlink target (relative or absolute as stored); None for files.
    #[serde(skip_serializing_if = "Option::is_none", default)]
    pub target: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Manifest {
    #[serde(rename = "engineRev")]
    pub engine_rev: String,
    pub platform: String,
    pub files: Vec<FileEntry>,
    #[serde(rename = "manifestHash")]
    pub manifest_hash: String,
}

/// OS/desktop droppings that must never make it into a manifest: a user merely
/// browsing the bundled engine in Finder/Explorer writes these, and they would
/// otherwise change the manifest hash and fail the offline seed against the pin.
pub fn is_junk_file(name: &str) -> bool {
    matches!(name, ".DS_Store" | "Thumbs.db" | "desktop.ini") || name.starts_with("._")
}

impl Manifest {
    /// Walk `root` and build a manifest. Entries are sorted by path so the
    /// manifest is deterministic for identical inputs. `manifest_hash` is the
    /// SHA-256 over the canonical JSON of the sorted file list (excluding the
    /// hash field itself). Known OS junk files ([`is_junk_file`]) are ignored,
    /// so a Finder-browsed tree hashes the same as the pristine CI tree.
    pub fn build_from_dir(
        root: &Path,
        engine_rev: &str,
        platform: &str,
    ) -> anyhow::Result<Manifest> {
        let mut files = Vec::new();
        for entry in WalkDir::new(root).sort_by_file_name() {
            let entry = entry?;
            let p = entry.path();
            if p == root {
                continue;
            }
            if entry.file_type().is_file() && is_junk_file(&entry.file_name().to_string_lossy()) {
                continue;
            }
            let rel = p.strip_prefix(root)?.to_string_lossy().replace('\\', "/");
            if entry.path_is_symlink() {
                let target = std::fs::read_link(p)?.to_string_lossy().replace('\\', "/");
                files.push(FileEntry {
                    path: rel,
                    kind: EntryKind::Symlink,
                    mode: None,
                    sha256: None,
                    size: None,
                    target: Some(target),
                });
            } else if entry.file_type().is_file() {
                let md = std::fs::metadata(p)?;
                files.push(FileEntry {
                    path: rel,
                    kind: EntryKind::File,
                    mode: file_mode(&md),
                    sha256: Some(sha256_file(p)?),
                    size: Some(md.len()),
                    target: None,
                });
            }
            // directories are implied by file paths; not recorded
        }
        files.sort_by(|a, b| a.path.cmp(&b.path));
        let manifest_hash = Self::hash_files(&files);
        Ok(Manifest {
            engine_rev: engine_rev.to_string(),
            platform: platform.to_string(),
            files,
            manifest_hash,
        })
    }

    fn hash_files(files: &[FileEntry]) -> String {
        let canonical = serde_json::to_vec(files).expect("file list serializes");
        sha256_bytes(&canonical)
    }

    /// Recompute the hash over the current file list and compare.
    pub fn self_consistent(&self) -> bool {
        Self::hash_files(&self.files) == self.manifest_hash
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::{symlink, PermissionsExt};

    /// OS droppings (a user browsing the bundled engine in Finder writes
    /// .DS_Store) must not change the manifest, or the offline seed fails its
    /// hash check against the pin built from the pristine CI tree.
    #[test]
    fn junk_files_do_not_change_the_manifest_hash() {
        let dir = tempfile::tempdir().unwrap();
        fixture(dir.path());
        let clean = Manifest::build_from_dir(dir.path(), "r1", "darwin-aarch64").unwrap();
        std::fs::write(dir.path().join(".DS_Store"), b"finder junk").unwrap();
        std::fs::write(dir.path().join("bin/._python3"), b"appledouble").unwrap();
        std::fs::write(dir.path().join("Thumbs.db"), b"explorer junk").unwrap();
        let junked = Manifest::build_from_dir(dir.path(), "r1", "darwin-aarch64").unwrap();
        assert_eq!(clean.manifest_hash, junked.manifest_hash);
        assert_eq!(clean.files.len(), junked.files.len());
    }

    fn fixture(root: &Path) {
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
    fn build_is_deterministic_and_records_kinds() {
        let d = tempfile::tempdir().unwrap();
        fixture(d.path());
        let m1 = Manifest::build_from_dir(d.path(), "rev1", "darwin-aarch64").unwrap();
        let m2 = Manifest::build_from_dir(d.path(), "rev1", "darwin-aarch64").unwrap();
        assert_eq!(m1, m2, "identical inputs produce identical manifests");
        assert!(m1.self_consistent());

        let py = m1.files.iter().find(|f| f.path == "bin/python3").unwrap();
        assert_eq!(py.kind, EntryKind::File);
        assert_eq!(py.mode.as_deref(), Some("0755"));
        assert!(py.sha256.is_some());

        let link = m1.files.iter().find(|f| f.path == "bin/python").unwrap();
        assert_eq!(link.kind, EntryKind::Symlink);
        assert_eq!(link.target.as_deref(), Some("python3"));
    }

    #[test]
    fn roundtrips_through_json() {
        let d = tempfile::tempdir().unwrap();
        fixture(d.path());
        let m = Manifest::build_from_dir(d.path(), "rev1", "linux-x86_64").unwrap();
        let json = serde_json::to_string_pretty(&m).unwrap();
        let back: Manifest = serde_json::from_str(&json).unwrap();
        assert_eq!(m, back);
    }
}
