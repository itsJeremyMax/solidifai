//! Global + workspace material library store.
//!
//! Mirrors [`crate::app_config`]: serde structs persisted as pretty JSON. The
//! GLOBAL library lives at `<app_config_dir>/materials.json` (the path the Python
//! engine's resolver reads, shared via `SOLIDIFAI_CONFIG_DIR`); a per-workspace
//! library lives at `<workspace>/materials.json`. Invariants: the global library
//! always has at least one material and a `default` that points at one that exists.

use std::{collections::BTreeMap, path::Path};

use serde::{Deserialize, Serialize};

use crate::store;

const CATALOG_JSON: &str = include_str!("../../engine/solidifai_engine/manufacturing_catalog.json");

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Catalog {
    bases: BTreeMap<String, CatalogBase>,
    processes: BTreeMap<String, CatalogProcess>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CatalogBase {
    default_process: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CatalogProcess {
    label: String,
    profile_settings: Vec<String>,
}

fn catalog() -> Result<Catalog, String> {
    serde_json::from_str(CATALOG_JSON).map_err(|e| format!("invalid manufacturing catalog: {e}"))
}

pub fn catalog_source() -> &'static str {
    CATALOG_JSON
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct Material {
    pub id: String,
    pub label: String,
    #[serde(default = "legacy_base")]
    pub base: String,
    pub color_hex: String,
    pub finish: String,
    /// Manufacturing process; derived from `base` when a record omits it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub process: Option<String>,
}

impl Material {
    #[cfg(test)]
    fn stub(id: &str, base: &str) -> Self {
        Material {
            id: id.into(),
            label: id.into(),
            base: base.into(),
            color_hex: "#bcbfc4".into(),
            finish: "matte".into(),
            process: None,
        }
    }

    /// The process for this material, deriving from `base` if unset.
    pub fn process_resolved(&self) -> Result<String, String> {
        if let Some(process) = &self.process {
            return process_exists(process)
                .then(|| process.clone())
                .ok_or_else(|| format!("unknown manufacturing process {process:?}"));
        }
        process_for_base(&self.base).ok_or_else(|| format!("unknown material base {:?}", self.base))
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Default)]
#[serde(rename_all = "camelCase")]
pub struct MaterialLibrary {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub default: Option<String>,
    #[serde(default)]
    pub materials: Vec<Material>,
}

fn legacy_base() -> String {
    "pla".into()
}

pub fn process_for_base(base: &str) -> Option<String> {
    catalog()
        .ok()?
        .bases
        .get(base)
        .map(|entry| entry.default_process.clone())
}

pub fn process_exists(process: &str) -> bool {
    catalog().is_ok_and(|catalog| catalog.processes.contains_key(process))
}

pub fn profile_settings(process: &str) -> Vec<String> {
    catalog()
        .ok()
        .and_then(|mut catalog| catalog.processes.remove(process))
        .map(|entry| entry.profile_settings)
        .unwrap_or_default()
}

pub fn process_label(process: &str) -> Option<String> {
    catalog()
        .ok()?
        .processes
        .get(process)
        .map(|entry| entry.label.clone())
}

impl MaterialLibrary {
    fn validate(&self) -> Result<(), String> {
        for material in &self.materials {
            if process_for_base(&material.base).is_none() {
                return Err(format!("unknown material base {:?}", material.base));
            }
            if let Some(process) = &material.process {
                if !process_exists(process) {
                    return Err(format!("unknown manufacturing process {process:?}"));
                }
            }
        }
        Ok(())
    }
    /// Remove a material by id. Rejects deleting the last material or the current
    /// default (the caller must reassign the default first).
    pub fn remove(&mut self, id: &str) -> Result<(), String> {
        if self.materials.len() <= 1 {
            return Err("cannot delete the last material".into());
        }
        if self.default.as_deref() == Some(id) {
            return Err("cannot delete the default material; pick another default first".into());
        }
        let before = self.materials.len();
        self.materials.retain(|m| m.id != id);
        if self.materials.len() == before {
            return Err(format!("no material with id {id:?}"));
        }
        Ok(())
    }

    /// Insert or replace a material (matched by id).
    pub fn upsert(&mut self, mat: Material) {
        if let Some(slot) = self.materials.iter_mut().find(|m| m.id == mat.id) {
            *slot = mat;
        } else {
            self.materials.push(mat);
        }
    }

    /// Set the default; the id must already exist.
    pub fn set_default(&mut self, id: &str) -> Result<(), String> {
        if !self.materials.iter().any(|m| m.id == id) {
            return Err(format!("no material with id {id:?}"));
        }
        self.default = Some(id.to_string());
        Ok(())
    }

    /// Guarantee the invariant: non-empty + a default that exists. Used after any
    /// mutation and after load.
    fn enforce_invariant(&mut self) {
        if self.materials.is_empty() {
            *self = seeded_library();
            return;
        }
        let ok = self
            .default
            .as_deref()
            .map(|d| self.materials.iter().any(|m| m.id == d))
            .unwrap_or(false);
        if !ok {
            self.default = Some(self.materials[0].id.clone());
        }
    }
}

/// The starter library seeded on first run.
pub fn seeded_library() -> MaterialLibrary {
    let m = |id: &str, label: &str, base: &str, color: &str, finish: &str| Material {
        id: id.into(),
        label: label.into(),
        base: base.into(),
        color_hex: color.into(),
        finish: finish.into(),
        process: None,
    };
    MaterialLibrary {
        default: Some("light-gray-pla".into()),
        materials: vec![
            m(
                "light-gray-pla",
                "Light Gray PLA",
                "pla",
                "#bfc2c6",
                "matte",
            ),
            m(
                "matte-black-pla",
                "Matte Black PLA",
                "pla",
                "#1f222a",
                "matte",
            ),
            m("natural-petg", "Natural PETG", "petg", "#dfe7e6", "gloss"),
            m("aluminum", "Aluminum", "aluminum", "#d6d9de", "metallic"),
        ],
    }
}

/// File name for both the global and per-workspace material libraries.
const MATERIALS_FILE: &str = "materials.json";

/// Load the global library from `<config_dir>/materials.json`, seeding +
/// persisting it if the file is missing or empty. `config_dir` is the canonical
/// app config dir (so the file lands where the engine reads it).
pub fn load_global(config_dir: &Path) -> MaterialLibrary {
    // A corrupt file is backed up (not silently wiped) and treated as empty, so
    // the invariant pass below re-seeds it and save_global rewrites a good file.
    let mut lib = match store::read_json(config_dir, MATERIALS_FILE) {
        store::ReadResult::Ok(v) => serde_json::from_value(v).unwrap_or_default(),
        store::ReadResult::Missing | store::ReadResult::Corrupt => MaterialLibrary::default(),
    };
    let was_empty = lib.materials.is_empty();
    lib.enforce_invariant();
    if was_empty {
        let _ = save_global(config_dir, &lib);
    }
    lib
}

/// Persist the global library, enforcing the invariant first. Routes through the
/// shared atomic writer so an interrupted write can never truncate the file.
pub fn save_global(config_dir: &Path, lib: &MaterialLibrary) -> Result<(), String> {
    let mut lib = lib.clone();
    lib.enforce_invariant();
    lib.validate()?;
    let value = serde_json::to_value(&lib).map_err(|e| format!("serialize: {e}"))?;
    store::write_json_atomic(config_dir, MATERIALS_FILE, &value)
}

/// Load a workspace library from `<workspace>/materials.json` (no seeding; a
/// workspace with no file simply has none). `default: None` means "inherit global".
pub fn load_workspace(workspace_root: &Path) -> MaterialLibrary {
    match store::read_json(workspace_root, MATERIALS_FILE) {
        store::ReadResult::Ok(v) => serde_json::from_value(v).unwrap_or_default(),
        store::ReadResult::Missing | store::ReadResult::Corrupt => MaterialLibrary::default(),
    }
}

/// Persist a workspace library to `<workspace>/materials.json` (atomic write).
pub fn save_workspace(workspace_root: &Path, lib: &MaterialLibrary) -> Result<(), String> {
    lib.validate()?;
    let value = serde_json::to_value(lib).map_err(|e| format!("serialize: {e}"))?;
    store::write_json_atomic(workspace_root, MATERIALS_FILE, &value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seed_library_has_default_that_exists() {
        let lib = seeded_library();
        let def = lib.default.clone().expect("seed sets a default");
        assert!(lib.materials.iter().any(|m| m.id == def));
        assert!(!lib.materials.is_empty());
    }

    #[test]
    fn seed_default_reproduces_pla_appearance() {
        let lib = seeded_library();
        let def = lib.default.clone().unwrap();
        let m = lib.materials.iter().find(|m| m.id == def).unwrap();
        assert_eq!(m.base, "pla");
        assert_eq!(m.finish, "matte");
    }

    #[test]
    fn process_derived_when_missing() {
        assert_eq!(process_for_base("pla"), Some("fdm".into()));
        assert_eq!(process_for_base("aluminum"), Some("cnc".into()));
        assert_eq!(process_for_base("mystery"), None);
    }

    #[test]
    fn explicit_unknown_process_is_rejected() {
        let mut mat = Material::stub("mystery", "pla");
        mat.process = Some("laser".into());
        assert!(mat.process_resolved().is_err());
    }

    #[test]
    fn catalog_loader_reads_the_shared_source() {
        assert!(catalog_source().contains("\"version\": 1"));
        assert_eq!(process_for_base("aluminum"), Some("cnc".into()));
        assert_eq!(profile_settings("fdm").len(), 4);
    }

    #[test]
    fn save_rejects_unknown_explicit_material_values() {
        let dir =
            std::env::temp_dir().join(format!("solidifai-invalid-mat-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let invalid = MaterialLibrary {
            default: Some("bad".into()),
            materials: vec![Material {
                id: "bad".into(),
                label: "Bad".into(),
                base: "moon-dust".into(),
                color_hex: "#000000".into(),
                finish: "matte".into(),
                process: Some("laser".into()),
            }],
        };
        assert!(save_global(&dir, &invalid).is_err());
        assert!(!dir.join("materials.json").exists());
    }

    #[test]
    fn load_missing_global_seeds_and_persists() {
        let dir = std::env::temp_dir().join(format!("solidifai-mat-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let lib = load_global(&dir);
        assert!(!lib.materials.is_empty());
        // file now exists on disk (seeded)
        assert!(dir.join("materials.json").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn delete_rejects_last_material() {
        let mut lib = MaterialLibrary {
            default: Some("a".into()),
            materials: vec![Material::stub("a", "pla")],
        };
        let err = lib.remove("a").unwrap_err();
        assert!(err.contains("last"));
    }

    #[test]
    fn delete_rejects_current_default() {
        let mut lib = MaterialLibrary {
            default: Some("a".into()),
            materials: vec![Material::stub("a", "pla"), Material::stub("b", "petg")],
        };
        let err = lib.remove("a").unwrap_err();
        assert!(err.contains("default"));
    }

    #[test]
    fn delete_non_default_succeeds() {
        let mut lib = MaterialLibrary {
            default: Some("a".into()),
            materials: vec![Material::stub("a", "pla"), Material::stub("b", "petg")],
        };
        lib.remove("b").unwrap();
        assert_eq!(lib.materials.len(), 1);
    }

    #[test]
    fn set_default_requires_existing_material() {
        let mut lib = MaterialLibrary {
            default: Some("a".into()),
            materials: vec![Material::stub("a", "pla")],
        };
        assert!(lib.set_default("ghost").is_err());
        lib.set_default("a").unwrap();
    }
}
