//! PTY host for solidifai.
//!
//! Exposes three Tauri commands (`pty_spawn`, `pty_write`, `pty_resize`) that let
//! the frontend drive an interactive shell running inside a real pseudo-terminal.
//!
//! The raw PTY mechanics live in [`open_pty`] / [`spawn_in_pty`], plain functions
//! that do NOT depend on any Tauri types. The Tauri commands are thin wrappers over
//! them, which keeps the core plumbing unit-testable without a running app.

use std::collections::HashMap;
use std::io::{Read, Write};

use parking_lot::Mutex;

use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtyPair, PtySize};
use tauri::ipc::Channel;
use tauri::State;

/// The three owned handles for a live PTY session: child process, master writer,
/// and master PTY. Dropping all three tears the session down.
type PtySession = (
    Box<dyn Child + Send + Sync>,
    Box<dyn Write + Send>,
    Box<dyn MasterPty + Send>,
);

/// Managed state holding live PTY sessions keyed by workspace ID (canonical root
/// path string). Each workspace tab gets its own independent shell session.
#[derive(Default)]
pub struct PtyState {
    sessions: Mutex<HashMap<String, PtySession>>,
}

impl PtyState {
    /// Register a new session for `ws_id`, replacing any prior entry (the old
    /// handles are dropped, which tears down that session).
    pub fn insert(
        &self,
        ws_id: &str,
        child: Box<dyn Child + Send + Sync>,
        writer: Box<dyn Write + Send>,
        master: Box<dyn MasterPty + Send>,
    ) {
        self.sessions
            .lock()
            .insert(ws_id.to_string(), (child, writer, master));
    }

    /// Returns `true` if a live session is registered for `ws_id`.
    #[cfg(test)]
    pub fn has(&self, ws_id: &str) -> bool {
        self.sessions.lock().contains_key(ws_id)
    }

    /// Kill + reap one session. Idempotent — safe to call when no session exists.
    pub fn kill_one(&self, ws_id: &str) {
        if let Some((mut child, _w, _m)) = self.sessions.lock().remove(ws_id) {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    /// Kill + reap every session (app exit / window destroy). Drain into a Vec
    /// first so the lock is released before the (potentially blocking) waits.
    pub fn kill_all(&self) {
        let drained: Vec<_> = self.sessions.lock().drain().collect();
        for (_, (mut child, _w, _m)) in drained {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Open a PTY of the given size. Tauri-independent.
fn open_pty(rows: u16, cols: u16) -> Result<PtyPair, String> {
    native_pty_system()
        .openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("openpty failed: {e}"))
}

/// Build a `CommandBuilder` for the user's shell (or an explicit program),
/// applying an optional working directory and extra environment variables.
///
/// Tauri-independent so it can be exercised in tests with an arbitrary program.
fn build_command(
    program: Option<&str>,
    args: &[&str],
    cwd: Option<String>,
    env: Option<HashMap<String, String>>,
) -> CommandBuilder {
    let shell = program
        .map(|p| p.to_string())
        .unwrap_or_else(|| std::env::var("SHELL").unwrap_or_else(|_| "/bin/zsh".to_string()));

    let mut cmd = CommandBuilder::new(shell);
    for arg in args {
        cmd.arg(arg);
    }

    // Working directory: explicit cwd, else the user's home, else the process cwd.
    let dir = cwd.or_else(|| std::env::var("HOME").ok()).or_else(|| {
        std::env::current_dir()
            .ok()
            .map(|p| p.display().to_string())
    });
    if let Some(dir) = dir {
        cmd.cwd(dir);
    }

    if let Some(env) = env {
        for (k, v) in env {
            cmd.env(k, v);
        }
    }

    cmd
}

/// Spawn `cmd` inside the slave side of `pair`, take the master writer, and start
/// a reader thread that pushes every chunk of raw output to `on_data`.
///
/// Returns `(child, writer, master)`. The caller owns the lifetimes:
/// dropping the master/writer/child tears the session down. Tauri-independent —
/// `on_data` is any `FnMut(&[u8])` so tests can collect bytes into a buffer and the
/// Tauri command can forward them over a `Channel`.
fn spawn_in_pty(
    pair: PtyPair,
    cmd: CommandBuilder,
    mut on_data: impl FnMut(&[u8]) + Send + 'static,
) -> Result<PtySession, String> {
    let child = pair
        .slave
        .spawn_command(cmd)
        .map_err(|e| format!("spawn_command failed: {e}"))?;
    // The slave handle must be dropped after spawning so that EOF is delivered to
    // the reader once the child exits; otherwise the read loop would block forever.
    drop(pair.slave);

    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| format!("try_clone_reader failed: {e}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|e| format!("take_writer failed: {e}"))?;

    std::thread::spawn(move || {
        let mut buf = [0u8; 8192];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break, // EOF: child closed the PTY.
                Ok(n) => on_data(&buf[..n]),
                Err(e) => {
                    // EIO is the normal signal that the slave side went away on Unix.
                    if e.kind() == std::io::ErrorKind::Interrupted {
                        continue;
                    }
                    break;
                }
            }
        }
    });

    Ok((child, writer, pair.master))
}

/// Open a PTY, spawn the user's shell, and stream raw output bytes to the frontend
/// via a high-throughput Tauri [`Channel`] (NOT events).
#[tauri::command]
pub fn pty_spawn(
    state: State<'_, PtyState>,
    on_data: Channel<Vec<u8>>,
    ws_id: String,
    cwd: Option<String>,
    env: Option<HashMap<String, String>>,
) -> Result<(), String> {
    // Reap any prior shell for this workspace tab before spawning a new one.
    state.kill_one(&ws_id);

    let pair = open_pty(24, 80)?;
    let cmd = build_command(None, &[], cwd, env);

    // Decouple the PTY reader from the frontend Channel. The reader thread must
    // NEVER block on a back-pressured Channel: if it did, the kernel PTY output
    // buffer would fill and the agent process would block on its next write, so a
    // BACKGROUND tab's agent (e.g. Claude) would freeze until the frontend drained.
    // The reader hands each chunk to an unbounded queue (non-blocking) and a
    // dedicated forwarder thread sends to the Channel at the frontend's own pace.
    // The PTY is therefore always drained, so every tab's agent keeps running
    // regardless of which one is focused.
    let (tx, rx) = std::sync::mpsc::channel::<Vec<u8>>();
    std::thread::spawn(move || {
        // Ends when `tx` drops (the reader hit EOF) or the frontend channel is gone.
        while let Ok(bytes) = rx.recv() {
            if on_data.send(bytes).is_err() {
                break;
            }
        }
    });

    let (child, writer, master) = spawn_in_pty(pair, cmd, move |bytes| {
        // Non-blocking hand-off; the forwarder thread owns the (blocking) Channel send.
        let _ = tx.send(bytes.to_vec());
    })?;

    state.insert(&ws_id, child, writer, master);
    Ok(())
}

/// Write bytes (keystrokes) to the PTY for a given workspace.
#[tauri::command]
pub fn pty_write(state: State<'_, PtyState>, ws_id: String, data: Vec<u8>) -> Result<(), String> {
    let mut guard = state.sessions.lock();
    let session = guard.get_mut(&ws_id).ok_or("PTY not spawned")?;
    session
        .1
        .write_all(&data)
        .map_err(|e| format!("pty_write failed: {e}"))?;
    session
        .1
        .flush()
        .map_err(|e| format!("pty_write flush failed: {e}"))
}

/// Resize the PTY for a given workspace.
#[tauri::command]
pub fn pty_resize(
    state: State<'_, PtyState>,
    ws_id: String,
    rows: u16,
    cols: u16,
) -> Result<(), String> {
    let guard = state.sessions.lock();
    let session = guard.get(&ws_id).ok_or("PTY not spawned")?;
    session
        .2
        .resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| format!("pty_resize failed: {e}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;
    use std::time::Duration;

    /// Proves the raw PTY plumbing works end-to-end without a running Tauri app:
    /// open a PTY, run a command in it, read the master, and verify the output.
    #[test]
    fn pty_echo_roundtrip() {
        let pair = open_pty(24, 80).expect("open_pty");
        // Use `sh -c printf` so we get exact bytes regardless of the host shell.
        let cmd = build_command(
            Some("/bin/sh"),
            &["-c", "printf solidifai-pty-ok"],
            None,
            None,
        );

        let (tx, rx) = mpsc::channel::<Vec<u8>>();
        let (mut child, _writer, _master) = spawn_in_pty(pair, cmd, move |bytes| {
            let _ = tx.send(bytes.to_vec());
        })
        .expect("spawn_in_pty");

        // Collect output until we see our marker or the channel closes (EOF).
        let mut collected = Vec::new();
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        while std::time::Instant::now() < deadline {
            match rx.recv_timeout(Duration::from_millis(500)) {
                Ok(chunk) => {
                    collected.extend_from_slice(&chunk);
                    if String::from_utf8_lossy(&collected).contains("solidifai-pty-ok") {
                        break;
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }

        let _ = child.wait();
        let out = String::from_utf8_lossy(&collected);
        assert!(
            out.contains("solidifai-pty-ok"),
            "expected PTY output to contain marker, got: {out:?}"
        );
    }

    /// Storing a live child in `PtyState` and calling `kill_one()` reaps it without
    /// panicking, and removes the session (so a second kill_one is a no-op).
    #[test]
    fn pty_state_kill_reaps_stored_child() {
        let state = PtyState::default();

        // Spawn a long-lived shell in a PTY and stash its handles in the state.
        let pair = open_pty(24, 80).expect("open_pty");
        let cmd = build_command(Some("/bin/sh"), &["-c", "sleep 30"], None, None);
        let (child, writer, master) = spawn_in_pty(pair, cmd, |_| {}).expect("spawn_in_pty");
        let pid = child.process_id();
        state.insert("/ws/x", child, writer, master);

        // kill_one() must terminate + reap the child and clear the slot.
        state.kill_one("/ws/x");
        assert!(
            !state.has("/ws/x"),
            "session slot should be empty after kill_one()"
        );
        // A second kill_one() with no session stored must be a harmless no-op.
        state.kill_one("/ws/x");

        // Sanity: we actually had a real process.
        assert!(pid.is_some(), "expected a spawned shell to have a pid");
    }

    /// Two sessions keyed by different workspace IDs are independent: killing one
    /// does not affect the other.
    #[test]
    fn pty_state_kills_one_session_without_touching_others() {
        let state = PtyState::default();

        let spawn_session = |tag: &str| {
            let pair = open_pty(24, 80).unwrap();
            let cmd = build_command(Some("/bin/sh"), &["-c", "sleep 30"], None, None);
            let (child, writer, master) = spawn_in_pty(pair, cmd, |_| {}).unwrap();
            state.insert(tag, child, writer, master);
        };

        spawn_session("/ws/a");
        spawn_session("/ws/b");

        state.kill_one("/ws/a");
        assert!(!state.has("/ws/a"), "a reaped");
        assert!(state.has("/ws/b"), "b still alive");

        state.kill_all();
        assert!(!state.has("/ws/b"));
    }
}
