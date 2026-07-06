//! Workspace thumbnail cache: store a captured PNG per workspace (keyed by
//! filesystem-safe FNV-1a hash of the path), list them back as data URLs.
//!
//! Storage layout under `<app_cache_dir>/thumbnails/`:
//!   `<key>.png`  — the raw PNG bytes
//!   `index.json` — sidecar map: workspace path → `{ capturedAt, partCount }`
//!
//! Pure helpers (`upsert`, `remove`, `load_index`, `save_index`) take a `&Path`
//! for the thumb dir so they are unit-testable without a live `AppHandle`.

use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use base64::Engine as _;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

// -- key --------------------------------------------------------------------

/// FNV-1a 64-bit hash of `path`, rendered as 16 lowercase hex chars. Stable,
/// filesystem-safe, and requires no extra crate.
fn key(path: &str) -> String {
    let mut hash: u64 = 0xcbf29ce484222325;
    for b in path.as_bytes() {
        hash ^= *b as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

// -- sidecar model ----------------------------------------------------------

/// Per-entry metadata stored in the sidecar index.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct ThumbInfo {
    pub captured_at: i64,
    pub part_count: u32,
}

const INDEX_FILE: &str = "index.json";

/// Read the sidecar index. Missing or corrupt → empty map (never errors out).
fn load_index(dir: &Path) -> BTreeMap<String, ThumbInfo> {
    let path = dir.join(INDEX_FILE);
    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => return BTreeMap::new(),
    };
    serde_json::from_str(&text).unwrap_or_default()
}

/// Atomically write the sidecar index: serialize → `.tmp` → rename.
fn save_index(dir: &Path, index: &BTreeMap<String, ThumbInfo>) -> Result<(), String> {
    fs::create_dir_all(dir)
        .map_err(|e| format!("failed to create thumb dir {}: {e}", dir.display()))?;
    let value =
        serde_json::to_value(index).map_err(|e| format!("failed to serialize thumb index: {e}"))?;
    crate::store::write_json_atomic(dir, INDEX_FILE, &value)
}

// -- pure helpers -----------------------------------------------------------

/// Write `png` bytes to `<dir>/<key(path)>.png`, then upsert the sidecar entry.
/// `now` is injected (milliseconds) so callers supply `crate::registry::now_ms()`
/// and tests can pass a fixed value.
pub fn upsert(dir: &Path, path: &str, png: &[u8], part_count: u32, now: i64) -> Result<(), String> {
    fs::create_dir_all(dir)
        .map_err(|e| format!("failed to create thumb dir {}: {e}", dir.display()))?;

    let png_path = dir.join(format!("{}.png", key(path)));
    fs::write(&png_path, png)
        .map_err(|e| format!("failed to write thumbnail {}: {e}", png_path.display()))?;

    let mut index = load_index(dir);
    index.insert(
        path.to_string(),
        ThumbInfo {
            captured_at: now,
            part_count,
        },
    );
    save_index(dir, &index)
}

/// Delete `<dir>/<key(path)>.png` and drop the sidecar entry. Best-effort:
/// individual failures are ignored so a partial delete never blocks a workspace
/// delete.
pub fn remove(dir: &Path, path: &str) {
    let png_path = dir.join(format!("{}.png", key(path)));
    let _ = fs::remove_file(&png_path);

    let mut index = load_index(dir);
    if index.remove(path).is_some() {
        let _ = save_index(dir, &index);
    }
}

// -- serialized entry for the frontend --------------------------------------

/// One thumbnail entry returned to the frontend.
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ThumbnailEntry {
    pub path: String,
    pub data_url: String,
    pub captured_at: i64,
    pub part_count: u32,
}

/// Build the list of thumbnail entries whose PNG file actually exists on disk.
/// Index entries without a corresponding file are silently skipped.
fn build_list(dir: &Path) -> Vec<ThumbnailEntry> {
    let index = load_index(dir);
    let mut entries: Vec<ThumbnailEntry> = index
        .into_iter()
        .filter_map(|(path, info)| {
            let png_path = dir.join(format!("{}.png", key(&path)));
            let bytes = fs::read(&png_path).ok()?;
            let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
            Some(ThumbnailEntry {
                data_url: format!("data:image/png;base64,{b64}"),
                captured_at: info.captured_at,
                part_count: info.part_count,
                path,
            })
        })
        .collect();
    // Newest first.
    entries.sort_by_key(|e| std::cmp::Reverse(e.captured_at));
    entries
}

// -- AppHandle helpers ------------------------------------------------------

/// Resolve (and create) the thumbnail cache directory.
fn thumb_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let dir = app
        .path()
        .app_cache_dir()
        .map_err(|e| format!("could not resolve app cache dir: {e}"))?
        .join("thumbnails");
    fs::create_dir_all(&dir)
        .map_err(|e| format!("failed to create thumb dir {}: {e}", dir.display()))?;
    Ok(dir)
}

// -- Tauri commands ---------------------------------------------------------

/// Store a captured PNG for `path`. Called by the frontend after capturing a
/// WebGL screenshot of the workspace preview.
#[tauri::command]
pub fn store_workspace_thumbnail(
    app: AppHandle,
    path: String,
    png: Vec<u8>,
    part_count: u32,
) -> Result<(), String> {
    let dir = thumb_dir(&app)?;
    upsert(&dir, &path, &png, part_count, crate::registry::now_ms())
}

/// All stored thumbnails whose PNG file still exists, as data URLs. Never
/// throws — returns an empty list on any error so the gallery degrades cleanly.
#[tauri::command]
pub fn list_workspace_thumbnails(app: AppHandle) -> Vec<ThumbnailEntry> {
    match thumb_dir(&app) {
        Ok(dir) => build_list(&dir),
        Err(_) => Vec::new(),
    }
}

/// Best-effort thumbnail cleanup for use in workspace delete. Called from
/// `workspaces::delete_workspace_blocking`; all failures are silently swallowed.
pub fn remove_thumbnail(app: &AppHandle, path: &str) {
    if let Ok(dir) = thumb_dir(app) {
        remove(&dir, path);
    }
}

// -- tests ------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use super::*;

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-thumb-test-{tag}-{}-{}",
            std::process::id(),
            crate::registry::now_ms()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    // -- key ----------------------------------------------------------------

    #[test]
    fn key_is_stable_and_16_hex_chars() {
        let k1 = key("/workspace/my-project");
        let k2 = key("/workspace/my-project");
        assert_eq!(k1, k2, "same input must produce the same key");
        assert_eq!(k1.len(), 16, "key must be 16 chars");
        assert!(
            k1.chars().all(|c| c.is_ascii_hexdigit()),
            "key must be all hex digits"
        );
    }

    #[test]
    fn key_differs_for_different_paths() {
        assert_ne!(key("/a"), key("/b"));
    }

    // -- sidecar round-trip -------------------------------------------------

    #[test]
    fn save_then_load_index_round_trips() {
        let dir = tmp_dir("rt");
        let mut index: BTreeMap<String, ThumbInfo> = BTreeMap::new();
        index.insert(
            "/ws/alpha".into(),
            ThumbInfo {
                captured_at: 1000,
                part_count: 3,
            },
        );
        index.insert(
            "/ws/beta".into(),
            ThumbInfo {
                captured_at: 2000,
                part_count: 7,
            },
        );
        save_index(&dir, &index).unwrap();
        let loaded = load_index(&dir);
        assert_eq!(loaded, index);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_index_missing_is_empty() {
        let dir = tmp_dir("missing");
        // Don't create any file — expect an empty map back.
        let index = load_index(&dir);
        assert!(index.is_empty());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_index_corrupt_is_empty() {
        let dir = tmp_dir("corrupt");
        fs::write(dir.join(INDEX_FILE), "[ broken json").unwrap();
        let index = load_index(&dir);
        assert!(index.is_empty());
        let _ = fs::remove_dir_all(&dir);
    }

    // -- upsert -------------------------------------------------------------

    #[test]
    fn upsert_writes_png_file_with_correct_bytes() {
        let dir = tmp_dir("upsert-png");
        let path = "/ws/test";
        let png = b"\x89PNG fake bytes";
        upsert(&dir, path, png, 2, 9999).unwrap();

        let png_path = dir.join(format!("{}.png", key(path)));
        assert!(png_path.is_file(), "png file must exist");
        let on_disk = fs::read(&png_path).unwrap();
        assert_eq!(on_disk, png);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn upsert_then_load_index_returns_entry() {
        let dir = tmp_dir("upsert-index");
        let path = "/ws/project";
        upsert(&dir, path, b"\x89PNG", 5, 42000).unwrap();

        let index = load_index(&dir);
        let entry = index.get(path).expect("entry must exist in index");
        assert_eq!(entry.captured_at, 42000);
        assert_eq!(entry.part_count, 5);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn upsert_overwrites_existing_entry() {
        let dir = tmp_dir("upsert-overwrite");
        let path = "/ws/project";
        upsert(&dir, path, b"old", 1, 100).unwrap();
        upsert(&dir, path, b"new", 9, 200).unwrap();

        let index = load_index(&dir);
        let entry = index.get(path).unwrap();
        assert_eq!(entry.captured_at, 200);
        assert_eq!(entry.part_count, 9);

        let png_path = dir.join(format!("{}.png", key(path)));
        assert_eq!(fs::read(&png_path).unwrap(), b"new");
        let _ = fs::remove_dir_all(&dir);
    }

    // -- build_list ---------------------------------------------------------

    #[test]
    fn list_skips_entries_whose_png_is_missing() {
        let dir = tmp_dir("list-missing");
        // Insert two entries into the index...
        upsert(&dir, "/ws/a", b"pngA", 1, 1000).unwrap();
        upsert(&dir, "/ws/b", b"pngB", 2, 2000).unwrap();
        // ...then delete one PNG file.
        fs::remove_file(dir.join(format!("{}.png", key("/ws/a")))).unwrap();

        let list = build_list(&dir);
        assert_eq!(
            list.len(),
            1,
            "only the entry whose file exists should appear"
        );
        assert_eq!(list[0].path, "/ws/b");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn list_returns_data_urls() {
        let dir = tmp_dir("list-dataurl");
        let png = b"\x89PNG test";
        upsert(&dir, "/ws/x", png, 3, 5000).unwrap();

        let list = build_list(&dir);
        assert_eq!(list.len(), 1);
        assert!(
            list[0].data_url.starts_with("data:image/png;base64,"),
            "data URL must have the correct prefix"
        );
        // Decode and verify round-trip.
        let b64 = list[0]
            .data_url
            .strip_prefix("data:image/png;base64,")
            .unwrap();
        let decoded = base64::engine::general_purpose::STANDARD
            .decode(b64)
            .unwrap();
        assert_eq!(decoded, png);
        let _ = fs::remove_dir_all(&dir);
    }

    // -- remove -------------------------------------------------------------

    #[test]
    fn remove_deletes_png_and_drops_index_entry() {
        let dir = tmp_dir("remove");
        let path = "/ws/to-delete";
        upsert(&dir, path, b"PNG!", 1, 100).unwrap();

        remove(&dir, path);

        let png_path = dir.join(format!("{}.png", key(path)));
        assert!(!png_path.exists(), "png file must be gone after remove");

        let index = load_index(&dir);
        assert!(!index.contains_key(path), "index entry must be gone");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn remove_is_idempotent_on_missing_entry() {
        let dir = tmp_dir("remove-noop");
        // Should not panic on a path that was never inserted.
        remove(&dir, "/ws/nonexistent");
        let _ = fs::remove_dir_all(&dir);
    }
}
