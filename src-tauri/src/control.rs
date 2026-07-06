//! Host-control channel: a local IPC endpoint (ipc.rs: UNIX socket on unix,
//! token-guarded loopback TCP on Windows) the engine (and its MCP bridge)
//! connects to so the agent's host-owned writes are delegated back to the one
//! Rust writer (`manufacturing::write`). The engine RPC mirrored, roles
//! reversed: Rust is the server here. Newline-delimited JSON request -> one
//! newline-delimited response, same framing as the engine RPC (rpc.rs).

use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use crate::ipc::{self, IpcListener, IpcStream};

use serde_json::{json, Value};

use crate::manufacturing::{self, Scope};

/// The control socket path, set once at startup. `spawn_engine_server` reads it to
/// inject `SOLIDIFAI_CONTROL_SOCK` into each engine.
static CONTROL_SOCK: OnceLock<PathBuf> = OnceLock::new();

pub fn socket_path() -> Option<PathBuf> {
    CONTROL_SOCK.get().cloned()
}

/// Bind the control socket under the app config dir and spawn its accept thread.
/// Best-effort: a bind failure is logged, not fatal (the GUI path still works).
pub fn start(config_dir: PathBuf) {
    let sock = config_dir.join("control.sock");
    let _ = std::fs::remove_file(&sock); // clear a stale socket from a prior run
    if let Err(e) = serve_on(&sock, config_dir) {
        tracing::warn!("control channel failed to start: {e}");
    }
}

/// Bind + spawn the accept loop. Stores the path in `CONTROL_SOCK`. Testable.
fn serve_on(sock: &Path, config_dir: PathBuf) -> Result<(), String> {
    // ipc::bind is owner-only by construction (socket mode 0600 on unix, a
    // token handshake behind a user-owned pointer file on windows): this is a
    // write-capable control surface.
    let listener = IpcListener::bind(sock).map_err(|e| format!("bind {}: {e}", sock.display()))?;
    let _ = CONTROL_SOCK.set(sock.to_path_buf());
    spawn_accept_loop(listener, config_dir);
    Ok(())
}

fn spawn_accept_loop(listener: IpcListener, config_dir: PathBuf) {
    std::thread::spawn(move || loop {
        match listener.accept() {
            // One thread per connection so a client that connects but never
            // sends a newline can't wedge the accept loop (head-of-line block).
            Ok((stream, token)) => {
                let cfg = config_dir.clone();
                std::thread::spawn(move || {
                    let _ = handle(stream, token.as_deref(), &cfg);
                });
            }
            Err(_) => continue,
        }
    });
}

fn handle(mut stream: IpcStream, token: Option<&str>, config_dir: &Path) -> std::io::Result<()> {
    // Bound the round-trip so a wedged client can't hold a thread forever.
    let _ = stream.set_read_timeout(Some(std::time::Duration::from_secs(30)));
    let _ = stream.set_write_timeout(Some(std::time::Duration::from_secs(10)));
    // TCP mode: the first line must be the shared token; drop silently if not.
    if let Some(expected) = token {
        if !ipc::authenticate(&mut stream, expected)? {
            return Ok(());
        }
    }
    // Read one request line.
    let mut buf = Vec::new();
    let mut byte = [0u8; 1];
    loop {
        match stream.read(&mut byte) {
            Ok(0) => break,
            Ok(_) => {
                if byte[0] == b'\n' {
                    break;
                }
                buf.push(byte[0]);
                // Cap the buffer: profile deltas are tiny, so a no-newline client
                // never legitimately grows past 1 MiB. Drop it rather than OOM.
                if buf.len() > 1 << 20 {
                    return Ok(());
                }
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    let resp = dispatch(&String::from_utf8_lossy(&buf), config_dir);
    stream.write_all(format!("{resp}\n").as_bytes())?;
    stream.flush()
}

/// Parse + route a request line to a response Value. Pure (testable) given config_dir.
fn dispatch(line: &str, config_dir: &Path) -> Value {
    let req: Value = match serde_json::from_str(line) {
        Ok(v) => v,
        Err(e) => return json!({"ok": false, "error": format!("invalid JSON: {e}")}),
    };
    match req.get("op").and_then(|v| v.as_str()) {
        Some("write_manufacturing_profile") => write_profile(&req, config_dir),
        Some("write_reference") => write_reference(&req, config_dir),
        other => json!({"ok": false, "error": format!("unknown op {other:?}")}),
    }
}

fn write_profile(req: &Value, config_dir: &Path) -> Value {
    let scope = match req.get("scope").and_then(|v| v.as_str()).map(Scope::parse) {
        Some(Ok(s)) => s,
        _ => return json!({"ok": false, "error": "missing/invalid scope"}),
    };
    let ws = req
        .get("workspace_root")
        .and_then(|v| v.as_str())
        .map(PathBuf::from);
    let set = req.get("set").cloned().unwrap_or_else(|| json!({}));
    let unset: Vec<String> = req
        .get("unset")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    match manufacturing::write(config_dir, scope, ws.as_deref(), &set, &unset) {
        Ok(profile) => json!({"ok": true, "profile": profile}),
        Err(e) => json!({"ok": false, "error": e}),
    }
}

fn write_reference(req: &Value, config_dir: &Path) -> Value {
    let result = match req.get("action").and_then(|v| v.as_str()) {
        Some("upsert") => match req.get("entry") {
            Some(entry) => crate::reference_library::upsert(config_dir, entry),
            None => Err("missing entry".into()),
        },
        Some("delete") => match req.get("id").and_then(|v| v.as_str()) {
            Some(id) => crate::reference_library::delete(config_dir, id),
            None => Err("missing id".into()),
        },
        other => Err(format!("unknown action {other:?}")),
    };
    match result {
        Ok(library) => {
            crate::reference_library::emit_updated();
            json!({"ok": true, "library": library})
        }
        Err(e) => json!({"ok": false, "error": e}),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    #[cfg(unix)]
    use std::os::unix::net::UnixStream;

    // The windows transport, exercised on every platform: token handshake in
    // front of the same dispatch loop, bad token dropped without a response.
    #[test]
    fn tcp_mode_round_trips_and_rejects_bad_token() {
        let dir = tempfile::tempdir().unwrap();
        let cfg = dir.path().join("cfg");
        let ws = dir.path().join("ws");
        std::fs::create_dir_all(&cfg).unwrap();
        std::fs::create_dir_all(&ws).unwrap();
        let sock = dir.path().join("control.sock");
        let listener = IpcListener::bind_tcp(&sock).unwrap();
        spawn_accept_loop(listener, cfg);

        let req = serde_json::json!({
            "op": "write_manufacturing_profile", "scope": "workspace",
            "workspace_root": ws.to_string_lossy(), "set": {"design": {"wallMm": 1.6}}, "unset": []
        });
        let mut s = ipc::connect_tcp(sock.to_str().unwrap()).unwrap();
        s.write_all(format!("{req}\n").as_bytes()).unwrap();
        let mut buf = String::new();
        s.read_to_string(&mut buf).unwrap();
        let resp: serde_json::Value = serde_json::from_str(buf.lines().next().unwrap()).unwrap();
        assert_eq!(resp["ok"].as_bool(), Some(true));
        assert!(ws.join("manufacturing-profile.json").exists());

        // Wrong token: connection is dropped without a response.
        let addr = std::fs::read_to_string(&sock)
            .unwrap()
            .lines()
            .next()
            .unwrap()
            .to_string();
        let mut bad = std::net::TcpStream::connect(addr).unwrap();
        bad.write_all(b"wrong-token\n").unwrap();
        bad.write_all(format!("{req}\n").as_bytes()).unwrap();
        let mut out = String::new();
        // The drop shows up as clean EOF or ECONNRESET depending on timing
        // (the server closes while the request bytes are still in flight).
        let res = bad.read_to_string(&mut out);
        assert!(out.is_empty(), "unauthenticated client must get nothing");
        if let Err(e) = res {
            assert_eq!(e.kind(), std::io::ErrorKind::ConnectionReset);
        }
    }

    #[cfg(unix)]
    #[test]
    fn write_op_round_trips_and_persists() {
        let cfg = std::env::temp_dir().join(format!("ctl-cfg-{}", std::process::id()));
        let ws = std::env::temp_dir().join(format!("ctl-ws-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&cfg);
        let _ = std::fs::remove_dir_all(&ws);
        std::fs::create_dir_all(&cfg).unwrap();
        std::fs::create_dir_all(&ws).unwrap();
        let sock = std::env::temp_dir().join(format!("ctl-{}.sock", std::process::id()));
        let _ = std::fs::remove_file(&sock);
        serve_on(&sock, cfg.clone()).unwrap(); // spawns the accept thread

        let req = serde_json::json!({
            "op": "write_manufacturing_profile", "scope": "workspace",
            "workspace_root": ws.to_string_lossy(), "set": {"design": {"wallMm": 1.6}}, "unset": []
        });
        let mut s = UnixStream::connect(&sock).unwrap();
        s.write_all(format!("{req}\n").as_bytes()).unwrap();
        let mut buf = String::new();
        s.read_to_string(&mut buf).unwrap();
        let resp: serde_json::Value = serde_json::from_str(buf.lines().next().unwrap()).unwrap();
        assert_eq!(resp["ok"].as_bool(), Some(true));
        assert_eq!(resp["profile"]["design"]["wallMm"].as_f64(), Some(1.6));
        assert!(ws.join("manufacturing-profile.json").exists());
    }

    #[cfg(unix)]
    #[test]
    fn write_reference_round_trips_and_persists() {
        let cfg = std::env::temp_dir().join(format!("ctl-ref-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&cfg);
        std::fs::create_dir_all(&cfg).unwrap();
        let sock = std::env::temp_dir().join(format!("ctl-ref-{}.sock", std::process::id()));
        let _ = std::fs::remove_file(&sock);
        serve_on(&sock, cfg.clone()).unwrap();

        // upsert
        let req = serde_json::json!({
            "op": "write_reference",
            "action": "upsert",
            "entry": {
                "id": "raspberry-pi-5", "category": "sbc",
                "dims_mm": {"pcb": [85.0, 56.0, 1.4]},
                "source": "https://datasheets.raspberrypi.com/rpi5.pdf",
                "origin": "learned", "verified_at": "2026-06-11", "verified_in": "ws"
            }
        });
        let mut s = UnixStream::connect(&sock).unwrap();
        s.write_all(format!("{req}\n").as_bytes()).unwrap();
        let mut buf = String::new();
        s.read_to_string(&mut buf).unwrap();
        let resp: serde_json::Value = serde_json::from_str(buf.lines().next().unwrap()).unwrap();
        assert_eq!(resp["ok"].as_bool(), Some(true));
        assert_eq!(resp["library"]["objects"][0]["id"], "raspberry-pi-5");
        assert!(cfg.join("reference-library.json").exists());

        // delete
        let del = serde_json::json!({"op": "write_reference", "action": "delete", "id": "raspberry-pi-5"});
        let mut s2 = UnixStream::connect(&sock).unwrap();
        s2.write_all(format!("{del}\n").as_bytes()).unwrap();
        let mut buf2 = String::new();
        s2.read_to_string(&mut buf2).unwrap();
        let resp2: serde_json::Value = serde_json::from_str(buf2.lines().next().unwrap()).unwrap();
        assert_eq!(resp2["ok"].as_bool(), Some(true));
        assert!(resp2["library"]["objects"].as_array().unwrap().is_empty());

        // unknown action returns ok:false
        let bad = serde_json::json!({"op": "write_reference", "action": "explode"});
        let mut s3 = UnixStream::connect(&sock).unwrap();
        s3.write_all(format!("{bad}\n").as_bytes()).unwrap();
        let mut buf3 = String::new();
        s3.read_to_string(&mut buf3).unwrap();
        let resp3: serde_json::Value = serde_json::from_str(buf3.lines().next().unwrap()).unwrap();
        assert_eq!(resp3["ok"].as_bool(), Some(false));
    }

    #[cfg(unix)]
    #[test]
    fn invalid_values_return_ok_false() {
        let cfg = std::env::temp_dir().join(format!("ctl2-cfg-{}", std::process::id()));
        let ws = std::env::temp_dir().join(format!("ctl2-ws-{}", std::process::id()));
        std::fs::create_dir_all(&cfg).unwrap();
        std::fs::create_dir_all(&ws).unwrap();
        let sock = std::env::temp_dir().join(format!("ctl2-{}.sock", std::process::id()));
        let _ = std::fs::remove_file(&sock);
        serve_on(&sock, cfg).unwrap();
        let req = serde_json::json!({
            "op": "write_manufacturing_profile", "scope": "workspace",
            "workspace_root": ws.to_string_lossy(), "set": {"process": {"overhangDeg": 999}}, "unset": []
        });
        let mut s = UnixStream::connect(&sock).unwrap();
        s.write_all(format!("{req}\n").as_bytes()).unwrap();
        let mut buf = String::new();
        s.read_to_string(&mut buf).unwrap();
        let resp: serde_json::Value = serde_json::from_str(buf.lines().next().unwrap()).unwrap();
        assert_eq!(resp["ok"].as_bool(), Some(false));
    }
}
