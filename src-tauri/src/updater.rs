//! Channel-aware (stable/beta) updater commands. Endpoints are chosen at call
//! time so the user's channel setting picks latest.json vs beta.json without a
//! rebuild. Download progress is streamed to the frontend via `updater://progress`.
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter};
use tauri_plugin_updater::UpdaterExt;

// Both channel manifests are mirrored to a single, permanent, NON-prerelease
// GitHub Release tagged `updater` (see the publish-manifest job in
// release-build.yml). We cannot use `/releases/latest/download/...` because that
// redirect resolves only to the latest non-prerelease, so the beta manifest
// (published from a pre-release) would 404. The fixed `updater` release gives both
// channels a stable URL.
const BASE: &str = "https://github.com/itsJeremyMax/solidifai/releases/download/updater";

#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Channel {
    Stable,
    Beta,
}

/// The static GitHub-release manifest URL for a channel.
pub fn endpoint_for(c: Channel) -> String {
    match c {
        Channel::Stable => format!("{BASE}/latest.json"),
        Channel::Beta => format!("{BASE}/beta.json"),
    }
}

fn build_updater(
    app: &AppHandle,
    channel: Channel,
) -> Result<tauri_plugin_updater::Updater, String> {
    let url = endpoint_for(channel)
        .parse()
        .map_err(|e| format!("bad updater endpoint: {e}"))?;
    app.updater_builder()
        .endpoints(vec![url])
        .map_err(|e| e.to_string())?
        .build()
        .map_err(|e| e.to_string())
}

#[derive(Serialize)]
pub struct UpdateInfo {
    pub available: bool,
    pub version: Option<String>,
    /// Release notes (the manifest `notes`/GitHub release body), when the manifest
    /// carries them. `None` for a manifest without a body or when no update exists.
    pub notes: Option<String>,
}

#[tauri::command]
pub async fn check_for_update(app: AppHandle, channel: Channel) -> Result<UpdateInfo, String> {
    let updater = build_updater(&app, channel)?;
    match updater.check().await {
        Ok(Some(u)) => Ok(UpdateInfo {
            available: true,
            version: Some(u.version.clone()),
            notes: u.body.clone(),
        }),
        // Manifest fetched and parsed, but not newer than us: genuinely current.
        // TargetNotFound is a manifest with no entry for this platform, which is
        // also "nothing to install for you" rather than a failure.
        Ok(None) | Err(tauri_plugin_updater::Error::TargetNotFound(_)) => Ok(UpdateInfo {
            available: false,
            version: None,
            notes: None,
        }),
        // The plugin collapses ANY non-2xx endpoint response into ReleaseNotFound,
        // so it means two different things per channel:
        //   • Beta   — a beta.json that doesn't exist yet is expected: no beta
        //              published means the user is on the newest beta (up to date).
        //   • Stable — latest.json is permanent, so a miss is a transient reach
        //              failure (offline, GitHub 5xx, a stale-CDN 403). Surfacing
        //              it as an error keeps a MANUAL check honest ("couldn't
        //              check") instead of a false "you're up to date"; background
        //              checks catch and swallow it, so they still stay silent.
        Err(tauri_plugin_updater::Error::ReleaseNotFound) => match channel {
            Channel::Beta => Ok(UpdateInfo {
                available: false,
                version: None,
                notes: None,
            }),
            Channel::Stable => {
                Err("Couldn't reach the update server. Check your connection and try again.".into())
            }
        },
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
pub async fn download_and_install(app: AppHandle, channel: Channel) -> Result<(), String> {
    let updater = build_updater(&app, channel)?;
    let Some(update) = updater.check().await.map_err(|e| e.to_string())? else {
        return Err("no update available".into());
    };
    let downloaded = Arc::new(AtomicU64::new(0));
    let app2 = app.clone();
    let dl = downloaded.clone();
    let bytes = update
        .download(
            move |chunk_length, content_length| {
                let total =
                    dl.fetch_add(chunk_length as u64, Ordering::Relaxed) + chunk_length as u64;
                let _ = app2.emit(
                    "updater://progress",
                    serde_json::json!({ "downloaded": total, "total": content_length }),
                );
            },
            || {},
        )
        .await
        .map_err(|e| e.to_string())?;
    // On Windows the plugin's install path launches the NSIS installer and then
    // terminates this process via std::process::exit(0) WITHOUT dispatching
    // RunEvent::Exit, so lib.rs's shutdown() would never run. Kill the workspace
    // engines + PTY agent shells here so the installer handoff can't orphan them.
    // If the handoff itself fails, everything is already dead (kill_all drained
    // the instance registry), so a plain Err would leave a zombie app whose UI
    // still says "ready". Relaunch instead: the user opted into close-and-update,
    // and this gives them back a working (un-updated) app; the failure is in the
    // rolling log and the update pill resurfaces on the next check.
    #[cfg(windows)]
    {
        crate::shutdown(&app);
        if let Err(e) = update.install(bytes) {
            tracing::error!("update install failed after engine shutdown; relaunching: {e}");
            app.restart();
        }
        return Ok(());
    }
    #[cfg(not(windows))]
    {
        update.install(bytes).map_err(|e| e.to_string())?;
        Ok(())
    }
}

/// Relaunch the app after an update, working around the single-instance guard.
///
/// `AppHandle::restart()` spawns the new process immediately, but
/// `tauri-plugin-single-instance` holds a lock until THIS process exits. The
/// fresh instance would start while we're still alive, see the held lock, forward
/// its launch to us, and exit itself — leaving nothing running (the "restart does
/// nothing after an update" bug). Instead we spawn a detached helper that waits
/// for this process to die (releasing the lock), then launches the freshly
/// installed app, and we exit now. Windows relaunches via the NSIS installer, so
/// this is a plain fallback there.
#[tauri::command]
pub fn relaunch_for_update(app: AppHandle) -> Result<(), String> {
    #[cfg(not(target_os = "windows"))]
    {
        use std::os::unix::process::CommandExt;

        let pid = std::process::id();
        let (launch, target) = relaunch_command()?;
        // Poll until our PID is gone so the single-instance lock is released, then
        // launch. `process_group(0)` detaches the helper so our exit can't signal it.
        // The launch snippet references the target as `$1`, passed as a raw argument
        // so `sh` never re-expands `$`/backtick/`\` etc. in an unusual install path.
        let script = format!("while kill -0 {pid} 2>/dev/null; do sleep 0.2; done; {launch}");
        std::process::Command::new("/bin/sh")
            .arg("-c")
            .arg(script)
            .arg("sh") // $0
            .arg(&target) // $1 — raw OsStr, never re-parsed by the shell
            .process_group(0)
            .spawn()
            .map_err(|e| format!("failed to spawn the relauncher: {e}"))?;
        // Exit cleanly so RunEvent::Exit reaps engines and the lock releases.
        app.exit(0);
        return Ok(());
    }
    #[cfg(target_os = "windows")]
    {
        app.restart();
    }
    #[allow(unreachable_code)]
    Ok(())
}

/// The launch snippet (referencing the target as `$1`) plus the raw target path to
/// pass as that argument, per platform. Keeping the path out of the script text
/// avoids any shell re-expansion of characters legal in a filesystem path.
#[cfg(target_os = "macos")]
fn relaunch_command() -> Result<(&'static str, std::ffi::OsString), String> {
    // current_exe is <App>.app/Contents/MacOS/<bin>; launch the .app bundle so it
    // starts as a proper GUI app via LaunchServices, not a bare binary. `exec`
    // replaces the shell so no stray process lingers.
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    let bundle = exe
        .ancestors()
        .find(|p| p.extension().is_some_and(|e| e == "app"))
        .ok_or("could not locate the .app bundle to relaunch")?;
    Ok(("exec open \"$1\"", bundle.as_os_str().to_os_string()))
}

#[cfg(target_os = "linux")]
fn relaunch_command() -> Result<(&'static str, std::ffi::OsString), String> {
    // Prefer the outer AppImage path when packaged that way; else re-exec the binary.
    let target = match std::env::var_os("APPIMAGE") {
        Some(v) => v,
        None => std::env::current_exe()
            .map_err(|e| e.to_string())?
            .into_os_string(),
    };
    Ok(("exec \"$1\"", target))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn endpoint_for_stable_and_beta() {
        assert!(endpoint_for(Channel::Stable).ends_with("/download/updater/latest.json"));
        assert!(endpoint_for(Channel::Beta).ends_with("/download/updater/beta.json"));
    }
}
