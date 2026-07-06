//! Workspace registry: the persisted launcher list of known workspaces.
//!
//! The app supports MULTIPLE named workspaces. The registry is a `Vec<Workspace>`
//! persisted at `<app_config_dir>/workspaces.json`. It records each workspace's
//! display name, absolute path, creation time, and last-opened time so the
//! frontend launcher can list them and surface the most-recently-used one.
//!
//! The registry is the source of truth for "what workspaces exist"; the *active*
//! workspace (the one the engine/watcher are bound to) lives in
//! [`crate::provision::WorkspaceState`].

use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::store;

/// A known workspace as surfaced to the frontend launcher.
///
/// Serializes to camelCase JSON exactly per the frontend contract:
/// `{ name, path, createdAt, lastOpenedAt }`.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct Workspace {
    /// Display name (human-friendly; not necessarily the folder segment).
    pub name: String,
    /// Absolute path to the workspace root.
    pub path: String,
    /// Creation time, epoch milliseconds.
    pub created_at: i64,
    /// Last time this workspace was opened, epoch milliseconds (None if never).
    pub last_opened_at: Option<i64>,
    /// When this workspace was archived (epoch ms), or None if active. `#[serde(default)]`
    /// lets legacy registries (written before archiving) load it as None; skipped from
    /// the file when None so active workspaces stay clean.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub archived_at: Option<i64>,
    /// Cached from <path>/workspace.json (source of truth is the file).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tags: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub proposed_name: Option<String>,
    /// Epoch-ms mtime of workspace.json we last cached; drives lazy reconcile.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub meta_synced_at: Option<i64>,
}

/// Current wall-clock time as epoch milliseconds.
pub fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

pub const REGISTRY_FILE: &str = "workspaces.json";
pub const CURRENT_VERSION: u32 = 2;

#[derive(Serialize, Deserialize, Default)]
#[serde(rename_all = "camelCase")]
struct Envelope {
    #[serde(default)]
    version: u32,
    #[serde(default)]
    workspaces: Vec<Workspace>,
}

/// Migrate a raw stored value up to [`CURRENT_VERSION`].
fn migrate(from: u32, mut v: Value) -> Value {
    if from < 1 {
        v = migrate_v0_to_v1(v);
    }
    if from < 2 {
        v = migrate_v1_to_v2(v);
    }
    v
}

/// v0 (a bare JSON array) -> v1 (`{ workspaces: [...] }`). The version stamp is
/// added by [`store::versioned_load`].
fn migrate_v0_to_v1(v: Value) -> Value {
    if v.is_array() {
        let mut m = serde_json::Map::new();
        m.insert("workspaces".into(), v);
        Value::Object(m)
    } else {
        v // already an object -- nothing to wrap.
    }
}

/// v1 -> v2: backfill each workspace.json from the registry's name + createdAt so
/// existing names survive the move of `name` into the per-folder file. The new
/// cache fields default empty via `#[serde(default)]`, so no value rewrite is
/// needed here; this pass only seeds the canonical files.
fn migrate_v1_to_v2(v: Value) -> Value {
    if let Some(list) = v.get("workspaces").and_then(Value::as_array) {
        for ws in list {
            let (Some(path), Some(name)) = (
                ws.get("path").and_then(Value::as_str),
                ws.get("name").and_then(Value::as_str),
            ) else {
                continue;
            };
            let root = Path::new(path);
            if !root.is_dir() || root.join("workspace.json").exists() {
                continue; // folder gone, or already has a record.
            }
            let created = ws.get("createdAt").and_then(Value::as_i64).unwrap_or(0);
            let seed = serde_json::json!({
                "schema": 1, "name": name, "createdAt": created,
                "description": "", "descriptionSource": "sol",
                "tags": [], "tagsSource": "sol",
                "proposedName": null, "proposedNameDismissed": null,
            });
            let _ = store::write_json_atomic(root, "workspace.json", &seed); // best-effort
        }
    }
    v
}

/// Load the registry. Missing/corrupt -> empty. A legacy bare-array file is
/// migrated to the versioned envelope on first load.
pub fn load(config_dir: &Path) -> Vec<Workspace> {
    let v = store::versioned_load(config_dir, REGISTRY_FILE, CURRENT_VERSION, migrate);
    serde_json::from_value::<Envelope>(v)
        .map(|e| e.workspaces)
        .unwrap_or_default()
}

/// Persist the registry as the versioned envelope (atomic write).
pub fn save(config_dir: &Path, workspaces: &[Workspace]) -> Result<(), String> {
    let env = Envelope {
        version: CURRENT_VERSION,
        workspaces: workspaces.to_vec(),
    };
    let v = serde_json::to_value(&env)
        .map_err(|e| format!("failed to serialize workspace registry: {e}"))?;
    store::write_json_atomic(config_dir, REGISTRY_FILE, &v)
}

/// Filter the registry to entries whose path still exists on disk (best-effort).
pub fn existing(workspaces: Vec<Workspace>) -> Vec<Workspace> {
    workspaces
        .into_iter()
        .filter(|w| Path::new(&w.path).is_dir())
        .collect()
}

/// Insert or update a workspace in the list, keyed by `path`. Preserves
/// `created_at` of an existing entry; updates `name` and `last_opened_at`.
pub fn upsert(workspaces: &mut Vec<Workspace>, ws: Workspace) {
    if let Some(existing) = workspaces.iter_mut().find(|w| w.path == ws.path) {
        existing.name = ws.name;
        if ws.last_opened_at.is_some() {
            existing.last_opened_at = ws.last_opened_at;
        }
    } else {
        workspaces.push(ws);
    }
}

/// Rename the registry entry at `path` (DISPLAY name only — the path stays the
/// identity). Returns the updated [`Workspace`], or `None` if no entry matches.
pub fn rename(workspaces: &mut [Workspace], path: &str, new_name: &str) -> Option<Workspace> {
    let entry = workspaces.iter_mut().find(|w| w.path == path)?;
    entry.name = new_name.to_string();
    Some(entry.clone())
}

/// Set or clear the archived timestamp for the entry at `path` (path is identity,
/// like rename). Returns the updated [`Workspace`], or `None` if no entry matches.
pub fn set_archived(
    workspaces: &mut [Workspace],
    path: &str,
    archived_at: Option<i64>,
) -> Option<Workspace> {
    let entry = workspaces.iter_mut().find(|w| w.path == path)?;
    entry.archived_at = archived_at;
    Some(entry.clone())
}

/// Remove the registry entry at `path`. Returns `true` if an entry was removed.
pub fn remove(workspaces: &mut Vec<Workspace>, path: &str) -> bool {
    let before = workspaces.len();
    workspaces.retain(|w| w.path != path);
    workspaces.len() != before
}

/// True if `path` is a registered workspace.
pub fn contains(workspaces: &[Workspace], path: &str) -> bool {
    workspaces.iter().any(|w| w.path == path)
}

/// Refresh each entry's cached content fields from its workspace.json when the
/// file's mtime is newer than the cached `meta_synced_at`. Returns true if any
/// entry changed (so the caller can persist). Stat-only when nothing changed.
pub fn reconcile_cache(workspaces: &mut [Workspace]) -> bool {
    let mut changed = false;
    for ws in workspaces.iter_mut() {
        let file = Path::new(&ws.path).join("workspace.json");
        let Ok(meta) = std::fs::metadata(&file) else {
            continue;
        };
        let mtime = meta
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_millis() as i64);
        if mtime.is_some() && mtime <= ws.meta_synced_at {
            continue; // cache current
        }
        let m = crate::workspace_meta::load(Path::new(&ws.path));
        let (desc, tags, proposed, name, created, _) = crate::workspace_meta::to_cache(&m, mtime);
        ws.name = name;
        ws.created_at = created;
        ws.description = desc;
        ws.tags = tags;
        ws.proposed_name = proposed;
        ws.meta_synced_at = mtime;
        changed = true;
    }
    changed
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::PathBuf;

    use super::*;

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-reg-test-{tag}-{}-{}",
            std::process::id(),
            now_ms()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn round_trip_save_then_load() {
        let dir = tmp_dir("rt");
        let ws = vec![
            Workspace {
                name: "Alpha".into(),
                path: "/tmp/alpha".into(),
                created_at: 1000,
                last_opened_at: Some(2000),
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
            Workspace {
                name: "Beta".into(),
                path: "/tmp/beta".into(),
                created_at: 1500,
                last_opened_at: None,
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
        ];
        save(&dir, &ws).expect("save");
        let loaded = load(&dir);
        assert_eq!(loaded, ws);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_missing_file_is_empty() {
        let dir = tmp_dir("missing");
        assert!(load(&dir).is_empty());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn workspace_serializes_to_camel_case_contract() {
        let ws = Workspace {
            name: "My Part".into(),
            path: "/ws".into(),
            created_at: 42,
            last_opened_at: Some(99),
            archived_at: None,
            description: None,
            tags: vec![],
            proposed_name: None,
            meta_synced_at: None,
        };
        let v = serde_json::to_value(&ws).unwrap();
        assert_eq!(v["name"], "My Part");
        assert_eq!(v["path"], "/ws");
        assert_eq!(v["createdAt"], 42);
        assert_eq!(v["lastOpenedAt"], 99);
        // Round-trips back from camelCase JSON.
        let back: Workspace = serde_json::from_value(v).unwrap();
        assert_eq!(back, ws);
    }

    #[test]
    fn existing_drops_missing_paths() {
        let dir = tmp_dir("existing");
        let present = dir.to_string_lossy().into_owned();
        let ws = vec![
            Workspace {
                name: "Present".into(),
                path: present.clone(),
                created_at: 1,
                last_opened_at: None,
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
            Workspace {
                name: "Gone".into(),
                path: "/no/such/path/solidifai".into(),
                created_at: 2,
                last_opened_at: None,
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
        ];
        let kept = existing(ws);
        assert_eq!(kept.len(), 1);
        assert_eq!(kept[0].path, present);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn upsert_updates_existing_and_preserves_created_at() {
        let mut list = vec![Workspace {
            name: "Old".into(),
            path: "/ws".into(),
            created_at: 100,
            last_opened_at: Some(200),
            archived_at: None,
            description: None,
            tags: vec![],
            proposed_name: None,
            meta_synced_at: None,
        }];
        upsert(
            &mut list,
            Workspace {
                name: "New".into(),
                path: "/ws".into(),
                created_at: 999, // ignored for existing entries
                last_opened_at: Some(300),
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
        );
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].name, "New");
        assert_eq!(list[0].created_at, 100, "created_at preserved");
        assert_eq!(list[0].last_opened_at, Some(300));

        // A new path appends.
        upsert(
            &mut list,
            Workspace {
                name: "Other".into(),
                path: "/ws2".into(),
                created_at: 50,
                last_opened_at: None,
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
        );
        assert_eq!(list.len(), 2);
    }

    #[test]
    fn rename_updates_display_name_only() {
        let mut list = vec![Workspace {
            name: "Old".into(),
            path: "/ws".into(),
            created_at: 100,
            last_opened_at: Some(200),
            archived_at: None,
            description: None,
            tags: vec![],
            proposed_name: None,
            meta_synced_at: None,
        }];
        let updated = rename(&mut list, "/ws", "Fresh Name").expect("renamed");
        assert_eq!(updated.name, "Fresh Name");
        assert_eq!(updated.path, "/ws", "path is unchanged (identity)");
        assert_eq!(updated.created_at, 100);
        assert_eq!(updated.last_opened_at, Some(200));
        assert_eq!(list[0].name, "Fresh Name");

        // Unknown path: no-op, returns None.
        assert!(rename(&mut list, "/nope", "x").is_none());
    }

    #[test]
    fn remove_drops_only_the_matching_entry() {
        let mut list = vec![
            Workspace {
                name: "A".into(),
                path: "/a".into(),
                created_at: 1,
                last_opened_at: None,
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
            Workspace {
                name: "B".into(),
                path: "/b".into(),
                created_at: 2,
                last_opened_at: None,
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            },
        ];
        assert!(contains(&list, "/a"));
        assert!(remove(&mut list, "/a"));
        assert!(!contains(&list, "/a"));
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].path, "/b");

        // Removing a missing path returns false and changes nothing.
        assert!(!remove(&mut list, "/a"));
        assert_eq!(list.len(), 1);
    }

    #[test]
    fn legacy_bare_array_migrates_to_versioned_envelope() {
        let dir = tmp_dir("legacy-array");
        // v0 on-disk format: a bare JSON array.
        fs::write(
            dir.join("workspaces.json"),
            r#"[{"name":"Old","path":"/ws","createdAt":1,"lastOpenedAt":null}]"#,
        )
        .unwrap();
        let loaded = load(&dir);
        assert_eq!(loaded.len(), 1);
        assert_eq!(loaded[0].name, "Old");
        // The file was rewritten as a versioned envelope.
        let on_disk: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(dir.join("workspaces.json")).unwrap())
                .unwrap();
        assert_eq!(on_disk["version"], 2);
        assert!(on_disk["workspaces"].is_array());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn save_writes_versioned_envelope() {
        let dir = tmp_dir("envelope");
        save(
            &dir,
            &[Workspace {
                name: "A".into(),
                path: "/a".into(),
                created_at: 1,
                last_opened_at: None,
                archived_at: None,
                description: None,
                tags: vec![],
                proposed_name: None,
                meta_synced_at: None,
            }],
        )
        .unwrap();
        let on_disk: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(dir.join("workspaces.json")).unwrap())
                .unwrap();
        assert_eq!(on_disk["version"], 2);
        assert_eq!(on_disk["workspaces"][0]["name"], "A");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn corrupt_registry_is_backed_up_not_wiped() {
        let dir = tmp_dir("corrupt-reg");
        fs::write(dir.join("workspaces.json"), "[ broken").unwrap();
        assert!(load(&dir).is_empty());
        let has_bak = fs::read_dir(&dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .any(|e| e.file_name().to_string_lossy().ends_with(".bak"));
        assert!(has_bak);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn v2_file_loads_without_re_migration() {
        let dir = tmp_dir("v2-stable");
        // A file already at the current version.
        let original = r#"{"version":2,"workspaces":[{"name":"A","path":"/a","createdAt":1,"lastOpenedAt":null}]}"#;
        fs::write(dir.join("workspaces.json"), original).unwrap();
        let loaded = load(&dir);
        assert_eq!(loaded.len(), 1);
        assert_eq!(loaded[0].name, "A");
        // A current-version file is returned untouched: load must not rewrite it
        // (no migration churn of the user's whole workspace list every load).
        assert_eq!(
            fs::read_to_string(dir.join("workspaces.json")).unwrap(),
            original
        );
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn set_archived_sets_and_clears_timestamp() {
        let mut list = vec![Workspace {
            name: "A".into(),
            path: "/a".into(),
            created_at: 1,
            last_opened_at: None,
            archived_at: None,
            description: None,
            tags: vec![],
            proposed_name: None,
            meta_synced_at: None,
        }];
        let archived = set_archived(&mut list, "/a", Some(555)).expect("found");
        assert_eq!(archived.archived_at, Some(555));
        assert_eq!(list[0].archived_at, Some(555));

        let restored = set_archived(&mut list, "/a", None).expect("found");
        assert_eq!(restored.archived_at, None);

        // Unknown path → None, no change.
        assert!(set_archived(&mut list, "/nope", Some(1)).is_none());
    }

    #[test]
    fn workspace_serializes_new_cache_fields_camel_case() {
        let ws = Workspace {
            name: "A".into(),
            path: "/a".into(),
            created_at: 1,
            last_opened_at: None,
            archived_at: None,
            description: Some("d".into()),
            tags: vec!["x".into()],
            proposed_name: Some("B".into()),
            meta_synced_at: Some(7),
        };
        let v = serde_json::to_value(&ws).unwrap();
        assert_eq!(v["description"], "d");
        assert_eq!(v["tags"][0], "x");
        assert_eq!(v["proposedName"], "B");
        assert_eq!(v["metaSyncedAt"], 7);
        let back: Workspace = serde_json::from_value(v).unwrap();
        assert_eq!(back, ws);
    }

    #[test]
    fn v1_record_loads_with_empty_cache_fields() {
        let dir = tmp_dir("v1-to-v2");
        let present = dir.to_string_lossy().into_owned();
        fs::write(
            dir.join("workspaces.json"),
            format!(
                r#"{{"version":1,"workspaces":[{{"name":"Old","path":"{present}","createdAt":5,"lastOpenedAt":null}}]}}"#
            ),
        ).unwrap();
        let loaded = load(&dir);
        assert_eq!(loaded.len(), 1);
        assert_eq!(loaded[0].description, None);
        assert!(loaded[0].tags.is_empty());
        // Backfilled the per-folder file from the registry name.
        let wj: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(dir.join("workspace.json")).unwrap()).unwrap();
        assert_eq!(wj["name"], "Old");
        assert_eq!(wj["createdAt"], 5);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_record_without_archived_at_loads_as_none() {
        let dir = tmp_dir("legacy-archived");
        fs::write(
            dir.join("workspaces.json"),
            r#"{"version":1,"workspaces":[{"name":"Old","path":"/ws","createdAt":1,"lastOpenedAt":null}]}"#,
        )
        .unwrap();
        let loaded = load(&dir);
        assert_eq!(loaded.len(), 1);
        assert_eq!(loaded[0].archived_at, None);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn reconcile_refreshes_cache_when_file_newer() {
        let dir = tmp_dir("reconcile");
        let root = dir.to_string_lossy().into_owned();
        fs::write(
            dir.join("workspace.json"),
            r#"{"schema":1,"name":"Fresh","createdAt":1,"description":"hello","tags":["t"]}"#,
        )
        .unwrap();
        let mut list = vec![Workspace {
            name: "Stale".into(),
            path: root.clone(),
            created_at: 1,
            last_opened_at: None,
            archived_at: None,
            description: None,
            tags: vec![],
            proposed_name: None,
            meta_synced_at: Some(0), // older than the file -> reconcile
        }];
        let changed = reconcile_cache(&mut list);
        assert!(changed);
        assert_eq!(list[0].name, "Fresh");
        assert_eq!(list[0].description.as_deref(), Some("hello"));
        assert_eq!(list[0].tags, vec!["t".to_string()]);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn reconcile_runs_when_meta_synced_at_is_none() {
        let dir = tmp_dir("reconcile-none");
        let root = dir.to_string_lossy().into_owned();
        fs::write(
            dir.join("workspace.json"),
            r#"{"schema":1,"name":"FromFile","createdAt":1,"description":"desc","tags":[]}"#,
        )
        .unwrap();
        let mut list = vec![Workspace {
            name: "Stale".into(),
            path: root.clone(),
            created_at: 1,
            last_opened_at: None,
            archived_at: None,
            description: None,
            tags: vec![],
            proposed_name: None,
            meta_synced_at: None, // never synced -> must reconcile
        }];
        let changed = reconcile_cache(&mut list);
        assert!(changed);
        assert_eq!(list[0].name, "FromFile");
        assert_eq!(list[0].description.as_deref(), Some("desc"));
        let _ = fs::remove_dir_all(&dir);
    }
}
