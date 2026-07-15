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
use serde_json::json;
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
const MANAGED_MARKER: &str = "solidifai-managed";

/// Canonical instructional content, embedded from `engine/workspace_templates/`
/// so it ships in the binary and is written verbatim.
const AGENTS_MD: &str = include_str!("../../engine/workspace_templates/AGENTS.md");
const CLAUDE_MD: &str = include_str!("../../engine/workspace_templates/CLAUDE.md");

const MFG_REGION_START: &str = "<!-- solidifai-profile:start";
const MFG_REGION_END: &str = "<!-- solidifai-profile:end -->";

const CUSTOM_START: &str = "<!-- solidifai-custom:start -->";
const CUSTOM_END: &str = "<!-- solidifai-custom:end -->";

/// The using-solidifai entry-point directive, injected verbatim into the agent's
/// context at session start (the Claude hook reads it; the Cursor rule embeds it).
/// No managed marker: it must land in context clean.
const USING_SOLIDIFAI_DIRECTIVE: &str = "\
solidifai CAD workspace: do this first.

Before you reply, take any action, or invoke any other skill, invoke the \
`using-solidifai` skill. It orients you to this workspace and the `solidifai-cad` \
engine that every other solidifai skill drives. This holds even when the request \
looks simple or maps cleanly to modeling or product design: those skills assume \
you have already read using-solidifai.

If your harness has no skill mechanism, read \
`.claude/skills/using-solidifai/SKILL.md` first instead, then continue.
";

/// The app-managed Agent Skills collection (multiple skills, each a directory with
/// `SKILL.md` plus optional `references/` and `examples/`). Embedded as a tree so
/// the whole thing ships in the binary and is written into every workspace under
/// both agent skill roots. Unlike the overridable templates, these are NOT
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
    format!("{:x}", Sha256::digest(bytes))
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
// (.mcp.json / .codex / opencode.json / .claude settings) are code-generated and
// NOT user-editable; CLAUDE.md stays the embedded `@AGENTS.md`; and the Agent
// Skills collection is app-managed (see `SKILLS_DIR`), not per-file overridable.

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
fn write_managed(path: &Path, content: &str) -> Result<bool, String> {
    if path.exists() {
        let existing = fs::read_to_string(path)
            .map_err(|e| format!("failed to read existing {}: {e}", path.display()))?;
        if !existing.contains(MANAGED_MARKER) {
            // User made this file their own; leave it untouched.
            return Ok(false);
        }
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
    }
    fs::write(path, content).map_err(|e| format!("failed to write {}: {e}", path.display()))?;
    Ok(true)
}

// -- config file builders (pure; produce strings with the managed marker) -----

/// `.mcp.json` — Claude Code / generic MCP server registration.
pub fn mcp_json(py: &str, sock: &str) -> String {
    let v = json!({
        "//": format!("{MANAGED_MARKER}: generated by solidifai; safe to overwrite"),
        "mcpServers": {
            "solidifai-cad": {
                "command": py,
                "args": ["-m", "solidifai_mcp"],
                "env": { "SOLIDIFAI_ENGINE_SOCK": sock }
            }
        }
    });
    pretty(&v)
}

/// `.claude/settings.json` — pre-approve the `.mcp.json` server (skip the per-server
/// prompt) and install a `SessionStart` hook injecting the using-solidifai directive
/// each session: the hard backstop for AGENTS.md's soft "read using-solidifai first"
/// line. `directive_path` is the absolute path to the file the hook prints.
pub fn claude_settings_json(py: &str, directive_path: &str) -> String {
    let v = json!({
        "//": format!("{MANAGED_MARKER}: generated by solidifai; safe to overwrite"),
        "enabledMcpjsonServers": ["solidifai-cad"],
        // No matcher: fire on every session start (startup, resume, clear, compact)
        // so the orientation is re-seeded after a context reset too.
        "hooks": {
            "SessionStart": [
                { "hooks": [
                    { "type": "command", "command": session_start_hook_command(py, directive_path) }
                ] }
            ]
        }
    });
    pretty(&v)
}

/// Shell command for a SessionStart hook: print the using-solidifai directive to
/// stdout so the harness injects it as context. Uses the engine's absolute Python
/// (already required for the MCP server) to read the directive path passed as
/// `argv[1]` — the path never enters the Python source, so there is no inline
/// quoting or Windows-backslash hazard across sh / cmd / powershell.
fn session_start_hook_command(py: &str, directive_path: &str) -> String {
    format!(
        "\"{py}\" -c \"import pathlib,sys; sys.stdout.write(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\" \"{directive_path}\""
    )
}

/// `.cursor/rules/using-solidifai.mdc` — Cursor has no session hook and does not
/// reliably inject AGENTS.md, so an `alwaysApply` project rule is its equivalent
/// of the Claude SessionStart hook: Cursor prepends it to every request. The
/// managed marker rides in an HTML comment (Cursor ignores it) so [`write_managed`]
/// can refresh it without clobbering a rule the user made their own.
pub fn cursor_rule_mdc() -> String {
    format!(
        "---\nalwaysApply: true\n---\n<!-- {MANAGED_MARKER}: generated by solidifai; safe to overwrite -->\n\n{USING_SOLIDIFAI_DIRECTIVE}"
    )
}

/// `opencode.json` — OpenCode MCP + instructions config.
///
/// OpenCode's config schema sets `additionalProperties: false`, so a `"//"`
/// comment key is rejected as an unrecognized key. It does enable
/// `allowComments`, so the managed marker rides on a leading JSONC `//` line
/// comment instead (still detected by `write_managed`).
pub fn opencode_json(py: &str, sock: &str) -> String {
    let v = json!({
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "solidifai-cad": {
                "type": "local",
                "command": [py, "-m", "solidifai_mcp"],
                "environment": { "SOLIDIFAI_ENGINE_SOCK": sock },
                "enabled": true
            }
        },
        "instructions": ["AGENTS.md"]
    });
    format!(
        "// {MANAGED_MARKER}: generated by solidifai; safe to overwrite\n{}",
        pretty(&v)
    )
}

/// `.codex/config.toml` — Codex MCP server registration.
pub fn codex_config_toml(py: &str, sock: &str) -> String {
    // Hand-rendered TOML so we can place a managed-marker comment at the top and
    // control quoting. Backslashes/quotes are not expected in our generated paths,
    // but escape defensively for TOML basic strings.
    let py_e = toml_escape(py);
    let sock_e = toml_escape(sock);
    format!(
        "# {MANAGED_MARKER}: generated by solidifai; safe to overwrite\n\
         \n\
         [mcp_servers.solidifai-cad]\n\
         command = \"{py_e}\"\n\
         args = [\"-m\", \"solidifai_mcp\"]\n\
         \n\
         [mcp_servers.solidifai-cad.env]\n\
         SOLIDIFAI_ENGINE_SOCK = \"{sock_e}\"\n"
    )
}

fn toml_escape(s: &str) -> String {
    s.replace('\\', "\\\\").replace('"', "\\\"")
}

fn pretty(v: &serde_json::Value) -> String {
    let mut s = serde_json::to_string_pretty(v).unwrap_or_else(|_| "{}".to_string());
    s.push('\n');
    s
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
    let kind = prof
        .get("process")
        .and_then(|p| p.get("kind"))
        .and_then(|v| v.as_str())
        .unwrap_or("fdm")
        .to_uppercase();

    // f64 Display drops trailing zeros (45.0 -> "45", 0.2 -> "0.2").
    let g = |x: f64| format!("{x}");

    format!(
        "{start} (managed by solidifai; reflects this workspace's manufacturing profile as of session start) -->\n\
         - Material: {mat} · Fit: {fit} ({clear} mm) · Wall: {wall} mm · Edge-break: {fillet} mm\n\
         - Process: {kind}, {nozzle} mm nozzle, {layer} mm layers, {overhang} deg overhang, {infill}% infill\n\
         - Print (advisory; the slicer owns the real values): {ntemp}C nozzle / {btemp}C bed, ~${cost}/kg\n\
         {end}",
        start = MFG_REGION_START,
        end = MFG_REGION_END,
        mat = mat_label,
        fit = fit,
        clear = g(clearance),
        wall = g(num(&["design", "wallMm"], 2.4)),
        fillet = g(num(&["design", "filletMm"], 1.0)),
        nozzle = g(num(&["process", "nozzleMm"], 0.4)),
        layer = g(num(&["process", "layerMm"], 0.2)),
        overhang = g(num(&["process", "overhangDeg"], 45.0)),
        infill = g(num(&["process", "infillPct"], 20.0)),
        ntemp = g(num(&["fabrication", "nozzleTempC"], 210.0)),
        btemp = g(num(&["fabrication", "bedTempC"], 60.0)),
        cost = g(num(&["fabrication", "filamentCostPerKg"], 25.0)),
    )
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
) -> Result<(), String> {
    let root = &ws.root;

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

    // The SessionStart hook reads this by absolute path. It is marker-less (so it
    // injects cleanly), which means it must bypass write_managed — write_managed
    // would mistake a marker-less existing file for a user-owned one and skip it.
    let directive_path = ws.dot.join("using-solidifai-directive.md");
    if let Some(parent) = directive_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("failed to create {}: {e}", parent.display()))?;
    }
    fs::write(&directive_path, USING_SOLIDIFAI_DIRECTIVE)
        .map_err(|e| format!("failed to write {}: {e}", directive_path.display()))?;
    let directive_str = directive_path.to_string_lossy();

    // MCP / agent config (code-generated; NOT user-editable). All four embed the
    // interpreter as the command, so when it is unknown (e.g. an offline first
    // launch before the engine cache exists) skip them rather than writing a
    // broken empty command; they are managed files, rewritten on the next open
    // once the engine resolves.
    if !py.is_empty() {
        write_managed(&root.join(".mcp.json"), &mcp_json(py, sock))?;
        write_managed(
            &root.join(".codex/config.toml"),
            &codex_config_toml(py, sock),
        )?;
        write_managed(&root.join("opencode.json"), &opencode_json(py, sock))?;
        write_managed(
            &root.join(".claude/settings.json"),
            &claude_settings_json(py, &directive_str),
        )?;
    }
    // Cursor's session-start equivalent (always-apply rule).
    write_managed(
        &root.join(".cursor/rules/using-solidifai.mdc"),
        &cursor_rule_mdc(),
    )?;

    // Instructions (AGENTS.md overridable; CLAUDE.md stays the embedded @AGENTS.md).
    write_managed(&root.join("AGENTS.md"), &agents)?;
    write_managed(&root.join("CLAUDE.md"), CLAUDE_MD)?;

    // App-managed Agent Skills collection: write the ENABLED embedded skills under
    // both agent skill roots (preserving subdirs). The enabled set is the
    // per-workspace agent config (default: all skills, auto-provision on). When
    // auto-provision is off the user hand-manages their skill dirs and we skip
    // writing entirely. Re-writes OUR enabled skill files so improvements flow;
    // never touches other skills the user added.
    let agent_cfg = crate::agent_config::load(&ws.dot);
    if agent_cfg.auto_provision_skills {
        let enabled = agent_cfg.enabled_skills.as_deref();
        write_skills_tree(&root.join(".claude/skills"), enabled)?;
        write_skills_tree(&root.join(".opencode/skills"), enabled)?;
    }

    // No starter model.py: a fresh workspace opens modelless (the viewport shows
    // its empty state) and the agent's first build writes model.py itself.

    Ok(())
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
    fn mcp_json_is_valid_and_has_contract_shape() {
        let s = mcp_json(PY, SOCK);
        let v: serde_json::Value = serde_json::from_str(&s).expect("valid JSON");
        let srv = &v["mcpServers"]["solidifai-cad"];
        assert_eq!(srv["command"], PY);
        assert_eq!(srv["args"][0], "-m");
        assert_eq!(srv["args"][1], "solidifai_mcp");
        assert_eq!(srv["env"]["SOLIDIFAI_ENGINE_SOCK"], SOCK);
        assert!(s.contains(MANAGED_MARKER));
    }

    #[test]
    fn opencode_json_is_valid_and_has_contract_shape() {
        let s = opencode_json(PY, SOCK);
        // The managed marker rides on a leading JSONC `//` comment, not a `"//"`
        // key (OpenCode's schema rejects unknown keys but allows comments).
        assert!(s.starts_with("// "));
        assert!(s.contains(MANAGED_MARKER));
        // Strip comment lines so we can validate the body as strict JSON.
        let body: String = s
            .lines()
            .filter(|l| !l.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n");
        let v: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
        assert_eq!(v["$schema"], "https://opencode.ai/config.json");
        let srv = &v["mcp"]["solidifai-cad"];
        assert_eq!(srv["type"], "local");
        assert_eq!(srv["command"][0], PY);
        assert_eq!(srv["command"][2], "solidifai_mcp");
        assert_eq!(srv["environment"]["SOLIDIFAI_ENGINE_SOCK"], SOCK);
        assert_eq!(srv["enabled"], true);
        assert_eq!(v["instructions"][0], "AGENTS.md");
    }

    #[test]
    fn claude_settings_enables_server_and_injects_using_solidifai_hook() {
        let directive = "/abs/ws/.solidifai/using-solidifai-directive.md";
        let s = claude_settings_json(PY, directive);
        let v: serde_json::Value = serde_json::from_str(&s).expect("valid JSON");
        assert_eq!(v["enabledMcpjsonServers"][0], "solidifai-cad");

        // A SessionStart hook injects the using-solidifai directive into the
        // agent's context at the start of every session (the hard backstop for
        // the soft "read using-solidifai first" instruction).
        let entry = &v["hooks"]["SessionStart"][0]["hooks"][0];
        assert_eq!(entry["type"], "command");
        let cmd = entry["command"]
            .as_str()
            .expect("SessionStart command string");
        assert!(cmd.contains(PY), "hook runs the engine python: {cmd}");
        assert!(
            cmd.contains(directive),
            "hook reads the directive file by absolute path: {cmd}"
        );
        assert!(s.contains(MANAGED_MARKER));
    }

    #[test]
    fn using_solidifai_directive_is_imperative_and_names_the_skill() {
        let d = USING_SOLIDIFAI_DIRECTIVE;
        assert!(d.contains("using-solidifai"), "directive names the skill");
        assert!(!d.trim().is_empty());
        // Injected verbatim into context, so it must not carry the managed marker.
        assert!(
            !d.contains(MANAGED_MARKER),
            "directive is injected as-is; no marker noise"
        );
    }

    #[test]
    fn cursor_rule_is_always_applied_and_names_the_skill() {
        let r = cursor_rule_mdc();
        // Cursor has no session hook and does not reliably inject AGENTS.md, so an
        // always-apply rule is its SessionStart-equivalent.
        assert!(
            r.contains("alwaysApply: true"),
            "rule must be always-applied"
        );
        assert!(r.contains("using-solidifai"), "rule names the skill");
        // Managed (via an HTML comment Cursor ignores) so provision can refresh it.
        assert!(r.contains(MANAGED_MARKER));
    }

    #[test]
    fn codex_toml_parses_and_has_contract_shape() {
        let s = codex_config_toml(PY, SOCK);
        let v: toml::Value = toml::from_str(&s).expect("valid TOML");
        let srv = &v["mcp_servers"]["solidifai-cad"];
        assert_eq!(srv["command"].as_str().unwrap(), PY);
        assert_eq!(srv["args"][0].as_str().unwrap(), "-m");
        assert_eq!(srv["args"][1].as_str().unwrap(), "solidifai_mcp");
        assert_eq!(srv["env"]["SOLIDIFAI_ENGINE_SOCK"].as_str().unwrap(), SOCK);
        assert!(s.contains(MANAGED_MARKER));
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
            "AGENTS.md",
            "CLAUDE.md",
            // Cross-harness using-solidifai entry-point: the Claude SessionStart
            // hook's directive file and the Cursor always-apply rule.
            ".solidifai/using-solidifai-directive.md",
            ".cursor/rules/using-solidifai.mdc",
        ];
        for rel in expected {
            assert!(ws.root.join(rel).is_file(), "missing {rel}");
        }

        // The Claude SessionStart hook must point at the directive file's real
        // absolute path in THIS workspace (not a placeholder), and the directive
        // file must carry the using-solidifai instruction.
        let settings = fs::read_to_string(ws.root.join(".claude/settings.json")).unwrap();
        let directive_abs = ws.root.join(".solidifai/using-solidifai-directive.md");
        assert!(
            settings.contains(&*directive_abs.to_string_lossy()),
            "SessionStart hook must reference the directive's absolute path"
        );
        let directive = fs::read_to_string(&directive_abs).unwrap();
        assert!(directive.contains("using-solidifai"));

        // No starter model is provisioned: a fresh workspace has no model.py
        // until the agent's first build creates it.
        assert!(
            !ws.root.join("model.py").exists(),
            "model.py should not be provisioned into a new workspace"
        );

        // The whole app-managed skill tree is provisioned under BOTH agent skill
        // roots, preserving subdirs (SKILL.md + references/ + examples/).
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
        for rel in skill_tree {
            assert!(
                ws.root.join(".claude").join(rel).is_file(),
                "missing .claude/{rel}"
            );
            assert!(
                ws.root.join(".opencode").join(rel).is_file(),
                "missing .opencode/{rel}"
            );
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

        // The provisioned AGENTS.md must carry the live manufacturing-profile region.
        let agents_out = fs::read_to_string(ws.root.join("AGENTS.md")).unwrap();
        assert!(agents_out.contains("## Manufacturing profile"));
        assert!(agents_out.contains("Wall: 2.4 mm"));

        // Second provision must not error (idempotent over our own files).
        provision(&ws, PY, SOCK, &templates).expect("second provision");

        let _ = fs::remove_dir_all(&ws.root);
        let _ = fs::remove_dir_all(&templates);
    }

    /// The always-loaded brief must LEAD with the using-solidifai directive, so
    /// every harness that reads AGENTS.md (Codex, OpenCode, Cursor, Claude via
    /// CLAUDE.md) sees it before anything else — the universal baseline behind the
    /// Claude/Cursor hard hooks.
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
