//! Global app-config store: viewport feature flags + launcher preferences,
//! persisted across workspaces.
//!
//! Mirrors [`crate::registry`]: a serde struct persisted as pretty JSON at
//! `<app_config_dir>/app-config.json`. These flags are GLOBAL (viewport features
//! apply to every workspace); AGENTS.md and agent-config are per-workspace and
//! live elsewhere (see [`crate::agent_config`]).
//!
//! `set_app_config` takes a PARTIAL patch (only the changed flags), so the store
//! merges the patch over the loaded config rather than replacing it — the
//! frontend never has to round-trip the whole object to flip one toggle.

use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::store;

/// Global viewport feature flags. Serializes to camelCase per the frontend
/// contract: `{ gtao, grid, smaa, softShadows }`.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AppConfig {
    /// Screen-space ambient occlusion (GTAO pass) in the Preview pipeline.
    pub gtao: bool,
    /// Work-plane grid visibility.
    pub grid: bool,
    /// SMAA anti-aliasing pass.
    pub smaa: bool,
    /// Soft (PCF) contact shadows vs hard shadows.
    pub soft_shadows: bool,
    /// Auto-update behavior: "notify" (default), "autoDownload", or "silent".
    #[serde(default = "default_update_behavior")]
    pub update_behavior: String,
    /// Update channel: "stable" (default) or "beta" (opt-in pre-releases).
    #[serde(default = "default_update_channel")]
    pub update_channel: String,
    /// The app version whose what's-new the user has already seen. `None` until
    /// the first post-update modal is dismissed; omitted from the file when unset.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_seen_version: Option<String>,
    /// The directory a workspace was last created in; the launcher pre-fills new
    /// workspaces here. `None` until the first create. Omitted from the file when
    /// unset; `#[serde(default)]` lets legacy files (and the skipped default) load
    /// it as `None`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_workspace_parent_dir: Option<String>,
    /// Home library view mode: "grid" (default) or "list".
    #[serde(default = "default_home_view")]
    pub home_view: String,
    /// Home library filter: "all" (default), "recent", or "archived".
    #[serde(default = "default_home_filter")]
    pub home_filter: String,
    /// Workspace path whose "Continue where you left off" hero the user dismissed,
    /// or None. The hero re-appears when a different workspace becomes most recent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub home_hero_dismissed: Option<String>,
}

/// Default update behavior: a quiet "update available" indicator the user clicks
/// to install (never interrupts a modeling session).
fn default_update_behavior() -> String {
    "notify".to_string()
}

/// Default update channel: stable releases only.
fn default_update_channel() -> String {
    "stable".to_string()
}

fn default_home_view() -> String {
    "grid".to_string()
}

fn default_home_filter() -> String {
    "all".to_string()
}

impl Default for AppConfig {
    /// Ships everything that makes the Preview look its best ON. Matches the
    /// current hardcoded scene defaults (GTAO enabled, grid visible, SMAA in the
    /// pass chain, PCFSoftShadowMap).
    fn default() -> Self {
        Self {
            gtao: true,
            grid: true,
            smaa: true,
            soft_shadows: true,
            update_behavior: default_update_behavior(),
            update_channel: default_update_channel(),
            last_seen_version: None,
            last_workspace_parent_dir: None,
            home_view: default_home_view(),
            home_filter: default_home_filter(),
            home_hero_dismissed: None,
        }
    }
}

pub const CONFIG_FILE: &str = "app-config.json";
pub const CURRENT_VERSION: u32 = 1;

/// Migrate a raw stored value up to [`CURRENT_VERSION`].
fn migrate(from: u32, mut v: Value) -> Value {
    if from < 1 {
        v = migrate_v0_to_v1(v);
    }
    v
}

/// v0 (no version; full object written by the old build) → v1 (sparse). Keep only
/// keys whose value differs from the shipped default; drop defaults so the user
/// starts tracking future default changes for settings they never deliberately set.
fn migrate_v0_to_v1(v: Value) -> Value {
    let defaults = serde_json::to_value(AppConfig::default()).unwrap_or(Value::Null);
    let mut out = Map::new();
    if let (Value::Object(stored), Value::Object(def)) = (&v, &defaults) {
        for (k, val) in stored {
            if k == "version" {
                continue;
            }
            match def.get(k) {
                Some(dv) if dv == val => {} // equals default → prune
                _ => {
                    out.insert(k.clone(), val.clone());
                }
            }
        }
    }
    Value::Object(out)
}

/// Compute the effective config: shipped defaults with the sparse `overrides`
/// merged on top. A stray `version` key in `overrides` is ignored by the typed
/// deserialize.
fn effective(overrides: &Value) -> AppConfig {
    let mut base = serde_json::to_value(AppConfig::default()).unwrap_or(Value::Null);
    merge(&mut base, overrides);
    serde_json::from_value(base).unwrap_or_default()
}

/// Load the effective app-config. Missing/corrupt file → shipped defaults. A
/// legacy full file is migrated to sparse on first load (self-healing).
pub fn load(config_dir: &Path) -> AppConfig {
    let overrides = store::versioned_load(config_dir, CONFIG_FILE, CURRENT_VERSION, migrate);
    effective(&overrides)
}

/// Apply a partial `patch` (the changed keys) over the persisted sparse overrides,
/// atomically save the result, and return the new effective config. Per the design
/// there is no runtime pruning: an explicit value equal to the default is
/// stored as an override and persists.
pub fn apply_patch(config_dir: &Path, patch: &Value) -> Result<AppConfig, String> {
    let mut overrides = store::versioned_load(config_dir, CONFIG_FILE, CURRENT_VERSION, migrate);
    merge(&mut overrides, patch);
    if let Value::Object(ref mut m) = overrides {
        m.insert("version".into(), Value::from(CURRENT_VERSION));
    }
    store::write_json_atomic(config_dir, CONFIG_FILE, &overrides)?;
    Ok(effective(&overrides))
}

/// Recursively merge `patch`'s object fields into `base` (shallow is enough for
/// our flat config, but recurse defensively for forward-compat nested fields).
fn merge(base: &mut Value, patch: &Value) {
    match (base, patch) {
        (Value::Object(b), Value::Object(p)) => {
            for (k, v) in p {
                merge(b.entry(k.clone()).or_insert(Value::Null), v);
            }
        }
        (b, p) => *b = p.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::fs;
    use std::path::{Path, PathBuf};

    fn tmp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-appcfg-test-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn read_file(dir: &Path) -> Value {
        serde_json::from_str(&fs::read_to_string(dir.join("app-config.json")).unwrap()).unwrap()
    }

    #[test]
    fn default_serializes_to_camel_case_contract() {
        let v = serde_json::to_value(AppConfig::default()).unwrap();
        assert_eq!(v["gtao"], true);
        assert_eq!(v["grid"], true);
        assert_eq!(v["smaa"], true);
        assert_eq!(v["softShadows"], true);
    }

    #[test]
    fn load_missing_file_is_default() {
        let dir = tmp_dir("missing");
        assert_eq!(load(&dir), AppConfig::default());
        assert!(!dir.join("app-config.json").is_file());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn apply_patch_writes_only_overrides_plus_version() {
        let dir = tmp_dir("sparse");
        let merged = apply_patch(&dir, &json!({ "gtao": false })).unwrap();
        assert!(!merged.gtao, "effective reflects the patch");
        assert!(merged.grid, "untouched flag stays at default");
        let on_disk = read_file(&dir);
        assert_eq!(on_disk["gtao"], false);
        assert_eq!(on_disk["version"], 1);
        assert!(
            on_disk.get("grid").is_none(),
            "default not frozen into file"
        );
        assert!(on_disk.get("smaa").is_none());
        assert!(on_disk.get("softShadows").is_none());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn effective_is_defaults_merged_with_overrides() {
        let dir = tmp_dir("effective");
        apply_patch(&dir, &json!({ "smaa": false })).unwrap();
        let cfg = load(&dir);
        assert!(!cfg.smaa, "override applied");
        assert!(
            cfg.gtao && cfg.grid && cfg.soft_shadows,
            "rest are defaults"
        );
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn patches_accumulate_across_calls() {
        let dir = tmp_dir("accumulate");
        apply_patch(&dir, &json!({ "gtao": false })).unwrap();
        let merged = apply_patch(&dir, &json!({ "grid": false })).unwrap();
        assert!(!merged.gtao && !merged.grid, "both overrides present");
        let on_disk = read_file(&dir);
        assert_eq!(on_disk["gtao"], false);
        assert_eq!(on_disk["grid"], false);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_full_file_migrates_to_sparse_pruning_defaults() {
        let dir = tmp_dir("legacy-full");
        // A v0 file written by the old build: full object, no version. gtao is the
        // only non-default value; the rest equal the shipped defaults.
        fs::write(
            dir.join("app-config.json"),
            r#"{"gtao":false,"grid":true,"smaa":true,"softShadows":true}"#,
        )
        .unwrap();
        let cfg = load(&dir);
        assert!(!cfg.gtao);
        assert!(cfg.grid && cfg.smaa && cfg.soft_shadows);
        let on_disk = read_file(&dir);
        assert_eq!(on_disk["version"], 1);
        assert_eq!(on_disk["gtao"], false);
        assert!(on_disk.get("grid").is_none(), "default-valued key pruned");
        assert!(on_disk.get("smaa").is_none());
        assert!(on_disk.get("softShadows").is_none());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn changing_a_default_reaches_a_user_who_never_set_it() {
        // The core guarantee: a sparse file omitting `grid` tracks whatever the
        // current default for `grid` is.
        let dir = tmp_dir("default-prop");
        apply_patch(&dir, &json!({ "gtao": false })).unwrap();
        let on_disk = read_file(&dir);
        assert!(on_disk.get("grid").is_none(), "grid never stored");
        // Effective grid == whatever AppConfig::default().grid is right now. If we
        // later flip that default, this user's effective grid flips with it,
        // because nothing is frozen in their file.
        assert_eq!(load(&dir).grid, AppConfig::default().grid);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn update_settings_default_and_patch() {
        let dir = tmp_dir("update-settings");
        let cfg = load(&dir);
        assert_eq!(cfg.update_behavior, "notify");
        assert_eq!(cfg.update_channel, "stable");
        assert_eq!(cfg.last_seen_version, None);
        let merged = apply_patch(
            &dir,
            &json!({ "updateBehavior": "silent", "updateChannel": "beta" }),
        )
        .unwrap();
        assert_eq!(merged.update_behavior, "silent");
        assert_eq!(merged.update_channel, "beta");
        let merged2 = apply_patch(&dir, &json!({ "lastSeenVersion": "1.2.3" })).unwrap();
        assert_eq!(merged2.last_seen_version, Some("1.2.3".to_string()));
        let on_disk = read_file(&dir);
        assert_eq!(on_disk["updateBehavior"], "silent");
        assert_eq!(on_disk["lastSeenVersion"], "1.2.3");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn last_workspace_parent_round_trips_as_an_override() {
        let dir = tmp_dir("parent");
        apply_patch(&dir, &json!({ "lastWorkspaceParentDir": "/tmp/solidifai" })).unwrap();
        assert_eq!(
            load(&dir).last_workspace_parent_dir,
            Some("/tmp/solidifai".to_string())
        );
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn patching_a_default_value_is_stored_not_pruned_at_runtime() {
        let dir = tmp_dir("d1-no-runtime-prune");
        // grid's default is true; explicitly patch it to true. An explicit user choice
        // must persist as an override (only the one-time v0->v1 migration prunes
        // default-valued keys, not apply_patch).
        apply_patch(&dir, &json!({ "grid": true })).unwrap();
        let on_disk = read_file(&dir);
        assert_eq!(
            on_disk["grid"], true,
            "explicit default persists (D1: no runtime pruning)"
        );
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn home_prefs_default_and_round_trip() {
        let c = AppConfig::default();
        assert_eq!(c.home_view, "grid");
        assert_eq!(c.home_filter, "all");
        let v = serde_json::to_value(&c).unwrap();
        assert_eq!(v["homeView"], "grid");
        assert_eq!(v["homeFilter"], "all");
    }

    #[test]
    fn corrupt_file_falls_back_to_defaults_without_wiping() {
        let dir = tmp_dir("corrupt");
        fs::write(dir.join("app-config.json"), "{ broken").unwrap();
        assert_eq!(load(&dir), AppConfig::default());
        // The unreadable file was backed up, not silently deleted.
        let has_bak = fs::read_dir(&dir).unwrap().filter_map(|e| e.ok()).any(|e| {
            let n = e.file_name();
            n.to_string_lossy().ends_with(".bak")
        });
        assert!(has_bak, "corrupt file preserved to a .bak");
        let _ = fs::remove_dir_all(&dir);
    }
}
