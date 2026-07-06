//! Multi-workspace launcher: registry + lifecycle commands.
//!
//! The app supports MULTIPLE named workspaces, each backed by its own LIVE engine.
//! At boot nothing is opened (the frontend shows a launcher). The first time a
//! workspace is *opened* its engine/watcher/provisioner start; switching to an
//! already-open workspace just re-focuses it and retargets the single artifact
//! watcher — the other workspaces keep running in the background.
//!
//! This module owns the Tauri commands the launcher + settings UI call:
//!   - workspace registry: `list_workspaces`, `create_workspace`, `open_workspace`,
//!     `close_workspace`, `close_workspace_tab`, `list_open_workspaces`,
//!     `get_active_workspace`
//!   - native folder picker: `pick_directory`
//!   - global template store: `get_templates`, `save_template`, `reset_template`
//!
//! The careful lifecycle bits ([`start_workspace`]) coordinate
//! [`crate::engine`], [`crate::watcher`], and [`crate::provision`].

use std::path::{Path, PathBuf};
use std::sync::Arc;

use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;

use crate::agent_config::{self, AgentConfig, SkillInfo};
use crate::app_config::{self, AppConfig};
use crate::engine;
use crate::instances::Instances;
use crate::materials::{self, MaterialLibrary};
use crate::provision::{self, WorkspacePaths, WorkspaceState};
use crate::registry::{self, now_ms, Workspace};
use crate::watcher;

/// A template surfaced to the settings UI. Serializes to the frontend contract:
/// `{ name, content, isCustom }`.
#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Template {
    pub name: String,
    pub content: String,
    pub is_custom: bool,
}

// -- config-dir helpers -----------------------------------------------------

/// The app config dir (`<app_config_dir>`), created if missing. This is the
/// single canonical location for all app-level stores (workspaces, materials,
/// destinations); the engine receives the same path via `SOLIDIFAI_CONFIG_DIR`.
pub(crate) fn config_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("could not resolve app config dir: {e}"))?;
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("failed to create config dir {}: {e}", dir.display()))?;
    Ok(dir)
}

/// The global template override store (`<app_config_dir>/templates`).
fn templates_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(config_dir(app)?.join("templates"))
}

/// The branded app folder under the user's Documents/home (`<base>/Solidifai`).
/// New workspaces nest one level below it, under [`WORKSPACES_SUBFOLDER`], so the
/// brand folder stays free for other user-facing content (exports, libraries).
const BRAND_FOLDER: &str = "Solidifai";

/// The subfolder that holds workspaces (`<base>/Solidifai/workspaces`). On the
/// `app_data` last-resort the brand level is dropped — `app_data_dir()` is already
/// namespaced by the bundle id, so workspaces land directly in `<app_data>/workspaces`.
const WORKSPACES_SUBFOLDER: &str = "workspaces";

/// Pure fallback chain for the default workspace parent, given already-resolved
/// base dirs. Extracted so the platform-independent preference order is
/// unit-testable without a live `AppHandle` or real OS dirs.
fn base_from_dirs(
    documents: Option<PathBuf>,
    home: Option<PathBuf>,
    app_data: Option<PathBuf>,
) -> PathBuf {
    if let Some(docs) = documents {
        return docs.join(BRAND_FOLDER).join(WORKSPACES_SUBFOLDER);
    }
    if let Some(home) = home {
        return home.join(BRAND_FOLDER).join(WORKSPACES_SUBFOLDER);
    }
    app_data
        .unwrap_or_else(|| PathBuf::from("."))
        .join(WORKSPACES_SUBFOLDER)
}

// -- lifecycle --------------------------------------------------------------

/// Point the single held artifact watcher at `ws`'s artifacts dir (only the focused
/// workspace drives a live viewport). Dropping the old watcher stops the old watch.
fn focus_watcher(app: &AppHandle, instances: &Arc<Instances>, ws: &WorkspacePaths) {
    let new_watcher = match watcher::start(app.clone(), &ws.artifacts, &ws.root) {
        Ok(w) => Some(w),
        Err(e) => {
            tracing::warn!("artifact watcher failed to start: {e}");
            None
        }
    };
    instances.set_watcher(new_watcher);
}

/// Bring a workspace fully online: ensure its engine exists in the registry,
/// provision it (with overridable templates + resolved interpreter + its socket),
/// retarget the single held artifact watcher onto it, and spawn the engine
/// supervisor for its socket/artifacts.
///
/// First-open only: callers re-focus an already-running workspace via
/// [`focus_watcher`] without re-provisioning or re-spawning.
pub fn start_workspace(
    app: &AppHandle,
    instances: &Arc<Instances>,
    ws: &WorkspacePaths,
) -> Result<(), String> {
    ws.ensure_dirs()?;
    let id = ws.root_str();
    let engine = instances.ensure(id.clone());
    engine.set_ws_id(&id);

    let socket = ws.socket_str();
    let artifacts = ws.artifacts_str();
    let templates = templates_dir(app)?;
    // The workspace's durable model file. A new workspace ships without one; the
    // engine loads + runs it on startup *if it exists*, and the agent's first
    // build writes it here. Passing the path lets the engine persist to / run the
    // right file once the model is created.
    let model = ws.root.join("model.py").to_string_lossy().into_owned();

    // Provision config + docs synchronously so the MCP files exist before the UI
    // (or an agent) touches the workspace. In prod the cached engine moves per
    // update, so external agent configs must point at the stable launcher shim;
    // in dev that is None and we use THIS workspace's own engine interpreter (the
    // supervisor's when already resolved, else the resolved venv path).
    let interpreter = engine::mcp_launcher(app)
        .or_else(|| engine.interpreter())
        .or_else(|| {
            engine::resolve_engine_dir(app)
                .map(|d| engine::interpreter_path(&d).to_string_lossy().into_owned())
                .ok()
        })
        .unwrap_or_default();
    provision::provision(ws, &interpreter, &socket, &templates)?;

    // Focused watcher (single): retarget the held one onto THIS workspace.
    focus_watcher(app, instances, ws);

    // Spawn the engine supervisor on a background thread (uv sync + version probe
    // run only the first time; subsequent opens reuse the cached env and emit
    // `ready` quickly).
    let app_handle = app.clone();
    let engine_for_thread = engine.clone();
    // Claim the supervisor generation HERE, atomically, before the thread spawns:
    // two concurrent kill+restart opens of the same workspace each get a distinct
    // token, and only the newest one survives the supervisor's generation checks
    // (the older one bails instead of spawning a second engine on the socket).
    let generation = engine.claim_generation();
    std::thread::spawn(move || {
        engine::start_supervised(
            app_handle,
            engine_for_thread,
            socket,
            artifacts,
            Some(model),
            generation,
        );
    });

    Ok(())
}

// -- registry commands ------------------------------------------------------

/// All known workspaces from the registry, with entries whose path no longer
/// exists dropped (best-effort; the surviving set is re-persisted).
#[tauri::command]
pub fn list_workspaces(app: AppHandle) -> Vec<Workspace> {
    let dir = match config_dir(&app) {
        Ok(d) => d,
        Err(_) => return Vec::new(),
    };
    let mut all = registry::load(&dir);
    if registry::reconcile_cache(&mut all) {
        let _ = registry::save(&dir, &all); // persist refreshed cache, best-effort
    }
    let kept = registry::existing(all.clone());
    if kept.len() != all.len() {
        let _ = registry::save(&dir, &kept);
    }
    kept
}

/// Create a new workspace directory under `parent_dir`, register it, and open it.
///
/// `name` is sanitized into a folder segment; the target `<parent_dir>/<folder>`
/// is created (error if it already exists as a non-empty dir).
///
/// `async` + `spawn_blocking`: this provisions the workspace (writes the embedded
/// config + skill tree) and opens it, all blocking file I/O. Tauri runs sync
/// commands on the **main thread**, so doing this inline froze the launcher; the
/// whole body runs on a blocking-pool thread instead. (The injected
/// `engine_state` is resolved inside via `app.state()`, so it is no longer a
/// command parameter — `AppHandle` is `Send` and works off the main thread.)
#[tauri::command]
pub async fn create_workspace(
    app: AppHandle,
    name: String,
    parent_dir: String,
) -> Result<Workspace, String> {
    tauri::async_runtime::spawn_blocking(move || create_workspace_blocking(app, name, parent_dir))
        .await
        .map_err(|e| format!("create_workspace task failed: {e}"))?
}

/// Synchronous body of [`create_workspace`], run on a blocking-pool thread.
fn create_workspace_blocking(
    app: AppHandle,
    name: String,
    parent_dir: String,
) -> Result<Workspace, String> {
    let folder = provision::sanitize_folder_name(&name);
    let root = Path::new(&parent_dir).join(&folder);

    // Reject an existing non-empty dir so we never adopt someone else's files.
    if root.exists() {
        let non_empty = std::fs::read_dir(&root)
            .map(|mut it| it.next().is_some())
            .unwrap_or(true);
        if non_empty {
            return Err(format!(
                "a non-empty directory already exists at {}",
                root.display()
            ));
        }
    }
    std::fs::create_dir_all(&root)
        .map_err(|e| format!("failed to create workspace dir {}: {e}", root.display()))?;

    let display_name = if name.trim().is_empty() {
        folder.clone()
    } else {
        name.trim().to_string()
    };

    let now = now_ms();

    // Seed the canonical per-folder record (Rust writes it; the engine reads it).
    {
        let seed = crate::workspace_meta::Meta {
            name: display_name.clone(),
            created_at: now,
            ..Default::default()
        };
        let _ = crate::workspace_meta::write(&root, &seed);
    }

    let ws = Workspace {
        name: display_name,
        path: root.to_string_lossy().into_owned(),
        created_at: now,
        last_opened_at: None,
        archived_at: None,
        description: None,
        tags: vec![],
        proposed_name: None,
        meta_synced_at: None,
    };

    let dir = config_dir(&app)?;
    let mut all = registry::load(&dir);
    registry::upsert(&mut all, ws.clone());
    registry::save(&dir, &all)?;

    // Remember where the user created this so the launcher pre-fills it next time
    // (best-effort — a failed write must never fail the create).
    if let Some(parent) = root.parent() {
        let _ = app_config::apply_patch(
            &dir,
            &serde_json::json!({ "lastWorkspaceParentDir": parent.to_string_lossy().into_owned() }),
        );
    }

    open_workspace_blocking(app, ws.path.clone())
}

/// Make the workspace at `path` focused. First open of a workspace provisions it +
/// spawns its engine + retargets the watcher; switching to an already-open
/// workspace just re-focuses it + retargets the watcher (no teardown of the others,
/// no re-provision, no re-spawn). Bumps `lastOpenedAt` and persists the registry.
/// Returns the focused workspace.
///
/// `async` + `spawn_blocking`: `start_workspace` provisions the workspace
/// synchronously (writes the embedded skill tree), which is blocking file I/O.
/// Running it on the main thread (where Tauri runs sync commands) stuttered the
/// launcher, so the whole body is offloaded to a blocking-pool thread.
#[tauri::command]
pub async fn open_workspace(app: AppHandle, path: String) -> Result<Workspace, String> {
    tauri::async_runtime::spawn_blocking(move || open_workspace_blocking(app, path))
        .await
        .map_err(|e| format!("open_workspace task failed: {e}"))?
}

/// Synchronous body of [`open_workspace`], run on a blocking-pool thread. Resolves
/// the managed engine state from `app` (rather than an injected `State` param) so
/// it can run off the main thread.
fn open_workspace_blocking(app: AppHandle, path: String) -> Result<Workspace, String> {
    let root = PathBuf::from(&path);
    if !root.is_dir() {
        return Err(format!("workspace path does not exist: {path}"));
    }
    let canonical = root.to_string_lossy().into_owned();
    let instances = app.state::<std::sync::Arc<Instances>>().inner().clone();

    // Idempotent open: if this workspace is already focused, don't re-focus or
    // retarget anything — just refresh its registry timestamp. The launcher opens a
    // workspace, then the router's engine-lifecycle hook also "opens" it on the
    // navigation that follows; without this guard we would needlessly re-provision
    // / restart the watcher on every open.
    let already_active = instances.focused_id().as_deref() == Some(canonical.as_str());

    // A workspace whose engine died terminally (e.g. the first-launch engine
    // fetch failed offline) gets a fresh start on ANY re-open instead of staying
    // dead for the whole session.
    let errored = instances
        .get(&canonical)
        .is_some_and(|e| e.current_status().status == "error");

    if !already_active || errored {
        // N live instances: switching does NOT tear down the previous workspace.
        // `ensure_new` decides spawn-vs-refocus atomically under one lock, so two
        // concurrent first-opens of the same workspace can't both spawn a supervisor.
        let ws_paths = WorkspacePaths::for_root(&root);
        let (engine, is_new) = instances.ensure_new(&canonical);
        app.state::<WorkspaceState>().set_focused(ws_paths.clone());
        instances.set_focus(canonical.clone());
        if is_new {
            // First open: provision + spawn its engine + watcher. `start_workspace`
            // calls `ensure(id)` internally, which returns the Arc just inserted here.
            start_workspace(&app, &instances, &ws_paths)?;
        } else if errored {
            // Kill first to reap any leftover child; `start_workspace` then claims
            // a fresh supervisor generation, so even two concurrent reopens of an
            // errored workspace resolve to exactly one live supervisor.
            engine.kill();
            start_workspace(&app, &instances, &ws_paths)?;
        } else {
            // Already running in the background: just re-focus + retarget the watcher.
            focus_watcher(&app, &instances, &ws_paths);
        }
    }

    let dir = config_dir(&app)?;
    let mut all = registry::load(&dir);
    let now = now_ms();
    let opened = if let Some(existing) = all.iter_mut().find(|w| w.path == canonical) {
        existing.last_opened_at = Some(now);
        existing.clone()
    } else {
        // Opening a path not yet in the registry: register it now.
        let name = root
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| "workspace".to_string());
        let ws = Workspace {
            name,
            path: canonical,
            created_at: now,
            last_opened_at: Some(now),
            archived_at: None,
            description: None,
            tags: vec![],
            proposed_name: None,
            meta_synced_at: None,
        };
        all.push(ws.clone());
        ws
    };
    registry::save(&dir, &all)?;

    Ok(opened)
}

/// Return to the launcher: clear focus + drop the viewport watcher. With N live
/// instances, going back to the launcher must NOT kill anything — every open
/// workspace keeps running in the background. Tearing a single tab down is the job
/// of [`close_workspace_tab`].
#[tauri::command]
pub fn close_workspace(
    app: AppHandle,
    instances: State<'_, std::sync::Arc<Instances>>,
) -> Result<(), String> {
    let instances = instances.inner().clone();
    let _ = &instances; // engines are intentionally left running.
    app.state::<WorkspaceState>().clear_focused();
    instances.clear_focus();
    instances.set_watcher(None);
    Ok(())
}

/// Tear down exactly ONE workspace tab: kill its engine + reap its agent shell +
/// drop it from the registry. If it was the focused tab, `remove` clears focus and
/// the frontend then focuses a sibling.
#[tauri::command]
pub async fn close_workspace_tab(app: AppHandle, path: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        let instances = app.state::<std::sync::Arc<Instances>>().inner().clone();
        instances.remove(&path); // kills that engine; clears focus if it was focused
        app.state::<crate::pty::PtyState>().kill_one(&path); // reap its agent shell
        if instances.open_ids().is_empty() {
            // No tabs remain: clear focus + drop the watcher. When siblings remain,
            // the frontend focuses one (openWorkspace -> focus_watcher), so don't
            // touch the watcher here or we'd race-clobber that sibling's watcher.
            app.state::<WorkspaceState>().clear_focused();
            instances.set_watcher(None);
        }
        Ok(())
    })
    .await
    .map_err(|e| format!("close_workspace_tab task failed: {e}"))?
}

/// The live tab set + which is focused (for the switcher + restore).
#[tauri::command]
pub fn list_open_workspaces(app: AppHandle) -> serde_json::Value {
    let instances = app.state::<std::sync::Arc<Instances>>();
    serde_json::json!({ "open": instances.open_ids(), "focused": instances.focused_id() })
}

/// The currently focused workspace, or `None` when the launcher is showing.
///
/// Re-reads the registry entry (for name/timestamps) keyed by the focused root.
#[tauri::command]
pub fn get_active_workspace(app: AppHandle, state: State<'_, WorkspaceState>) -> Option<Workspace> {
    let root = state.focused.lock().clone()?.root_str();
    let dir = config_dir(&app).ok()?;
    registry::load(&dir).into_iter().find(|w| w.path == root)
}

/// The focused workspace root path, if any.
fn focused_root_path(app: &AppHandle) -> Option<String> {
    app.state::<WorkspaceState>()
        .focused
        .lock()
        .clone()
        .map(|p| p.root_str())
}

// -- workspace metadata (single writer while open) --------------------------
//
// Each workspace's `workspace.json` is the source of truth for its name,
// description, tags, and staged name proposal; the registry only caches it. The
// invariant: while a workspace is OPEN its live engine is the sole writer of that
// file (so concurrent Rust + engine writes can't clobber each other). When a
// workspace is closed there is no engine, so Rust writes the file directly via
// `workspace_meta`. Every command below routes to the TARGET path's OWN engine
// socket (`socket_for`, NOT the focused one — editing a background tab must not
// touch the focused workspace's file), falling back to a direct file write when
// that path has no live engine, then refreshes the registry cache for that one
// entry and returns it.

/// Refresh the registry cache for one workspace from its workspace.json and save.
fn recache_one(app: &AppHandle, path: &str) -> Result<Workspace, String> {
    let dir = config_dir(app)?;
    let mut all = registry::load(&dir);
    if let Some(ws) = all.iter_mut().find(|w| w.path == path) {
        ws.meta_synced_at = None; // force reconcile of this entry
    }
    registry::reconcile_cache(&mut all);
    registry::save(&dir, &all)?;
    all.into_iter()
        .find(|w| w.path == path)
        .ok_or_else(|| format!("no registered workspace at {path}"))
}

/// Edit a workspace's description/tags. Routes through the live engine when the
/// workspace is open (single writer), else writes workspace.json directly. Returns
/// the refreshed registry entry.
#[tauri::command]
pub async fn edit_workspace_details(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    path: String,
    description: Option<String>,
    tags: Option<Vec<String>>,
) -> Result<Workspace, String> {
    if let Some(sock) = state.socket_for(&path) {
        let patch = serde_json::json!({ "description": description, "tags": tags });
        crate::rpc::engine_rpc_on(
            sock,
            "set_workspace_meta",
            serde_json::json!({ "patch": patch, "force": true, "user": true }),
        )
        .await?;
    } else {
        crate::workspace_meta::apply_user_edit(Path::new(&path), description, tags)?;
    }
    recache_one(&app, &path)
}

/// Accept a staged name (or rename): set the canonical workspace name and clear any
/// proposal. Engine when open, direct file when closed. Returns the refreshed entry.
#[tauri::command]
pub async fn accept_proposed_name(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    path: String,
    name: String,
) -> Result<Workspace, String> {
    if name.trim().is_empty() {
        return Err("workspace name cannot be empty".into());
    }
    if let Some(sock) = state.socket_for(&path) {
        crate::rpc::engine_rpc_on(
            sock,
            "set_workspace_name",
            serde_json::json!({ "name": name }),
        )
        .await?;
    } else {
        crate::workspace_meta::set_name(Path::new(&path), &name)?;
    }
    recache_one(&app, &path)
}

/// Dismiss the staged name proposal (records it as dismissed, clears the pending
/// one). Engine when open, direct file when closed. Returns the refreshed entry.
#[tauri::command]
pub async fn dismiss_proposed_name(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    path: String,
) -> Result<Workspace, String> {
    if let Some(sock) = state.socket_for(&path) {
        crate::rpc::engine_rpc_on(sock, "dismiss_proposed_name", serde_json::json!({})).await?;
    } else {
        crate::workspace_meta::dismiss(Path::new(&path))?;
    }
    recache_one(&app, &path)
}

/// Rename a workspace's DISPLAY name. The path is the identity, so the folder on
/// disk is NOT moved/renamed. Rejects empty names. Returns the updated workspace.
///
/// Goes through the same canonical path as accepting a proposal so a manual rename
/// also writes workspace.json (not just the registry cache): the engine when the
/// workspace is open, the file directly when it is closed. The JS call site still
/// passes `{ path, newName }`; Tauri injects `app`/`state`.
#[tauri::command]
pub async fn rename_workspace(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    path: String,
    new_name: String,
) -> Result<Workspace, String> {
    accept_proposed_name(app, state, path, new_name).await
}

/// Archive a workspace (registry flag only; files are left untouched on disk).
/// Reversible via [`restore_workspace`]. Re-throws so the launcher surfaces errors.
#[tauri::command]
pub fn archive_workspace(app: AppHandle, path: String) -> Result<Workspace, String> {
    set_archived_at(&app, &path, Some(now_ms()))
}

/// Restore an archived workspace (clears the archived flag).
#[tauri::command]
pub fn restore_workspace(app: AppHandle, path: String) -> Result<Workspace, String> {
    set_archived_at(&app, &path, None)
}

/// Shared body: load the registry, flip `archived_at` for `path`, persist, return
/// the updated entry. Errors if the path is not registered.
fn set_archived_at(
    app: &AppHandle,
    path: &str,
    archived_at: Option<i64>,
) -> Result<Workspace, String> {
    let dir = config_dir(app)?;
    let mut list = registry::load(&dir);
    let updated = registry::set_archived(&mut list, path, archived_at)
        .ok_or_else(|| format!("workspace not found: {path}"))?;
    registry::save(&dir, &list)?;
    Ok(updated)
}

/// Delete a workspace: unlist it from the registry, tearing down its live instance
/// first if it is open (focused or background). When `delete_files` is true, also
/// `remove_dir_all` the workspace directory — but only if it is a registered
/// workspace dir (guarded; never a parent or the home directory).
///
/// `async` + `spawn_blocking`: a `remove_dir_all` of a large workspace is blocking
/// I/O that would otherwise run on the main thread.
#[tauri::command]
pub async fn delete_workspace(
    app: AppHandle,
    path: String,
    delete_files: bool,
) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || delete_workspace_blocking(app, path, delete_files))
        .await
        .map_err(|e| format!("delete_workspace task failed: {e}"))?
}

/// Synchronous body of [`delete_workspace`], run on a blocking-pool thread.
fn delete_workspace_blocking(
    app: AppHandle,
    path: String,
    delete_files: bool,
) -> Result<(), String> {
    let dir = config_dir(&app)?;
    let mut all = registry::load(&dir);
    if !registry::contains(&all, &path) {
        return Err(format!("no registered workspace at {path}"));
    }

    // Tear down the deleted workspace if it is OPEN (focused or background): kill
    // its engine + reap its agent shell. If it happened to be the focused tab, also
    // clear focus + drop the viewport watcher.
    let instances = app.state::<std::sync::Arc<Instances>>().inner().clone();
    let was_focused = focused_root_path(&app).as_deref() == Some(path.as_str());
    if instances.get(&path).is_some() {
        instances.remove(&path);
        app.state::<crate::pty::PtyState>().kill_one(&path);
    }
    if was_focused {
        app.state::<WorkspaceState>().clear_focused();
        instances.set_watcher(None);
    }

    // Optionally remove the directory from disk. Guard hard: only delete a path
    // that is exactly a registered workspace dir, is absolute, has a parent (i.e.
    // is not a filesystem root), and is not the user's home directory.
    if delete_files {
        let root = PathBuf::from(&path);
        if !root.is_absolute() {
            return Err(format!("refusing to delete non-absolute path: {path}"));
        }
        if root.parent().is_none() {
            return Err(format!("refusing to delete filesystem root: {path}"));
        }
        if let Some(home) = dirs::home_dir() {
            if root == home {
                return Err("refusing to delete the home directory".to_string());
            }
        }
        if root.exists() {
            std::fs::remove_dir_all(&root)
                .map_err(|e| format!("failed to delete {}: {e}", root.display()))?;
        }
    }

    registry::remove(&mut all, &path);
    registry::save(&dir, &all)?;

    // Best-effort: evict the cached thumbnail so the home gallery stays tidy.
    crate::thumbnails::remove_thumbnail(&app, &path);

    Ok(())
}

// -- folder picker ----------------------------------------------------------

/// The default *parent* directory for a new workspace, resolved cross-platform.
///
/// Preference order:
///   1. the directory a workspace was last created in (if it still exists),
///   2. `<Documents>/Solidifai/workspaces` — `document_dir()` is Known Folders on
///      Windows, `$XDG_DOCUMENTS_DIR` on Linux, `~/Documents` on macOS,
///   3. `<home>/Solidifai/workspaces` — when Documents is unresolved (e.g. a headless
///      Linux box with no XDG user-dirs configured),
///   4. `<app_data>/workspaces` — last resort so the result is never empty.
///
/// Read-only: the directory is created lazily by `create_workspace`'s
/// `create_dir_all`, so calling this never touches the filesystem.
#[tauri::command]
pub fn default_workspace_dir(app: AppHandle) -> String {
    // 1. Prefer the last-used parent if it still exists on disk.
    if let Ok(dir) = config_dir(&app) {
        if let Some(last) = app_config::load(&dir).last_workspace_parent_dir {
            let p = PathBuf::from(&last);
            if p.is_dir() {
                return p.to_string_lossy().into_owned();
            }
        }
    }
    // 2-4. Computed cross-platform base.
    base_from_dirs(
        app.path().document_dir().ok(),
        dirs::home_dir(),
        app.path().app_data_dir().ok(),
    )
    .to_string_lossy()
    .into_owned()
}

/// Native folder picker. Returns the chosen absolute path, or `None` if cancelled.
///
/// MUST be `async`. Synchronous Tauri commands run on the **main thread**, and
/// `blocking_pick_folder` would deadlock there: on macOS the native panel needs
/// the main-thread run loop, so blocking that thread while the panel is up
/// freezes the whole dialog. As an `async` command this runs off the main
/// thread; we push the blocking picker onto a blocking-pool thread so the main
/// thread stays free to drive the panel.
#[tauri::command]
pub async fn pick_directory(app: AppHandle) -> Option<String> {
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .blocking_pick_folder()
            .and_then(|p| p.into_path().ok())
            .map(|p| p.to_string_lossy().into_owned())
    })
    .await
    .ok()
    .flatten()
}

/// Native file picker for a CAD/mesh file to import (STEP/STP/BREP/STL). Returns
/// the absolute path, or None if the user cancelled. Blocking dialog runs off the
/// main thread (like `pick_directory`).
#[tauri::command]
pub async fn pick_cad_file(app: AppHandle) -> Option<String> {
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .add_filter("CAD & mesh", &["step", "stp", "brep", "stl"])
            .blocking_pick_file()
            .and_then(|p| p.into_path().ok())
            .map(|p| p.to_string_lossy().into_owned())
    })
    .await
    .ok()
    .flatten()
}

// -- template store commands ------------------------------------------------

/// The overridable templates: each carries the user override from the store
/// when present (`isCustom=true`), else the embedded default (`isCustom=false`).
#[tauri::command]
pub fn get_templates(app: AppHandle) -> Vec<Template> {
    let dir = match templates_dir(&app) {
        Ok(d) => d,
        Err(_) => PathBuf::new(),
    };
    provision::TEMPLATE_NAMES
        .iter()
        .filter_map(|name| {
            provision::resolve_template(&dir, name).map(|(content, is_custom)| Template {
                name: (*name).to_string(),
                content,
                is_custom,
            })
        })
        .collect()
}

/// Write a template override to the store (validates `name` ∈ the overridable set).
#[tauri::command]
pub fn save_template(app: AppHandle, name: String, content: String) -> Result<(), String> {
    let dir = templates_dir(&app)?;
    provision::write_template_override(&dir, &name, &content)
}

/// Delete a template override (revert to the embedded default).
#[tauri::command]
pub fn reset_template(app: AppHandle, name: String) -> Result<(), String> {
    let dir = templates_dir(&app)?;
    provision::delete_template_override(&dir, &name)
}

// -- app-config store commands (GLOBAL viewport feature flags) --------------

/// The global app-config (viewport feature flags). Missing/unparseable file →
/// shipped defaults, so the viewport always has a valid config.
#[tauri::command]
pub fn get_app_config(app: AppHandle) -> AppConfig {
    let dir = match config_dir(&app) {
        Ok(d) => d,
        Err(_) => return AppConfig::default(),
    };
    app_config::load(&dir)
}

/// Apply a PARTIAL patch (only the changed flags) to the global app-config and
/// persist the merged result. Returns the merged config so the frontend store
/// can adopt the authoritative value (and recover if its optimistic guess and
/// the backend ever diverge).
#[tauri::command]
pub fn set_app_config(app: AppHandle, patch: serde_json::Value) -> Result<AppConfig, String> {
    let dir = config_dir(&app)?;
    app_config::apply_patch(&dir, &patch)
}

// -- material library commands (GLOBAL + per-workspace) ---------------------

/// Read the global material library, seeding + persisting it on first run. Lives
/// at `<app_config_dir>/materials.json` so the engine's resolver reads the same file.
#[tauri::command]
pub fn get_global_materials(app: AppHandle) -> Result<MaterialLibrary, String> {
    let dir = config_dir(&app)?;
    Ok(materials::load_global(&dir))
}

/// Persist the whole global library (invariants enforced backend-side), then
/// return the reloaded authoritative copy so the frontend adopts backend truth.
#[tauri::command]
pub fn set_global_materials(
    app: AppHandle,
    library: MaterialLibrary,
) -> Result<MaterialLibrary, String> {
    let dir = config_dir(&app)?;
    materials::save_global(&dir, &library)?;
    Ok(materials::load_global(&dir))
}

/// Read the active workspace's material library (empty when no workspace is open
/// or the workspace has no `materials.json`).
#[tauri::command]
pub fn get_workspace_materials(state: State<'_, WorkspaceState>) -> MaterialLibrary {
    match state.focused_root() {
        Some(root) => materials::load_workspace(&root),
        None => MaterialLibrary::default(),
    }
}

/// Persist the active workspace's material library, then return the reloaded copy.
#[tauri::command]
pub fn set_workspace_materials(
    state: State<'_, WorkspaceState>,
    library: MaterialLibrary,
) -> Result<MaterialLibrary, String> {
    let root = state
        .focused_root()
        .ok_or_else(|| "no workspace is open".to_string())?;
    materials::save_workspace(&root, &library)?;
    Ok(materials::load_workspace(&root))
}

// -- agent-config store commands (PER-WORKSPACE skills + runtime settings) --

/// The focused workspace's `.solidifai` dir, or an error when none is open.
fn active_dot_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let root = focused_root_path(app).ok_or_else(|| "no workspace is open".to_string())?;
    Ok(PathBuf::from(root).join(".solidifai"))
}

/// List every available skill with its enabled state for the active workspace.
/// Errors when no workspace is open (agent config is per-workspace).
#[tauri::command]
pub fn list_skills(app: AppHandle) -> Result<Vec<SkillInfo>, String> {
    let dot = active_dot_dir(&app)?;
    let cfg = agent_config::load(&dot);
    Ok(agent_config::list_skills(&cfg))
}

/// The active workspace's persisted agent config (enabled skills + runtime flags).
#[tauri::command]
pub fn get_agent_config(app: AppHandle) -> Result<AgentConfig, String> {
    let dot = active_dot_dir(&app)?;
    Ok(agent_config::load(&dot))
}

/// Replace the active workspace's agent config and persist it. The new skill set
/// takes effect on the NEXT workspace open (the provisioner re-runs and writes
/// only the enabled skills). Returns the saved config so the UI adopts backend truth.
#[tauri::command]
pub fn set_agent_config(app: AppHandle, config: AgentConfig) -> Result<AgentConfig, String> {
    let dot = active_dot_dir(&app)?;
    agent_config::save(&dot, &config)?;
    Ok(config)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_from_dirs_prefers_documents() {
        let p = base_from_dirs(
            Some(PathBuf::from("/docs")),
            Some(PathBuf::from("/home")),
            Some(PathBuf::from("/data")),
        );
        assert_eq!(
            p,
            PathBuf::from("/docs").join("Solidifai").join("workspaces")
        );
    }

    #[test]
    fn base_from_dirs_falls_back_to_home_when_no_documents() {
        let p = base_from_dirs(
            None,
            Some(PathBuf::from("/home")),
            Some(PathBuf::from("/data")),
        );
        assert_eq!(
            p,
            PathBuf::from("/home").join("Solidifai").join("workspaces")
        );
    }

    #[test]
    fn base_from_dirs_falls_back_to_app_data() {
        let p = base_from_dirs(None, None, Some(PathBuf::from("/data")));
        assert_eq!(p, PathBuf::from("/data").join("workspaces"));
    }

    #[test]
    fn base_from_dirs_last_resort_is_relative_workspaces() {
        let p = base_from_dirs(None, None, None);
        assert_eq!(p, PathBuf::from(".").join("workspaces"));
    }

    #[test]
    fn template_serializes_to_camel_case_contract() {
        let t = Template {
            name: "AGENTS.md".into(),
            content: "hi".into(),
            is_custom: true,
        };
        let v = serde_json::to_value(&t).unwrap();
        assert_eq!(v["name"], "AGENTS.md");
        assert_eq!(v["content"], "hi");
        assert_eq!(v["isCustom"], true);
    }

    #[test]
    fn seed_writes_named_workspace_json() {
        let dir = std::env::temp_dir().join(format!("sf-seed-{}", registry::now_ms()));
        std::fs::create_dir_all(&dir).unwrap();
        let m = crate::workspace_meta::Meta {
            name: "Brand New".into(),
            created_at: 42,
            ..Default::default()
        };
        crate::workspace_meta::write(&dir, &m).unwrap();
        let back = crate::workspace_meta::load(&dir);
        assert_eq!(back.name, "Brand New");
        assert_eq!(back.created_at, 42);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
