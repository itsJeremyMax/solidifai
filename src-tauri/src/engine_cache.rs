//! Content-addressed engine cache in app-data. The engine's runtime home is here,
//! never the app bundle, so app updates can ship engine-less. Layout:
//!   engines/<manifestHash>/   a verified engine tree (.ready marker when usable)
//!   engines/current           pointer (symlink on unix, hash file on windows)
//!   engines/python-current    launcher shim that execs current's interpreter
//!   engines/.staging/         in-progress assembly, never pointed at until verified

use engine_pack::manifest::Manifest;
use engine_pack::verify::verify_tree;
use std::path::{Path, PathBuf};

pub struct EngineCache {
    root: PathBuf,
}

impl EngineCache {
    pub fn new(app_data: &Path) -> Self {
        Self {
            root: app_data.join("engines"),
        }
    }

    pub fn root(&self) -> &Path {
        &self.root
    }
    pub fn engine_dir(&self, hash: &str) -> PathBuf {
        self.root.join(hash)
    }
    pub fn ready_marker(&self, hash: &str) -> PathBuf {
        self.engine_dir(hash).join(".ready")
    }
    /// A staging dir for ONE assemble/install attempt. Unique per call (pid +
    /// counter) so overlapping attempts can never share a path; leftovers from
    /// failed attempts are swept by [`gc`](Self::gc).
    pub fn staging_dir(&self, hash: &str) -> PathBuf {
        use std::sync::atomic::{AtomicU64, Ordering};
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let n = NEXT.fetch_add(1, Ordering::Relaxed);
        self.root
            .join(".staging")
            .join(format!("{hash}.{}.{n}.tmp", std::process::id()))
    }
    pub fn current_pointer(&self) -> PathBuf {
        self.root.join("current")
    }
    pub fn launcher(&self) -> PathBuf {
        self.root.join(if cfg!(windows) {
            "python-current.cmd"
        } else {
            "python-current"
        })
    }
    pub fn is_ready(&self, hash: &str) -> bool {
        self.ready_marker(hash).exists()
    }

    pub fn interpreter_in(dir: &Path) -> PathBuf {
        if cfg!(windows) {
            dir.join("python.exe")
        } else {
            dir.join("bin/python3")
        }
    }

    /// Verify a fully-assembled `staging` tree against `manifest`, then install it.
    /// Used for fetched (untrusted) engines. On verify failure staging is removed
    /// and the prior engine + `current` are left untouched.
    pub fn install_verified(&self, staging: &Path, manifest: &Manifest) -> anyhow::Result<PathBuf> {
        if let Err(e) = verify_tree(staging, manifest) {
            let _ = std::fs::remove_dir_all(staging);
            return Err(e);
        }
        self.finalize(staging, manifest)
    }

    /// Atomically move `staging` into the cache, mark it ready, record its rev (the
    /// next fetch's delta base), and repoint `current`.
    fn finalize(&self, staging: &Path, manifest: &Manifest) -> anyhow::Result<PathBuf> {
        std::fs::create_dir_all(&self.root)?;
        let hash = &manifest.manifest_hash;
        let dest = self.engine_dir(hash);
        if dest.exists() {
            std::fs::remove_dir_all(&dest)?;
        }
        std::fs::rename(staging, &dest)?;
        std::fs::write(dest.join(".engine-rev"), &manifest.engine_rev)?;
        std::fs::write(self.ready_marker(hash), b"")?;
        // launcher before current, so once current flips the shim is already present
        self.write_launcher()?;
        self.repoint_current(hash)?;
        Ok(dest)
    }

    /// The engineRev of a cached engine dir (recorded at install), if present.
    pub fn rev_of(dir: &Path) -> Option<String> {
        std::fs::read_to_string(dir.join(".engine-rev"))
            .ok()
            .map(|s| s.trim().to_string())
    }

    fn repoint_current(&self, hash: &str) -> anyhow::Result<()> {
        let tmp = self.root.join(".current.tmp");
        let _ = std::fs::remove_file(&tmp);
        #[cfg(unix)]
        std::os::unix::fs::symlink(hash, &tmp)?;
        #[cfg(windows)]
        std::fs::write(&tmp, hash)?;
        // rename replaces an existing pointer atomically; no remove-first window
        std::fs::rename(&tmp, self.current_pointer())?;
        Ok(())
    }

    /// The active engine dir, if `current` resolves to a ready tree.
    pub fn current_dir(&self) -> Option<PathBuf> {
        let cur = self.current_pointer();
        #[cfg(unix)]
        let hash = std::fs::read_link(&cur)
            .ok()?
            .to_string_lossy()
            .into_owned();
        #[cfg(windows)]
        let hash = std::fs::read_to_string(&cur).ok()?.trim().to_string();
        self.is_ready(&hash).then(|| self.engine_dir(&hash))
    }

    pub fn write_launcher(&self) -> anyhow::Result<()> {
        std::fs::create_dir_all(&self.root)?;
        let launcher = self.launcher();
        #[cfg(unix)]
        let content = "#!/bin/sh\nexec \"$(dirname \"$0\")/current/bin/python3\" \"$@\"\n";
        #[cfg(windows)]
        let content = "@echo off\r\nset /p H=<\"%~dp0current\"\r\n\"%~dp0%H%\\python.exe\" %*\r\n";
        // Already correct: don't rewrite. The shim is exec'd by external agents at
        // arbitrary times, and this runs on every workspace open outside the
        // resolve lock — a truncate-then-write here could hand an agent a torn read.
        if std::fs::read(&launcher).is_ok_and(|cur| cur == content.as_bytes()) {
            return Ok(());
        }
        // First write (or content change): temp + rename so the shim path only
        // ever holds a complete file.
        let tmp = self
            .root
            .join(format!(".launcher.{}.tmp", std::process::id()));
        std::fs::write(&tmp, content)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o755))?;
        }
        std::fs::rename(&tmp, &launcher)?;
        Ok(())
    }

    /// Remove cached engine dirs not in `keep`, plus stale staging. The engine
    /// `current` points at (the running engine + next delta base) is always kept,
    /// regardless of `keep`, so a naive caller can't strand it.
    pub fn gc(&self, keep: &[&str]) {
        let reserved = [
            "current",
            ".staging",
            ".current.tmp",
            "python-current",
            "python-current.cmd",
        ];
        let current = self
            .current_dir()
            .and_then(|d| d.file_name().map(|n| n.to_string_lossy().into_owned()));
        if let Ok(rd) = std::fs::read_dir(&self.root) {
            for entry in rd.flatten() {
                let name = entry.file_name().to_string_lossy().into_owned();
                if reserved.contains(&name.as_str())
                    || keep.contains(&name.as_str())
                    || current.as_deref() == Some(name.as_str())
                {
                    continue;
                }
                let _ = std::fs::remove_dir_all(entry.path());
            }
        }
        let _ = std::fs::remove_dir_all(self.root.join(".staging"));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    fn build_tree(dir: &Path) -> Manifest {
        std::fs::create_dir_all(dir.join("bin")).unwrap();
        std::fs::write(dir.join("bin/python3"), b"#!/bin/sh\necho hi\n").unwrap();
        std::fs::set_permissions(
            dir.join("bin/python3"),
            std::fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        std::fs::write(dir.join("lib.py"), b"x = 1").unwrap();
        Manifest::build_from_dir(dir, "rev", "darwin-aarch64").unwrap()
    }

    #[test]
    fn paths_are_under_engines_root() {
        let c = EngineCache::new(Path::new("/app"));
        assert_eq!(c.engine_dir("ab"), Path::new("/app/engines/ab"));
        assert_eq!(c.current_pointer(), Path::new("/app/engines/current"));
        let s = c.staging_dir("ab");
        assert!(s.starts_with("/app/engines/.staging"));
        assert_ne!(c.staging_dir("ab"), s, "staging is unique per call");
    }

    #[test]
    fn install_verified_installs_and_points_current() {
        let app = tempfile::tempdir().unwrap();
        let cache = EngineCache::new(app.path());
        let staging = cache.staging_dir("placeholder");
        std::fs::create_dir_all(staging.parent().unwrap()).unwrap();
        let manifest = build_tree(&staging);

        let dest = cache.install_verified(&staging, &manifest).unwrap();
        assert!(cache.is_ready(&manifest.manifest_hash));
        assert_eq!(cache.current_dir().unwrap(), dest);
        assert!(EngineCache::interpreter_in(&dest).is_file());
        assert!(!staging.exists(), "staging consumed by the rename");

        // launcher resolves through current to the interpreter
        let resolved = cache
            .launcher()
            .parent()
            .unwrap()
            .join("current/bin/python3");
        assert!(resolved.exists());
    }

    #[test]
    fn install_verified_rejects_tampered_tree() {
        let app = tempfile::tempdir().unwrap();
        let cache = EngineCache::new(app.path());
        let staging = cache.staging_dir("x");
        std::fs::create_dir_all(staging.parent().unwrap()).unwrap();
        let manifest = build_tree(&staging);
        std::fs::write(staging.join("lib.py"), b"tampered").unwrap();

        assert!(cache.install_verified(&staging, &manifest).is_err());
        assert!(!cache.engine_dir(&manifest.manifest_hash).exists());
        assert!(cache.current_dir().is_none());
    }

    #[test]
    fn gc_keeps_listed_and_removes_others() {
        let app = tempfile::tempdir().unwrap();
        let cache = EngineCache::new(app.path());
        for h in ["aaa", "bbb", "ccc"] {
            std::fs::create_dir_all(cache.engine_dir(h)).unwrap();
        }
        cache.write_launcher().unwrap();
        cache.gc(&["aaa", "bbb"]);
        assert!(cache.engine_dir("aaa").exists());
        assert!(cache.engine_dir("bbb").exists());
        assert!(!cache.engine_dir("ccc").exists());
        assert!(cache.launcher().exists(), "launcher is reserved, not gc'd");
    }

    #[test]
    fn gc_never_deletes_current_even_with_empty_keep() {
        let app = tempfile::tempdir().unwrap();
        let cache = EngineCache::new(app.path());
        let staging = cache.staging_dir("x");
        std::fs::create_dir_all(staging.parent().unwrap()).unwrap();
        let manifest = build_tree(&staging);
        cache.install_verified(&staging, &manifest).unwrap();
        std::fs::create_dir_all(cache.engine_dir("stale")).unwrap();

        cache.gc(&[]); // empty keep — current's target must still survive
        assert!(cache.engine_dir(&manifest.manifest_hash).exists());
        assert!(cache.current_dir().is_some());
        assert!(!cache.engine_dir("stale").exists());
    }
}
