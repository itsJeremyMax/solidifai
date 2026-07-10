//! Engine environment resolution + supervisor for the Python CAD engine.
//!
//! Responsibilities:
//!   1. Locate the engine source dir (`engine/`) and the `uv` binary.
//!   2. Provision the engine's virtualenv with `uv sync` (idempotent).
//!   3. Read the installed `build123d` version for the status pill.
//!   4. Spawn the long-lived engine RPC server and keep its `Child` in managed
//!      state, restarting it once if it exits unexpectedly, and killing it on
//!      app exit / window destroy.
//!
//! Status is reported to the frontend via `engine-status` events. The geometry
//! RPC proxy lives in [`crate::rpc`]; this module only manages the *process*.
//!
//! Dev vs prod: [`resolve_engine_dir`] picks the bundled `engine-dist` resource
//! in release builds and the dev `../engine` checkout under `tauri dev`.

use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use parking_lot::Mutex;
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};

use crate::engine_cache::EngineCache;
use crate::engine_fetch;
use crate::engine_pin::EnginePin;
use engine_pack::manifest::Manifest;

/// A `Command` that never allocates a console window on Windows. The release
/// shell is a GUI-subsystem process (`windows_subsystem = "windows"` in main.rs),
/// so a console-subsystem child (python.exe, uv, orca-slicer) would otherwise get
/// a fresh visible console — and closing that stray window kills the child.
/// No-op on other platforms. Every child spawn outside the PTY (which uses
/// ConPTY) must go through this.
pub(crate) fn quiet_command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    #[cfg_attr(not(windows), allow(unused_mut))]
    let mut cmd = Command::new(program);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

/// Managed state for the engine process and the paths the rest of the app needs.
///
/// `child` is the live engine server process (if running). The supervisor thread
/// owns restarts; `lib.rs` kills the child on window-destroy / exit by calling
/// [`EngineState::kill`].
pub struct EngineState {
    pub child: Arc<Mutex<Option<Child>>>,
    /// Absolute path to the engine UNIX socket the server listens on.
    pub socket_path: Mutex<Option<String>>,
    /// Absolute path to the resolved engine interpreter (`<engine>/.venv/bin/python`).
    pub interpreter: Mutex<Option<String>>,
    /// build123d version string, once known.
    pub version: Mutex<Option<String>>,
    /// The most recently emitted `engine-status` payload. The frontend pill can
    /// mount AFTER the one-time `ready` emit; `get_engine_status` lets it seed
    /// itself from this stored value so it never gets stuck on "provisioning".
    pub last_status: Mutex<EngineStatus>,
    /// Monotonic supervisor generation. Each supervisor owns the value its spawner
    /// claimed via [`claim_generation`](Self::claim_generation);
    /// [`kill`](Self::kill) bumps it so a stale supervisor thread
    /// (from a previous workspace) knows to stop instead of restarting the engine
    /// or fighting the new supervisor for the `child` slot.
    pub generation: AtomicU64,
    /// The workspace canonical root path this engine serves. Stamped onto every
    /// emitted `engine-status` event so multi-workspace listeners can route by id.
    ws_id: Mutex<Option<String>>,
}

impl Default for EngineState {
    fn default() -> Self {
        Self {
            child: Arc::default(),
            socket_path: Mutex::default(),
            interpreter: Mutex::default(),
            version: Mutex::default(),
            last_status: Mutex::new(EngineStatus::provisioning_for("")),
            generation: AtomicU64::new(0),
            ws_id: Mutex::new(None),
        }
    }
}

impl EngineState {
    /// Best-effort: read the current engine socket path.
    pub fn socket(&self) -> Option<String> {
        self.socket_path.lock().clone()
    }

    /// The cached engine interpreter path, once env has been resolved.
    pub fn interpreter(&self) -> Option<String> {
        self.interpreter.lock().clone()
    }

    /// The most recently emitted engine status (defaults to `provisioning`).
    pub fn current_status(&self) -> EngineStatus {
        self.last_status.lock().clone()
    }

    /// Record the workspace id this engine serves. Every status emitted after this
    /// call will carry the given id in the `wsId` field. `start_workspace` calls this
    /// before starting the supervisor.
    pub fn set_ws_id(&self, id: &str) {
        *self.ws_id.lock() = Some(id.to_string());
    }

    /// Emit an `engine-status` event AND store it as the last status, so a late
    /// `get_engine_status` query always reflects the latest emitted value.
    /// The status's `ws_id` is overwritten from `self.ws_id` before storing/emitting
    /// so every event carries the right workspace id regardless of how the status
    /// was constructed.
    fn set_status(&self, app: &AppHandle, status: EngineStatus) {
        let mut status = status;
        status.ws_id = self.ws_id.lock().clone().unwrap_or_default();
        *self.last_status.lock() = status.clone();
        emit_status(app, status);
    }

    /// Kill the engine child if running, and bump the supervisor generation so any
    /// live supervisor thread stops instead of restarting. Called on
    /// window-destroy / app exit AND before switching workspaces.
    pub fn kill(&self) {
        // Bump first so a supervisor that wakes up between the take and its next
        // generation check sees the new value and bails out.
        self.generation.fetch_add(1, Ordering::SeqCst);
        if let Some(mut child) = self.child.lock().take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    /// The current supervisor generation.
    fn current_generation(&self) -> u64 {
        self.generation.load(Ordering::SeqCst)
    }

    /// Atomically bump the generation and return the new value: the caller's
    /// supervisor claims ownership, and every earlier supervisor (even one still
    /// inside `resolve_env`) becomes stale. Claimed on the spawning thread BEFORE
    /// the supervisor thread starts, so two concurrent kill+restart opens of the
    /// same workspace can never both think they own the engine.
    pub fn claim_generation(&self) -> u64 {
        self.generation.fetch_add(1, Ordering::SeqCst) + 1
    }
}

/// `engine-status` event payload. Matches the frontend contract exactly:
/// `{ status, interpreter, version, message, wsId }`.
#[derive(Clone, Serialize)]
pub struct EngineStatus {
    pub status: String,
    pub interpreter: Option<String>,
    pub version: Option<String>,
    pub message: Option<String>,
    /// The workspace canonical root path this engine serves. Stamped by
    /// [`EngineState::set_status`] from the stored `ws_id`; constructors set it
    /// to `""` as a placeholder that gets overwritten before emit.
    #[serde(rename = "wsId")]
    pub ws_id: String,
    /// 0..1 fraction, only set while `status == "updating"` (engine download).
    pub progress: Option<f64>,
}

impl EngineStatus {
    fn provisioning() -> Self {
        Self {
            status: "provisioning".into(),
            interpreter: None,
            version: None,
            message: None,
            ws_id: String::new(),
            progress: None,
        }
    }

    fn ready(interpreter: String, version: String) -> Self {
        Self {
            status: "ready".into(),
            interpreter: Some(interpreter),
            version: Some(version),
            message: None,
            ws_id: String::new(),
            progress: None,
        }
    }

    fn error(message: String) -> Self {
        Self {
            status: "error".into(),
            interpreter: None,
            version: None,
            message: Some(message),
            ws_id: String::new(),
            progress: None,
        }
    }

    /// Engine download progress; `total` is None until the server reports a length.
    pub fn updating(downloaded: u64, total: Option<u64>) -> Self {
        Self {
            status: "updating".into(),
            interpreter: None,
            version: None,
            message: Some("Updating engine".into()),
            ws_id: String::new(),
            progress: total
                .filter(|t| *t > 0)
                .map(|t| (downloaded as f64 / t as f64).min(1.0)),
        }
    }

    /// A post-download update phase (verify/install). Same `updating` status and
    /// dot, but `progress` is None: the work has no byte count, so the pill shows
    /// an indeterminate (spinning) ring and this `message` instead of a frozen
    /// "100%". `message` is the pill's label while this phase is live.
    pub fn updating_phase(message: &str) -> Self {
        Self {
            status: "updating".into(),
            interpreter: None,
            version: None,
            message: Some(message.into()),
            ws_id: String::new(),
            progress: None,
        }
    }

    /// Public constructor: `provisioning` status pre-tagged with a workspace id.
    pub fn provisioning_for(ws_id: &str) -> Self {
        let mut s = Self::provisioning();
        s.ws_id = ws_id.to_string();
        s
    }

    /// Public constructor: `ready` status pre-tagged with a workspace id.
    pub fn ready_for(ws_id: &str, interpreter: String, version: String) -> Self {
        let mut s = Self::ready(interpreter, version);
        s.ws_id = ws_id.to_string();
        s
    }

    /// Public constructor: `error` status pre-tagged with a workspace id.
    pub fn error_for(ws_id: &str, message: String) -> Self {
        let mut s = Self::error(message);
        s.ws_id = ws_id.to_string();
        s
    }
}

fn emit_status(app: &AppHandle, status: EngineStatus) {
    // Ignore emit errors: a missing window during shutdown is not fatal.
    let _ = app.emit("engine-status", status);
}

/// Return the current engine status so the frontend pill can seed itself even if
/// it mounted after the one-time `engine-status` "ready" emit. Serializes to the
/// frontend contract: `{ status, interpreter, version, message }`.
#[tauri::command]
pub fn get_engine_status(
    state: State<'_, std::sync::Arc<crate::instances::Instances>>,
) -> EngineStatus {
    state
        .focused_engine()
        .map(|e| e.current_status())
        .unwrap_or_else(|| EngineStatus::provisioning_for(""))
}

/// All live engines' current statuses (each carries its `wsId`). Lets the switcher
/// seed per-tab dots on mount / after a reload.
#[tauri::command]
pub fn get_engine_statuses(
    instances: State<'_, std::sync::Arc<crate::instances::Instances>>,
) -> Vec<EngineStatus> {
    instances.all_statuses()
}

/// True when `engine_dir` is a bundled, self-contained interpreter (engine-dist)
/// rather than the dev tree (which has a `.venv`).
pub fn is_bundled_engine(engine_dir: &Path) -> bool {
    engine_dir.join("bin/python3").is_file() || engine_dir.join("python.exe").is_file()
}

/// Choose the engine dir from candidate inputs (pure, unit-testable): the bundled
/// `engine-dist` under the resource dir when it holds a *real* self-contained
/// interpreter, else the dev fallback (`../engine`, live source).
///
/// The bundle must pass [`is_bundled_engine`], not merely exist: `engine-dist`
/// is entirely gitignored (absent in a fresh clone; built only in CI / by
/// `build-engine-dist.sh`), so in dev the directory is missing or holds a stale
/// local build. Anything short of a real interpreter must fall through to the
/// live dev checkout — otherwise the app silently runs
/// whatever frozen engine happens to sit there, which can lag the source after a
/// feature merge and 404 its new RPC methods.
pub fn pick_engine_dir(resource_dir: Option<PathBuf>, dev_fallback: PathBuf) -> PathBuf {
    if let Some(rd) = resource_dir {
        let bundled = rd.join("engine-dist");
        if is_bundled_engine(&bundled) {
            return bundled;
        }
    }
    dev_fallback
}

/// Pure resolver core (no `AppHandle`) so dev/bundled/override selection is
/// testable. Precedence: `SOLIDIFAI_ENGINE_DIR` override > bundled resource > dev sibling.
pub fn resolve_engine_dir_from(
    env_override: Option<String>,
    resource_dir: Option<PathBuf>,
    dev_fallback: PathBuf,
) -> Result<PathBuf, String> {
    if let Some(dir) = env_override {
        let p = PathBuf::from(&dir);
        return p
            .canonicalize()
            .map_err(|e| format!("SOLIDIFAI_ENGINE_DIR ({dir}) is not accessible: {e}"));
    }
    let chosen = pick_engine_dir(resource_dir, dev_fallback);
    chosen
        .canonicalize()
        .map_err(|e| format!("engine dir not found at {}: {e}", chosen.display()))
}

/// `engine` release index. Repo slug matches tauri.conf's updater endpoint.
const ENGINE_INDEX_URL: &str =
    "https://github.com/itsJeremyMax/solidifai/releases/download/engine/solidifai-engine-index.json";

/// Resolve the engine dir for the running app.
///
/// Env override and dev builds keep the original behavior (dev tree / bundled
/// `engine-dist` resource). A real pin resolves through the content-addressed
/// cache so app updates can ship engine-less: cache-hit, else seed from the
/// installer-bundled engine, else fetch the pinned engine.
pub fn resolve_engine_dir(app: &AppHandle) -> Result<PathBuf, String> {
    resolve_engine_dir_status(app, None)
}

/// [`resolve_engine_dir`] with an optional [`EngineState`] to report download
/// progress through. With a state, progress goes through `set_status` so it
/// carries the workspace id and persists as `last_status` (a late-mounting pill
/// or a webview reload seeds with live progress); without one (the provisioning
/// interpreter fallback has no state) it falls back to a bare emit.
fn resolve_engine_dir_status(
    app: &AppHandle,
    state: Option<&EngineState>,
) -> Result<PathBuf, String> {
    let pin = EnginePin::embedded();
    if std::env::var("SOLIDIFAI_ENGINE_DIR").is_ok() || pin.is_dev() {
        return resolve_engine_dir_from(
            std::env::var("SOLIDIFAI_ENGINE_DIR").ok(),
            app.path().resource_dir().ok(),
            PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../engine")),
        );
    }

    let app_data = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("no app data dir: {e}"))?;
    let cache = EngineCache::new(&app_data);
    let bundle = app
        .path()
        .resource_dir()
        .ok()
        .map(|r| r.join("engine-dist"))
        .filter(|d| d.is_dir());
    let pubkey = updater_pubkey()?;
    // The download reports every 64KB read (thousands of emits for a full
    // archive), so throttle that byte stream; the final report (done == total)
    // always goes out. Phase transitions (verify/install) are rare and always
    // emit immediately so the pill flips off "100%" the instant bytes land.
    let mut last_emit: Option<std::time::Instant> = None;
    let mut emit = |p: engine_fetch::Progress| {
        let status = match p {
            engine_fetch::Progress::Downloading { done, total } => {
                let now = std::time::Instant::now();
                let due = last_emit
                    .is_none_or(|t| now.duration_since(t) >= std::time::Duration::from_millis(100));
                if !due && total != Some(done) {
                    return;
                }
                last_emit = Some(now);
                EngineStatus::updating(done, total)
            }
            engine_fetch::Progress::Verifying => EngineStatus::updating_phase("Verifying engine"),
            engine_fetch::Progress::Installing => EngineStatus::updating_phase("Installing engine"),
        };
        match state {
            Some(s) => s.set_status(app, status),
            None => emit_status(app, status),
        }
    };
    resolve_cached_engine_dir(
        &cache,
        &pin,
        &current_platform(),
        bundle.as_deref(),
        &pubkey,
        &mut emit,
    )
}

/// The stable MCP launcher path when a cached engine is in use (real pin). External
/// agent configs point here so they survive engine swaps. `None` in dev, so the
/// caller keeps its existing interpreter resolution.
pub fn mcp_launcher(app: &AppHandle) -> Option<String> {
    if EnginePin::embedded().is_dev() {
        return None;
    }
    let app_data = app.path().app_data_dir().ok()?;
    let cache = EngineCache::new(&app_data);
    // Deterministic path, returned even before any engine is installed: the shim
    // execs whatever `current` points at, so agent configs stay valid across
    // engine swaps and a first launch never falls back to a blocking in-command
    // fetch (or, offline, an empty interpreter path). Written best-effort so the
    // file exists as early as possible.
    let _ = cache.write_launcher();
    Some(cache.launcher().to_string_lossy().into_owned())
}

fn current_platform() -> String {
    let os = match std::env::consts::OS {
        "macos" => "darwin",
        other => other,
    };
    format!("{os}-{}", std::env::consts::ARCH)
}

fn updater_pubkey() -> Result<String, String> {
    let conf: serde_json::Value = serde_json::from_str(include_str!("../tauri.conf.json"))
        .map_err(|e| format!("tauri.conf.json: {e}"))?;
    conf["plugins"]["updater"]["pubkey"]
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| "updater pubkey missing in tauri.conf.json".to_string())
}

/// Serializes engine resolution process-wide. Every workspace tab has its own
/// supervisor thread and they share one cache; without this, two first opens
/// during a seed/fetch could interleave installs and clobber a just-installed
/// engine. The waiter re-checks the cache under the lock and becomes a hit.
static RESOLVE_LOCK: Mutex<()> = Mutex::new(());

/// cache-hit -> seed-from-bundle -> fetch. Pure over its inputs (the fetch is the
/// only side-effecting branch and is exercised only in real release builds).
fn resolve_cached_engine_dir(
    cache: &EngineCache,
    pin: &EnginePin,
    platform: &str,
    bundle: Option<&Path>,
    pubkey: &str,
    on_progress: &mut dyn FnMut(engine_fetch::Progress),
) -> Result<PathBuf, String> {
    let _guard = RESOLVE_LOCK.lock();
    if cache.is_ready(&pin.manifest_hash) {
        cache.gc(&[&pin.manifest_hash]);
        return Ok(cache.engine_dir(&pin.manifest_hash));
    }
    if let Some(bundle) = bundle {
        match seed_from_bundle(cache, pin, platform, bundle) {
            Ok(dir) => {
                cache.gc(&[&pin.manifest_hash]);
                return Ok(dir);
            }
            // Fall through to a network fetch if the bundle is absent/mismatched.
            Err(e) => eprintln!("engine seed from bundle failed ({e}); fetching"),
        }
    }
    let current_dir = cache.current_dir();
    let current_rev = current_dir.as_deref().and_then(EngineCache::rev_of);
    let dir = engine_fetch::ensure(
        &engine_fetch::HttpTransport::default(),
        cache,
        ENGINE_INDEX_URL,
        pin,
        platform,
        current_rev.as_deref(),
        current_dir.as_deref(),
        pubkey,
        on_progress,
    )
    .map_err(|e| {
        // Full chain to the log; the status pill gets a short human message. A
        // failed open is retried on the next open_workspace (workspaces.rs), so
        // point the user there for network errors.
        tracing::warn!("engine fetch failed: {e:#}");
        // Walk the whole chain: a mid-body network drop surfaces as an io::Error
        // whose source is the reqwest error, not a top-level reqwest::Error.
        if e.chain().any(|c| c.is::<reqwest::Error>()) {
            "Couldn't download the engine. Check your connection and reopen the workspace to retry."
                .to_string()
        } else {
            format!("engine install failed: {e}")
        }
    })?;
    // Sweep superseded engines + stale staging/archives, keeping the pinned one
    // (gc always protects `current`, the next delta base). Best-effort.
    cache.gc(&[&pin.manifest_hash]);
    Ok(dir)
}

/// Copy the installer-bundled engine into the cache (offline first-run), verifying
/// it matches the pin before trusting the copy.
fn seed_from_bundle(
    cache: &EngineCache,
    pin: &EnginePin,
    platform: &str,
    bundle: &Path,
) -> anyhow::Result<PathBuf> {
    // Hashing the bundle into a manifest verifies it: a tampered/extra file changes
    // manifest_hash, which must match the pin embedded in the signed app binary.
    let manifest = Manifest::build_from_dir(bundle, &pin.engine_rev, platform)?;
    if manifest.manifest_hash != pin.manifest_hash {
        anyhow::bail!("bundled engine does not match pin");
    }
    // Unique staging per attempt; verify the copy before installing (the copy is
    // not atomic, so a torn tree must never be finalized as ready).
    let staging = cache.staging_dir(&pin.manifest_hash);
    let result = copy_tree(bundle, &staging)
        .map_err(anyhow::Error::from)
        .and_then(|_| cache.install_verified(&staging, &manifest));
    if result.is_err() {
        let _ = std::fs::remove_dir_all(&staging);
    }
    result
}

fn copy_tree(src: &Path, dst: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let from = entry.path();
        let to = dst.join(entry.file_name());
        let ft = entry.file_type()?;
        // Skip OS droppings (.DS_Store et al): the manifest walker ignores them,
        // so copying one into staging would fail install_verified's exact-tree
        // check and needlessly push an offline first run onto the network path.
        if ft.is_file() && engine_pack::manifest::is_junk_file(&entry.file_name().to_string_lossy())
        {
            continue;
        }
        if ft.is_symlink() {
            #[cfg(unix)]
            std::os::unix::fs::symlink(std::fs::read_link(&from)?, &to)?;
            #[cfg(windows)]
            {
                let _ = std::fs::copy(&from, &to);
            }
        } else if ft.is_dir() {
            copy_tree(&from, &to)?;
        } else {
            std::fs::copy(&from, &to)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let mode = std::fs::metadata(&from)?.permissions().mode();
                std::fs::set_permissions(&to, std::fs::Permissions::from_mode(mode))?;
            }
        }
    }
    Ok(())
}

/// Locate the `uv` binary: PATH, then `~/.local/bin/uv`, then `/opt/homebrew/bin/uv`.
pub fn resolve_uv() -> Result<PathBuf, String> {
    // 1) PATH lookup via `command -v`-style probe (works without extra crates).
    if let Some(p) = which_on_path("uv") {
        return Ok(p);
    }
    // 2) Well-known install locations.
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(home) = dirs::home_dir() {
        candidates.push(home.join(".local/bin/uv"));
    }
    candidates.push(PathBuf::from("/opt/homebrew/bin/uv"));
    for c in candidates {
        if c.is_file() {
            return Ok(c);
        }
    }
    Err("could not find the `uv` binary on PATH, ~/.local/bin, or /opt/homebrew/bin".to_string())
}

/// Minimal PATH search for an executable, avoiding an extra dependency.
pub(crate) fn which_on_path(name: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(name);
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

/// Path to the engine interpreter: the bundled standalone interpreter for an
/// `engine-dist` bundle, else the dev venv interpreter.
pub fn interpreter_path(engine_dir: &Path) -> PathBuf {
    if is_bundled_engine(engine_dir) {
        if cfg!(windows) {
            engine_dir.join("python.exe")
        } else {
            engine_dir.join("bin/python3")
        }
    } else if cfg!(windows) {
        engine_dir.join(".venv/Scripts/python.exe")
    } else {
        engine_dir.join(".venv/bin/python")
    }
}

/// Run `uv sync` in `engine_dir` to provision/refresh the virtualenv. Idempotent.
fn uv_sync(uv: &Path, engine_dir: &Path) -> Result<(), String> {
    let output = quiet_command(uv)
        .arg("sync")
        .current_dir(engine_dir)
        .output()
        .map_err(|e| format!("failed to run `uv sync`: {e}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "`uv sync` failed (status {}): {}",
            output.status,
            stderr.trim()
        ));
    }
    Ok(())
}

/// Read the Python + build123d versions via the engine interpreter and format a
/// compact pill string, e.g. `"py3.12 · build123d 0.10.0"`. The probe prints
/// `"<pyMaj>.<pyMin> <build123dVersion>"`, which we reformat in Rust to avoid
/// embedding non-ASCII in the `-c` argument.
fn engine_version(interpreter: &Path) -> Result<String, String> {
    let output = quiet_command(interpreter)
        .args([
            "-c",
            "import sys, build123d; print(f'{sys.version_info.major}.{sys.version_info.minor} {build123d.__version__}')",
        ])
        .output()
        .map_err(|e| format!("failed to run interpreter for version probe: {e}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("could not import build123d: {}", stderr.trim()));
    }
    let out = String::from_utf8_lossy(&output.stdout);
    let mut parts = out.split_whitespace();
    let (py, b123d) = (parts.next().unwrap_or(""), parts.next().unwrap_or(""));
    if py.is_empty() || b123d.is_empty() {
        return Err("version probe returned empty output".to_string());
    }
    Ok(format!("py{py} \u{00b7} build123d {b123d}"))
}

/// The RPC contract revision this host shell was built against. The engine reports
/// its own value from `solidifai_engine/protocol.py`; a mismatch means the engine
/// the app loaded is out of step with this shell (typically a stale `engine-dist`
/// bundle that predates a feature). Bump this AND `PROTOCOL_VERSION` on the engine
/// side together whenever the RPC method set changes.
const EXPECTED_ENGINE_PROTOCOL: u32 = 12;

/// Read the engine's reported protocol version. A bundle that predates the
/// constant (or can't import the engine) prints `0`, which `check_protocol` then
/// surfaces as "stale" rather than letting the probe itself fail obscurely.
fn engine_protocol(interpreter: &Path) -> Result<u32, String> {
    let output = quiet_command(interpreter)
        .args([
            "-c",
            "try:\n from solidifai_engine.protocol import PROTOCOL_VERSION as P\nexcept Exception:\n P = 0\nprint(P)",
        ])
        .output()
        .map_err(|e| format!("failed to run interpreter for protocol probe: {e}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("engine protocol probe failed: {}", stderr.trim()));
    }
    let out = String::from_utf8_lossy(&output.stdout);
    out.trim().parse::<u32>().map_err(|_| {
        format!(
            "engine protocol probe returned non-integer: {:?}",
            out.trim()
        )
    })
}

/// Compare the engine's protocol against what this shell expects, returning a
/// loud, actionable error on mismatch. Pure so the message logic is unit-tested.
fn check_protocol(engine: u32, expected: u32) -> Result<(), String> {
    if engine == expected {
        return Ok(());
    }
    let why = if engine < expected {
        "the engine is older than this app build (a stale engine-dist bundle?)"
    } else {
        "the engine is newer than this app build"
    };
    Err(format!(
        "engine/app protocol mismatch: engine reports {engine}, app expects \
         {expected}; {why}. Rebuild the bundle (scripts/build-engine-dist.sh) \
         or restart `tauri dev` against the live engine."
    ))
}

/// Spawn the engine RPC server process.
///
/// `<py> -m solidifai_engine --socket <sock> --artifacts <artifacts> [--model <model>]`,
/// cwd = engine dir. When `model_path` is set, the engine loads + runs that model on
/// startup so the workspace's durable model is live as soon as the engine is ready.
/// `interpreter`/`engine_dir` come from [`resolve_engine_dir`], so this runs the
/// bundled `engine-dist` interpreter in release builds and the dev venv otherwise.
fn spawn_engine_server(
    interpreter: &Path,
    engine_dir: &Path,
    socket_path: &str,
    artifacts_dir: &str,
    config_dir: &Path,
    app_version: &str,
    model_path: Option<&str>,
) -> Result<Child, String> {
    let mut cmd = quiet_command(interpreter);
    cmd.args([
        "-m",
        "solidifai_engine",
        "--socket",
        socket_path,
        "--artifacts",
        artifacts_dir,
    ]);
    if let Some(model) = model_path {
        cmd.args(["--model", model]);
    }
    // Host owns the canonical config dir; the engine reads/writes the same global
    // library + destinations from it (one spawn covers MCP bridges via the socket).
    cmd.env("SOLIDIFAI_CONFIG_DIR", config_dir);
    // Propagate the single-sourced app version (package.json -> tauri.conf ->
    // package_info) so the engine can report the true release, e.g. in report_issue.
    cmd.env("SOLIDIFAI_APP_VERSION", app_version);
    // Let the engine reach the control channel so it can delegate profile writes.
    if let Some(ctl) = crate::control::socket_path() {
        cmd.env("SOLIDIFAI_CONTROL_SOCK", ctl);
    }
    cmd.current_dir(engine_dir)
        .spawn()
        .map_err(|e| format!("failed to spawn engine server: {e}"))
}

/// The app-global engine environment: the resolved engine source dir, its venv
/// interpreter, and the build123d version string. This is workspace-independent —
/// only the socket/artifacts differ per workspace — so it is resolved once and
/// cached on [`EngineState`].
struct ResolvedEnv {
    engine_dir: PathBuf,
    interpreter: PathBuf,
    interpreter_str: String,
    version: String,
}

/// Resolve (and cache) the engine environment: locate the engine dir, run
/// `uv sync`, probe the build123d version. Subsequent calls reuse the cached
/// interpreter+version on [`EngineState`] and skip `uv sync` / the version probe,
/// since the engine venv is app-global (only socket/artifacts are per-workspace).
fn resolve_env(state: &Arc<EngineState>, app: &AppHandle) -> Result<ResolvedEnv, String> {
    let engine_dir = resolve_engine_dir_status(app, Some(state))?;

    // Fast path: env already resolved on a previous workspace open. Skip the
    // expensive `uv sync` + version probe.
    if let (Some(interpreter_str), Some(version)) = (
        state.interpreter.lock().clone(),
        state.version.lock().clone(),
    ) {
        return Ok(ResolvedEnv {
            interpreter: PathBuf::from(&interpreter_str),
            engine_dir,
            interpreter_str,
            version,
        });
    }

    let interpreter = interpreter_path(&engine_dir);
    // The bundled engine ships a frozen venv; only the dev tree needs `uv sync`.
    if !is_bundled_engine(&engine_dir) {
        let uv = resolve_uv()?;
        uv_sync(&uv, &engine_dir)?;
    }
    if !interpreter.is_file() {
        return Err(format!(
            "engine interpreter missing after provisioning: {}",
            interpreter.display()
        ));
    }

    let version = engine_version(&interpreter)?;

    // Reject an engine whose RPC contract doesn't match this shell before we
    // spawn it, so a stale bundle fails loudly here instead of 404-ing methods
    // at call time. Skipped only via the cached fast path above (same engine).
    check_protocol(engine_protocol(&interpreter)?, EXPECTED_ENGINE_PROTOCOL)?;

    let interpreter_str = interpreter.to_string_lossy().into_owned();

    // Cache the app-global env so future opens are fast.
    *state.interpreter.lock() = Some(interpreter_str.clone());
    *state.version.lock() = Some(version.clone());

    Ok(ResolvedEnv {
        engine_dir,
        interpreter,
        interpreter_str,
        version,
    })
}

/// Full startup sequence, run on a background thread so the window paints first.
///
/// Resolves env (cached after the first time) → emits `provisioning` →
/// `uv sync` + version probe (first open only) → emits `ready` → spawns the engine
/// and supervises it (one restart on unexpected exit). All failures are surfaced
/// as `engine-status{error}` events.
///
/// `socket_path` and `artifacts_dir` MUST match what the provisioner wrote into the
/// workspace MCP config, so external agents and the engine agree on the socket.
/// `model_path`, when set, is the workspace's `model.py`; the engine loads + runs it
/// on startup *if the file exists*, so the durable model is live as soon as the
/// engine is ready. A fresh workspace ships none — it's created on the agent's
/// first build — so the viewport shows its empty state until then.
///
/// This is reusable across workspace switches: `open_workspace` calls
/// [`EngineState::kill`] (which makes the prior supervisor thread exit) and then
/// spawns a fresh call to this for the new socket/artifacts.
pub fn start_supervised(
    app: AppHandle,
    state: Arc<EngineState>,
    socket_path: String,
    artifacts_dir: String,
    model_path: Option<String>,
    generation: u64,
) {
    // Already superseded before we even started (a second kill+restart of this
    // workspace claimed a newer generation): stop before touching status or env.
    if state.current_generation() != generation {
        return;
    }
    state.set_status(&app, EngineStatus::provisioning());

    let env = match resolve_env(&state, &app) {
        Ok(e) => e,
        Err(e) => {
            // Don't clobber a newer supervisor's status with our stale failure.
            if state.current_generation() == generation {
                state.set_status(&app, EngineStatus::error(e));
            }
            return;
        }
    };
    let ResolvedEnv {
        engine_dir,
        interpreter,
        interpreter_str,
        version,
    } = env;

    // The active socket for this workspace (rpc proxy reads this).
    *state.socket_path.lock() = Some(socket_path.clone());

    // Canonical app config dir, handed to the engine so it shares the host's
    // global library + destinations files.
    let config_dir = match app.path().app_config_dir() {
        Ok(d) => d,
        Err(e) => {
            state.set_status(&app, EngineStatus::error(format!("config dir: {e}")));
            return;
        }
    };

    // `generation` was claimed by our spawner via `claim_generation()`. If a
    // later `kill()` or a newer supervisor bumps it, this thread stops instead
    // of restarting or clobbering the next supervisor's engine.

    // Spawn + supervise. Try once, and restart a single time on unexpected exit.
    let mut attempts = 0u32;
    let app_version = app.package_info().version.to_string();
    loop {
        // A switch/shutdown happened while we were getting here: stop.
        if state.current_generation() != generation {
            return;
        }
        attempts += 1;
        match spawn_engine_server(
            &interpreter,
            &engine_dir,
            &socket_path,
            &artifacts_dir,
            &config_dir,
            &app_version,
            model_path.as_deref(),
        ) {
            Ok(child) => {
                // Wrap immediately so any bail-out before the child is stored reaps it.
                let child = ChildGuard::new(child);
                // Only claim the child slot if we're still the current generation;
                // otherwise a newer supervisor owns it — let `child` drop and reap ours.
                let mut guard = state.child.lock();
                if state.current_generation() != generation {
                    return;
                }
                *guard = Some(child.into_child());
                drop(guard);
                // Ready once the process is up; the socket appears shortly after.
                state.set_status(
                    &app,
                    EngineStatus::ready(interpreter_str.clone(), version.clone()),
                );
            }
            Err(e) => {
                state.set_status(&app, EngineStatus::error(e));
                return;
            }
        }

        // Block until the child exits (or is taken/killed for shutdown).
        let exit = wait_for_child(&state.child);

        // If our generation is stale, a switch/shutdown took the child: stop
        // silently (don't emit an error or restart for the old workspace).
        if state.current_generation() != generation {
            return;
        }

        match exit {
            // Taken out from under us (kill() on shutdown): stop supervising.
            ChildExit::Gone => return,
            ChildExit::Exited(status) => {
                if attempts >= 2 {
                    state.set_status(
                        &app,
                        EngineStatus::error(format!(
                            "engine exited again ({status}); giving up after one restart"
                        )),
                    );
                    return;
                }
                state.set_status(
                    &app,
                    EngineStatus::error(format!(
                        "engine exited unexpectedly ({status}); restarting once"
                    )),
                );
                // Loop to restart.
            }
        }
    }
}

/// Reaps the engine child (kill + wait) on drop unless `into_child` takes it out
/// first. The supervisor wraps the child the moment it spawns, so a bail-out before
/// it's stored — a stale-generation switch or a panic — can't leak an un-killed
/// process (`std::process::Child` does not kill on drop).
struct ChildGuard(Option<Child>);

impl ChildGuard {
    fn new(child: Child) -> Self {
        Self(Some(child))
    }

    /// Take the child out, defusing the guard — the caller owns reaping from here.
    fn into_child(mut self) -> Child {
        self.0.take().expect("ChildGuard child already taken")
    }
}

impl Drop for ChildGuard {
    fn drop(&mut self) {
        if let Some(mut child) = self.0.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

enum ChildExit {
    /// The child was removed from state (shutdown) — stop supervising.
    Gone,
    /// The child exited on its own with the given status string.
    Exited(String),
}

/// Poll the managed child until it exits or is removed from state by `kill()`.
fn wait_for_child(child: &Arc<Mutex<Option<Child>>>) -> ChildExit {
    loop {
        {
            let mut guard = child.lock();
            match guard.as_mut() {
                None => return ChildExit::Gone,
                Some(c) => match c.try_wait() {
                    Ok(Some(status)) => {
                        // Clear the slot so kill() on shutdown is a no-op.
                        *guard = None;
                        return ChildExit::Exited(format!("{status}"));
                    }
                    Ok(None) => { /* still running */ }
                    Err(e) => {
                        *guard = None;
                        return ChildExit::Exited(format!("wait failed: {e}"));
                    }
                },
            }
        }
        std::thread::sleep(std::time::Duration::from_millis(300));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `quiet_command` must behave exactly like a plain `Command` apart from the
    /// Windows creation flags (cross-platform dispatch check).
    #[test]
    fn quiet_command_spawns_like_a_plain_command() {
        let (shell, flag) = if cfg!(windows) {
            ("cmd", "/C")
        } else {
            ("sh", "-c")
        };
        let status = quiet_command(shell)
            .args([flag, "exit 0"])
            .status()
            .expect("quiet_command spawns");
        assert!(status.success());
    }

    #[test]
    fn resolve_engine_dir_from_override_then_dev_sibling() {
        let tmp = std::env::temp_dir();
        let resolved = resolve_engine_dir_from(
            Some(tmp.to_string_lossy().into_owned()),
            None,
            PathBuf::from("/nonexistent-dev-engine"),
        )
        .expect("env override resolves");
        assert_eq!(resolved, tmp.canonicalize().unwrap());

        // No override, no resource: the dev sibling `<manifest>/../engine` resolves.
        let dir = resolve_engine_dir_from(
            None,
            None,
            PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../engine")),
        )
        .expect("engine dir resolves in dev checkout");
        assert!(
            dir.join("pyproject.toml").is_file(),
            "expected engine/pyproject.toml"
        );
    }

    #[test]
    fn pick_engine_dir_prefers_real_bundle_but_stub_falls_back() {
        let dev = std::env::temp_dir().join("dev-engine-fallback");

        // A *real* bundle (engine-dist with a standalone interpreter) is picked.
        let tmp = std::env::temp_dir().join(format!("eng-pick-{}", std::process::id()));
        let bundled = tmp.join("engine-dist");
        std::fs::create_dir_all(bundled.join("bin")).unwrap();
        std::fs::write(bundled.join("bin/python3"), b"#!/bin/sh\n").unwrap();
        assert_eq!(pick_engine_dir(Some(tmp.clone()), dev.clone()), bundled);

        // No resource dir -> dev fallback.
        assert_eq!(pick_engine_dir(None, dev.clone()), dev);

        // A *stub* engine-dist (dir exists but no interpreter) must fall back to
        // the live dev checkout, not silently run an empty/frozen bundle.
        let stub_root = std::env::temp_dir().join(format!("eng-stub-{}", std::process::id()));
        std::fs::create_dir_all(stub_root.join("engine-dist")).unwrap();
        assert_eq!(pick_engine_dir(Some(stub_root.clone()), dev.clone()), dev);

        // Resource dir present but no engine-dist subdir at all -> dev fallback.
        let empty = std::env::temp_dir().join(format!("eng-empty-{}", std::process::id()));
        std::fs::create_dir_all(&empty).unwrap();
        assert_eq!(pick_engine_dir(Some(empty.clone()), dev.clone()), dev);

        std::fs::remove_dir_all(&tmp).ok();
        std::fs::remove_dir_all(&stub_root).ok();
        std::fs::remove_dir_all(&empty).ok();
    }

    #[test]
    fn check_protocol_matches_and_flags_drift() {
        // Exact match is the only OK case.
        assert!(check_protocol(EXPECTED_ENGINE_PROTOCOL, EXPECTED_ENGINE_PROTOCOL).is_ok());

        // A stale (older) engine names the bundle as the likely culprit.
        let stale = check_protocol(0, 1).unwrap_err();
        assert!(stale.contains("older"), "got: {stale}");
        assert!(
            stale.contains("engine-dist"),
            "should suggest a rebuild: {stale}"
        );

        // A newer engine than the shell is also a mismatch (shell out of date).
        assert!(check_protocol(2, 1).is_err());
    }

    #[test]
    fn expected_protocol_matches_engine_source() {
        // The bump-both-together contract (see EXPECTED_ENGINE_PROTOCOL) is easy to
        // miss from the engine side, where this crate isn't touched. Read the live
        // engine source so drift fails in CI instead of at app startup.
        let src = std::fs::read_to_string(
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../engine/solidifai_engine/protocol.py"),
        )
        .expect("engine protocol.py should exist in the repo checkout");
        let engine_version: u32 = src
            .lines()
            .find_map(|l| l.strip_prefix("PROTOCOL_VERSION = "))
            .expect("protocol.py should define PROTOCOL_VERSION")
            .trim()
            .parse()
            .expect("PROTOCOL_VERSION should be an integer");
        assert_eq!(
            engine_version, EXPECTED_ENGINE_PROTOCOL,
            "engine protocol.py and EXPECTED_ENGINE_PROTOCOL must be bumped together"
        );
    }

    #[test]
    fn is_bundled_engine_detects_standalone_interpreter() {
        let tmp = std::env::temp_dir().join(format!("eng-bundled-{}", std::process::id()));
        let bin = tmp.join("bin");
        std::fs::create_dir_all(&bin).unwrap();
        assert!(!is_bundled_engine(&tmp)); // no interpreter yet
        std::fs::write(bin.join("python3"), b"#!/bin/sh\n").unwrap();
        assert!(is_bundled_engine(&tmp));
        std::fs::remove_dir_all(&tmp).ok();
    }

    #[test]
    fn interpreter_path_dev_is_under_venv() {
        // A dir with no standalone interpreter is treated as the dev tree.
        let p = interpreter_path(Path::new("/tmp/definitely-not-bundled-engine"));
        assert!(p.ends_with(".venv/bin/python") || p.ends_with(".venv/Scripts/python.exe"));
    }

    #[test]
    fn interpreter_path_bundled_uses_standalone() {
        let tmp = std::env::temp_dir().join(format!("eng-interp-{}", std::process::id()));
        let bin = tmp.join("bin");
        std::fs::create_dir_all(&bin).unwrap();
        std::fs::write(bin.join("python3"), b"#!/bin/sh\n").unwrap();
        let p = interpreter_path(&tmp);
        assert!(p.ends_with("bin/python3"), "got {p:?}");
        std::fs::remove_dir_all(&tmp).ok();
    }

    /// `kill()` bumps the supervisor generation so a stale supervisor thread (from
    /// a previous workspace) bails instead of restarting/clobbering the new one.
    #[test]
    fn kill_bumps_generation() {
        let state = EngineState::default();
        let g0 = state.current_generation();
        state.kill(); // no child stored; still bumps the generation.
        let g1 = state.current_generation();
        assert_eq!(g1, g0 + 1, "kill must advance the supervisor generation");
        state.kill();
        assert_eq!(state.current_generation(), g0 + 2);
    }

    /// `claim_generation()` bumps AND returns the new value in one atomic step:
    /// of two racing kill+restart opens, exactly one supervisor token matches the
    /// final generation, so exactly one supervisor survives its checks.
    #[test]
    fn claim_generation_returns_the_new_current_value() {
        let state = EngineState::default();
        let g1 = state.claim_generation();
        assert_eq!(state.current_generation(), g1);
        let g2 = state.claim_generation();
        assert!(g2 > g1, "claims must be strictly increasing");
        assert_eq!(
            state.current_generation(),
            g2,
            "only the newest claim is current"
        );
    }

    /// A ChildGuard reaps its process on drop, but `into_child` defuses it so the
    /// stored child outlives the guard — this is what keeps the supervisor's
    /// spawn->store window from leaking an engine on a stale-generation bail.
    #[test]
    fn child_guard_reaps_on_drop_and_into_child_defuses() {
        use std::process::Command;

        // into_child hands back a still-running child (the guard did not reap it).
        let live = Command::new("sleep")
            .arg("30")
            .spawn()
            .expect("spawn sleep");
        let mut raw = ChildGuard::new(live).into_child();
        assert!(
            raw.try_wait().unwrap().is_none(),
            "into_child child should still run"
        );
        let _ = raw.kill();
        let _ = raw.wait();

        // Dropping a ChildGuard kills + waits the child synchronously.
        let doomed = Command::new("sleep")
            .arg("30")
            .spawn()
            .expect("spawn sleep");
        let pid = doomed.id();
        drop(ChildGuard::new(doomed));
        let alive = Command::new("kill")
            .arg("-0")
            .arg(pid.to_string())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        assert!(!alive, "ChildGuard drop must kill + reap the child");
    }

    #[test]
    fn engine_status_serializes_to_contract_shape() {
        let s = EngineStatus::ready("/py".into(), "0.10.0".into());
        let v = serde_json::to_value(&s).unwrap();
        assert_eq!(v["status"], "ready");
        assert_eq!(v["interpreter"], "/py");
        assert_eq!(v["version"], "0.10.0");
        assert!(v["message"].is_null());
        assert_eq!(v["wsId"], ""); // placeholder; set_status stamps the real id before emit

        let e = EngineStatus::error("boom".into());
        let v = serde_json::to_value(&e).unwrap();
        assert_eq!(v["status"], "error");
        assert_eq!(v["message"], "boom");
        assert!(v["interpreter"].is_null());
    }

    #[test]
    fn engine_status_payload_carries_ws_id() {
        let s = EngineStatus::ready_for("/ws/a", "/py".into(), "0.6".into());
        let v = serde_json::to_value(&s).unwrap();
        assert_eq!(v["wsId"], "/ws/a");
        assert_eq!(v["status"], "ready");
        assert_eq!(v["version"], "0.6");
    }

    #[test]
    fn engine_state_defaults_to_provisioning() {
        let state = EngineState::default();
        let s = state.current_status();
        assert_eq!(s.status, "provisioning");
        assert!(s.version.is_none());
    }

    /// After storing a `ready(...)`, the value `get_engine_status` returns (i.e.
    /// `current_status()`) reflects the latest status, version included.
    #[test]
    fn current_status_returns_last_stored_ready() {
        let state = EngineState::default();
        *state.last_status.lock() = EngineStatus::ready("/py".into(), "0.10.0".into());

        let s = state.current_status();
        assert_eq!(s.status, "ready");
        assert_eq!(s.interpreter.as_deref(), Some("/py"));
        assert_eq!(s.version.as_deref(), Some("0.10.0"));
        assert!(s.message.is_none());

        // And it still serializes to the frontend contract shape.
        let v = serde_json::to_value(&s).unwrap();
        assert_eq!(v["status"], "ready");
        assert_eq!(v["version"], "0.10.0");
    }

    fn fake_bundle(root: &Path) -> Manifest {
        use std::os::unix::fs::PermissionsExt;
        std::fs::create_dir_all(root.join("bin")).unwrap();
        std::fs::write(root.join("bin/python3"), b"#!/bin/sh\necho hi\n").unwrap();
        std::fs::set_permissions(
            root.join("bin/python3"),
            std::fs::Permissions::from_mode(0o755),
        )
        .unwrap();
        std::fs::write(root.join("lib.py"), b"x = 1").unwrap();
        Manifest::build_from_dir(root, "rev1", &current_platform()).unwrap()
    }

    fn pin_for(manifest: &Manifest) -> EnginePin {
        serde_json::from_str(&format!(
            r#"{{"engineRev":"{}","manifestHash":"{}"}}"#,
            manifest.engine_rev, manifest.manifest_hash
        ))
        .unwrap()
    }

    #[test]
    fn cached_resolver_seeds_from_bundle_then_hits_cache() {
        let tmp = tempfile::tempdir().unwrap();
        let bundle = tmp.path().join("engine-dist");
        let manifest = fake_bundle(&bundle);
        let pin = pin_for(&manifest);
        let cache = EngineCache::new(&tmp.path().join("app"));

        // cache empty -> seeds from the bundle (offline)
        let dir = resolve_cached_engine_dir(
            &cache,
            &pin,
            &current_platform(),
            Some(&bundle),
            "unused",
            &mut |_| {},
        )
        .unwrap();
        assert_eq!(dir, cache.engine_dir(&pin.manifest_hash));
        assert!(cache.is_ready(&pin.manifest_hash));
        assert!(EngineCache::interpreter_in(&dir).is_file());
        assert_eq!(EngineCache::rev_of(&dir).as_deref(), Some("rev1"));

        // second call is a pure cache hit (bundle not even consulted)
        let dir2 = resolve_cached_engine_dir(
            &cache,
            &pin,
            &current_platform(),
            None,
            "unused",
            &mut |_| {},
        )
        .unwrap();
        assert_eq!(dir2, dir);
    }

    #[test]
    fn seed_rejects_bundle_that_mismatches_pin() {
        let tmp = tempfile::tempdir().unwrap();
        let bundle = tmp.path().join("engine-dist");
        fake_bundle(&bundle);
        let wrong: EnginePin =
            serde_json::from_str(r#"{"engineRev":"rev1","manifestHash":"deadbeef"}"#).unwrap();
        let cache = EngineCache::new(&tmp.path().join("app"));
        assert!(seed_from_bundle(&cache, &wrong, &current_platform(), &bundle).is_err());
        assert!(!cache.is_ready("deadbeef"));
    }

    #[test]
    fn current_platform_is_os_arch() {
        let p = current_platform();
        assert!(p.contains('-'));
        assert!(
            !p.starts_with("macos"),
            "macos is normalized to darwin: {p}"
        );
    }

    #[test]
    fn engine_status_updating_carries_progress() {
        let v = serde_json::to_value(EngineStatus::updating(50, Some(100))).unwrap();
        assert_eq!(v["status"], "updating");
        assert_eq!(v["progress"], 0.5);
        // unknown total -> no fraction
        let v2 = serde_json::to_value(EngineStatus::updating(50, None)).unwrap();
        assert!(v2["progress"].is_null());
    }
}
