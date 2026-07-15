//! Newline-delimited JSON RPC client for the Python CAD engine.
//!
//! The engine listens on a local IPC endpoint (see `engine/solidifai_engine/server.py`
//! and `ipc.rs`: a UNIX socket on unix, loopback TCP behind a pointer file on
//! Windows). Each request is one JSON line `{"id":N,"method":..,"params":{..}}\n`;
//! each response is one JSON line `{"id":N,"ok":bool,"result"|"error":..}\n`.
//!
//! [`engine_call`] performs a full request/response round-trip and returns the engine's
//! `result` (as a JSON string) on success, or a clear error string. The framing helpers
//! ([`encode_request`] / [`parse_response`]) are split out so they can be unit-tested
//! without a live socket.

use std::io::{Read, Write};
use std::sync::atomic::{AtomicI64, Ordering};
use std::time::Duration;

use serde::Serialize;
use serde_json::Value;
use tauri::{AppHandle, Emitter, State};

use crate::instances::Instances;

/// Monotonic request id source. The engine echoes the id; we don't currently
/// pipeline on a single connection (each call opens its own stream), but a unique
/// id keeps responses self-describing and matches the MCP bridge's behaviour.
static NEXT_ID: AtomicI64 = AtomicI64::new(1);
const CLIENT_PROTOCOL: u32 = 13;
const CLIENT_CAPABILITIES: &[&str] = &[
    "build_brief_v2",
    "conformance",
    "operations",
    "readiness",
    "strict_export",
];

fn next_id() -> i64 {
    NEXT_ID.fetch_add(1, Ordering::Relaxed)
}

/// Encode a single RPC request as a newline-terminated JSON line.
///
/// Tauri-independent and pure so the line framing can be unit-tested.
pub fn encode_request(id: i64, method: &str, params: &Value) -> String {
    let req = serde_json::json!({
        "id": id,
        "method": method,
        "params": params,
        "client": {
            "protocol": CLIENT_PROTOCOL,
            "capabilities": CLIENT_CAPABILITIES,
        },
    });
    // `serde_json::to_string` never fails for a Value built from owned data.
    format!("{}\n", serde_json::to_string(&req).unwrap_or_default())
}

/// Parse a single response line into the engine's `result` (as a compact JSON
/// string) on success, or `Err(error_message)` on an `ok:false` envelope or
/// malformed line.
///
/// Tauri-independent and pure so the framing can be unit-tested.
pub fn parse_response(line: &str) -> Result<String, String> {
    let line = line.trim();
    if line.is_empty() {
        return Err("engine returned an empty response".to_string());
    }
    let resp: Value =
        serde_json::from_str(line).map_err(|e| format!("invalid engine response JSON: {e}"))?;

    if resp.get("ok").and_then(Value::as_bool) == Some(true) {
        // `result` may be any JSON value (string, object, ...). Re-serialize it so
        // the command layer always returns a JSON string to the frontend.
        let result = resp.get("result").cloned().unwrap_or(Value::Null);
        Ok(serde_json::to_string(&result).unwrap_or_else(|_| "null".to_string()))
    } else {
        let err = resp
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("engine returned an error")
            .to_string();
        Err(err)
    }
}

/// Connect to the engine socket at `sock`, send one `method`/`params` request, read
/// one response line, and return the engine `result` as a JSON string.
///
/// Returns a clear `Err(..)` string when the engine is unreachable (e.g. still
/// starting up) or reports an error, so the UI can surface "engine not ready yet"
/// without panicking.
pub fn engine_call(sock: &str, method: &str, params: Value) -> Result<String, String> {
    let mut stream = crate::ipc::connect(sock).map_err(|e| {
        format!(
            "engine not ready: cannot connect to {sock} ({e}); the engine may still be starting"
        )
    })?;
    // Bound the round-trip so a wedged engine can't hang a UI command forever.
    let _ = stream.set_read_timeout(Some(Duration::from_secs(30)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(10)));

    let line = encode_request(next_id(), method, &params);
    stream
        .write_all(line.as_bytes())
        .map_err(|e| format!("failed to send request to engine: {e}"))?;
    stream
        .flush()
        .map_err(|e| format!("failed to flush request to engine: {e}"))?;

    // Read until the first newline: the engine sends exactly one JSON line back.
    let mut buf: Vec<u8> = Vec::with_capacity(4096);
    let mut byte = [0u8; 1];
    loop {
        match stream.read(&mut byte) {
            Ok(0) => break, // EOF before newline.
            Ok(_) => {
                if byte[0] == b'\n' {
                    break;
                }
                buf.push(byte[0]);
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(format!("failed to read engine response: {e}")),
        }
    }

    if buf.is_empty() {
        return Err("engine closed the connection without responding".to_string());
    }
    let text = String::from_utf8_lossy(&buf).into_owned();
    parse_response(&text)
}

// -- Tauri command proxies --------------------------------------------------
//
// Thin wrappers that read the live socket path from managed state and forward to
// [`engine_call`]. They return the engine's `result` as a JSON string, or a clear
// error string when the engine is not ready / reports an error.
//
// Every proxy is `async`. Tauri runs *synchronous* commands on the **main
// thread**, so doing the blocking socket round-trip there froze the entire window
// (a spinning cursor) for as long as the engine took to rebuild — the freeze scaled
// with model complexity. As `async` commands they run off the main thread, and the
// blocking round-trip itself is pushed onto a blocking-pool thread via
// [`tauri::async_runtime::spawn_blocking`] — the same pattern `pick_directory` uses
// — so the UI run loop keeps pumping while the engine works.

/// Resolve the FOCUSED engine socket from the registry, or a clear not-ready error.
fn socket(state: &State<'_, std::sync::Arc<Instances>>) -> Result<String, String> {
    state
        .focused_socket()
        .ok_or_else(|| "engine not ready: the engine has not started yet".to_string())
}

/// Resolve the socket, then run one blocking [`engine_call`] off the main thread.
///
/// The socket is read synchronously (cheap, no I/O) *before* the await, so the
/// non-`Send` [`State`] borrow never crosses an await point; only the owned socket
/// path + params move onto the blocking-pool thread.
async fn call(
    state: &State<'_, std::sync::Arc<Instances>>,
    method: &'static str,
    params: Value,
) -> Result<String, String> {
    let sock = socket(state)?;
    tauri::async_runtime::spawn_blocking(move || engine_call(&sock, method, params))
        .await
        .map_err(|e| format!("engine call task failed: {e}"))?
}

/// Crate-internal: run one RPC against a SPECIFIC engine socket, off-thread.
///
/// Lets [`crate::workspaces`] route metadata writes through the TARGET workspace's
/// own live engine (the single writer of its workspace.json while open) instead of
/// the focused engine — editing an open-but-not-focused workspace must not write
/// into the focused workspace's file.
pub(crate) async fn engine_rpc_on(
    sock: String,
    method: &'static str,
    params: Value,
) -> Result<String, String> {
    tauri::async_runtime::spawn_blocking(move || engine_call(&sock, method, params))
        .await
        .map_err(|e| format!("engine call task failed: {e}"))?
}

/// `model-updated` payload — mirrors the watcher's contract (`{ buildId }`).
#[derive(Clone, Serialize)]
struct ModelUpdated {
    #[serde(rename = "buildId")]
    build_id: u64,
}

/// Run a build-producing RPC and, on success, emit `model-updated { buildId }`
/// straight from the engine's response.
///
/// The engine writes its artifacts (GLB then JSON) *before* it replies, so by the
/// time this returns the new model is already on disk — the frontend can refresh
/// off this event immediately. This is the authoritative, deterministic refresh
/// signal: it never misses (unlike the filesystem [`crate::watcher`], which
/// depends on the OS reporting an atomic rename inside a hidden dir and stays on
/// only as a fallback for *out-of-band* edits — the agent/terminal editing the
/// model over the MCP socket, which never crosses this command layer).
///
/// Emitting a buildId the frontend has already loaded is a no-op there (it
/// dedupes), so the redundant-with-the-watcher case is harmless.
async fn call_and_notify(
    app: &AppHandle,
    state: &State<'_, std::sync::Arc<Instances>>,
    method: &'static str,
    params: Value,
) -> Result<String, String> {
    let result = match call(state, method, params).await {
        Ok(r) => r,
        Err(e) => return Err(e),
    };
    // The engine result is JSON like `{"ok":true,"buildId":N,...}`; emit when a
    // buildId is present so only genuine new builds trigger a viewport refresh.
    if let Ok(v) = serde_json::from_str::<Value>(&result) {
        if let Some(build_id) = v.get("buildId").and_then(Value::as_u64) {
            let _ = app.emit("model-updated", ModelUpdated { build_id });
        }
    }
    Ok(result)
}

#[tauri::command]
pub async fn engine_execute_script(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    code: String,
) -> Result<String, String> {
    call_and_notify(
        &app,
        &state,
        "execute_script",
        serde_json::json!({ "code": code }),
    )
    .await
}

#[tauri::command]
pub async fn engine_render(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call_and_notify(&app, &state, "render", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_get_model_info(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "get_model_info", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_get_params(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "get_params", serde_json::json!({})).await
}

/// Read the assembly's nested skeleton contract (params/scalars/frames/joints)
/// plus per-child occurrences. Read-only; never rebuilds. The engine replies
/// `{"ok":false,...}` for a single-model workspace, which the frontend treats as
/// "no assembly metadata" rather than an error.
#[tauri::command]
pub async fn engine_get_assembly_tree(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "get_assembly_tree", serde_json::json!({})).await
}

/// Read the focused workspace's live metadata straight from its engine (the single
/// writer while open). Metadata *writes* go through the high-level commands in
/// [`crate::workspaces`], which pick engine-vs-direct, so no set/name/dismiss
/// forwarders live here.
#[tauri::command]
pub async fn engine_get_workspace_meta(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "get_workspace_meta", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_set_params(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    values: Value,
) -> Result<String, String> {
    call_and_notify(
        &app,
        &state,
        "set_params",
        serde_json::json!({ "values": values }),
    )
    .await
}

#[tauri::command]
pub async fn engine_export(
    state: State<'_, std::sync::Arc<Instances>>,
    format: String,
    path: String,
    options: Option<serde_json::Value>,
) -> Result<String, String> {
    crate::fs_guard::validate_outgoing_path(&path)?;
    call(
        &state,
        "export",
        serde_json::json!({ "format": format, "path": path, "options": options }),
    )
    .await
}

#[tauri::command]
pub async fn engine_export_with_override(
    state: State<'_, std::sync::Arc<Instances>>,
    format: String,
    path: String,
    options: Option<serde_json::Value>,
) -> Result<String, String> {
    crate::fs_guard::validate_outgoing_path(&path)?;
    let engine = state
        .focused_engine()
        .ok_or_else(|| "engine not ready: the engine has not started yet".to_string())?;
    let workspace = engine
        .workspace_id()
        .ok_or_else(|| "engine workspace is unavailable".to_string())?;
    let readiness: Value =
        serde_json::from_str(&call(&state, "get_readiness", serde_json::json!({})).await?)
            .map_err(|e| format!("invalid engine readiness: {e}"))?;
    let model = if readiness.get("level").and_then(Value::as_str) == Some("ready") {
        None
    } else {
        Some(
            serde_json::from_str(&call(&state, "get_model_info", serde_json::json!({})).await?)
                .map_err(|e| format!("invalid engine model info: {e}"))?,
        )
    };
    let nonce =
        override_nonce_for_readiness(&engine, &workspace, &readiness, model.as_ref(), &format)?;
    call(
        &state,
        "export",
        override_export_params(format, path, options, nonce),
    )
    .await
}

fn override_export_params(
    format: String,
    path: String,
    options: Option<Value>,
    nonce: Option<String>,
) -> Value {
    let mut params = serde_json::json!({ "format": format, "path": path, "options": options });
    if let Some(nonce) = nonce {
        params["overrideNonce"] = Value::String(nonce);
    }
    params
}

/// Ready exports use the normal strict channel without a capability. Any
/// non-ready result needs a nonce bound to the build observed after readiness;
/// if that build races before export, the engine rejects the scoped nonce.
fn override_nonce_for_readiness(
    authority: &crate::engine::EngineState,
    workspace: &str,
    readiness: &Value,
    model: Option<&Value>,
    format: &str,
) -> Result<Option<String>, String> {
    let level = readiness
        .get("level")
        .and_then(Value::as_str)
        .ok_or_else(|| "engine readiness has no level".to_string())?;
    if level == "ready" {
        return Ok(None);
    }
    let build_id = model
        .and_then(|value| value.get("buildId"))
        .and_then(Value::as_u64)
        .ok_or_else(|| "engine has no current build to override".to_string())?;
    Ok(Some(
        authority.issue_export_override(workspace, build_id, format),
    ))
}

#[tauri::command]
pub async fn engine_get_conformance(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "get_conformance", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_get_readiness(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "get_readiness", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_history(state: State<'_, std::sync::Arc<Instances>>) -> Result<String, String> {
    call(&state, "history", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_undo(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call_and_notify(&app, &state, "undo", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_redo(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call_and_notify(&app, &state, "redo", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_goto(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    index: i64,
) -> Result<String, String> {
    call_and_notify(&app, &state, "goto", serde_json::json!({ "index": index })).await
}

#[tauri::command]
pub async fn engine_feature_at(
    state: State<'_, std::sync::Arc<Instances>>,
    point: Value,
) -> Result<String, String> {
    call(&state, "feature_at", serde_json::json!({ "point": point })).await
}

#[tauri::command]
pub async fn engine_set_feature(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    name: String,
    values: Value,
) -> Result<String, String> {
    call_and_notify(
        &app,
        &state,
        "set_feature",
        serde_json::json!({ "name": name, "values": values }),
    )
    .await
}

#[tauri::command]
pub async fn engine_set_part_material(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    part_id: String,
    material: Option<String>,
) -> Result<String, String> {
    call_and_notify(
        &app,
        &state,
        "set_part_material",
        serde_json::json!({ "part_id": part_id, "material": material }),
    )
    .await
}

#[tauri::command]
pub async fn engine_analyze_dfm(
    state: State<'_, std::sync::Arc<Instances>>,
    process: Option<String>,
) -> Result<String, String> {
    call(
        &state,
        "analyze_dfm",
        serde_json::json!({ "process": process }),
    )
    .await
}

#[tauri::command]
pub async fn engine_measure(state: State<'_, std::sync::Arc<Instances>>) -> Result<String, String> {
    call(&state, "measure", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_stress_check(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "stress_check", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_tolerance_stack(
    state: State<'_, std::sync::Arc<Instances>>,
    chain: Value,
) -> Result<String, String> {
    call(
        &state,
        "tolerance_stack",
        serde_json::json!({ "chain": chain }),
    )
    .await
}

#[tauri::command]
pub async fn engine_check_requirements(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "check_requirements", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_set_requirements(
    state: State<'_, std::sync::Arc<Instances>>,
    requirements: Value,
) -> Result<String, String> {
    call(
        &state,
        "set_requirements",
        serde_json::json!({ "requirements": requirements }),
    )
    .await
}

#[tauri::command]
pub async fn engine_sweep(
    state: State<'_, std::sync::Arc<Instances>>,
    param: String,
    values: Value,
    checks: Option<bool>,
) -> Result<String, String> {
    call(
        &state,
        "sweep",
        serde_json::json!({ "param": param, "values": values, "checks": checks.unwrap_or(false) }),
    )
    .await
}

#[tauri::command]
pub async fn engine_optimize(
    state: State<'_, std::sync::Arc<Instances>>,
    param: String,
    objective: Option<String>,
    steps: Option<u32>,
    constraints: Option<Value>,
) -> Result<String, String> {
    call(
        &state,
        "optimize",
        serde_json::json!({
            "param": param,
            "objective": objective.unwrap_or_else(|| "min_mass".into()),
            "steps": steps.unwrap_or(9),
            "constraints": constraints,
        }),
    )
    .await
}

#[tauri::command]
pub async fn engine_converge_to_spec(
    state: State<'_, std::sync::Arc<Instances>>,
    objective: String,
    apply: bool,
) -> Result<String, String> {
    call(
        &state,
        "converge_to_spec",
        serde_json::json!({ "objective": objective, "apply": apply }),
    )
    .await
}

#[tauri::command]
pub async fn engine_analyze_import(
    state: State<'_, std::sync::Arc<Instances>>,
    name: Option<String>,
) -> Result<String, String> {
    call(
        &state,
        "analyze_import",
        serde_json::json!({ "name": name }),
    )
    .await
}

#[tauri::command]
pub async fn engine_diff_against(
    state: State<'_, std::sync::Arc<Instances>>,
    index: u32,
) -> Result<String, String> {
    call(
        &state,
        "diff_against",
        serde_json::json!({ "index": index }),
    )
    .await
}

#[tauri::command]
pub async fn engine_build_report(
    state: State<'_, std::sync::Arc<Instances>>,
    views: Option<Value>,
) -> Result<String, String> {
    call(
        &state,
        "build_report",
        serde_json::json!({ "views": views }),
    )
    .await
}

#[allow(clippy::too_many_arguments)]
#[tauri::command]
pub async fn engine_check_motion(
    state: State<'_, std::sync::Arc<Instances>>,
    part: String,
    kind: Option<String>,
    axis_origin: Option<Value>,
    axis_dir: Option<Value>,
    start: Option<f64>,
    stop: Option<f64>,
    steps: Option<u32>,
) -> Result<String, String> {
    call(
        &state,
        "check_motion",
        serde_json::json!({
            "part": part,
            "kind": kind.unwrap_or_else(|| "revolute".into()),
            "axis_origin": axis_origin,
            "axis_dir": axis_dir,
            "start": start.unwrap_or(0.0),
            "stop": stop.unwrap_or(90.0),
            "steps": steps.unwrap_or(12),
        }),
    )
    .await
}

#[tauri::command]
pub async fn engine_import_reference(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    path: String,
    name: Option<String>,
) -> Result<String, String> {
    crate::fs_guard::validate_outgoing_path(&path)?;
    call_and_notify(
        &app,
        &state,
        "import_reference",
        serde_json::json!({ "path": path, "name": name }),
    )
    .await
}

#[tauri::command]
pub async fn engine_remove_import(
    app: AppHandle,
    state: State<'_, std::sync::Arc<Instances>>,
    id: String,
) -> Result<String, String> {
    call_and_notify(
        &app,
        &state,
        "remove_import",
        serde_json::json!({ "id": id }),
    )
    .await
}

#[tauri::command]
pub async fn engine_create_drawing(
    state: State<'_, std::sync::Arc<Instances>>,
    path: Option<String>,
    options: Option<serde_json::Value>,
) -> Result<String, String> {
    if let Some(ref p) = path {
        crate::fs_guard::validate_outgoing_path(p)?;
    }
    call(
        &state,
        "create_drawing",
        serde_json::json!({ "path": path, "options": options }),
    )
    .await
}

// -- Fabrication commands --------------------------------------------------

#[tauri::command]
pub async fn engine_fab_detect(
    state: State<'_, std::sync::Arc<Instances>>,
) -> Result<String, String> {
    call(&state, "fab_detect", serde_json::json!({})).await
}

#[tauri::command]
pub async fn engine_fab_estimate(
    state: State<'_, std::sync::Arc<Instances>>,
    destination_id: Option<String>,
) -> Result<String, String> {
    call(
        &state,
        "fab_estimate",
        serde_json::json!({ "destination_id": destination_id }),
    )
    .await
}

#[tauri::command]
pub async fn engine_fab_orient(
    state: State<'_, std::sync::Arc<Instances>>,
    overhang_deg: Option<f64>,
) -> Result<String, String> {
    // Omit overhang_deg when unset so the engine falls back to the workspace
    // manufacturing profile's process.overhangDeg (matching Sol's fab_orient).
    let params = match overhang_deg {
        Some(deg) => serde_json::json!({ "overhang_deg": deg }),
        None => serde_json::json!({}),
    };
    call(&state, "fab_orient", params).await
}

#[tauri::command]
pub async fn engine_fab_open(
    state: State<'_, std::sync::Arc<Instances>>,
    destination_id: Option<String>,
) -> Result<String, String> {
    call(
        &state,
        "fab_open",
        serde_json::json!({ "destination_id": destination_id }),
    )
    .await
}

/// Read the build brief a workspace recorded at `<ws_path>/build_brief.json`. We
/// read the file straight from disk (not via the engine) so the read-only Plan
/// panel works even with no live engine, mirroring how the engine writes it. A
/// missing OR unparseable file returns `Ok(None)` (the panel shows its empty
/// state); only a real read error surfaces as `Err`.
#[tauri::command]
pub fn get_build_brief(ws_path: String) -> Result<Option<Value>, String> {
    let path = std::path::Path::new(&ws_path).join("build_brief.json");
    match std::fs::read_to_string(&path) {
        Ok(s) => Ok(serde_json::from_str(&s).ok()),
        Err(ref e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("failed to read build_brief.json: {e}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::io::{BufRead, BufReader, Write};
    #[cfg(unix)]
    use std::os::unix::net::UnixListener;

    #[test]
    fn encode_request_is_one_newline_terminated_line() {
        let line = encode_request(7, "execute_script", &json!({"code": "show(x)"}));
        assert!(line.ends_with('\n'), "request must be newline-terminated");
        assert_eq!(line.matches('\n').count(), 1, "exactly one line");

        let parsed: Value = serde_json::from_str(line.trim()).expect("valid JSON");
        assert_eq!(parsed["id"], 7);
        assert_eq!(parsed["method"], "execute_script");
        assert_eq!(parsed["params"]["code"], "show(x)");
        assert_eq!(
            parsed["client"],
            json!({
                "protocol": 13,
                "capabilities": [
                    "build_brief_v2",
                    "conformance",
                    "operations",
                    "readiness",
                    "strict_export",
                ],
            })
        );
    }

    #[test]
    fn parse_response_ok_string_result() {
        let out = parse_response(r#"{"id":1,"ok":true,"result":"pong"}"#).expect("ok");
        // Result is re-serialized JSON, so a string result keeps its quotes.
        assert_eq!(out, "\"pong\"");
    }

    #[test]
    fn parse_response_ok_object_result() {
        let out = parse_response(r#"{"id":1,"ok":true,"result":{"buildId":3}}"#).expect("ok");
        let v: Value = serde_json::from_str(&out).unwrap();
        assert_eq!(v["buildId"], 3);
    }

    #[test]
    fn parse_response_error_envelope() {
        let err = parse_response(r#"{"id":1,"ok":false,"error":"boom"}"#).unwrap_err();
        assert_eq!(err, "boom");
    }

    #[test]
    fn parse_response_rejects_empty_and_garbage() {
        assert!(parse_response("   ").is_err());
        assert!(parse_response("not json").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn engine_call_round_trips_over_a_real_socket() {
        // Stand up a fake engine on a temp UNIX socket that echoes a pong.
        let dir = std::env::temp_dir().join(format!("solidifai-rpc-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let sock = dir.join("engine.sock");
        let _ = std::fs::remove_file(&sock);
        let listener = UnixListener::bind(&sock).unwrap();

        let handle = std::thread::spawn(move || {
            let (conn, _) = listener.accept().unwrap();
            let mut reader = BufReader::new(conn.try_clone().unwrap());
            let mut line = String::new();
            reader.read_line(&mut line).unwrap();
            let req: Value = serde_json::from_str(line.trim()).unwrap();
            assert_eq!(req["method"], "ping");
            let id = req["id"].clone();
            let resp = json!({"id": id, "ok": true, "result": "pong"});
            let mut conn = conn;
            conn.write_all((resp.to_string() + "\n").as_bytes())
                .unwrap();
            conn.flush().unwrap();
        });

        let out = engine_call(sock.to_str().unwrap(), "ping", json!({})).expect("call ok");
        assert_eq!(out, "\"pong\"");
        handle.join().unwrap();
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn engine_call_reports_clear_error_when_unreachable() {
        let err = engine_call("/nonexistent/solidifai/engine.sock", "ping", json!({})).unwrap_err();
        assert!(
            err.contains("engine not ready"),
            "expected a clear not-ready error, got: {err}"
        );
    }

    #[test]
    fn ready_override_export_never_mints_pending_nonces() {
        let authority = crate::engine::EngineState::default();
        let ready = json!({"level": "ready"});
        for _ in 0..3 {
            assert!(
                override_nonce_for_readiness(&authority, "/workspace", &ready, None, "stl")
                    .unwrap()
                    .is_none()
            );
        }
        assert_eq!(authority.pending_override_count(), 0);
        assert!(
            override_export_params("stl".into(), "/out.stl".into(), None, None)
                .get("overrideNonce")
                .is_none()
        );
    }

    #[test]
    fn blocked_override_nonce_is_single_use_and_wrong_build_is_rejected() {
        let authority = crate::engine::EngineState::default();
        let blocked = json!({"level": "blocked"});
        let nonce = override_nonce_for_readiness(
            &authority,
            "/workspace",
            &blocked,
            Some(&json!({"buildId": 7})),
            "stl",
        )
        .unwrap()
        .unwrap();
        assert_eq!(authority.pending_override_count(), 1);
        assert!(authority
            .consume_export_override(&nonce, "/workspace", 8, "stl")
            .is_none());
        assert!(authority
            .consume_export_override(&nonce, "/workspace", 7, "stl")
            .is_some());
        assert!(authority
            .consume_export_override(&nonce, "/workspace", 7, "stl")
            .is_none());
    }
}
