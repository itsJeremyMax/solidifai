//! Workspace provisioner.
//!
//! On startup the app provisions `~/solidifai-workspace` with everything an
//! external coding agent (Claude Code / Codex / OpenCode) needs to reach the CAD
//! engine through the `solidifai-cad` MCP server, plus instructional docs. A new
//! workspace ships no starter model — the agent creates `model.py` on its first
//! build, and the viewport shows its empty state until then.
//!
//! ## Idempotency / "managed" marker
//!
//! Every file we write carries a `solidifai-managed` marker (a comment in
//! markdown/py/toml, a `"//"` key in JSON). [`write_managed`] writes a file only
//! when it is missing OR already contains that marker — so we never clobber a
//! file the user hand-edited and made their own, but we freely refresh our own.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, State};
use tauri_plugin_opener::OpenerExt;

/// Per-user directory for engine IPC endpoints, set once at startup (the app
/// config dir). The socket / Windows pointer file must NOT live under the
/// user-chosen workspace root: on Windows the pointer file (which holds the
/// auth token) would inherit the workspace directory's ACLs, so a workspace on
/// a shared or world-readable path exposes the token; on unix a deep workspace
/// path can push the socket past the ~104-byte AF_UNIX sun_path limit. Tests
/// (and any pre-init call) fall back to the OS temp dir, which is per-user on
/// every supported platform.
static IPC_DIR: OnceLock<PathBuf> = OnceLock::new();

pub fn init_ipc_dir(config_dir: &Path) {
    let _ = IPC_DIR.set(config_dir.join("ipc"));
}

fn ipc_dir() -> PathBuf {
    IPC_DIR
        .get()
        .cloned()
        .unwrap_or_else(|| std::env::temp_dir().join("solidifai-ipc"))
}

/// Marker substring that flags a file as owned/managed by solidifai.
pub(crate) const MANAGED_MARKER: &str = "solidifai-managed";

/// Summary of the managed files handled by one provisioning pass. Paths are
/// workspace-relative so callers can surface them without exposing host paths.
#[derive(Clone, Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProvisionReport {
    pub written: Vec<String>,
    pub skipped_user_owned: Vec<String>,
    pub errors: Vec<String>,
}

/// Canonical instructional content, embedded from `engine/workspace_templates/`
/// so it ships in the binary and is written verbatim.
const AGENTS_MD: &str = include_str!("../../engine/workspace_templates/AGENTS.md");

const MFG_REGION_START: &str = "<!-- solidifai-profile:start";
const MFG_REGION_END: &str = "<!-- solidifai-profile:end -->";

const CUSTOM_START: &str = "<!-- solidifai-custom:start -->";
const CUSTOM_END: &str = "<!-- solidifai-custom:end -->";

/// The app-managed Agent Skills collection (multiple skills, each a directory with
/// `SKILL.md` plus optional `references/` and `examples/`). Embedded as a tree so
/// the whole thing ships in the binary and is written into every workspace under
/// each adapter's native skill root. Unlike the overridable templates, these are NOT
/// per-file user-editable: we always refresh OUR skill files on each provision so
/// improvements flow, but we never touch other skills a user adds.
static SKILLS_DIR: include_dir::Dir =
    include_dir::include_dir!("$CARGO_MANIFEST_DIR/../engine/workspace_templates/skills");

/// Read access to the embedded Agent Skills tree (for listing available skills in
/// the agent-config UI). The tree is the single source of truth for "what skills
/// ship", so the config surface enumerates from here rather than a hardcoded list.
pub fn skills_dir() -> &'static include_dir::Dir<'static> {
    &SKILLS_DIR
}

/// The frontmatter `description:` line of an embedded skill's `SKILL.md`, or
/// `None` if the skill / file / field is absent. Pulled so the agent-config UI can
/// show a one-line description per skill without duplicating it in Rust.
pub fn skill_description(skill_name: &str) -> Option<String> {
    let rel = format!("{skill_name}/SKILL.md");
    let file = SKILLS_DIR.get_file(&rel)?;
    let text = file.contents_utf8()?;
    // SKILL.md frontmatter is `--- ... ---` YAML; find the `description:` line.
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("description:") {
            return Some(rest.trim().to_string());
        }
    }
    None
}

/// Resolved workspace layout for an arbitrary root. All paths are absolute.
#[derive(Clone, Debug)]
pub struct WorkspacePaths {
    /// The workspace root (e.g. `~/solidifai-workspace` or any user-chosen dir).
    pub root: PathBuf,
    /// `<root>/.solidifai` — the engine's private dir (artifacts live here).
    pub dot: PathBuf,
    /// `<root>/.solidifai/artifacts`
    pub artifacts: PathBuf,
    /// `<ipc_dir>/engine-<hash-of-root>.sock` — deliberately OUTSIDE the
    /// workspace (see [`IPC_DIR`]); the hash keys the endpoint to its workspace.
    pub socket: PathBuf,
}

impl WorkspacePaths {
    /// Derive the workspace layout for an arbitrary root.
    pub fn for_root(root: impl Into<PathBuf>) -> Self {
        let root = root.into();
        let dot = root.join(".solidifai");
        let artifacts = dot.join("artifacts");
        let digest = engine_pack::hash::sha256_bytes(root.to_string_lossy().as_bytes());
        let socket = ipc_dir().join(format!("engine-{}.sock", &digest[..12]));
        Self {
            root,
            dot,
            artifacts,
            socket,
        }
    }

    /// Create the workspace dir tree (`root`, `.solidifai`, `.solidifai/artifacts`)
    /// and the per-user IPC dir the socket lives in.
    pub fn ensure_dirs(&self) -> Result<(), String> {
        fs::create_dir_all(&self.artifacts).map_err(|e| {
            format!(
                "failed to create workspace dirs at {}: {e}",
                self.artifacts.display()
            )
        })?;
        if let Some(parent) = self.socket.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("failed to create ipc dir at {}: {e}", parent.display()))?;
        }
        // Older versions bound the socket inside the workspace; clear the stale
        // file so it can't confuse anything scanning `.solidifai/`.
        let _ = fs::remove_file(self.dot.join("engine.sock"));
        Ok(())
    }

    pub fn artifacts_str(&self) -> String {
        self.artifacts.to_string_lossy().into_owned()
    }
    pub fn socket_str(&self) -> String {
        self.socket.to_string_lossy().into_owned()
    }
    pub fn root_str(&self) -> String {
        self.root.to_string_lossy().into_owned()
    }
}

/// Managed state holding the layout of the *focused* workspace, or `None` when the
/// launcher is showing (no workspace focused).
///
/// Set by `open_workspace` / `create_workspace`, cleared by `close_workspace`. The
/// artifact/model commands read paths from here and error when no workspace is open.
#[derive(Default)]
pub struct WorkspaceState {
    pub focused: Mutex<Option<WorkspacePaths>>,
}

impl WorkspaceState {
    fn paths(&self) -> Result<WorkspacePaths, String> {
        self.focused
            .lock()
            .clone()
            .ok_or_else(|| "no workspace is open".to_string())
    }

    /// The focused workspace root, or `None` when no workspace is open. Used by the
    /// material-library commands to find `<root>/materials.json`.
    pub fn focused_root(&self) -> Option<PathBuf> {
        self.focused.lock().clone().map(|p| p.root)
    }

    /// Set the focused workspace layout.
    pub fn set_focused(&self, ws: WorkspacePaths) {
        *self.focused.lock() = Some(ws);
    }

    /// Clear the focused workspace (return to launcher).
    pub fn clear_focused(&self) {
        *self.focused.lock() = None;
    }
}

// -- workspace Tauri commands ----------------------------------------------

/// Absolute path to the ACTIVE workspace root. Errors when no workspace is open.
#[tauri::command]
pub fn get_workspace_dir(state: State<'_, WorkspaceState>) -> Result<String, String> {
    Ok(state.paths()?.root_str())
}

/// Absolute path to the workspace's `exports/` folder, creating it if needed.
/// This is where exports land by default, so the Save dialog can open here.
#[tauri::command]
pub fn get_export_dir(state: State<'_, WorkspaceState>) -> Result<String, String> {
    let dir = Path::new(&state.paths()?.root_str()).join("exports");
    fs::create_dir_all(&dir).map_err(|e| format!("failed to create exports dir: {e}"))?;
    Ok(dir.to_string_lossy().into_owned())
}

/// Reveal a workspace folder in the OS file manager. Takes no path from the
/// webview: the directory is resolved server-side from the active workspace, so
/// the command cannot open arbitrary locations (this is why the `opener` plugin
/// no longer grants the webview an unscoped `open-path`). `which` selects the
/// workspace root or its `exports/` folder.
#[tauri::command]
pub fn reveal_workspace_dir(
    app: AppHandle,
    state: State<'_, WorkspaceState>,
    which: String,
) -> Result<(), String> {
    let root = state.paths()?.root;
    let dir = match which.as_str() {
        "workspace" => root,
        "exports" => {
            let d = root.join("exports");
            fs::create_dir_all(&d).map_err(|e| format!("failed to create exports dir: {e}"))?;
            d
        }
        other => return Err(format!("unknown reveal target: {other}")),
    };
    app.opener()
        .open_path(dir.to_string_lossy().into_owned(), None::<&str>)
        .map_err(|e| format!("failed to open folder: {e}"))
}

/// True if the workspace at `path` has a `model.py` (the agent's durable model
/// source). A fresh workspace has none; its first build writes one. Lets the
/// viewport show a loading state (vs the empty prompt) while a model that exists
/// is still building its artifacts.
#[tauri::command]
pub fn workspace_has_model(path: String) -> bool {
    std::path::Path::new(&path).join("model.py").exists()
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CurrentPublication {
    publication_id: String,
    model_json: String,
    model_glb: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct GenerationManifest {
    #[serde(default)]
    json_sha256: Option<String>,
    #[serde(default)]
    glb_sha256: Option<String>,
}

/// A manifest and GLB read from one immutable publication. `publication_id` is
/// absent only for the root-file fallback used by engines predating current.json.
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelSnapshot {
    pub publication_id: Option<String>,
    pub manifest: String,
    pub glb: Vec<u8>,
}

fn is_file_name(value: &str) -> bool {
    let path = Path::new(value);
    !value.is_empty() && path.file_name().and_then(|name| name.to_str()) == Some(value)
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// Resolve current.json exactly once, then read its matching immutable pair. A
/// missing pointer means this is an old engine, so root compatibility mirrors are
/// the only valid source. Any malformed pointer or generation is an error instead
/// of silently mixing it with root files.
fn read_model_snapshot_from_artifacts(artifacts: &Path) -> Result<Option<ModelSnapshot>, String> {
    let current = artifacts.join("current.json");
    match fs::read_to_string(&current) {
        Ok(pointer_text) => {
            let pointer: CurrentPublication = serde_json::from_str(&pointer_text)
                .map_err(|e| format!("could not parse {}: {e}", current.display()))?;
            if !is_file_name(&pointer.publication_id)
                || !is_file_name(&pointer.model_json)
                || !is_file_name(&pointer.model_glb)
            {
                return Err("current.json has an unsafe generation path".to_string());
            }
            let generation = artifacts.join("generations").join(&pointer.publication_id);
            let manifest_path = generation.join(&pointer.model_json);
            let glb_path = generation.join(&pointer.model_glb);
            let manifest = fs::read_to_string(&manifest_path)
                .map_err(|e| format!("could not read {}: {e}", manifest_path.display()))?;
            let glb = fs::read(&glb_path)
                .map_err(|e| format!("could not read {}: {e}", glb_path.display()))?;
            if let Ok(generation_manifest) = fs::read_to_string(generation.join("manifest.json")) {
                let hashes: GenerationManifest = serde_json::from_str(&generation_manifest)
                    .map_err(|e| format!("could not parse generation manifest: {e}"))?;
                if hashes
                    .json_sha256
                    .as_deref()
                    .is_some_and(|hash| hash != sha256_hex(manifest.as_bytes()))
                    || hashes
                        .glb_sha256
                        .as_deref()
                        .is_some_and(|hash| hash != sha256_hex(&glb))
                {
                    return Err(
                        "generation manifest hashes do not match published artifacts".to_string(),
                    );
                }
            }
            Ok(Some(ModelSnapshot {
                publication_id: Some(pointer.publication_id),
                manifest,
                glb,
            }))
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let manifest_path = artifacts.join("model.json");
            let glb_path = artifacts.join("model.glb");
            match (fs::read_to_string(&manifest_path), fs::read(&glb_path)) {
                (Ok(manifest), Ok(glb)) => Ok(Some(ModelSnapshot {
                    publication_id: None,
                    manifest,
                    glb,
                })),
                (Err(error), _) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
                (_, Err(error)) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
                (Err(error), _) => Err(format!(
                    "could not read {}: {error}",
                    manifest_path.display()
                )),
                (_, Err(error)) => Err(format!("could not read {}: {error}", glb_path.display())),
            }
        }
        Err(error) => Err(format!("could not read {}: {error}", current.display())),
    }
}

/// Read a coherent model snapshot in one IPC call. It prefers the immutable
/// current.json generation and retains root-file compatibility for older engines.
#[tauri::command]
pub async fn read_model_snapshot(
    state: State<'_, WorkspaceState>,
    ws_id: Option<String>,
) -> Result<Option<ModelSnapshot>, String> {
    let artifacts = match ws_id {
        Some(root) => WorkspacePaths::for_root(root).artifacts,
        None => {
            let Ok(paths) = state.paths() else {
                return Ok(None);
            };
            paths.artifacts
        }
    };
    tauri::async_runtime::spawn_blocking(move || read_model_snapshot_from_artifacts(&artifacts))
        .await
        .map_err(|e| format!("read_model_snapshot task failed: {e}"))?
}

/// The legacy fixed workspace root (`~/solidifai-workspace`). Used only to
/// best-effort auto-register existing users' workspaces at boot.
pub fn legacy_workspace_root() -> Option<PathBuf> {
    dirs::home_dir().map(|h| h.join("solidifai-workspace"))
}

// -- overridable templates -------------------------------------------------
//
// One template is user-overridable via the global settings store: AGENTS.md.
// An override lives at `<app_config_dir>/templates/<name>`. When present, it
// wins over the embedded `include_str!` default. The other config files
// Adapter configs and harness pointers are code-generated and NOT user-editable;
// the Agent Skills collection is app-managed (see `SKILLS_DIR`), not per-file
// overridable.

/// The overridable template names.
pub const TEMPLATE_NAMES: [&str; 1] = ["AGENTS.md"];

/// True if `name` is one of the overridable templates.
pub fn is_template_name(name: &str) -> bool {
    TEMPLATE_NAMES.contains(&name)
}

/// The embedded default content for an overridable template, or `None` if the
/// name is not one of the overridable set.
pub fn embedded_template(name: &str) -> Option<&'static str> {
    match name {
        "AGENTS.md" => Some(AGENTS_MD),
        _ => None,
    }
}

/// Path to a template override file inside the templates dir.
fn template_override_path(templates_dir: &Path, name: &str) -> PathBuf {
    templates_dir.join(name)
}

/// Resolve a template's effective content: the user override from the store if
/// present, else the embedded default. Returns `(content, is_custom)`.
pub fn resolve_template(templates_dir: &Path, name: &str) -> Option<(String, bool)> {
    let embedded = embedded_template(name)?;
    let override_path = template_override_path(templates_dir, name);
    match fs::read_to_string(&override_path) {
        Ok(content) => Some((content, true)),
        Err(_) => Some((embedded.to_string(), false)),
    }
}

/// Write a template override to the store (validates the name). Creates the
/// templates dir if missing.
pub fn write_template_override(
    templates_dir: &Path,
    name: &str,
    content: &str,
) -> Result<(), String> {
    if !is_template_name(name) {
        return Err(format!("unknown template: {name}"));
    }
    fs::create_dir_all(templates_dir).map_err(|e| {
        format!(
            "failed to create templates dir {}: {e}",
            templates_dir.display()
        )
    })?;
    let path = template_override_path(templates_dir, name);
    fs::write(&path, content).map_err(|e| format!("failed to write {}: {e}", path.display()))
}

/// Delete a template override (revert to the embedded default). Validates the
/// name; a missing override is not an error.
pub fn delete_template_override(templates_dir: &Path, name: &str) -> Result<(), String> {
    if !is_template_name(name) {
        return Err(format!("unknown template: {name}"));
    }
    let path = template_override_path(templates_dir, name);
    match fs::remove_file(&path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(format!("failed to delete {}: {e}", path.display())),
    }
}

/// Windows reserved device names. A folder named exactly one of these (matched
/// case-insensitively on the stem before the first `.`) fails to create on
/// Windows, so we prefix it with `_` to keep the segment creatable everywhere.
const WIN_RESERVED: [&str; 22] = [
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

/// Sanitize a display name into a single safe folder segment. Keeps alphanumerics,
/// dash, underscore, and dot; collapses every other run into a single dash; trims
/// leading/trailing dashes and dots. Falls back to `"workspace"` if empty.
pub fn sanitize_folder_name(name: &str) -> String {
    let mut out = String::with_capacity(name.len());
    let mut last_dash = false;
    for ch in name.chars() {
        if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' || ch == '.' {
            out.push(ch);
            last_dash = false;
        } else if !last_dash {
            out.push('-');
            last_dash = true;
        }
    }
    let trimmed = out.trim_matches(|c| c == '-' || c == '.');
    let result = if trimmed.is_empty() {
        "workspace".to_string()
    } else {
        trimmed.to_string()
    };
    // Escape Windows reserved device names (compare the stem before the first dot).
    let stem = result.split('.').next().unwrap_or(&result);
    if WIN_RESERVED.iter().any(|r| r.eq_ignore_ascii_case(stem)) {
        format!("_{result}")
    } else {
        result
    }
}

/// Write `content` to `path` if the file is missing or is one of ours (contains
/// the managed marker). Creates parent dirs as needed. Returns `Ok(true)` if it
/// wrote, `Ok(false)` if it skipped a user-owned file.
enum WriteOutcome {
    Written,
    SkippedUserOwned,
}

fn write_managed(path: &Path, content: &str) -> Result<WriteOutcome, String> {
    if path.exists() {
        let existing = fs::read_to_string(path)
            .map_err(|e| format!("failed to read existing {}: {e}", path.display()))?;
        if !existing.contains(MANAGED_MARKER) {
            // User made this file their own; leave it untouched.
            return Ok(WriteOutcome::SkippedUserOwned);
        }
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
    }
    fs::write(path, content).map_err(|e| format!("failed to write {}: {e}", path.display()))?;
    Ok(WriteOutcome::Written)
}

fn record_write(report: &mut ProvisionReport, root: &Path, path: &Path, outcome: WriteOutcome) {
    let relative = path
        .strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .into_owned();
    match outcome {
        WriteOutcome::Written => report.written.push(relative),
        WriteOutcome::SkippedUserOwned => report.skipped_user_owned.push(relative),
    }
}

/// Render the full `## Manufacturing profile` region (markers + lines).
fn render_profile_block(config_dir: &Path, workspace_root: &Path) -> String {
    let prof = crate::manufacturing::resolve(config_dir, Some(workspace_root));
    let (_mat_id, mat_label) =
        crate::manufacturing::resolved_default_material(config_dir, workspace_root);

    let num = |path: &[&str], default: f64| -> f64 {
        let mut cur = &prof;
        for k in path {
            cur = match cur.get(k) {
                Some(v) => v,
                None => return default,
            };
        }
        cur.as_f64().unwrap_or(default)
    };
    let fit = prof
        .get("design")
        .and_then(|d| d.get("fit"))
        .and_then(|v| v.as_str())
        .unwrap_or("normal")
        .to_string();
    let clearance = num(
        &["fits", &format!("{fit}Mm")],
        num(&["fits", "normalMm"], 0.2),
    );
    let process_id = prof
        .get("process")
        .and_then(|p| p.get("id"))
        .and_then(|v| v.as_str())
        .unwrap_or("fdm");
    let process_label =
        crate::materials::process_label(process_id).unwrap_or_else(|| process_id.to_uppercase());
    let process_settings = prof
        .get("process")
        .and_then(|p| p.get("settings"))
        .unwrap_or(&serde_json::Value::Null);
    let process_num = |key: &str, default: f64| {
        process_settings
            .get(key)
            .and_then(serde_json::Value::as_f64)
            .unwrap_or(default)
    };

    // f64 Display drops trailing zeros (45.0 -> "45", 0.2 -> "0.2").
    let g = |x: f64| format!("{x}");

    let mut block = format!(
        "{start} (managed by solidifai; reflects this workspace's manufacturing profile as of session start) -->\n\
         - Material: {mat} · Fit: {fit} ({clear} mm) · Wall: {wall} mm · Edge-break: {fillet} mm\n\
         - Process: {label} ({id})",
        start = MFG_REGION_START,
        mat = mat_label,
        fit = fit,
        clear = g(clearance),
        wall = g(num(&["design", "wallMm"], 2.4)),
        fillet = g(num(&["design", "filletMm"], 1.0)),
        label = process_label,
        id = process_id,
    );
    if crate::materials::profile_settings(process_id).contains(&"nozzleMm".to_string()) {
        block.push_str(&format!(
            ", {} mm nozzle, {} mm layers, {} deg overhang, {}% infill\n\
             - Print (advisory; the slicer owns the real values): {}C nozzle / {}C bed, ~${}/kg",
            g(process_num("nozzleMm", 0.4)),
            g(process_num("layerMm", 0.2)),
            g(process_num("overhangDeg", 45.0)),
            g(process_num("infillPct", 20.0)),
            g(num(&["fabrication", "nozzleTempC"], 210.0)),
            g(num(&["fabrication", "bedTempC"], 60.0)),
            g(num(&["fabrication", "filamentCostPerKg"], 25.0)),
        ));
    }
    block.push_str(&format!("\n{MFG_REGION_END}"));
    block
}

/// Replace the marked region in `text` with `block` (inclusive of both markers).
/// If the markers are not both present, the text is returned unchanged.
fn replace_profile_region(text: &str, block: &str) -> String {
    let Some(start) = text.find(MFG_REGION_START) else {
        return text.to_string();
    };
    let Some(end_rel) = text[start..].find(MFG_REGION_END) else {
        return text.to_string();
    };
    let end = start + end_rel + MFG_REGION_END.len();
    let mut out = String::with_capacity(text.len());
    out.push_str(&text[..start]);
    out.push_str(block);
    out.push_str(&text[end..]);
    out
}

/// Replace the content BETWEEN the custom-instructions markers with `block`,
/// keeping the markers themselves in place (unlike `render_profile_block`,
/// `custom_instructions::render_block` emits no markers of its own). If both
/// markers are not present the text is returned unchanged. An empty `block`
/// collapses the region back to the two bare markers on consecutive lines.
fn replace_custom_region(text: &str, block: &str) -> String {
    let Some(start) = text.find(CUSTOM_START) else {
        return text.to_string();
    };
    let content_start = start + CUSTOM_START.len();
    let Some(end_rel) = text[content_start..].find(CUSTOM_END) else {
        return text.to_string();
    };
    let end = content_start + end_rel;
    let between = if block.is_empty() {
        "\n".to_string()
    } else {
        format!("\n\n{block}\n\n")
    };
    let mut out = String::with_capacity(text.len() + between.len());
    out.push_str(&text[..content_start]);
    out.push_str(&between);
    out.push_str(&text[end..]);
    out
}

/// Provision (idempotently) all workspace files.
///
/// `py` is the absolute engine interpreter path; `sock` is the absolute engine
/// socket path (must match what the supervisor uses). `templates_dir` is the
/// global settings template store: AGENTS.md uses the user override there when
/// present, else the embedded default. No starter `model.py` is written — a new
/// workspace stays modelless until the agent's first build creates it.
pub fn provision(
    ws: &WorkspacePaths,
    py: &str,
    sock: &str,
    templates_dir: &Path,
) -> Result<ProvisionReport, String> {
    let root = &ws.root;
    let mut report = ProvisionReport::default();

    // Render the live manufacturing-profile region into the always-loaded brief.
    // Rust stays the sole writer of AGENTS.md. config_dir is the parent of the
    // template store (templates_dir is always <config_dir>/templates).
    let config_dir = templates_dir.parent().unwrap_or(templates_dir);
    let agents = template_content(templates_dir, "AGENTS.md");
    let agents = replace_profile_region(&agents, &render_profile_block(config_dir, root.as_path()));
    let agents = replace_custom_region(
        &agents,
        &crate::custom_instructions::render_block(config_dir, root.as_path()),
    );

    // Instruction pointers are independent of the engine and must be available
    // on an offline first launch. MCP config embeds the interpreter as its command,
    // so defer only those files until it has been resolved.
    for adapter in crate::agent_harness::adapter_registry() {
        for output in adapter.instruction_outputs() {
            let path = root.join(output.path);
            let outcome = write_managed(&path, &output.content)?;
            record_write(&mut report, root, &path, outcome);
        }
    }
    if !py.is_empty() {
        for adapter in crate::agent_harness::adapter_registry() {
            for output in adapter.mcp_outputs(py, sock) {
                let path = root.join(output.path);
                let outcome = write_managed(&path, &output.content)?;
                record_write(&mut report, root, &path, outcome);
            }
        }
    }

    // Instructions are rendered above with the live manufacturing and custom
    // regions. Harness pointers are renderer outputs owned by agent_harness.
    let agents_path = root.join("AGENTS.md");
    let outcome = write_managed(&agents_path, &agents)?;
    record_write(&mut report, root, &agents_path, outcome);

    // App-managed Agent Skills collection: write the ENABLED embedded skills under
    // every distinct adapter skill root (preserving subdirs). The enabled set is the
    // per-workspace agent config (default: all skills, auto-provision on). When
    // auto-provision is off the user hand-manages their skill dirs and we skip
    // writing entirely. Re-writes OUR enabled skill files so improvements flow;
    // never touches other skills the user added.
    let agent_cfg = crate::agent_config::load(&ws.dot);
    if agent_cfg.auto_provision_skills {
        let enabled = agent_cfg.enabled_skills.as_deref();
        for skill_root in crate::agent_harness::skill_roots() {
            write_skills_tree(&root.join(skill_root), enabled)?;
        }
    }

    // No starter model.py: a fresh workspace opens modelless (the viewport shows
    // its empty state) and the agent's first build writes model.py itself.

    Ok(report)
}

/// Recursively write the ENABLED embedded skills into `dest` (a `skills/` root),
/// preserving relative subdirectories. App-managed files are (over)written so
/// improvements flow; other skills the user adds under `dest` are left alone. A
/// skill that is in the embedded set but DISABLED for this workspace is removed
/// from `dest` (if a prior provision wrote it), so toggling a skill off takes
/// effect on the next workspace open. `enabled` is the per-workspace allow-list of
/// skill names (a top-level subdir of `SKILLS_DIR`); `None` means all enabled.
fn write_skills_tree(dest: &Path, enabled: Option<&[String]>) -> Result<(), String> {
    for sub in SKILLS_DIR.dirs() {
        // A nameless dir would make `skill_dest == dest`; skip it entirely so we
        // can never `remove_dir_all` the whole skills root.
        let Some(skill_name) = sub
            .path()
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
        else {
            continue;
        };
        let is_enabled = match enabled {
            None => true,
            Some(set) => set.contains(&skill_name),
        };
        let skill_dest = dest.join(&skill_name);
        if is_enabled {
            write_dir_recursive(sub, dest)?;
        } else if skill_dest.is_dir() {
            // Previously provisioned but now disabled: drop our copy. (Guarded to a
            // skill subdir we ship; never touches user-added skill dirs.)
            fs::remove_dir_all(&skill_dest).map_err(|e| {
                format!(
                    "failed to remove disabled skill {}: {e}",
                    skill_dest.display()
                )
            })?;
        }
    }
    for file in SKILLS_DIR.files() {
        let target = dest.join(file.path());
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
        }
        fs::write(&target, file.contents())
            .map_err(|e| format!("failed to write {}: {e}", target.display()))?;
    }
    Ok(())
}

/// Write every file in `dir` into `dest/<relpath>`, creating parent dirs as
/// needed. `dir.path()` is relative to the embed root, so it maps straight onto
/// `dest`. Always overwrites (app-managed files).
fn write_dir_recursive(dir: &include_dir::Dir, dest: &Path) -> Result<(), String> {
    for file in dir.files() {
        let target = dest.join(file.path());
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
        }
        fs::write(&target, file.contents())
            .map_err(|e| format!("failed to write {}: {e}", target.display()))?;
    }
    for sub in dir.dirs() {
        write_dir_recursive(sub, dest)?;
    }
    Ok(())
}

/// Effective content for an overridable template (override else embedded).
/// Returns empty only if given a name outside the overridable set (callers pass
/// literals from [`TEMPLATE_NAMES`]).
fn template_content(templates_dir: &Path, name: &str) -> String {
    resolve_template(templates_dir, name)
        .map(|(content, _)| content)
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    const PY: &str = "/abs/engine/.venv/bin/python";
    const SOCK: &str = "/abs/ws/.solidifai/engine.sock";

    fn unique(tag: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "solidifai-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    fn tmp_ws() -> WorkspacePaths {
        let ws = WorkspacePaths::for_root(unique("prov-test"));
        ws.ensure_dirs().unwrap();
        ws
    }

    /// The engine endpoint must never live under the user-chosen workspace root
    /// (Windows pointer-file ACLs, unix sun_path length), must be stable per
    /// root, and distinct across roots.
    #[test]
    fn engine_socket_lives_outside_the_workspace() {
        let a = WorkspacePaths::for_root(unique("sock-a"));
        let b = WorkspacePaths::for_root(unique("sock-b"));
        assert!(
            !a.socket.starts_with(&a.root),
            "socket must not inherit workspace-dir ACLs: {}",
            a.socket.display()
        );
        assert_ne!(a.socket, b.socket, "one endpoint per workspace");
        assert_eq!(
            a.socket,
            WorkspacePaths::for_root(a.root.clone()).socket,
            "endpoint must be stable for a given root"
        );
        // AF_UNIX sun_path budget (~104 bytes): the endpoint stays short no
        // matter how deep the workspace root is.
        assert!(
            a.socket.as_os_str().len() < 104,
            "socket path too long: {}",
            a.socket.display()
        );
        a.ensure_dirs().unwrap();
        assert!(a.socket.parent().unwrap().is_dir(), "ipc dir created");
    }

    /// An empty templates dir (no overrides) so provision uses embedded defaults.
    fn tmp_templates() -> PathBuf {
        let dir = unique("tmpl-test");
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn assert_skill_tree_matches(source: &include_dir::Dir, dest: &Path) {
        for file in source.files() {
            assert_eq!(
                fs::read(dest.join(file.path())).unwrap(),
                file.contents(),
                "provisioned skill differs from canonical template: {}",
                file.path().display()
            );
        }
        for child in source.dirs() {
            assert_skill_tree_matches(child, dest);
        }
    }

    #[test]
    fn provisioned_agent_skill_trees_match_canonical_templates_byte_for_byte() {
        let ws = tmp_ws();
        let templates = tmp_templates();
        provision(&ws, PY, SOCK, &templates).expect("provision");

        assert_skill_tree_matches(&SKILLS_DIR, &ws.root.join(".claude/skills"));
        assert_skill_tree_matches(&SKILLS_DIR, &ws.root.join(".opencode/skills"));

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    #[test]
    fn snapshot_resolves_one_immutable_generation_even_when_legacy_mirrors_fail() {
        let ws = tmp_ws();
        let generation = ws.artifacts.join("generations/pub-1");
        fs::create_dir_all(&generation).unwrap();
        let manifest = r#"{"schema":2,"buildId":1,"publicationId":"pub-1"}"#;
        let glb = b"matching-glb";
        fs::write(generation.join("model.json"), manifest).unwrap();
        fs::write(generation.join("model.glb"), glb).unwrap();
        fs::write(
            ws.artifacts.join("current.json"),
            r#"{"publicationId":"pub-1","buildId":1,"modelJson":"model.json","modelGlb":"model.glb"}"#,
        )
        .unwrap();
        // Compatibility mirrors are written after current.json and may be stale or
        // unavailable without invalidating the immutable published pair.
        fs::write(ws.artifacts.join("model.json"), "not json").unwrap();

        let snapshot = read_model_snapshot_from_artifacts(&ws.artifacts)
            .unwrap()
            .expect("published snapshot");
        assert_eq!(snapshot.publication_id.as_deref(), Some("pub-1"));
        assert_eq!(snapshot.manifest, manifest);
        assert_eq!(snapshot.glb, glb);

        let _ = fs::remove_dir_all(&ws.root);
    }

    #[test]
    fn snapshot_falls_back_to_legacy_root_artifacts_without_current_pointer() {
        let ws = tmp_ws();
        fs::write(
            ws.artifacts.join("model.json"),
            r#"{"schema":1,"buildId":4}"#,
        )
        .unwrap();
        fs::write(ws.artifacts.join("model.glb"), b"legacy-glb").unwrap();

        let snapshot = read_model_snapshot_from_artifacts(&ws.artifacts)
            .unwrap()
            .expect("legacy snapshot");
        assert_eq!(snapshot.publication_id, None);
        assert_eq!(snapshot.manifest, r#"{"schema":1,"buildId":4}"#);
        assert_eq!(snapshot.glb, b"legacy-glb");

        let _ = fs::remove_dir_all(&ws.root);
    }

    #[test]
    fn provision_writes_all_files_and_is_idempotent() {
        let ws = tmp_ws();
        let templates = tmp_templates();
        provision(&ws, PY, SOCK, &templates).expect("first provision");

        let expected = [
            ".mcp.json",
            ".codex/config.toml",
            "opencode.json",
            ".claude/settings.json",
            ".gemini/settings.json",
            ".github/mcp.json",
            ".pi/mcp.json",
            "AGENTS.md",
            "CLAUDE.md",
            "GEMINI.md",
        ];
        for rel in expected {
            assert!(ws.root.join(rel).is_file(), "missing {rel}");
        }

        // No starter model is provisioned: a fresh workspace has no model.py
        // until the agent's first build creates it.
        assert!(
            !ws.root.join("model.py").exists(),
            "model.py should not be provisioned into a new workspace"
        );

        // The whole app-managed skill tree is provisioned under every distinct
        // adapter skill root, preserving subdirs (SKILL.md + references/ +
        // examples/).
        let skill_tree = [
            "skills/using-solidifai/SKILL.md",
            "skills/solidifai-product-design/SKILL.md",
            "skills/solidifai-modeling/SKILL.md",
            "skills/solidifai-modeling/references/build123d-cookbook.md",
            "skills/solidifai-modeling/references/workflow.md",
            "skills/solidifai-modeling/examples/bracket.py",
            "skills/solidifai-modeling/examples/enclosure.py",
            "skills/solidifai-modeling/examples/flanged-mount.py",
            "skills/solidifai-modeling/examples/parametric-knob.py",
            "skills/solidifai-debugging/SKILL.md",
            "skills/solidifai-debugging/references/common-errors.md",
        ];
        for root in [".agents", ".claude", ".opencode", ".gemini"] {
            for rel in skill_tree {
                assert!(
                    ws.root.join(root).join(rel).is_file(),
                    "missing {root}/{rel}"
                );
            }
        }

        // The provisioned SKILL.md matches the embedded source (frontmatter name).
        let skill =
            fs::read_to_string(ws.root.join(".claude/skills/solidifai-modeling/SKILL.md")).unwrap();
        assert!(
            skill.contains("name: solidifai-modeling"),
            "SKILL.md should carry name: solidifai-modeling"
        );
        assert_eq!(
            fs::read_to_string(ws.root.join("CLAUDE.md")).unwrap().trim_end(),
            "<!-- solidifai-managed: safe to overwrite. Canonical copy: engine/workspace_templates/CLAUDE.md -->\n@AGENTS.md".trim_end()
        );
        assert_eq!(
            fs::read_to_string(ws.root.join("GEMINI.md")).unwrap().trim_end(),
            "<!-- solidifai-managed: safe to overwrite. Canonical copy: engine/workspace_templates/GEMINI.md -->\n@AGENTS.md".trim_end()
        );

        // The provisioned AGENTS.md must carry the live manufacturing-profile region.
        let agents_out = fs::read_to_string(ws.root.join("AGENTS.md")).unwrap();
        assert!(agents_out.contains("## Manufacturing profile"));
        assert!(agents_out.contains("Wall: 2.4 mm"));

        // Second provision must not error (idempotent over our own files).
        provision(&ws, PY, SOCK, &templates).expect("second provision");

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    #[test]
    fn workspace_provisioning_exposes_the_six_documented_harnesses_in_display_order() {
        let documented_names = crate::agent_harness::adapter_registry()
            .iter()
            .map(|adapter| adapter.display_name)
            .collect::<Vec<_>>();

        assert_eq!(
            documented_names,
            [
                "Codex",
                "Claude Code",
                "OpenCode",
                "Gemini CLI",
                "GitHub Copilot CLI",
                "Pi",
            ]
        );
    }

    #[test]
    fn provision_reports_written_and_user_owned_paths() {
        let ws = tmp_ws();
        let templates = tmp_templates();
        let user_owned = ws.root.join(".pi/mcp.json");
        fs::create_dir_all(user_owned.parent().unwrap()).unwrap();
        fs::write(&user_owned, "USER OWNED").unwrap();

        let report = provision(&ws, PY, SOCK, &templates).expect("provision");

        assert!(report.written.contains(&"AGENTS.md".to_string()));
        assert!(report
            .skipped_user_owned
            .contains(&".pi/mcp.json".to_string()));
        assert!(report.errors.is_empty());

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    #[test]
    fn provision_writes_harness_instruction_pointers_without_an_interpreter() {
        let ws = tmp_ws();
        let templates = tmp_templates();

        provision(&ws, "", SOCK, &templates).expect("offline provision");

        assert!(
            ws.root.join("CLAUDE.md").is_file(),
            "Claude pointer must not depend on the interpreter"
        );
        assert!(
            ws.root.join("GEMINI.md").is_file(),
            "Gemini pointer must not depend on the interpreter"
        );
        for rel in [
            ".mcp.json",
            ".claude/settings.json",
            ".codex/config.toml",
            "opencode.json",
            ".gemini/settings.json",
            ".github/mcp.json",
            ".pi/mcp.json",
        ] {
            assert!(
                !ws.root.join(rel).exists(),
                "MCP configuration must wait for an interpreter: {rel}"
            );
        }

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    /// The always-loaded brief must LEAD with the using-solidifai directive, so
    /// every harness that reads AGENTS.md (directly or through a harness pointer)
    /// sees it before anything else.
    #[test]
    fn provisioned_agents_md_leads_with_using_solidifai_directive() {
        let ws = tmp_ws();
        let templates = tmp_templates();
        provision(&ws, PY, SOCK, &templates).expect("provision");

        let agents = fs::read_to_string(ws.root.join("AGENTS.md")).unwrap();
        let directive = agents
            .find("invoke the `using-solidifai` skill")
            .expect("AGENTS.md must carry the using-solidifai directive");
        let title = agents
            .find("# solidifai CAD workspace")
            .expect("AGENTS.md title");
        assert!(
            directive < title,
            "the directive must lead the file, before the title"
        );

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    /// Provisioning re-writes OUR skill files (so improvements flow) but never
    /// touches other skills the user added under the same skills root.
    #[test]
    fn provision_refreshes_managed_skills_and_preserves_user_skills() {
        let ws = tmp_ws();
        let templates = tmp_templates();

        // A user's own skill, plus a stale copy of one of our skill files.
        let user_skill = ws.root.join(".claude/skills/my-own-skill/SKILL.md");
        fs::create_dir_all(user_skill.parent().unwrap()).unwrap();
        fs::write(&user_skill, "MY OWN SKILL").unwrap();
        let managed = ws.root.join(".claude/skills/solidifai-modeling/SKILL.md");
        fs::create_dir_all(managed.parent().unwrap()).unwrap();
        fs::write(&managed, "STALE").unwrap();

        provision(&ws, PY, SOCK, &templates).expect("provision");

        // Our skill file is refreshed to the embedded content...
        let refreshed = fs::read_to_string(&managed).unwrap();
        assert!(refreshed.contains("name: solidifai-modeling"));
        assert_ne!(refreshed, "STALE", "managed skill should be overwritten");
        // ...but the user's own skill is left untouched.
        assert_eq!(fs::read_to_string(&user_skill).unwrap(), "MY OWN SKILL");

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    #[test]
    fn write_managed_preserves_user_owned_files() {
        let ws = tmp_ws();
        let user_file = ws.root.join("AGENTS.md");
        fs::create_dir_all(&ws.root).unwrap();
        fs::write(&user_file, "MY OWN NOTES, NOT MANAGED").unwrap();

        // Provision should skip the user-owned AGENTS.md (no marker) but still
        // write the other files.
        let templates = tmp_templates();
        provision(&ws, PY, SOCK, &templates).expect("provision over user file");
        assert_eq!(
            fs::read_to_string(&user_file).unwrap(),
            "MY OWN NOTES, NOT MANAGED",
            "user-owned file must be preserved"
        );
        assert!(ws.root.join(".mcp.json").is_file());

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    #[test]
    fn template_override_beats_embedded_and_reset_reverts() {
        let templates = tmp_templates();

        // No override yet: resolve returns the embedded default, not custom.
        let (content, is_custom) = resolve_template(&templates, "AGENTS.md").unwrap();
        assert_eq!(content, AGENTS_MD);
        assert!(!is_custom);

        // Write an override: it wins and is marked custom.
        write_template_override(&templates, "AGENTS.md", "MY CUSTOM AGENTS").expect("write");
        let (content, is_custom) = resolve_template(&templates, "AGENTS.md").unwrap();
        assert_eq!(content, "MY CUSTOM AGENTS");
        assert!(is_custom);

        // The override flows through provisioning.
        let ws = tmp_ws();
        provision(&ws, PY, SOCK, &templates).expect("provision with override");
        assert_eq!(
            fs::read_to_string(ws.root.join("AGENTS.md")).unwrap(),
            "MY CUSTOM AGENTS"
        );

        // Reset removes the override and reverts to the embedded default.
        delete_template_override(&templates, "AGENTS.md").expect("delete");
        let (content, is_custom) = resolve_template(&templates, "AGENTS.md").unwrap();
        assert_eq!(content, AGENTS_MD);
        assert!(!is_custom);
        // Resetting again (no override present) is a harmless no-op.
        delete_template_override(&templates, "AGENTS.md").expect("delete idempotent");

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    #[test]
    fn template_store_validates_names() {
        let templates = tmp_templates();
        assert!(write_template_override(&templates, "bogus.md", "x").is_err());
        assert!(delete_template_override(&templates, "bogus.md").is_err());
        assert!(resolve_template(&templates, "bogus.md").is_none());
        for name in TEMPLATE_NAMES {
            assert!(is_template_name(name));
            assert!(embedded_template(name).is_some());
        }
        let _ = fs::remove_dir_all(&templates);
    }

    /// The overridable set is exactly AGENTS.md — SKILL.md and model.py are both
    /// gone (skills are app-managed; the starter model is no longer provisioned).
    /// This is what `get_templates()` maps over, so it now returns AGENTS.md only.
    #[test]
    fn overridable_set_is_agents_only() {
        assert_eq!(TEMPLATE_NAMES, ["AGENTS.md"]);
        assert!(is_template_name("AGENTS.md"));
        assert!(!is_template_name("model.py"));
        assert!(embedded_template("model.py").is_none());
        assert!(!is_template_name("SKILL.md"));
        assert!(embedded_template("SKILL.md").is_none());

        // Each overridable name resolves to its embedded default (not custom) when
        // no override exists — the shape get_templates() reports.
        let templates = tmp_templates();
        for name in TEMPLATE_NAMES {
            let (content, is_custom) = resolve_template(&templates, name).expect("resolves");
            assert!(!content.is_empty());
            assert!(!is_custom);
        }
        let _ = fs::remove_dir_all(&templates);
    }

    /// A disabled skill is not written; an already-written disabled skill is
    /// removed on re-provision; user-added skills survive either way.
    #[test]
    fn provision_honors_disabled_skills() {
        let ws = tmp_ws();
        let templates = tmp_templates();

        // Disable solidifai-debugging for this workspace.
        let cfg = crate::agent_config::AgentConfig {
            enabled_skills: Some(vec![
                "solidifai-modeling".to_string(),
                "using-solidifai".to_string(),
            ]),
            auto_provision_skills: true,
        };
        crate::agent_config::save(&ws.dot, &cfg).expect("save agent config");

        provision(&ws, PY, SOCK, &templates).expect("provision");

        let claude = ws.root.join(".claude/skills");
        assert!(claude.join("solidifai-modeling/SKILL.md").is_file());
        assert!(claude.join("using-solidifai/SKILL.md").is_file());
        assert!(
            !claude.join("solidifai-debugging").exists(),
            "disabled skill must not be written"
        );

        // Re-enable debugging, re-provision: it appears.
        let cfg2 = crate::agent_config::AgentConfig {
            enabled_skills: None,
            auto_provision_skills: true,
        };
        crate::agent_config::save(&ws.dot, &cfg2).expect("save agent config 2");
        provision(&ws, PY, SOCK, &templates).expect("re-provision");
        assert!(claude.join("solidifai-debugging/SKILL.md").is_file());

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    /// Guard: the PROVISIONED skill files (what users actually get) must not
    /// hardcode the old "PLA default / FDM is the process" assumptions. The
    /// templates are embedded at build time, so this asserts on the files written
    /// into a temp workspace, matching the real `.claude/skills/...` layout.
    #[test]
    fn provisioned_skills_are_not_pla_or_fdm_hardcoded() {
        let ws = tmp_ws();
        let templates = tmp_templates();
        provision(&ws, PY, SOCK, &templates).expect("provision");

        let read = |rel: &str| fs::read_to_string(ws.root.join(rel)).unwrap();

        let agents = read("AGENTS.md");
        assert!(
            !agents.contains("matte light-gray PLA"),
            "AGENTS.md must not hardcode the PLA default appearance"
        );
        assert!(
            !agents.contains("pla` (default)") && !agents.contains("pla (default)"),
            "AGENTS.md must not mark PLA as the default material"
        );

        let manu = read(".claude/skills/solidifai-product-design/references/manufacturability.md");
        assert!(
            !manu.contains("FDM unless the user says otherwise"),
            "manufacturability must read the process from the material, not default to FDM"
        );
        assert!(
            manu.contains("isDefault") || manu.contains("list_materials"),
            "manufacturability must point at list_materials for the process"
        );

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    #[test]
    fn renders_profile_region_with_builtin_defaults() {
        let block = render_profile_block(Path::new("/no/config"), Path::new("/no/ws"));
        assert!(block.contains("solidifai-profile:start"));
        assert!(block.contains("solidifai-profile:end"));
        assert!(block.contains("Wall: 2.4 mm"));
        assert!(block.contains("45 deg overhang"));
        assert!(block.contains("Material:")); // echoed default material present
    }

    #[test]
    fn workspace_override_changes_the_rendered_region() {
        let dir = std::env::temp_dir().join(format!("sol-prof-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("manufacturing-profile.json"),
            r#"{"schema":1,"design":{"wallMm":3.2}}"#,
        )
        .unwrap();
        let block = render_profile_block(Path::new("/no/config"), &dir);
        assert!(block.contains("Wall: 3.2 mm"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn replace_region_swaps_between_markers() {
        let text =
            "head\n<!-- solidifai-profile:start x -->\nOLD\n<!-- solidifai-profile:end -->\ntail";
        let out = replace_profile_region(text, "NEWBLOCK");
        assert!(out.contains("NEWBLOCK"));
        assert!(!out.contains("OLD"));
        assert!(out.starts_with("head"));
        assert!(out.trim_end().ends_with("tail"));
    }

    #[test]
    fn renders_schema_one_fdm_profile_with_legacy_settings() {
        let dir = unique("profile-v1-fdm");
        fs::create_dir_all(&dir).unwrap();
        fs::write(
            dir.join("manufacturing-profile.json"),
            r#"{"schema":1,"process":{"kind":"fdm","nozzleMm":0.6,"infillPct":35}}"#,
        )
        .unwrap();
        let block = render_profile_block(Path::new("/no/config"), &dir);
        assert!(block.contains("Process: FDM (fdm), 0.6 mm nozzle"));
        assert!(block.contains("35% infill"));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn renders_v2_non_fdm_profiles_without_fdm_controls() {
        for process in ["cnc", "sla", "sls"] {
            let dir = unique(&format!("profile-v2-{process}"));
            fs::create_dir_all(&dir).unwrap();
            fs::write(
                dir.join("manufacturing-profile.json"),
                format!(r#"{{"schema":2,"process":{{"id":"{process}","settings":{{}}}}}}"#),
            )
            .unwrap();
            let block = render_profile_block(Path::new("/no/config"), &dir);
            assert!(block.contains(&format!("({process})")));
            assert!(
                !block.contains("nozzle"),
                "{process} must not render nozzle controls"
            );
            assert!(
                !block.contains("infill"),
                "{process} must not render infill controls"
            );
            let _ = fs::remove_dir_all(&dir);
        }
    }

    #[test]
    fn sparse_workspace_profile_inherits_catalog_process_from_global() {
        let config = unique("profile-global");
        let workspace = unique("profile-workspace");
        fs::create_dir_all(&config).unwrap();
        fs::create_dir_all(&workspace).unwrap();
        fs::write(
            config.join("manufacturing-profile.json"),
            r#"{"schema":2,"process":{"id":"cnc","settings":{}}}"#,
        )
        .unwrap();
        fs::write(
            workspace.join("manufacturing-profile.json"),
            r#"{"schema":1,"process":{"overhangDeg":55}}"#,
        )
        .unwrap();
        let block = render_profile_block(&config, &workspace);
        assert!(block.contains("CNC (cnc)"));
        assert!(!block.contains("nozzle"));
        let _ = fs::remove_dir_all(&config);
        let _ = fs::remove_dir_all(&workspace);
    }

    #[test]
    fn profile_region_uses_catalog_process_label_and_settings() {
        let block = render_profile_block(Path::new("/no/config"), Path::new("/no/ws"));
        assert!(block.contains("FDM (fdm)"));
        assert_eq!(crate::materials::profile_settings("fdm").len(), 4);
    }

    #[test]
    fn replace_region_noop_when_end_marker_missing() {
        let text = "a\n<!-- solidifai-profile:start x -->\nbody no end\n";
        assert_eq!(replace_profile_region(text, "NEW"), text);
    }

    #[test]
    fn replace_custom_region_swaps_between_markers_and_keeps_them() {
        let text = "head\n<!-- solidifai-custom:start -->\n<!-- solidifai-custom:end -->\ntail";
        let out = replace_custom_region(text, "## Custom instructions\n\nHELLO");
        assert!(out.contains("HELLO"));
        assert!(out.contains(CUSTOM_START), "start marker preserved");
        assert!(out.contains(CUSTOM_END), "end marker preserved");
        assert!(out.starts_with("head"));
        assert!(out.trim_end().ends_with("tail"));
    }

    #[test]
    fn replace_custom_region_empty_block_collapses_to_bare_markers() {
        let text =
            "head\n<!-- solidifai-custom:start -->\nOLD BODY\n<!-- solidifai-custom:end -->\ntail";
        let out = replace_custom_region(text, "");
        assert!(!out.contains("OLD BODY"));
        assert!(out.contains(&format!("{CUSTOM_START}\n{CUSTOM_END}")));
    }

    #[test]
    fn replace_custom_region_noop_when_markers_absent() {
        let text = "no markers here\n";
        assert_eq!(replace_custom_region(text, "BLOCK"), text);
    }

    #[test]
    fn sanitize_folder_name_escapes_windows_reserved_names() {
        // Reserved device names fail mkdir on Windows even though valid elsewhere.
        assert_eq!(sanitize_folder_name("CON"), "_CON");
        assert_eq!(sanitize_folder_name("con"), "_con");
        assert_eq!(sanitize_folder_name("NUL"), "_NUL");
        assert_eq!(sanitize_folder_name("COM1"), "_COM1");
        assert_eq!(sanitize_folder_name("LPT9"), "_LPT9");
        // Matched on the stem before the first dot.
        assert_eq!(sanitize_folder_name("nul.txt"), "_nul.txt");
        // Names that merely start with a reserved word are untouched.
        assert_eq!(sanitize_folder_name("console"), "console");
        assert_eq!(sanitize_folder_name("common"), "common");
        assert_eq!(sanitize_folder_name("com10"), "com10");
    }

    #[test]
    fn sanitize_folder_name_produces_safe_segments() {
        assert_eq!(sanitize_folder_name("My Part"), "My-Part");
        assert_eq!(sanitize_folder_name("a/b\\c"), "a-b-c");
        assert_eq!(sanitize_folder_name("  spaced  "), "spaced");
        assert_eq!(sanitize_folder_name("..//.."), "workspace");
        assert_eq!(sanitize_folder_name(""), "workspace");
        assert_eq!(sanitize_folder_name("keep-_.dots"), "keep-_.dots");
        assert_eq!(sanitize_folder_name("emoji \u{1f600} test"), "emoji-test");
        // No path separators survive.
        assert!(!sanitize_folder_name("x/../../etc").contains('/'));
    }
}
