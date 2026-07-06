//! Artifact watcher: emits `model-updated` when the engine writes a new model,
//! and `workspace-meta-updated` when its `workspace.json` changes.
//!
//! The engine atomically replaces `<ws>/.solidifai/artifacts/model.json` on every
//! successful build (GLB first, then JSON — see `engine/solidifai_engine/render.py`).
//! We watch the artifacts directory and, on a debounced change to `model.json`,
//! read it, parse `buildId`, and emit `model-updated { buildId }` to the frontend.
//!
//! Separately we watch the workspace root (non-recursively) for `workspace.json`
//! writes (Sol editing the workspace name/description/tags). On change we refresh
//! the registry cache for that one entry and emit `workspace-meta-updated { wsId }`
//! so the open editor's name-suggestion bar updates live.
//!
//! `*.tmp` staging files are ignored so we only react to finalized artifacts.

use std::path::{Path, PathBuf};
use std::time::Duration;

use notify::RecursiveMode;
use notify_debouncer_full::{new_debouncer, DebounceEventResult, Debouncer, RecommendedCache};
use serde::Serialize;
use tauri::{AppHandle, Emitter};

/// Managed state that keeps the debouncer alive for the app's lifetime. Dropping
/// it stops the watch, so it must be held somewhere (here, in Tauri state).
pub struct WatcherState {
    _debouncer: Debouncer<notify::RecommendedWatcher, RecommendedCache>,
}

/// `model-updated` event payload. Matches the frontend contract: `{ buildId }`.
#[derive(Clone, Serialize)]
struct ModelUpdated {
    #[serde(rename = "buildId")]
    build_id: u64,
}

/// `workspace-meta-updated` event payload. `rename_all` makes `ws_id` serialize as
/// `wsId`, matching the frontend listener's `{ wsId }` contract.
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct WorkspaceMetaUpdated {
    ws_id: String,
}

/// `build-brief-updated` event payload. Same `{ wsId }` contract: emitted when
/// the engine writes `build_brief.json`, so the read-only Plan panel refreshes.
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct BuildBriefUpdated {
    ws_id: String,
}

/// True when `path` is the finalized `model.json` (not a `*.tmp` stage file).
fn is_model_json(path: &Path) -> bool {
    path.file_name().and_then(|n| n.to_str()) == Some("model.json")
}

/// True when `path` is a workspace's `workspace.json` metadata file.
fn is_workspace_json(path: &Path) -> bool {
    path.file_name().and_then(|n| n.to_str()) == Some("workspace.json")
}

/// True when `path` is a workspace's `build_brief.json` (the plan Sol commits to).
fn is_build_brief_json(path: &Path) -> bool {
    path.file_name().and_then(|n| n.to_str()) == Some("build_brief.json")
}

/// Parse the `buildId` out of a `model.json` document.
fn parse_build_id(json: &str) -> Option<u64> {
    let v: serde_json::Value = serde_json::from_str(json).ok()?;
    v.get("buildId").and_then(serde_json::Value::as_u64)
}

/// Read `model.json` and emit `model-updated { buildId }` if it parses.
fn emit_model_updated(app: &AppHandle, model_json: &Path) {
    let Ok(text) = std::fs::read_to_string(model_json) else {
        return; // file vanished mid-write; the next event will catch up.
    };
    if let Some(build_id) = parse_build_id(&text) {
        let _ = app.emit("model-updated", ModelUpdated { build_id });
    }
}

/// Refresh this workspace's registry cache from its `workspace.json`, then emit
/// `workspace-meta-updated { wsId }`. Recache only touches the registry file (in
/// the app config dir), never `workspace.json`, so this does not re-trigger us.
fn emit_meta_updated(app: &AppHandle, root: &Path) {
    let ws_id = root.to_string_lossy().into_owned();
    if let Ok(dir) = crate::workspaces::config_dir(app) {
        let mut all = crate::registry::load(&dir);
        if let Some(ws) = all.iter_mut().find(|w| Path::new(&w.path) == root) {
            ws.meta_synced_at = None; // force reconcile of this entry
        }
        crate::registry::reconcile_cache(&mut all);
        let _ = crate::registry::save(&dir, &all);
    }
    let _ = app.emit("workspace-meta-updated", WorkspaceMetaUpdated { ws_id });
}

/// Emit `build-brief-updated { wsId }` so the open editor's Plan panel re-reads
/// `build_brief.json`. The panel reads the file itself, so we only need to notify.
fn emit_build_brief_updated(app: &AppHandle, root: &Path) {
    let ws_id = root.to_string_lossy().into_owned();
    let _ = app.emit("build-brief-updated", BuildBriefUpdated { ws_id });
}

/// Start watching `artifacts_dir` (recursively, for `model.json`) and `root`
/// (non-recursively, for `workspace.json`) with a 200 ms debounce. Returns a
/// [`WatcherState`] the caller must keep alive (store in Tauri state).
pub fn start(app: AppHandle, artifacts_dir: &Path, root: &Path) -> Result<WatcherState, String> {
    let artifacts_owned = artifacts_dir.to_path_buf();
    let root_owned: PathBuf = root.to_path_buf();

    let mut debouncer = new_debouncer(
        Duration::from_millis(200),
        None,
        move |result: DebounceEventResult| {
            let events = match result {
                Ok(events) => events,
                Err(_errors) => return, // transient watch errors: ignore, keep watching.
            };
            // A single debounced batch can touch both files (build + meta edit), so
            // handle each independently — never `else`.
            //
            // If any event touched the finalized model.json, re-read it once and
            // emit. We don't trust the event's own buildId; we read the file so the
            // emitted id always matches what's on disk.
            let model_touched = events
                .iter()
                .any(|ev| ev.paths.iter().any(|p| is_model_json(p)));
            if model_touched {
                emit_model_updated(&app, &artifacts_owned.join("model.json"));
            }
            // If any event touched workspace.json, recache + notify the frontend.
            let meta_touched = events
                .iter()
                .any(|ev| ev.paths.iter().any(|p| is_workspace_json(p)));
            if meta_touched {
                emit_meta_updated(&app, &root_owned);
            }
            // build_brief.json also lives in the root (already covered by the
            // NonRecursive root watch above), so no extra `.watch()` call.
            let brief_touched = events
                .iter()
                .any(|ev| ev.paths.iter().any(|p| is_build_brief_json(p)));
            if brief_touched {
                emit_build_brief_updated(&app, &root_owned);
            }
        },
    )
    .map_err(|e| format!("failed to create artifact debouncer: {e}"))?;

    debouncer
        .watch(artifacts_dir, RecursiveMode::Recursive)
        .map_err(|e| format!("failed to watch {}: {e}", artifacts_dir.display()))?;
    // workspace.json lives directly in the root; NonRecursive keeps us off the
    // whole tree (and off the artifacts dir we already watch above).
    debouncer
        .watch(root, RecursiveMode::NonRecursive)
        .map_err(|e| format!("failed to watch {}: {e}", root.display()))?;

    Ok(WatcherState {
        _debouncer: debouncer,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    #[test]
    fn is_model_json_matches_only_finalized_file() {
        assert!(is_model_json(Path::new(
            "/ws/.solidifai/artifacts/model.json"
        )));
        assert!(!is_model_json(Path::new(
            "/ws/.solidifai/artifacts/model.json.tmp"
        )));
        assert!(!is_model_json(Path::new(
            "/ws/.solidifai/artifacts/model.glb"
        )));
        assert!(!is_model_json(Path::new("/ws/.solidifai/artifacts/")));
    }

    #[test]
    fn is_workspace_json_matches_only_the_meta_file() {
        assert!(is_workspace_json(Path::new("/ws/workspace.json")));
        assert!(!is_workspace_json(Path::new("/ws/workspace.json.tmp")));
        assert!(!is_workspace_json(Path::new(
            "/ws/.solidifai/artifacts/model.json"
        )));
        assert!(!is_workspace_json(Path::new("/ws/")));
    }

    #[test]
    fn matches_build_brief_json() {
        assert!(is_build_brief_json(Path::new("/ws/build_brief.json")));
        assert!(!is_build_brief_json(Path::new("/ws/build_brief.json.tmp")));
        assert!(!is_build_brief_json(Path::new("/ws/workspace.json")));
        assert!(!is_build_brief_json(Path::new("/ws/model.py")));
    }

    #[test]
    fn parse_build_id_reads_contract_field() {
        assert_eq!(
            parse_build_id(r#"{"schema":1,"buildId":7,"units":"mm"}"#),
            Some(7)
        );
        assert_eq!(parse_build_id(r#"{"buildId":0}"#), Some(0));
        assert_eq!(parse_build_id(r#"{"no":"build"}"#), None);
        assert_eq!(parse_build_id("not json"), None);
    }

    /// End-to-end: a real debouncer watching a temp dir fires our path filter when
    /// model.json is written, and not for a *.tmp write. We exercise the same
    /// filtering logic the live handler uses by collecting touched paths.
    #[test]
    fn debouncer_fires_on_model_json_write() {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-watch-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();

        let (tx, rx) = mpsc::channel::<bool>();
        let mut debouncer = new_debouncer(
            Duration::from_millis(100),
            None,
            move |result: DebounceEventResult| {
                if let Ok(events) = result {
                    if events
                        .iter()
                        .any(|ev| ev.paths.iter().any(|p| is_model_json(p)))
                    {
                        let _ = tx.send(true);
                    }
                }
            },
        )
        .unwrap();
        debouncer.watch(&dir, RecursiveMode::Recursive).unwrap();

        // A .tmp write must NOT trigger the model.json filter.
        std::fs::write(dir.join("model.json.tmp"), b"{}").unwrap();
        // The finalized write MUST trigger it.
        std::fs::write(dir.join("model.json"), br#"{"buildId":1}"#).unwrap();

        let got = rx.recv_timeout(Duration::from_secs(5)).unwrap_or(false);
        assert!(got, "expected a model.json change to be observed");

        drop(debouncer);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
