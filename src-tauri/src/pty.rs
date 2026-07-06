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
    build_command_with_env(program, args, cwd, env, |key| std::env::var(key).ok())
}

/// [`build_command`] with the host environment lookups injected, so tests can
/// exercise launch-path-specific branches (no SHELL, no HOME, AppImage) without
/// mutating the process environment (which races other tests).
fn build_command_with_env(
    program: Option<&str>,
    args: &[&str],
    cwd: Option<String>,
    env: Option<HashMap<String, String>>,
    host_env: impl Fn(&str) -> Option<String>,
) -> CommandBuilder {
    let shell = program.map(|p| p.to_string()).unwrap_or_else(|| {
        // SHELL is a unix convention; a Windows GUI launch sets neither SHELL
        // nor HOME, so fall back to COMSPEC (the OS's own default-shell pointer).
        #[cfg(unix)]
        {
            host_env("SHELL").unwrap_or_else(|| "/bin/zsh".to_string())
        }
        #[cfg(windows)]
        {
            host_env("COMSPEC").unwrap_or_else(|| "cmd.exe".to_string())
        }
    });

    let mut cmd = CommandBuilder::new(shell);
    for arg in args {
        cmd.arg(arg);
    }

    // Launched from Finder/Dock the app gets launchd's minimal environment: no
    // TERM (curses tools abort) and no Homebrew in PATH (user rc files that call
    // `brew --prefix` or prompt tools break). An interactive session (no explicit
    // program) therefore runs as a LOGIN shell so /etc/zprofile + ~/.zprofile
    // rebuild PATH, and TERM defaults to what xterm.js emulates. Dev runs are
    // unaffected: there the parent env already carries both, and the explicit
    // env map below still overrides everything.
    #[cfg(unix)]
    if program.is_none() {
        cmd.arg("-l");
        scrub_appimage_env(&mut cmd, &host_env);
    }
    #[cfg(unix)]
    {
        if host_env("TERM").is_none() {
            cmd.env("TERM", "xterm-256color");
        }
        if host_env("COLORTERM").is_none() {
            cmd.env("COLORTERM", "truecolor");
        }
    }

    // Working directory: explicit cwd, else the user's home (HOME on unix;
    // Windows GUI launches set USERPROFILE instead), else the process cwd.
    let dir = cwd
        .or_else(|| host_env("HOME"))
        .or_else(|| host_env("USERPROFILE"))
        .or_else(|| {
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

/// A Linux AppImage launches through an AppRun that exports LD_LIBRARY_PATH
/// pointing into $APPDIR/usr/lib so the bundled webkit/gtk libs resolve. User
/// tools run in the interactive terminal must NOT inherit that: system
/// git/node/python would link the bundle's older libstdc++/libssl and fail with
/// "GLIBCXX_... not found" style errors. Login-shell rc files rebuild PATH but
/// never clear LD_LIBRARY_PATH, so it has to be stripped here. Only applies when
/// actually running inside an AppImage; .deb/dev launches are left untouched,
/// and callers only invoke this for interactive sessions (explicit programs run
/// exactly as requested).
#[cfg(unix)]
fn scrub_appimage_env(cmd: &mut CommandBuilder, host_env: &impl Fn(&str) -> Option<String>) {
    if host_env("APPIMAGE").is_some() || host_env("APPDIR").is_some() {
        cmd.env_remove("LD_LIBRARY_PATH");
        cmd.env_remove("LD_PRELOAD");
    }
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

    /// An interactive session (default shell) must survive a Finder launch: login
    /// shell so rc files can rebuild PATH, and a TERM default for curses tools.
    /// An explicit program is left exactly as requested.
    #[test]
    #[cfg(unix)]
    fn build_command_interactive_shell_is_login_with_term() {
        let cmd = build_command(None, &[], None, None);
        assert!(
            cmd.get_argv().iter().any(|a| a == "-l"),
            "default shell should be spawned as a login shell"
        );
        assert!(
            cmd.get_env("TERM").is_some(),
            "TERM must be set or defaulted"
        );

        let explicit = build_command(Some("/bin/sh"), &["-c", "true"], None, None);
        assert!(
            !explicit.get_argv().iter().any(|a| a == "-l"),
            "explicit programs must not gain a login flag"
        );
    }

    /// Fake host-environment lookup backed by a fixed key/value slice, so tests
    /// never mutate the real process environment (which races other tests).
    fn env_of(pairs: &'static [(&'static str, &'static str)]) -> impl Fn(&str) -> Option<String> {
        move |key| {
            pairs
                .iter()
                .find(|(k, _)| *k == key)
                .map(|(_, v)| (*v).to_string())
        }
    }

    /// Shell selection honors SHELL when present and falls back to a fixed
    /// default when unset (a stripped launch environment).
    #[test]
    #[cfg(unix)]
    fn build_command_shell_env_and_fallback() {
        let from_env =
            build_command_with_env(None, &[], None, None, env_of(&[("SHELL", "/bin/bash")]));
        assert_eq!(from_env.get_argv()[0], "/bin/bash");

        let fallback = build_command_with_env(None, &[], None, None, env_of(&[]));
        assert_eq!(fallback.get_argv()[0], "/bin/zsh");
    }

    /// Windows GUI launches set neither SHELL nor HOME: the shell must come from
    /// COMSPEC (cmd.exe fallback) and the cwd from USERPROFILE.
    #[test]
    #[cfg(windows)]
    fn build_command_windows_uses_comspec_and_userprofile() {
        let cmd = build_command_with_env(
            None,
            &[],
            None,
            None,
            env_of(&[
                ("COMSPEC", "C:\\Windows\\System32\\cmd.exe"),
                ("USERPROFILE", "C:\\Users\\test"),
            ]),
        );
        assert_eq!(cmd.get_argv()[0], "C:\\Windows\\System32\\cmd.exe");
        assert!(
            !cmd.get_argv().iter().any(|a| a == "-l"),
            "the unix login flag must not leak onto Windows shells"
        );
        assert_eq!(cmd.get_cwd().unwrap(), "C:\\Users\\test");

        let bare = build_command_with_env(None, &[], None, None, env_of(&[]));
        assert_eq!(bare.get_argv()[0], "cmd.exe");
    }

    /// Working directory falls back HOME -> USERPROFILE -> process cwd, and an
    /// explicit cwd always wins.
    #[test]
    fn build_command_cwd_fallback_chain() {
        let explicit = build_command_with_env(
            None,
            &[],
            Some("/ws/here".into()),
            None,
            env_of(&[("HOME", "/home/u")]),
        );
        assert_eq!(explicit.get_cwd().unwrap(), "/ws/here");

        let home = build_command_with_env(
            None,
            &[],
            None,
            None,
            env_of(&[("HOME", "/home/u"), ("USERPROFILE", "C:\\Users\\u")]),
        );
        assert_eq!(home.get_cwd().unwrap(), "/home/u");

        let profile = build_command_with_env(
            None,
            &[],
            None,
            None,
            env_of(&[("USERPROFILE", "C:\\Users\\u")]),
        );
        assert_eq!(profile.get_cwd().unwrap(), "C:\\Users\\u");
    }

    /// Inside an AppImage the AppRun-exported loader vars must be stripped from
    /// interactive shells (user tools would link the bundled libs), but only
    /// there: a normal install keeps them.
    #[test]
    #[cfg(unix)]
    fn scrub_appimage_env_strips_loader_vars_only_inside_appimage() {
        let seed = |cmd: &mut CommandBuilder| {
            cmd.env("LD_LIBRARY_PATH", "/tmp/.mount_x/usr/lib");
            cmd.env("LD_PRELOAD", "/tmp/.mount_x/hook.so");
        };

        let mut inside = CommandBuilder::new("/bin/zsh");
        seed(&mut inside);
        scrub_appimage_env(
            &mut inside,
            &env_of(&[("APPIMAGE", "/opt/solidifai.AppImage")]),
        );
        assert!(inside.get_env("LD_LIBRARY_PATH").is_none());
        assert!(inside.get_env("LD_PRELOAD").is_none());

        let mut appdir_only = CommandBuilder::new("/bin/zsh");
        seed(&mut appdir_only);
        scrub_appimage_env(&mut appdir_only, &env_of(&[("APPDIR", "/tmp/.mount_x")]));
        assert!(appdir_only.get_env("LD_LIBRARY_PATH").is_none());

        let mut outside = CommandBuilder::new("/bin/zsh");
        seed(&mut outside);
        scrub_appimage_env(&mut outside, &env_of(&[]));
        assert_eq!(
            outside.get_env("LD_LIBRARY_PATH").unwrap(),
            "/tmp/.mount_x/usr/lib"
        );
        assert_eq!(
            outside.get_env("LD_PRELOAD").unwrap(),
            "/tmp/.mount_x/hook.so"
        );
    }

    /// The explicit env map from the frontend is applied after the AppImage
    /// scrub, so a caller-provided LD_LIBRARY_PATH still wins.
    #[test]
    #[cfg(unix)]
    fn build_command_explicit_env_overrides_appimage_scrub() {
        let mut env = HashMap::new();
        env.insert("LD_LIBRARY_PATH".to_string(), "/custom/lib".to_string());
        let cmd = build_command_with_env(
            None,
            &[],
            None,
            Some(env),
            env_of(&[("APPIMAGE", "/opt/solidifai.AppImage")]),
        );
        assert_eq!(cmd.get_env("LD_LIBRARY_PATH").unwrap(), "/custom/lib");
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
