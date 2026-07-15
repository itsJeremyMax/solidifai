//! Global + workspace manufacturing profile: the sole writer (Rust) of
//! `manufacturing-profile.json`. Mirrors `materials.rs` for file I/O. The engine
//! (Python) only READS the profile; its writes are delegated here over the
//! control channel (`control.rs`). Validation + merge live here, in one place.

use std::path::Path;

use parking_lot::Mutex;
use serde::Serialize;
use serde_json::{json, Value};

use crate::store;

const PROFILE_FILE: &str = "manufacturing-profile.json";
const SCHEMA: i64 = 2;

/// Builtin defaults, embedded from the shared asset (same file the Python engine reads).
const DEFAULTS: &str =
    include_str!("../../engine/solidifai_engine/manufacturing_profile_defaults.json");

/// Serializes every write (GUI command thread + control-socket thread) so the two
/// callers can never race the read-merge-write on the same file. The payoff of
/// "one writer": a single in-process lock is enough.
static WRITE_LOCK: Mutex<()> = Mutex::new(());

const FITS: [&str; 3] = ["loose", "normal", "tight"];
// (section, sub, min, max) inclusive — mirrors manufacturing_profile.py _BOUNDS.
const BOUNDS: &[(&str, &str, f64, f64)] = &[
    ("design", "wallMm", 0.1, 100.0),
    ("design", "filletMm", 0.0, 100.0),
    ("design", "minFeatureMm", 0.05, 100.0),
    ("fits", "looseMm", 0.0, 5.0),
    ("fits", "normalMm", 0.0, 5.0),
    ("fits", "tightMm", 0.0, 5.0),
    ("process", "nozzleMm", 0.1, 2.0),
    ("process", "layerMm", 0.02, 1.0),
    ("process", "overhangDeg", 0.0, 90.0),
    ("process", "infillPct", 0.0, 100.0),
    ("fabrication", "nozzleTempC", 150.0, 400.0),
    ("fabrication", "bedTempC", 0.0, 150.0),
    ("fabrication", "filamentCostPerKg", 0.0, 100000.0),
];

#[derive(Clone, Copy)]
pub enum Scope {
    Global,
    Workspace,
}

impl Scope {
    pub fn parse(s: &str) -> Result<Scope, String> {
        match s {
            "global" => Ok(Scope::Global),
            "workspace" => Ok(Scope::Workspace),
            other => Err(format!(
                "scope must be 'global' or 'workspace', got {other:?}"
            )),
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaterialEcho {
    pub id: String,
    pub label: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProfileView {
    pub resolved: Value,
    pub overrides: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub global_overrides: Option<Value>,
    pub material: MaterialEcho,
}

fn builtin() -> Value {
    serde_json::from_str(DEFAULTS).unwrap_or_else(|_| json!({}))
}

/// The sparse overrides at one layer dir ({} if missing/corrupt). Strips `schema`.
fn load_overrides(dir: &Path) -> Value {
    match store::read_json(dir, PROFILE_FILE) {
        store::ReadResult::Ok(mut v) => {
            if let Some(o) = v.as_object_mut() {
                o.remove("schema");
            }
            normalize_profile(v)
        }
        _ => json!({}),
    }
}

/// Schema 1 stored process fields beside `kind`; schema 2 makes the process id
/// explicit and nests process-specific settings. Reads remain migration-safe.
fn normalize_profile(mut value: Value) -> Value {
    let Some(obj) = value.as_object_mut() else {
        return value;
    };
    obj.remove("schema");
    let Some(process) = obj.get_mut("process").and_then(Value::as_object_mut) else {
        return value;
    };
    if process.contains_key("id") {
        let id = process.remove("id").unwrap();
        let settings = process
            .remove("settings")
            .filter(Value::is_object)
            .unwrap_or_else(|| json!({}));
        *process = serde_json::Map::from_iter([
            (String::from("id"), id),
            (String::from("settings"), settings),
        ]);
        return value;
    }
    let id = process.remove("kind");
    let settings = Value::Object(std::mem::take(process));
    *process = serde_json::Map::from_iter(
        id.map(|id| (String::from("id"), id))
            .into_iter()
            .chain([(String::from("settings"), settings)]),
    );
    value
}

/// Deep-merge `override_` into `base` (objects merge recursively; scalars/arrays
/// replace). Mirrors manufacturing_profile.py's _deep_merge.
pub fn json_deep_merge(base: &mut Value, override_: &Value) {
    if let (Some(b), Some(o)) = (base.as_object_mut(), override_.as_object()) {
        for (k, v) in o {
            match b.get_mut(k) {
                Some(existing) if existing.is_object() && v.is_object() => {
                    json_deep_merge(existing, v)
                }
                _ => {
                    b.insert(k.clone(), v.clone());
                }
            }
        }
    }
}

/// Resolve builtin <= global <= (workspace, if any).
pub fn resolve(config_dir: &Path, workspace_root: Option<&Path>) -> Value {
    let mut prof = builtin();
    if let Some(o) = prof.as_object_mut() {
        o.remove("schema");
    }
    json_deep_merge(&mut prof, &load_overrides(config_dir));
    if let Some(ws) = workspace_root {
        json_deep_merge(&mut prof, &load_overrides(ws));
    }
    if let Some(o) = prof.as_object_mut() {
        o.insert("schema".into(), json!(SCHEMA));
    }
    prof
}

/// The effective default material (id, label), echoed from the materials library.
pub fn resolved_default_material(config_dir: &Path, workspace_root: &Path) -> (String, String) {
    let g = crate::materials::load_global(config_dir);
    let w = crate::materials::load_workspace(workspace_root);
    let id = w
        .default
        .clone()
        .or_else(|| g.default.clone())
        .unwrap_or_else(|| "pla".to_string());
    let label = w
        .materials
        .iter()
        .chain(g.materials.iter())
        .find(|m| m.id == id)
        .map(|m| m.label.clone())
        .unwrap_or_else(|| id.clone());
    (id, label)
}

/// Validate a sparse override object (the merged result, schema-free). Mirrors
/// manufacturing_profile.py validate(): unknown keys, bad enums, out-of-range,
/// reject `material`/`schema`.
pub fn validate(values: &Value) -> Result<(), String> {
    let obj = values
        .as_object()
        .ok_or("manufacturing profile must be an object")?;
    if obj.contains_key("schema") {
        return Err("schema is managed internally; omit it".into());
    }
    if obj.contains_key("material") {
        return Err(
            "material is owned by the materials library, not the manufacturing profile".into(),
        );
    }
    let template = builtin();
    let template = template.as_object().unwrap();
    for (key, section) in obj {
        let allowed = template
            .get(key)
            .and_then(|v| v.as_object())
            .ok_or_else(|| format!("unknown manufacturing-profile key {key:?}"))?;
        let sec = section
            .as_object()
            .ok_or_else(|| format!("{key:?} must be an object"))?;
        for (sub, val) in sec {
            if !allowed.contains_key(sub) {
                return Err(format!("unknown {key}.{sub} key"));
            }
            if key == "design" && sub == "fit" {
                let s = val.as_str().unwrap_or("");
                if !FITS.contains(&s) {
                    return Err(format!("design.fit must be one of {FITS:?}, got {val}"));
                }
            }
            if key == "process" && sub == "id" {
                let s = val.as_str().unwrap_or("");
                if !crate::materials::process_exists(s) {
                    return Err(format!("unknown process.id {val}"));
                }
            }
            if key == "process" && sub == "settings" {
                let settings = val
                    .as_object()
                    .ok_or("process.settings must be an object")?;
                let process_id = sec.get("id").and_then(Value::as_str).unwrap_or("fdm");
                for (setting, value) in settings {
                    if !crate::materials::profile_settings(process_id).contains(setting) {
                        return Err(format!(
                            "process {process_id:?} has no supported profile settings"
                        ));
                    }
                    if let Some((_, _, lo, hi)) = BOUNDS
                        .iter()
                        .find(|(k, s, _, _)| *k == "process" && *s == setting)
                    {
                        let n = value.as_f64().ok_or_else(|| {
                            format!("process.settings.{setting} must be a number")
                        })?;
                        if n < *lo || n > *hi {
                            return Err(format!(
                                "process.settings.{setting} must be in [{lo}, {hi}], got {n}"
                            ));
                        }
                    }
                }
            }
            if let Some((_, _, lo, hi)) = BOUNDS.iter().find(|(k, s, _, _)| k == key && s == sub) {
                let n = val
                    .as_f64()
                    .ok_or_else(|| format!("{key}.{sub} must be a number, got {val}"))?;
                if n < *lo || n > *hi {
                    return Err(format!("{key}.{sub} must be in [{lo}, {hi}], got {n}"));
                }
            }
        }
    }
    Ok(())
}

/// Remove a `section.sub` dotted key from a sparse object; prune emptied sections.
fn remove_dotted(obj: &mut Value, dotted: &str) {
    let Some((section, sub)) = dotted.split_once('.') else {
        return;
    };
    if let Some(map) = obj.as_object_mut() {
        let mut empty = false;
        if let Some(sec) = map.get_mut(section).and_then(|v| v.as_object_mut()) {
            if section == "process" && sub != "id" && sub != "settings" {
                if let Some(settings) = sec.get_mut("settings").and_then(Value::as_object_mut) {
                    settings.remove(sub);
                    if settings.is_empty() {
                        sec.remove("settings");
                    }
                }
            } else {
                sec.remove(sub);
            }
            empty = sec.is_empty();
        }
        if empty {
            map.remove(section);
        }
    }
}

/// The single write entry point: lock -> load layer sparse -> merge `set` ->
/// delete `unset` -> validate -> atomic write (with schema) -> return resolved.
pub fn write(
    config_dir: &Path,
    scope: Scope,
    workspace_root: Option<&Path>,
    set: &Value,
    unset: &[String],
) -> Result<Value, String> {
    let _guard = WRITE_LOCK.lock();
    let target_dir: &Path = match scope {
        Scope::Global => config_dir,
        Scope::Workspace => workspace_root.ok_or("no workspace is open")?,
    };
    let mut merged = load_overrides(target_dir);
    let set = normalize_profile(set.clone());
    json_deep_merge(&mut merged, &set);
    for key in unset {
        remove_dotted(&mut merged, key);
    }
    validate(&merged)?;
    let mut payload = merged.clone();
    if let Some(o) = payload.as_object_mut() {
        o.insert("schema".into(), json!(SCHEMA));
    }
    store::write_json_atomic(target_dir, PROFILE_FILE, &payload)?;
    Ok(resolve(config_dir, workspace_root))
}

/// Build the unified GUI view for a scope: resolved + this layer's overrides +
/// (for workspace) the global overrides for inheritance attribution + material echo.
pub fn view(
    config_dir: &Path,
    scope: Scope,
    workspace_root: Option<&Path>,
) -> Result<ProfileView, String> {
    let (resolved, overrides, global_overrides) = match scope {
        Scope::Global => (resolve(config_dir, None), load_overrides(config_dir), None),
        Scope::Workspace => {
            let ws = workspace_root.ok_or("no workspace is open")?;
            (
                resolve(config_dir, Some(ws)),
                load_overrides(ws),
                Some(load_overrides(config_dir)),
            )
        }
    };
    let ws_for_mat = workspace_root.unwrap_or(config_dir);
    let (id, label) = resolved_default_material(config_dir, ws_for_mat);
    Ok(ProfileView {
        resolved,
        overrides,
        global_overrides,
        material: MaterialEcho { id, label },
    })
}

// -- Tauri commands (GUI-facing) --------------------------------------------

use tauri::{AppHandle, State};

use crate::provision::WorkspaceState;
use crate::workspaces::config_dir;

#[tauri::command]
pub fn get_global_manufacturing_profile(app: AppHandle) -> Result<ProfileView, String> {
    view(&config_dir(&app)?, Scope::Global, None)
}

#[tauri::command]
pub fn set_global_manufacturing_profile(
    app: AppHandle,
    set: Value,
    unset: Vec<String>,
) -> Result<ProfileView, String> {
    let cfg = config_dir(&app)?;
    write(&cfg, Scope::Global, None, &set, &unset)?;
    view(&cfg, Scope::Global, None)
}

#[tauri::command]
pub fn get_workspace_manufacturing_profile(
    app: AppHandle,
    state: State<'_, WorkspaceState>,
) -> Result<ProfileView, String> {
    let cfg = config_dir(&app)?;
    let root = state.focused_root().ok_or("no workspace is open")?;
    view(&cfg, Scope::Workspace, Some(&root))
}

#[tauri::command]
pub fn set_workspace_manufacturing_profile(
    app: AppHandle,
    state: State<'_, WorkspaceState>,
    set: Value,
    unset: Vec<String>,
) -> Result<ProfileView, String> {
    let cfg = config_dir(&app)?;
    let root = state.focused_root().ok_or("no workspace is open")?;
    write(&cfg, Scope::Workspace, Some(&root), &set, &unset)?;
    view(&cfg, Scope::Workspace, Some(&root))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn tmp(tag: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("mfg-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn resolve_layers_builtin_global_workspace() {
        let cfg = tmp("res-cfg");
        let ws = tmp("res-ws");
        std::fs::write(
            cfg.join("manufacturing-profile.json"),
            r#"{"design":{"wallMm":3.0}}"#,
        )
        .unwrap();
        std::fs::write(
            ws.join("manufacturing-profile.json"),
            r#"{"design":{"wallMm":1.6}}"#,
        )
        .unwrap();
        let r = resolve(&cfg, Some(&ws));
        assert_eq!(r["design"]["wallMm"].as_f64(), Some(1.6)); // workspace wins
        assert_eq!(r["design"]["minFeatureMm"].as_f64(), Some(1.0)); // builtin fills in
        assert_eq!(r["schema"].as_i64(), Some(2));
    }

    #[test]
    fn resolve_global_only_ignores_workspace() {
        let cfg = tmp("g-cfg");
        std::fs::write(
            cfg.join("manufacturing-profile.json"),
            r#"{"process":{"infillPct":35}}"#,
        )
        .unwrap();
        let r = resolve(&cfg, None);
        assert_eq!(r["process"]["settings"]["infillPct"].as_f64(), Some(35.0));
    }

    #[test]
    fn sparse_schema_one_process_settings_keep_global_process() {
        let cfg = tmp("sparse-cfg");
        let ws = tmp("sparse-ws");
        std::fs::write(
            cfg.join(PROFILE_FILE),
            r#"{"schema":1,"process":{"kind":"cnc"}}"#,
        )
        .unwrap();
        std::fs::write(
            ws.join(PROFILE_FILE),
            r#"{"schema":1,"process":{"overhangDeg":55}}"#,
        )
        .unwrap();
        let resolved = resolve(&cfg, Some(&ws));
        assert_eq!(resolved["process"]["id"], "cnc");
        assert_eq!(resolved["process"]["settings"]["overhangDeg"], 55);
    }

    #[test]
    fn validate_rejects_unknown_enum_range_material_schema() {
        assert!(validate(&json!({"bogus": {}})).is_err());
        assert!(validate(&json!({"design": {"fit": "snug"}})).is_err());
        assert!(validate(&json!({"process": {"overhangDeg": 120}})).is_err()); // > 90
        assert!(validate(&json!({"material": "petg"})).is_err());
        assert!(validate(&json!({"schema": 1})).is_err());
        assert!(validate(&json!({"design": {"fit": "tight", "wallMm": 1.8}})).is_ok());
    }

    #[test]
    fn write_merges_then_unset_resets() {
        let cfg = tmp("w-cfg");
        let ws = tmp("w-ws");
        // set two fields
        write(
            &cfg,
            Scope::Workspace,
            Some(&ws),
            &json!({"design": {"wallMm": 1.6, "filletMm": 2.0}}),
            &[],
        )
        .unwrap();
        let on_disk: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(ws.join("manufacturing-profile.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(on_disk["design"]["wallMm"].as_f64(), Some(1.6));
        assert_eq!(on_disk["schema"].as_i64(), Some(2));
        // unset one — it drops back to inherited; the other override stays
        write(
            &cfg,
            Scope::Workspace,
            Some(&ws),
            &json!({}),
            &["design.wallMm".to_string()],
        )
        .unwrap();
        let after: serde_json::Value = serde_json::from_str(
            &std::fs::read_to_string(ws.join("manufacturing-profile.json")).unwrap(),
        )
        .unwrap();
        assert!(after["design"].get("wallMm").is_none());
        assert_eq!(after["design"]["filletMm"].as_f64(), Some(2.0));
    }

    #[test]
    fn write_rejects_invalid_without_touching_disk() {
        let cfg = tmp("inv-cfg");
        let ws = tmp("inv-ws");
        assert!(write(
            &cfg,
            Scope::Workspace,
            Some(&ws),
            &json!({"process": {"overhangDeg": 999}}),
            &[]
        )
        .is_err());
        assert!(!ws.join("manufacturing-profile.json").exists());
    }

    /// Cross-runtime parity fixture, shared with the Python resolver's test so
    /// the two `resolve` implementations can never silently drift.
    const PARITY_CASES: &str =
        include_str!("../../engine/tests/manufacturing_profile_parity_cases.json");

    /// JSON equality that treats numbers by value (45 == 45.0), so the int/float
    /// encoding of the fixture vs the asset never causes spurious failures.
    fn json_num_eq(a: &serde_json::Value, b: &serde_json::Value) -> bool {
        use serde_json::Value;
        match (a, b) {
            (Value::Object(x), Value::Object(y)) => {
                x.len() == y.len()
                    && x.iter()
                        .all(|(k, v)| y.get(k).is_some_and(|w| json_num_eq(v, w)))
            }
            (Value::Array(x), Value::Array(y)) => {
                x.len() == y.len() && x.iter().zip(y).all(|(v, w)| json_num_eq(v, w))
            }
            (Value::Number(x), Value::Number(y)) => match (x.as_f64(), y.as_f64()) {
                (Some(p), Some(q)) => (p - q).abs() < 1e-9,
                _ => x == y,
            },
            _ => a == b,
        }
    }

    #[test]
    fn view_workspace_tags_overrides_and_echoes_material() {
        let cfg = tmp("v-cfg");
        let ws = tmp("v-ws");
        std::fs::write(
            ws.join("manufacturing-profile.json"),
            r#"{"design":{"wallMm":1.6}}"#,
        )
        .unwrap();
        let v = view(&cfg, Scope::Workspace, Some(&ws)).unwrap();
        assert_eq!(v.overrides["design"]["wallMm"].as_f64(), Some(1.6)); // set-here
        assert!(v.global_overrides.is_some());
        assert_eq!(v.resolved["design"]["wallMm"].as_f64(), Some(1.6));
        assert!(!v.material.id.is_empty()); // echoed default material
    }

    #[test]
    fn view_global_has_no_global_overrides_field() {
        let cfg = tmp("vg-cfg");
        let v = view(&cfg, Scope::Global, None).unwrap();
        assert!(v.global_overrides.is_none());
    }

    #[test]
    fn rust_resolver_matches_shared_parity_cases() {
        let cases: serde_json::Value = serde_json::from_str(PARITY_CASES).unwrap();
        let base = std::env::temp_dir().join(format!("sol-parity-mfg-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base); // start clean so stale files can't leak in
        let write_if = |dir: &std::path::Path, v: &serde_json::Value| {
            if v.as_object().is_some_and(|o| !o.is_empty()) {
                std::fs::write(
                    dir.join("manufacturing-profile.json"),
                    serde_json::to_string(v).unwrap(),
                )
                .unwrap();
            }
        };
        for (i, case) in cases.as_array().unwrap().iter().enumerate() {
            let config = base.join(format!("c{i}-config"));
            let ws = base.join(format!("c{i}-ws"));
            std::fs::create_dir_all(&config).unwrap();
            std::fs::create_dir_all(&ws).unwrap();
            write_if(&config, &case["global"]);
            write_if(&ws, &case["workspace"]);
            let got = resolve(&config, Some(&ws));
            assert!(
                json_num_eq(&got, &case["expected"]),
                "parity case {} diverged:\n  got: {got}\n  exp: {}",
                case["name"],
                case["expected"],
            );
        }
        let _ = std::fs::remove_dir_all(&base);
    }
}
