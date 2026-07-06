//! App-level print destinations (the "connections" in the Printers UI).
//!
//! Mirrors [`crate::materials`] — native commands so the top-level Printers page
//! works with no workspace engine. Destinations live at
//! `<app_config_dir>/destinations.json`, the same file the engine reads for slice
//! estimates. Slicer detection + profiles live in [`crate::slicers`].

use std::path::Path;

use serde::{Deserialize, Serialize};
use tauri::AppHandle;

use crate::store::{self, ReadResult};

const DESTINATIONS_FILE: &str = "destinations.json";
const SCHEMA: u32 = 1;

/// One configured print / export destination (a "connection" in the UI).
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct Destination {
    pub id: String,
    pub name: String,
    #[serde(default = "default_kind")]
    pub kind: String,
    pub provider: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub printer_profile: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub filament_profile: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub process_profile: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub connection: Option<String>,
}

fn default_kind() -> String {
    "local".to_string()
}

/// Read the destination list from `<dir>/destinations.json`. Missing or corrupt
/// (or any entry that fails to parse) yields an empty list; never errors.
pub fn load(dir: &Path) -> Vec<Destination> {
    match store::read_json(dir, DESTINATIONS_FILE) {
        ReadResult::Ok(v) => v
            .get("destinations")
            .and_then(|d| serde_json::from_value(d.clone()).ok())
            .unwrap_or_default(),
        ReadResult::Missing | ReadResult::Corrupt => Vec::new(),
    }
}

/// Persist the destination list atomically as `{ schema, destinations }` — the
/// shape the engine's `destinations` module also reads.
pub fn save(dir: &Path, destinations: &[Destination]) -> Result<(), String> {
    let value = serde_json::json!({ "schema": SCHEMA, "destinations": destinations });
    store::write_json_atomic(dir, DESTINATIONS_FILE, &value)
}

// -- Tauri commands --------------------------------------------------------

#[tauri::command]
pub fn get_destinations(app: AppHandle) -> Result<Vec<Destination>, String> {
    Ok(load(&crate::workspaces::config_dir(&app)?))
}

#[tauri::command]
pub fn set_destinations(
    app: AppHandle,
    destinations: Vec<Destination>,
) -> Result<Vec<Destination>, String> {
    let dir = crate::workspaces::config_dir(&app)?;
    save(&dir, &destinations)?;
    Ok(load(&dir))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-dest-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn dest(id: &str, name: &str) -> Destination {
        Destination {
            id: id.into(),
            name: name.into(),
            kind: "local".into(),
            provider: "orca".into(),
            printer_profile: None,
            filament_profile: None,
            process_profile: None,
            connection: None,
        }
    }

    #[test]
    fn load_missing_is_empty() {
        let dir = tmp_dir("missing");
        assert!(load(&dir).is_empty());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn save_then_load_round_trips() {
        let dir = tmp_dir("round");
        let mut d = dest("a", "Garage");
        d.printer_profile = Some("Voron 0.2".into());
        save(&dir, std::slice::from_ref(&d)).unwrap();
        let back = load(&dir);
        assert_eq!(back, vec![d]);
        // Persisted in the engine-compatible envelope.
        let raw = std::fs::read_to_string(dir.join(DESTINATIONS_FILE)).unwrap();
        let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(v["schema"], SCHEMA);
        assert_eq!(v["destinations"][0]["printerProfile"], "Voron 0.2");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn load_defaults_kind_when_absent() {
        let dir = tmp_dir("kind");
        let raw = r#"{"schema":1,"destinations":[{"id":"x","name":"X","provider":"orca"}]}"#;
        std::fs::write(dir.join(DESTINATIONS_FILE), raw).unwrap();
        assert_eq!(load(&dir)[0].kind, "local");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn process_profile_round_trips() {
        let dir = tmp_dir("proc");
        let mut d = dest("p", "Bench");
        d.process_profile = Some("0.20mm Optimized PETG @BBL X1C".into());
        save(&dir, std::slice::from_ref(&d)).unwrap();
        let raw = std::fs::read_to_string(dir.join(DESTINATIONS_FILE)).unwrap();
        let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(
            v["destinations"][0]["processProfile"],
            "0.20mm Optimized PETG @BBL X1C"
        );
        assert_eq!(load(&dir), vec![d]);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
