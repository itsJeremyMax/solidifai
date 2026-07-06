//! User-level reference library: verified real-world object dims that Sol
//! learns during grounding. Rust is the sole writer (GUI commands + the
//! engine's control-channel delegation both land here); the engine reads the
//! file directly. File: <config-dir>/reference-library.json.

use parking_lot::Mutex;
use serde_json::{json, Value};
use std::path::Path;
use std::sync::OnceLock;
use tauri::{AppHandle, Emitter};

pub const FILE_NAME: &str = "reference-library.json";

// The packaged seed (universal items: cells, port cutouts); same
// include pattern as manufacturing.rs's parity cases.
const SEED: &str = include_str!("../../engine/solidifai_engine/reference_dims.json");

// Serializes GUI and control-socket writes.
static WRITE_LOCK: Mutex<()> = Mutex::new(());

pub fn seed_objects() -> Value {
    serde_json::from_str::<Value>(SEED)
        .ok()
        .and_then(|v| v.get("objects").cloned())
        .unwrap_or_else(|| json!([]))
}

pub fn load_user(config_dir: &Path) -> Value {
    // store::read_json backs up unparseable bytes to a .bak before reporting
    // Corrupt, so falling back to defaults here can never silently destroy data.
    match crate::store::read_json(config_dir, FILE_NAME) {
        crate::store::ReadResult::Ok(v)
            if v.get("objects").map(|o| o.is_array()).unwrap_or(false) =>
        {
            v
        }
        _ => json!({"schema": 1, "units": "mm", "objects": []}),
    }
}

const KNOWN_KEYS: &[&str] = &[
    "id",
    "aliases",
    "category",
    "dims_mm",
    "mounting_holes",
    "notes",
    "source",
    "origin",
    "verified_at",
    "verified_in",
];

fn is_dim_value(v: &Value) -> bool {
    v.is_number()
        || v.as_array()
            .map(|a| !a.is_empty() && a.iter().all(Value::is_number))
            .unwrap_or(false)
}

pub fn validate(entry: &Value) -> Result<(), String> {
    let obj = entry.as_object().ok_or("entry must be an object")?;
    for key in obj.keys() {
        if !KNOWN_KEYS.contains(&key.as_str()) {
            return Err(format!("unknown key {key:?}"));
        }
    }
    let id = obj.get("id").and_then(Value::as_str).unwrap_or("");
    if id.is_empty()
        || !id.chars().next().unwrap().is_ascii_alphanumeric()
        || !id
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' || c == '.')
    {
        return Err("id must be kebab-case (lowercase letters, digits, hyphens, dots)".into());
    }
    if obj
        .get("category")
        .and_then(Value::as_str)
        .unwrap_or("")
        .is_empty()
    {
        return Err("category must be a non-empty string".into());
    }
    let dims = obj.get("dims_mm").and_then(Value::as_object);
    match dims {
        Some(d) if !d.is_empty() && d.values().all(is_dim_value) => {}
        _ => return Err("dims_mm must be a non-empty object of numbers or number arrays".into()),
    }
    let source = obj.get("source").and_then(Value::as_str).unwrap_or("");
    if !source.starts_with("https://") && !source.starts_with("http://") {
        return Err("source must be an http(s) URL".into());
    }
    if let Some(aliases) = obj.get("aliases") {
        let ok = aliases
            .as_array()
            .map(|a| a.iter().all(Value::is_string))
            .unwrap_or(false);
        if !ok {
            return Err("aliases must be an array of strings".into());
        }
    }
    if let Some(holes) = obj.get("mounting_holes") {
        if !holes.is_object() {
            return Err("mounting_holes must be an object".into());
        }
    }
    for key in ["notes", "verified_at", "verified_in"] {
        if let Some(v) = obj.get(key) {
            if !v.is_string() {
                return Err(format!("{key} must be a string"));
            }
        }
    }
    match obj.get("origin").and_then(Value::as_str) {
        Some("learned") | Some("manual") => Ok(()),
        Some(other) => Err(format!("origin must be learned or manual, not {other:?}")),
        None => Err("origin is required (learned or manual)".into()),
    }
}

fn save(config_dir: &Path, lib: &mut Value) -> Result<Value, String> {
    if let Some(objs) = lib.get_mut("objects").and_then(Value::as_array_mut) {
        objs.sort_by(|a, b| {
            a["id"]
                .as_str()
                .unwrap_or("")
                .cmp(b["id"].as_str().unwrap_or(""))
        });
    }
    crate::store::write_json_atomic(config_dir, FILE_NAME, lib)?;
    Ok(lib.clone())
}

static APP: OnceLock<AppHandle> = OnceLock::new();

pub fn set_app_handle(app: AppHandle) {
    let _ = APP.set(app);
}

/// Fires `reference-library-updated` so the frontend live-syncs.
/// Called from both GUI commands and the control-socket worker thread;
/// AppHandle is Send+Sync so this is safe on any thread.
pub fn emit_updated() {
    if let Some(app) = APP.get() {
        let _ = app.emit("reference-library-updated", ());
    }
}

#[tauri::command]
pub fn get_reference_library(app: AppHandle) -> Result<Value, String> {
    let cfg = crate::workspaces::config_dir(&app)?;
    Ok(json!({
        "seed": seed_objects(),
        "user": load_user(&cfg)["objects"],
    }))
}

/// GUI writes always carry `origin: "manual"`. No verified_at stamped here
/// because no YYYY-MM-DD formatting exists in this codebase without chrono.
#[tauri::command]
pub fn save_reference_entry(app: AppHandle, mut entry: Value) -> Result<Value, String> {
    if let Some(obj) = entry.as_object_mut() {
        obj.insert("origin".into(), json!("manual"));
    }
    let cfg = crate::workspaces::config_dir(&app)?;
    let lib = upsert(&cfg, &entry)?;
    emit_updated();
    Ok(lib)
}

#[tauri::command]
pub fn delete_reference_entry(app: AppHandle, id: String) -> Result<Value, String> {
    let cfg = crate::workspaces::config_dir(&app)?;
    let lib = delete(&cfg, &id)?;
    emit_updated();
    Ok(lib)
}

pub fn upsert(config_dir: &Path, entry: &Value) -> Result<Value, String> {
    validate(entry)?;
    let _guard = WRITE_LOCK.lock();
    let mut lib = load_user(config_dir);
    let objs = lib["objects"].as_array_mut().unwrap();
    let id = entry["id"].as_str().unwrap();
    objs.retain(|e| e["id"].as_str() != Some(id));
    objs.push(entry.clone());
    save(config_dir, &mut lib)
}

pub fn delete(config_dir: &Path, id: &str) -> Result<Value, String> {
    let _guard = WRITE_LOCK.lock();
    let mut lib = load_user(config_dir);
    let objs = lib["objects"].as_array_mut().unwrap();
    let before = objs.len();
    objs.retain(|e| e["id"].as_str() != Some(id));
    if objs.len() == before {
        return Err(format!("no user entry with id {id:?}"));
    }
    save(config_dir, &mut lib)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn tmp(tag: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("reflib-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn entry() -> serde_json::Value {
        json!({
            "id": "raspberry-pi-5",
            "aliases": ["pi 5", "rpi5"],
            "category": "sbc",
            "dims_mm": {"pcb": [85.0, 56.0, 1.4], "height_max": 18.0},
            "mounting_holes": {"count": 4, "dia": 2.7, "thread": "M2.5", "pattern": [58.0, 49.0], "edge_offset": 3.5},
            "notes": "verified against the official mechanical drawing",
            "source": "https://datasheets.raspberrypi.com/rpi5/raspberry-pi-5-mechanical-drawing.pdf",
            "origin": "learned",
            "verified_at": "2026-06-11",
            "verified_in": "cyberdeck"
        })
    }

    #[test]
    fn upsert_creates_file_and_round_trips() {
        let cfg = tmp("upsert");
        let lib = upsert(&cfg, &entry()).unwrap();
        let objs = lib["objects"].as_array().unwrap();
        assert_eq!(objs.len(), 1);
        assert_eq!(objs[0]["id"], "raspberry-pi-5");
        let loaded = load_user(&cfg);
        assert_eq!(loaded["objects"][0]["id"], "raspberry-pi-5");
    }

    #[test]
    fn upsert_replaces_same_id_and_sorts_by_id() {
        let cfg = tmp("replace");
        upsert(&cfg, &entry()).unwrap();
        let mut e2 = entry();
        e2["notes"] = json!("updated notes");
        upsert(&cfg, &e2).unwrap();
        let mut e3 = entry();
        e3["id"] = json!("aa-cell-holder");
        upsert(&cfg, &e3).unwrap();
        let lib = load_user(&cfg);
        let objs = lib["objects"].as_array().unwrap();
        assert_eq!(objs.len(), 2);
        assert_eq!(objs[0]["id"], "aa-cell-holder"); // sorted for stable diffs
        assert_eq!(objs[1]["notes"], "updated notes");
    }

    #[test]
    fn delete_removes_and_missing_id_errors() {
        let cfg = tmp("delete");
        upsert(&cfg, &entry()).unwrap();
        delete(&cfg, "raspberry-pi-5").unwrap();
        assert!(load_user(&cfg)["objects"].as_array().unwrap().is_empty());
        assert!(delete(&cfg, "raspberry-pi-5").is_err());
    }

    #[test]
    fn validation_rejects_bad_entries() {
        let cfg = tmp("validate");
        let cases: Vec<(serde_json::Value, &str)> = vec![
            (
                {
                    let mut e = entry();
                    e.as_object_mut().unwrap().remove("id");
                    e
                },
                "id",
            ),
            (
                {
                    let mut e = entry();
                    e["id"] = json!("Has Spaces");
                    e
                },
                "id",
            ),
            (
                {
                    let mut e = entry();
                    e.as_object_mut().unwrap().remove("dims_mm");
                    e
                },
                "dims_mm",
            ),
            (
                {
                    let mut e = entry();
                    e["dims_mm"] = json!({});
                    e
                },
                "dims_mm",
            ),
            (
                {
                    let mut e = entry();
                    e["dims_mm"] = json!({"pcb": "big"});
                    e
                },
                "dims_mm",
            ),
            (
                {
                    let mut e = entry();
                    e["source"] = json!("ftp://nope");
                    e
                },
                "source",
            ),
            (
                {
                    let mut e = entry();
                    e["origin"] = json!("guessed");
                    e
                },
                "origin",
            ),
            (
                {
                    let mut e = entry();
                    e["aliases"] = json!([1, 2]);
                    e
                },
                "aliases",
            ),
            (
                {
                    let mut e = entry();
                    e["surprise"] = json!(true);
                    e
                },
                "surprise",
            ),
        ];
        for (bad, needle) in cases {
            let err = upsert(&cfg, &bad).unwrap_err();
            assert!(
                err.contains(needle),
                "error {err:?} should mention {needle}"
            );
        }
    }

    #[test]
    fn corrupt_file_is_backed_up_before_overwrite() {
        let cfg = tmp("corrupt");
        std::fs::write(cfg.join(FILE_NAME), "{nope").unwrap();
        upsert(&cfg, &entry()).unwrap();
        assert_eq!(load_user(&cfg)["objects"][0]["id"], "raspberry-pi-5");
        // The unparseable bytes survived to a .bak (store::read_json's contract).
        let baks: Vec<_> = std::fs::read_dir(&cfg)
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| {
                let n = e.file_name();
                let n = n.to_string_lossy();
                n.starts_with("reference-library.json.") && n.ends_with(".bak")
            })
            .collect();
        assert_eq!(baks.len(), 1, "exactly one backup written");
        assert_eq!(std::fs::read_to_string(baks[0].path()).unwrap(), "{nope");
    }

    #[test]
    fn seed_parses_and_load_user_defaults_empty() {
        let cfg = tmp("seed");
        let seed = seed_objects();
        assert!(!seed.as_array().unwrap().is_empty());
        let lib = load_user(&cfg);
        assert!(lib["objects"].as_array().unwrap().is_empty());
    }
}
