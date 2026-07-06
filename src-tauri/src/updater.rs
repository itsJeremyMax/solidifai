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
}

#[tauri::command]
pub async fn check_for_update(app: AppHandle, channel: Channel) -> Result<UpdateInfo, String> {
    let updater = build_updater(&app, channel)?;
    match updater.check().await {
        Ok(Some(u)) => Ok(UpdateInfo {
            available: true,
            version: Some(u.version.clone()),
        }),
        // The plugin skips ANY non-2xx endpoint response without recording an
        // error, so ReleaseNotFound covers both a manifest that doesn't exist
        // yet (Beta before any prerelease published beta.json) and a transient
        // GitHub 5xx; the two are indistinguishable here. TargetNotFound is a
        // manifest with no entry for this platform. Treat all of it as "no
        // update" rather than flashing a failure in the top bar.
        Ok(None)
        | Err(
            tauri_plugin_updater::Error::ReleaseNotFound
            | tauri_plugin_updater::Error::TargetNotFound(_),
        ) => Ok(UpdateInfo {
            available: false,
            version: None,
        }),
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
    update
        .download_and_install(
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
    Ok(())
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
