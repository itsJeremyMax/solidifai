//! Real engine smoke test (dev only).
//!
//! Resolves the engine interpreter the same way the app does, spawns the Python
//! engine server, and calls `engine_call(ping)` over the UNIX socket — exercising
//! the exact line framing the app uses against the *real* engine.
//!
//! Skips gracefully (passes) when the engine venv isn't provisioned, so CI on a
//! machine without `uv sync` having run doesn't fail. The Python-side smoke
//! (`engine/scripts/smoke.py`) already covers the engine itself.

use std::path::PathBuf;
use std::process::Command;
use std::time::{Duration, Instant};

use solidifai_lib::{engine, rpc};

#[test]
fn engine_ping_round_trip_real() {
    // Resolve the engine dir the same way the app does, minus the `AppHandle`
    // (unavailable in an integration test): honor the env override, skip the
    // bundled resource dir, fall back to the dev `engine/` sibling.
    let dev_fallback = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../engine"));
    let engine_dir = match engine::resolve_engine_dir_from(
        std::env::var("SOLIDIFAI_ENGINE_DIR").ok(),
        None,
        dev_fallback,
    ) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("skipping: cannot resolve engine dir: {e}");
            return;
        }
    };
    let interpreter = engine::interpreter_path(&engine_dir);
    if !interpreter.is_file() {
        eprintln!(
            "skipping: engine venv not provisioned ({}); run `uv sync` in engine/",
            interpreter.display()
        );
        return;
    }

    // Unique temp socket + artifacts.
    let base: PathBuf = std::env::temp_dir().join(format!(
        "solidifai-engine-smoke-{}-{}",
        std::process::id(),
        Instant::now().elapsed().as_nanos()
    ));
    let sock = base.join("engine.sock");
    let artifacts = base.join("artifacts");
    std::fs::create_dir_all(&artifacts).unwrap();

    let mut child = Command::new(&interpreter)
        .args([
            "-m",
            "solidifai_engine",
            "--socket",
            sock.to_str().unwrap(),
            "--artifacts",
            artifacts.to_str().unwrap(),
        ])
        .current_dir(&engine_dir)
        .spawn()
        .expect("spawn engine server");

    // Wait for the engine to bind the socket (build123d import is heavy).
    let deadline = Instant::now() + Duration::from_secs(30);
    while !sock.exists() && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }

    let result = if sock.exists() {
        rpc::engine_call(sock.to_str().unwrap(), "ping", serde_json::json!({}))
    } else {
        Err("engine never created socket".to_string())
    };

    // Tear the engine down before asserting.
    let _ = child.kill();
    let _ = child.wait();
    let _ = std::fs::remove_dir_all(&base);

    let out = result.expect("ping should succeed against the real engine");
    assert_eq!(out, "\"pong\"", "expected pong, got {out}");
}
