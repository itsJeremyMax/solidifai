//! One-time migration of app-level stores into the unified config dir.
//!
//! Earlier builds scattered config across three places (the host's Tauri dir, the
//! engine's `<config>/solidifai`, and `~/.solidifai`). They now all live in
//! `<app_config_dir>` (see [`crate::workspaces::config_dir`]); this moves any
//! pre-existing files in so user data isn't orphaned.

use std::path::{Path, PathBuf};

/// Move legacy `materials.json` / `destinations.json` into `canonical` when the
/// canonical copy is absent. Best-effort: failures are logged, never fatal. Must
/// run before anything reads (and re-seeds) the canonical files.
pub fn migrate_into(canonical: &Path) {
    for (legacy_dir, file) in legacy_sources() {
        let src = legacy_dir.join(file);
        let dst = canonical.join(file);
        if dst.exists() || !src.is_file() {
            continue;
        }
        match move_file(&src, &dst) {
            Ok(()) => {
                tracing::info!(from = %src.display(), to = %dst.display(), "migrated legacy config")
            }
            Err(e) => tracing::warn!(from = %src.display(), "config migration skipped: {e}"),
        }
    }
}

/// (dir, file) pairs from builds that predated the unified config dir. The old
/// engine `app_config_dir` is `dirs::config_dir()/solidifai` on every OS.
fn legacy_sources() -> Vec<(PathBuf, &'static str)> {
    let mut out = Vec::new();
    if let Some(home) = dirs::home_dir() {
        out.push((home.join(".solidifai"), "materials.json"));
    }
    if let Some(cfg) = dirs::config_dir() {
        out.push((cfg.join("solidifai"), "destinations.json"));
    }
    out
}

fn move_file(src: &Path, dst: &Path) -> std::io::Result<()> {
    if let Some(parent) = dst.parent() {
        std::fs::create_dir_all(parent)?;
    }
    // rename fails across filesystems; fall back to copy + remove.
    std::fs::rename(src, dst).or_else(|_| {
        std::fs::copy(src, dst)?;
        std::fs::remove_file(src)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn move_file_relocates_and_removes_source() {
        let base = std::env::temp_dir().join(format!("solidifai-legacy-{}", std::process::id()));
        let from = base.join("old");
        let to = base.join("new");
        std::fs::create_dir_all(&from).unwrap();
        std::fs::write(from.join("materials.json"), "{\"x\":1}").unwrap();

        move_file(&from.join("materials.json"), &to.join("materials.json")).unwrap();

        assert!(!from.join("materials.json").exists(), "source removed");
        assert_eq!(
            std::fs::read_to_string(to.join("materials.json")).unwrap(),
            "{\"x\":1}"
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn migrate_skips_when_canonical_present() {
        let base = std::env::temp_dir().join(format!("solidifai-legacy2-{}", std::process::id()));
        let canonical = base.join("canonical");
        std::fs::create_dir_all(&canonical).unwrap();
        std::fs::write(canonical.join("materials.json"), "keep").unwrap();

        // A canonical file already present is never overwritten by migration.
        migrate_into(&canonical);
        assert_eq!(
            std::fs::read_to_string(canonical.join("materials.json")).unwrap(),
            "keep"
        );
        let _ = std::fs::remove_dir_all(&base);
    }
}
