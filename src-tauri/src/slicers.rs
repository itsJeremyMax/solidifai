//! Slicer detection, profiles, and the user-overridable binary store.
//!
//! Provider-agnostic by design: a small [`Provider`] registry drives detection
//! and the Settings UI, so adding a slicer is a new registry entry (today only
//! OrcaSlicer is wired). The user can override a provider's executable path; the
//! override is persisted to `<app_config_dir>/slicers.json` — the same file the
//! engine reads — so native detection, the engine, and the Settings UI all agree.

use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

use crate::store::{self, ReadResult};

const SLICERS_FILE: &str = "slicers.json";
const SCHEMA: u32 = 1;
/// Bound on the `--version` probe so a slicer that ignores the flag (and would
/// otherwise launch its GUI) can't wedge a command thread.
const VERSION_TIMEOUT: Duration = Duration::from_secs(4);

// -- Provider registry -----------------------------------------------------

/// A supported slicer. `default_candidates` are the OS install locations probed
/// when there is no override; `config_dir` is where the slicer keeps its user
/// printer/filament profiles.
struct Provider {
    id: &'static str,
    label: &'static str,
    default_candidates: fn() -> Vec<PathBuf>,
    config_dir: fn() -> Option<PathBuf>,
}

const PROVIDERS: &[Provider] = &[Provider {
    id: "orca",
    label: "OrcaSlicer",
    default_candidates: orca_candidates,
    config_dir: orca_config_dir,
}];

fn provider(id: &str) -> Option<&'static Provider> {
    PROVIDERS.iter().find(|p| p.id == id)
}

/// OrcaSlicer's user config dir, matching the engine's OrcaProvider (macOS
/// Application Support, Windows APPDATA, Linux XDG_CONFIG_HOME/.config).
fn orca_config_dir() -> Option<PathBuf> {
    dirs::config_dir().map(|d| d.join("OrcaSlicer"))
}

/// Default OrcaSlicer executable candidates for this OS (mirrors the engine).
fn orca_candidates() -> Vec<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        vec![PathBuf::from(
            "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer",
        )]
    }
    #[cfg(target_os = "windows")]
    {
        let mut out = Vec::new();
        for var in ["PROGRAMFILES", "PROGRAMFILES(X86)"] {
            if let Some(pf) = std::env::var_os(var) {
                out.push(Path::new(&pf).join("OrcaSlicer").join("orca-slicer.exe"));
                out.push(Path::new(&pf).join("Bambu Studio").join("orca-slicer.exe"));
            }
        }
        out
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let mut out = Vec::new();
        if let Some(home) = dirs::home_dir() {
            out.push(home.join("OrcaSlicer.AppImage"));
        }
        out.push(PathBuf::from("/opt/OrcaSlicer/orca-slicer"));
        out.push(PathBuf::from("/usr/local/bin/orca-slicer"));
        out
    }
}

// -- Override store (slicers.json) -----------------------------------------

/// Per-provider override: `{ "executablePath": "..." }`. Absent = auto-detect.
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
struct Override {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    executable_path: Option<String>,
}

/// Read the override map (`{ schema, slicers: { <id>: {...} } }`). Never errors.
fn load_overrides(dir: &Path) -> std::collections::BTreeMap<String, Override> {
    match store::read_json(dir, SLICERS_FILE) {
        ReadResult::Ok(v) => v
            .get("slicers")
            .and_then(|s| serde_json::from_value(s.clone()).ok())
            .unwrap_or_default(),
        ReadResult::Missing | ReadResult::Corrupt => Default::default(),
    }
}

fn save_overrides(
    dir: &Path,
    map: &std::collections::BTreeMap<String, Override>,
) -> Result<(), String> {
    let value = serde_json::json!({ "schema": SCHEMA, "slicers": map });
    store::write_json_atomic(dir, SLICERS_FILE, &value)
}

// -- Detection -------------------------------------------------------------

/// Resolve a configured path to a runnable executable file, unwrapping a macOS
/// `.app` bundle to its inner binary. Returns None when nothing usable is there.
fn resolve_executable(path: &Path) -> Option<PathBuf> {
    if path.is_file() {
        return Some(path.to_path_buf());
    }
    #[cfg(target_os = "macos")]
    if path.extension().and_then(|e| e.to_str()) == Some("app") {
        let macos = path.join("Contents/MacOS");
        // Prefer a binary named after the bundle; else the first file inside.
        if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
            let named = macos.join(stem);
            if named.is_file() {
                return Some(named);
            }
        }
        if let Ok(entries) = std::fs::read_dir(&macos) {
            for e in entries.flatten() {
                if e.path().is_file() {
                    return Some(e.path());
                }
            }
        }
    }
    None
}

/// Run `<exe> --version`, bounded by [`VERSION_TIMEOUT`], and return the last
/// whitespace token of stdout (OrcaSlicer prints e.g. `OrcaSlicer 2.1.1`).
fn probe_version(exe: &Path) -> Option<String> {
    let mut child = Command::new(exe)
        .arg("--version")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;

    let deadline = Instant::now() + VERSION_TIMEOUT;
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => break,
            Ok(Some(_)) => return None,
            Ok(None) if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(50)),
            Err(_) => return None,
        }
    }

    let mut out = String::new();
    child.stdout.take()?.read_to_string(&mut out).ok()?;
    out.split_whitespace().last().map(str::to_string)
}

/// Detection result for one provider.
struct Detected {
    found: bool,
    executable: Option<String>,
    version: Option<String>,
}

/// Probe a provider: the override path (if any) is tried before the OS defaults.
fn detect(p: &Provider, override_path: Option<&str>) -> Detected {
    let candidates = override_path
        .map(PathBuf::from)
        .into_iter()
        .chain((p.default_candidates)());
    for c in candidates {
        if let Some(exe) = resolve_executable(&c) {
            let version = probe_version(&exe);
            return Detected {
                found: true,
                executable: Some(exe.to_string_lossy().into_owned()),
                version,
            };
        }
    }
    Detected {
        found: false,
        executable: None,
        version: None,
    }
}

// -- Profiles --------------------------------------------------------------

/// Slicer status + profile catalogue for the add-connection modal.
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct ProfileSet {
    /// True when the slicer executable was found (override or auto-detected).
    pub found: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    pub printers: Vec<String>,
    pub filaments: Vec<String>,
    pub processes: Vec<String>,
}

/// Preset names (`*.json` stems) for one category across system + user scopes.
/// Real Orca layout: `<config>/<scope>/<group>/<category>/*.json` where group is a
/// vendor (system) or account id (user); the printer category is named `machine`.
fn profile_names(config: &Path, category: &str) -> Vec<String> {
    let mut names = std::collections::BTreeSet::new();
    for scope in ["system", "user"] {
        let scope_dir = config.join(scope);
        let Ok(groups) = std::fs::read_dir(&scope_dir) else {
            continue;
        };
        for group in groups.filter_map(|e| e.ok()) {
            let cat_dir = group.path().join(category);
            let Ok(entries) = std::fs::read_dir(&cat_dir) else {
                continue;
            };
            for e in entries.filter_map(|e| e.ok()) {
                let p = e.path();
                if p.extension().and_then(|x| x.to_str()) == Some("json") {
                    if let Some(s) = p.file_stem().and_then(|s| s.to_str()) {
                        names.insert(s.to_string());
                    }
                }
            }
        }
    }
    names.into_iter().collect()
}

// -- Settings view ---------------------------------------------------------

/// One row of the Settings → Slicers list.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct SlicerEntry {
    pub id: String,
    pub label: String,
    pub found: bool,
    /// The resolved executable in use (override or auto-detected).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub executable: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    /// The user-set override, if any (null means "auto-detect").
    #[serde(skip_serializing_if = "Option::is_none")]
    pub override_path: Option<String>,
}

fn config_view(dir: &Path) -> Vec<SlicerEntry> {
    let overrides = load_overrides(dir);
    PROVIDERS
        .iter()
        .map(|p| {
            let ov = overrides.get(p.id).and_then(|o| o.executable_path.clone());
            let d = detect(p, ov.as_deref());
            SlicerEntry {
                id: p.id.into(),
                label: p.label.into(),
                found: d.found,
                executable: d.executable,
                version: d.version,
                override_path: ov,
            }
        })
        .collect()
}

// -- Tauri commands --------------------------------------------------------

/// Slicer status + profiles for the active fabrication provider (OrcaSlicer),
/// honoring any configured override.
#[tauri::command]
pub fn get_slicer_profiles(app: AppHandle) -> Result<ProfileSet, String> {
    let dir = crate::workspaces::config_dir(&app)?;
    let Some(p) = provider("orca") else {
        return Ok(ProfileSet::default());
    };
    let ov = load_overrides(&dir)
        .get(p.id)
        .and_then(|o| o.executable_path.clone());
    let d = detect(p, ov.as_deref());
    let mut set = ProfileSet {
        found: d.found,
        version: d.version,
        ..Default::default()
    };
    if let Some(config) = (p.config_dir)() {
        set.printers = profile_names(&config, "machine");
        set.filaments = profile_names(&config, "filament");
        set.processes = profile_names(&config, "process");
    }
    Ok(set)
}

/// The supported slicers with their detected status + override, for Settings.
#[tauri::command]
pub fn get_slicer_config(app: AppHandle) -> Result<Vec<SlicerEntry>, String> {
    Ok(config_view(&crate::workspaces::config_dir(&app)?))
}

/// Set (or clear, when `executable_path` is null) a provider's binary override,
/// then return the refreshed config. A macOS `.app` is resolved to its binary.
#[tauri::command]
pub fn set_slicer_override(
    app: AppHandle,
    id: String,
    executable_path: Option<String>,
) -> Result<Vec<SlicerEntry>, String> {
    if provider(&id).is_none() {
        return Err(format!("unknown slicer '{id}'"));
    }
    let dir = crate::workspaces::config_dir(&app)?;
    let mut overrides = load_overrides(&dir);
    match executable_path.filter(|s| !s.trim().is_empty()) {
        Some(raw) => {
            // Store the resolved binary so the engine gets a runnable path; fall
            // back to the raw input (so Settings echoes it and shows "not found").
            let stored = resolve_executable(Path::new(&raw))
                .map(|p| p.to_string_lossy().into_owned())
                .unwrap_or(raw);
            overrides.insert(
                id,
                Override {
                    executable_path: Some(stored),
                },
            );
        }
        None => {
            overrides.remove(&id);
        }
    }
    save_overrides(&dir, &overrides)?;
    Ok(config_view(&dir))
}

/// Native file picker for a slicer executable (a macOS `.app` is accepted too).
#[tauri::command]
pub async fn pick_slicer_binary(app: AppHandle) -> Option<String> {
    tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .blocking_pick_file()
            .and_then(|p| p.into_path().ok())
            .map(|p| p.to_string_lossy().into_owned())
    })
    .await
    .ok()
    .flatten()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-slicers-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn detect_prefers_override_over_defaults() {
        let dir = tmp_dir("override");
        let exe = dir.join("my-orca");
        std::fs::write(&exe, b"#!/bin/sh\necho OrcaSlicer 9.9.9\n").unwrap();
        let p = provider("orca").unwrap();
        let d = detect(p, Some(exe.to_str().unwrap()));
        assert!(d.found);
        assert_eq!(d.executable.as_deref(), Some(exe.to_str().unwrap()));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn detect_missing_override_reports_not_found() {
        // A bogus override with (on this CI box) no real Orca installed.
        let p = provider("orca").unwrap();
        let d = detect(p, Some("/no/such/slicer"));
        // `found` depends on whether a default candidate exists on the host; the
        // bogus override itself must not be what's reported.
        assert_ne!(d.executable.as_deref(), Some("/no/such/slicer"));
    }

    #[test]
    fn override_store_round_trips_and_clears() {
        let dir = tmp_dir("store");
        let mut map = std::collections::BTreeMap::new();
        map.insert(
            "orca".to_string(),
            Override {
                executable_path: Some("/x/orca".into()),
            },
        );
        save_overrides(&dir, &map).unwrap();
        assert_eq!(
            load_overrides(&dir)
                .get("orca")
                .unwrap()
                .executable_path
                .as_deref(),
            Some("/x/orca")
        );
        // Persisted under the engine-readable envelope.
        let raw = std::fs::read_to_string(dir.join(SLICERS_FILE)).unwrap();
        let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(v["schema"], SCHEMA);
        assert_eq!(v["slicers"]["orca"]["executablePath"], "/x/orca");

        map.remove("orca");
        save_overrides(&dir, &map).unwrap();
        assert!(!load_overrides(&dir).contains_key("orca"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn config_view_lists_registered_providers() {
        let dir = tmp_dir("view");
        let view = config_view(&dir);
        assert_eq!(view.len(), PROVIDERS.len());
        assert_eq!(view[0].id, "orca");
        assert!(view[0].override_path.is_none());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn profile_names_lists_json_names_only() {
        let dir = tmp_dir("profiles2");
        let machines = dir.join("user").join("default").join("machine");
        std::fs::create_dir_all(&machines).unwrap();
        std::fs::write(machines.join("Voron 0.2.json"), "{}").unwrap();
        std::fs::write(machines.join("Prusa MK4.json"), "{}").unwrap();
        std::fs::write(machines.join("notes.txt"), "x").unwrap();
        let mut got = profile_names(&dir, "machine");
        got.sort();
        assert_eq!(got, vec!["Prusa MK4".to_string(), "Voron 0.2".to_string()]);
        assert!(profile_names(&dir, "filament").is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn profile_names_use_real_layout_and_include_processes() {
        let dir = tmp_dir("profiles");
        let w = |rel: &str| {
            let p = dir.join(rel);
            std::fs::create_dir_all(p.parent().unwrap()).unwrap();
            std::fs::write(&p, "{}").unwrap();
        };
        w("system/BBL/machine/X1C.json");
        w("user/default/process/PETG.json");
        w("user/482203983/filament/My PLA.json");

        let mut printers = profile_names(&dir, "machine");
        let processes = profile_names(&dir, "process");
        let filaments = profile_names(&dir, "filament");
        printers.sort();
        assert_eq!(printers, vec!["X1C".to_string()]);
        assert_eq!(processes, vec!["PETG".to_string()]);
        assert_eq!(filaments, vec!["My PLA".to_string()]);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
