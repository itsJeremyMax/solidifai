use engine_pack::archive::{assemble, write_full, write_pack};
use engine_pack::manifest::Manifest;
use engine_pack::verify::verify_tree;
use std::os::unix::fs::{symlink, PermissionsExt};
use std::path::Path;

fn write(root: &Path, rel: &str, bytes: &[u8], mode: u32) {
    let p = root.join(rel);
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(&p, bytes).unwrap();
    std::fs::set_permissions(&p, std::fs::Permissions::from_mode(mode)).unwrap();
}

/// The core guarantee: assembling tree2 from (tree1 + pack(tree1->tree2))
/// reproduces tree2 exactly, and verifies against tree2's manifest.
#[test]
fn assemble_from_base_and_pack_reproduces_target() {
    let t1 = tempfile::tempdir().unwrap();
    write(t1.path(), "bin/python3", b"#!/fake\n", 0o755);
    write(t1.path(), "lib/big.so", &vec![7u8; 200_000], 0o644); // "native lib", unchanged
    write(t1.path(), "lib/code.py", b"version one", 0o644);
    symlink("python3", t1.path().join("bin/python")).unwrap();
    let m1 = Manifest::build_from_dir(t1.path(), "r1", "darwin-aarch64").unwrap();

    let t2 = tempfile::tempdir().unwrap();
    write(t2.path(), "bin/python3", b"#!/fake\n", 0o755); // unchanged
    write(t2.path(), "lib/big.so", &vec![7u8; 200_000], 0o644); // unchanged
    write(t2.path(), "lib/code.py", b"version two is longer", 0o644); // changed
    write(t2.path(), "lib/added.py", b"brand new", 0o644); // added
    symlink("python3", t2.path().join("bin/python")).unwrap();
    let m2 = Manifest::build_from_dir(t2.path(), "r2", "darwin-aarch64").unwrap();

    // pack contains only the changed/added files (+ symlink), not the big lib
    let pack = t2.path().join("../t.pack.tar.zst");
    let n = write_pack(t2.path(), &m2, &m1, &pack).unwrap();
    assert!(n <= 3, "pack should not carry the unchanged 200KB lib");

    // assemble using t1 as the delta base
    let out = tempfile::tempdir().unwrap();
    assemble(Some(t1.path()), &pack, &m2, out.path()).unwrap();

    // reconstructed tree verifies and hashes identical to target
    verify_tree(out.path(), &m2).unwrap();
    let m_out = Manifest::build_from_dir(out.path(), "r2", "darwin-aarch64").unwrap();
    assert_eq!(m_out.manifest_hash, m2.manifest_hash);
}

/// Full-archive path: a client with no base assembles entirely from the full archive.
#[test]
fn assemble_from_full_archive_with_no_base() {
    let t = tempfile::tempdir().unwrap();
    write(t.path(), "a.py", b"alpha", 0o644);
    write(t.path(), "b/c.so", &vec![1u8; 5000], 0o644);
    let m = Manifest::build_from_dir(t.path(), "r", "linux-x86_64").unwrap();

    let full = t.path().join("../f.full.tar.zst");
    write_full(t.path(), &m, &full).unwrap();

    let out = tempfile::tempdir().unwrap();
    // a full archive contains every file, so it works as a "pack" with no base
    assemble(None, &full, &m, out.path()).unwrap();
    verify_tree(out.path(), &m).unwrap();
}

/// Tamper detection: corrupting a base file the pack relies on must fail verify.
#[test]
fn corrupted_base_file_fails_verification() {
    let t1 = tempfile::tempdir().unwrap();
    write(t1.path(), "keep.so", &vec![9u8; 1000], 0o644);
    write(t1.path(), "x.py", b"one", 0o644);
    let m1 = Manifest::build_from_dir(t1.path(), "r1", "p").unwrap();

    let t2 = tempfile::tempdir().unwrap();
    write(t2.path(), "keep.so", &vec![9u8; 1000], 0o644); // unchanged -> sourced from base
    write(t2.path(), "x.py", b"two", 0o644);
    let m2 = Manifest::build_from_dir(t2.path(), "r2", "p").unwrap();

    let pack = t2.path().join("../c.pack.tar.zst");
    write_pack(t2.path(), &m2, &m1, &pack).unwrap();

    // corrupt the base copy of keep.so
    write(t1.path(), "keep.so", &vec![0u8; 1000], 0o644);

    let out = tempfile::tempdir().unwrap();
    let res = assemble(Some(t1.path()), &pack, &m2, out.path());
    assert!(
        res.is_err(),
        "corrupted base file must fail tree verification"
    );
}

/// Drive the CLI end-to-end: build a manifest, write a full archive, assemble
/// from it with no base, and confirm the file content survived.
#[test]
fn cli_manifest_full_assemble_roundtrip() {
    let bin = env!("CARGO_BIN_EXE_engine-pack");
    let t = tempfile::tempdir().unwrap();
    write(t.path(), "a.py", b"hello", 0o644);
    write(t.path(), "lib/x.so", &vec![3u8; 8000], 0o644);

    let man = t.path().join("../m.json");
    let full = t.path().join("../f.tar.zst");
    let out = tempfile::tempdir().unwrap();

    use std::ffi::OsStr;
    let st = |args: &[&OsStr]| {
        std::process::Command::new(bin)
            .args(args)
            .status()
            .unwrap()
            .success()
    };
    assert!(st(&[
        OsStr::new("manifest"),
        t.path().as_os_str(),
        OsStr::new("r"),
        OsStr::new("p"),
        man.as_os_str()
    ]));
    assert!(st(&[
        OsStr::new("full"),
        t.path().as_os_str(),
        man.as_os_str(),
        full.as_os_str()
    ]));
    assert!(st(&[
        OsStr::new("assemble"),
        OsStr::new("-"),
        full.as_os_str(),
        man.as_os_str(),
        out.path().as_os_str()
    ]));

    assert_eq!(std::fs::read(out.path().join("a.py")).unwrap(), b"hello");
}

/// A pure rename (same bytes, new path) must ship in the pack so assemble finds it.
#[test]
fn pack_ships_moved_file() {
    let t1 = tempfile::tempdir().unwrap();
    write(t1.path(), "lib/foo.so", &vec![5u8; 4000], 0o644);
    write(t1.path(), "keep.py", b"k", 0o644);
    let m1 = Manifest::build_from_dir(t1.path(), "r1", "p").unwrap();

    let t2 = tempfile::tempdir().unwrap();
    write(t2.path(), "lib/vendor/foo.so", &vec![5u8; 4000], 0o644); // moved, same bytes
    write(t2.path(), "keep.py", b"k", 0o644);
    let m2 = Manifest::build_from_dir(t2.path(), "r2", "p").unwrap();

    let pack = t2.path().join("../mv.pack.tar.zst");
    write_pack(t2.path(), &m2, &m1, &pack).unwrap();

    let out = tempfile::tempdir().unwrap();
    assemble(Some(t1.path()), &pack, &m2, out.path()).unwrap(); // ENOENT before the fix
    verify_tree(out.path(), &m2).unwrap();
}

/// verify_tree rejects a file on disk that the manifest does not list.
#[test]
fn verify_tree_rejects_extra_file() {
    let t = tempfile::tempdir().unwrap();
    write(t.path(), "a.py", b"a", 0o644);
    let m = Manifest::build_from_dir(t.path(), "r", "p").unwrap();
    verify_tree(t.path(), &m).unwrap();
    write(t.path(), "evil.py", b"x", 0o644);
    assert!(verify_tree(t.path(), &m).is_err());
}
