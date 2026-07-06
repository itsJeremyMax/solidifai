//! Process-wide observability: a tracing subscriber (compact stderr + a
//! daily-rolling file in the OS log dir), a panic hook that records panics, and
//! the command the webview uses to forward its own uncaught errors here. So a
//! crash in any layer (shell, engine spawn, or frontend) leaves a trail on disk.

use std::sync::OnceLock;

use tauri::{AppHandle, Manager};
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::{fmt, EnvFilter};

// The non-blocking writer's guard must outlive the process to flush on exit;
// parked here for the app lifetime.
static GUARD: OnceLock<WorkerGuard> = OnceLock::new();

/// Initialize tracing once at startup. Level is `info` by default, overridable
/// via the `SOLIDIFAI_LOG` env var (e.g. `SOLIDIFAI_LOG=debug`). File logging is
/// best-effort: if the log dir cannot be resolved, stderr still works.
pub fn init(app: &AppHandle) {
    let filter =
        EnvFilter::try_from_env("SOLIDIFAI_LOG").unwrap_or_else(|_| EnvFilter::new("info"));

    let file_layer = app.path().app_log_dir().ok().and_then(|dir| {
        std::fs::create_dir_all(&dir).ok()?;
        let appender = tracing_appender::rolling::daily(&dir, "solidifai.log");
        let (non_blocking, guard) = tracing_appender::non_blocking(appender);
        // If init runs twice (it should not), keep the first guard.
        let _ = GUARD.set(guard);
        Some(fmt::layer().with_ansi(false).with_writer(non_blocking))
    });

    // Option<Layer> is itself a no-op Layer when None, so this composes whether
    // or not the file layer is present.
    tracing_subscriber::registry()
        .with(filter)
        .with(fmt::layer().compact().with_writer(std::io::stderr))
        .with(file_layer)
        .init();

    install_panic_hook();
}

/// Log panics (message + location) through tracing before the default hook runs,
/// so an unwind that would otherwise vanish to stderr lands in the log file too.
fn install_panic_hook() {
    let default = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let location = info
            .location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_else(|| "unknown".to_string());
        let message = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "panic".to_string());
        tracing::error!(location = %location, "panic: {message}");
        default(info);
    }));
}

/// Record an uncaught error forwarded from the webview (window.onerror /
/// unhandledrejection / error boundary) into the shared log.
#[tauri::command]
pub fn log_frontend_error(message: String, source: Option<String>, stack: Option<String>) {
    tracing::error!(
        source = source.unwrap_or_default(),
        stack = stack.unwrap_or_default(),
        "frontend error: {message}"
    );
}
