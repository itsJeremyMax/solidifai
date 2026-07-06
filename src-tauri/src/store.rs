//! Shared durability layer for the on-disk JSON settings stores.
//!
//! Owns the parts every store needs but should not re-implement: atomic writes
//! (temp + fsync + rename), corruption backup (never silently wipe an unreadable
//! file), and versioned load with migration dispatch. Everything here is untyped
//! (`serde_json::Value`) — migrations restructure raw JSON; callers type at the
//! edges.

use std::fs;
use std::path::Path;

use serde_json::{Map, Value};

/// Outcome of reading a JSON file from disk.
pub enum ReadResult {
    /// No file present (a normal, silent "use defaults" case).
    Missing,
    /// Parsed successfully.
    Ok(Value),
    /// Present but unparseable. The original bytes have been backed up; the caller
    /// should fall back to defaults rather than treat this as data.
    Corrupt,
}

/// Epoch milliseconds, for backup-file naming. Saturates to 0 on a clock error.
fn now_ms() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

/// Atomically write `value` as pretty JSON to `dir/file`: write to a sibling
/// `<file>.tmp`, fsync it, then rename over the target. An interrupted write can
/// never truncate the real file (the rename is same-directory, hence atomic).
pub fn write_json_atomic(dir: &Path, file: &str, value: &Value) -> Result<(), String> {
    use std::io::Write;
    fs::create_dir_all(dir).map_err(|e| format!("failed to create dir {}: {e}", dir.display()))?;
    let path = dir.join(file);
    let tmp = dir.join(format!("{file}.tmp"));
    let mut text = serde_json::to_string_pretty(value)
        .map_err(|e| format!("failed to serialize {file}: {e}"))?;
    text.push('\n');
    {
        let mut f = fs::File::create(&tmp)
            .map_err(|e| format!("failed to create {}: {e}", tmp.display()))?;
        f.write_all(text.as_bytes())
            .map_err(|e| format!("failed to write {}: {e}", tmp.display()))?;
        f.sync_all()
            .map_err(|e| format!("failed to fsync {}: {e}", tmp.display()))?;
    }
    fs::rename(&tmp, &path).map_err(|e| {
        format!(
            "failed to rename {} -> {}: {e}",
            tmp.display(),
            path.display()
        )
    })
}

/// Read `dir/file` as JSON. A present-but-unparseable file is copied to
/// `<file>.<epoch_ms>.bak`, logged, and reported [`ReadResult::Corrupt`] — we
/// never discard an unreadable file without first preserving its bytes.
pub fn read_json(dir: &Path, file: &str) -> ReadResult {
    let path = dir.join(file);
    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => return ReadResult::Missing,
    };
    match serde_json::from_str::<Value>(&text) {
        Ok(v) => ReadResult::Ok(v),
        Err(e) => {
            let bak = dir.join(format!("{file}.{}.bak", now_ms()));
            let _ = fs::write(&bak, text.as_bytes());
            tracing::warn!(
                path = %path.display(),
                backup = %bak.display(),
                "store file was unparseable ({e}); backed up and using defaults"
            );
            ReadResult::Corrupt
        }
    }
}

/// Top-level integer `version` (absent or non-integer → 0).
fn version_of(v: &Value) -> u32 {
    v.get("version").and_then(|x| x.as_u64()).unwrap_or(0) as u32
}

/// An empty store document stamped at `version` (the in-memory fallback for a
/// missing, corrupt, or un-migratable file). No file is written for these.
fn empty_at(version: u32) -> Value {
    let mut m = Map::new();
    m.insert("version".into(), Value::from(version));
    Value::Object(m)
}

/// Load `dir/file`, migrate it up to `current_version` via `migrate`, write the
/// upgraded file back (best-effort, self-healing), and return the migrated value.
///
/// - Missing or corrupt → an empty object `{ "version": current_version }` and no
///   file is written (the store stays absent until a real save).
/// - Already at `current_version` or NEWER → returned untouched (a newer file from
///   a future build is never downgraded; its unknown keys are preserved).
/// - Older → `migrate(from, value)` is applied, the result is stamped with
///   `current_version`, and written back.
///
/// `migrate` must return a JSON object; a non-object result is treated as
/// un-migratable and falls back to an empty stamped document (no write-back).
pub fn versioned_load(
    dir: &Path,
    file: &str,
    current_version: u32,
    migrate: impl Fn(u32, Value) -> Value,
) -> Value {
    let loaded = match read_json(dir, file) {
        ReadResult::Ok(v) => v,
        ReadResult::Missing | ReadResult::Corrupt => {
            return empty_at(current_version);
        }
    };
    let from = version_of(&loaded);
    if from >= current_version {
        return loaded; // current or newer: leave as-is, preserving unknown keys.
    }
    let migrated = migrate(from, loaded);
    // A migration must yield an object so the version stamp can land and the file
    // can self-heal. If it doesn't (e.g. a hand-corrupted scalar/array a migration
    // couldn't normalize), fall back to the empty default rather than writing back
    // an unstamped value that would re-migrate on every load.
    let Value::Object(mut m) = migrated else {
        return empty_at(current_version);
    };
    m.insert("version".into(), Value::from(current_version));
    let out = Value::Object(m);
    let _ = write_json_atomic(dir, file, &out); // self-healing; ignore failures.
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_dir(tag: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-store-test-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn atomic_write_leaves_no_tmp_file() {
        let dir = tmp_dir("atomic");
        write_json_atomic(&dir, "x.json", &serde_json::json!({ "a": 1 })).unwrap();
        assert!(dir.join("x.json").is_file(), "target written");
        assert!(!dir.join("x.json.tmp").is_file(), "no leftover tmp");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn read_json_missing_is_missing() {
        let dir = tmp_dir("missing");
        assert!(matches!(read_json(&dir, "nope.json"), ReadResult::Missing));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn read_json_corrupt_backs_up_and_reports_corrupt() {
        let dir = tmp_dir("corrupt");
        fs::write(dir.join("bad.json"), "{ not json").unwrap();
        assert!(matches!(read_json(&dir, "bad.json"), ReadResult::Corrupt));
        // The original bytes were preserved to a .bak (no silent wipe).
        let baks: Vec<_> = fs::read_dir(&dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| {
                let n = e.file_name();
                let n = n.to_string_lossy();
                n.starts_with("bad.json.") && n.ends_with(".bak")
            })
            .collect();
        assert_eq!(baks.len(), 1, "exactly one backup written");
        assert_eq!(
            fs::read_to_string(baks[0].path()).unwrap(),
            "{ not json",
            "backup holds the original bytes"
        );
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn versioned_load_missing_returns_empty_at_current_version() {
        let dir = tmp_dir("vl-missing");
        let v = versioned_load(&dir, "c.json", 1, |_from, val| val);
        assert_eq!(v["version"], 1);
        // No file is created for a missing store (load has no side effect here).
        assert!(!dir.join("c.json").is_file());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn versioned_load_migrates_and_writes_back() {
        let dir = tmp_dir("vl-migrate");
        // A v0 file (no version key) with a legacy field.
        fs::write(dir.join("c.json"), r#"{"legacy":true}"#).unwrap();
        let v = versioned_load(&dir, "c.json", 1, |from, mut val| {
            assert_eq!(from, 0);
            if let Value::Object(ref mut m) = val {
                m.insert("migrated".into(), Value::Bool(true));
            }
            val
        });
        assert_eq!(v["version"], 1);
        assert_eq!(v["migrated"], true);
        // Self-healing write-back persisted the upgraded file.
        let on_disk: Value =
            serde_json::from_str(&fs::read_to_string(dir.join("c.json")).unwrap()).unwrap();
        assert_eq!(on_disk["version"], 1);
        assert_eq!(on_disk["migrated"], true);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn versioned_load_preserves_unknown_keys_through_migration() {
        let dir = tmp_dir("vl-unknown");
        // v0 file carrying a key the migration does not touch.
        fs::write(dir.join("c.json"), r#"{"futureKey":42}"#).unwrap();
        let v = versioned_load(&dir, "c.json", 1, |_from, val| val); // no-op migration
        assert_eq!(v["futureKey"], 42, "unknown key survived");
        assert_eq!(v["version"], 1);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn versioned_load_current_version_is_untouched() {
        let dir = tmp_dir("vl-current");
        fs::write(dir.join("c.json"), r#"{"version":1,"keep":"yes"}"#).unwrap();
        let v = versioned_load(&dir, "c.json", 1, |_from, _val| {
            panic!("migration must not run when already at current version")
        });
        assert_eq!(v["keep"], "yes");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn versioned_load_newer_file_is_not_downgraded() {
        let dir = tmp_dir("vl-newer");
        // A file written by a hypothetical future build (version 2 > current 1).
        fs::write(dir.join("c.json"), r#"{"version":2,"newField":"x"}"#).unwrap();
        let v = versioned_load(&dir, "c.json", 1, |_from, _val| {
            panic!("must not migrate a newer file")
        });
        assert_eq!(v["version"], 2, "version left intact");
        assert_eq!(v["newField"], "x", "newer field preserved");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn versioned_load_non_object_migration_falls_back_without_writeback() {
        let dir = tmp_dir("vl-nonobject");
        // A v0 file that is valid JSON but a scalar a migration can't normalize.
        fs::write(dir.join("c.json"), "42").unwrap();
        let v = versioned_load(&dir, "c.json", 1, |_from, val| val); // identity: stays a scalar
                                                                     // Falls back to the empty stamped default...
        assert_eq!(v["version"], 1);
        // ...and does NOT clobber the original file with an unstamped value.
        assert_eq!(fs::read_to_string(dir.join("c.json")).unwrap(), "42");
        let _ = fs::remove_dir_all(&dir);
    }
}
