//! Per-workspace agent-config store: which skills the coding agent uses + a
//! narrow set of agent runtime settings.
//!
//! There is no in-app agent launch — the user runs their own agentic CLI in the
//! terminal, which reads the workspace's provisioned skill tree
//! (`.claude/skills` + `.opencode/skills`, written by [`crate::provision`]). So
//! "the agent launch reads the enabled set" means the PROVISIONER writes only the
//! enabled skills; re-opening the workspace re-provisions to match the config.
//!
//! Persisted at `<ws>/.solidifai/agent-config.json` (per-workspace, beside the
//! artifacts). A missing file means "all skills enabled, auto-provision on" — the
//! shipped default.

use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::provision;
use crate::store;

/// One available skill, surfaced to the agent-config UI. `enabled` reflects the
/// per-workspace config (defaulting to true when the workspace has no config yet).
/// Serializes to camelCase: `{ name, description, enabled }`.
#[derive(Clone, Debug, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct SkillInfo {
    /// The skill directory name / frontmatter `name` (e.g. `solidifai-modeling`).
    pub name: String,
    /// The skill's frontmatter `description` (one line for the toggle row).
    pub description: String,
    /// Whether this skill is enabled for the workspace.
    pub enabled: bool,
}

/// The persisted per-workspace agent config. Serializes to camelCase:
/// `{ enabledSkills, autoProvisionSkills }`.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AgentConfig {
    /// The skill names enabled for this workspace. `None` (absent file) means
    /// "all embedded skills enabled" — we never want a missing file to silently
    /// strip every skill from a working workspace.
    pub enabled_skills: Option<Vec<String>>,
    /// Whether the provisioner manages the skill tree (false = user hand-manages).
    pub auto_provision_skills: bool,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            enabled_skills: None,
            auto_provision_skills: true,
        }
    }
}

/// The names of the embedded skills (the directory names under `SKILLS_DIR`),
/// sorted for a stable UI order.
pub fn embedded_skill_names() -> Vec<String> {
    let mut names: Vec<String> = provision::skills_dir()
        .dirs()
        .filter_map(|d| {
            d.path()
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
        })
        .collect();
    names.sort();
    names
}

pub const CONFIG_FILE: &str = "agent-config.json";
pub const CURRENT_VERSION: u32 = 1;

#[derive(Serialize, Deserialize)]
struct Envelope {
    #[serde(default)]
    version: u32,
    #[serde(flatten)]
    inner: AgentConfig,
}

/// Migrate a raw stored value up to [`CURRENT_VERSION`]. v0 (no version) → v1
/// needs no field changes; the version stamp itself is applied by
/// `store::versioned_load`.
fn migrate(_from: u32, v: Value) -> Value {
    v
}

/// Load the per-workspace agent config. Missing/corrupt → [`AgentConfig::default`].
pub fn load(ws_dot: &Path) -> AgentConfig {
    let v = store::versioned_load(ws_dot, CONFIG_FILE, CURRENT_VERSION, migrate);
    serde_json::from_value::<Envelope>(v)
        .map(|e| e.inner)
        .unwrap_or_default()
}

pub fn save(ws_dot: &Path, config: &AgentConfig) -> Result<(), String> {
    let env = Envelope {
        version: CURRENT_VERSION,
        inner: config.clone(),
    };
    let v =
        serde_json::to_value(&env).map_err(|e| format!("failed to serialize agent-config: {e}"))?;
    store::write_json_atomic(ws_dot, CONFIG_FILE, &v)
}

pub fn is_skill_enabled(config: &AgentConfig, skill: &str) -> bool {
    match &config.enabled_skills {
        None => true,
        Some(set) => set.iter().any(|s| s == skill),
    }
}

/// List every embedded skill with its frontmatter name/description and its
/// enabled state under `config`.
pub fn list_skills(config: &AgentConfig) -> Vec<SkillInfo> {
    embedded_skill_names()
        .into_iter()
        .map(|name| {
            let description = provision::skill_description(&name).unwrap_or_default();
            let enabled = is_skill_enabled(config, &name);
            SkillInfo {
                name,
                description,
                enabled,
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    use std::fs;
    use std::path::PathBuf;

    fn tmp_dot(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "solidifai-agentcfg-test-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn embedded_skills_are_the_three_shipped() {
        let names = embedded_skill_names();
        assert!(names.contains(&"solidifai-modeling".to_string()));
        assert!(names.contains(&"solidifai-debugging".to_string()));
        assert!(names.contains(&"using-solidifai".to_string()));
    }

    #[test]
    fn default_enables_all_skills() {
        let cfg = AgentConfig::default();
        for name in embedded_skill_names() {
            assert!(
                is_skill_enabled(&cfg, &name),
                "{name} should default-enabled"
            );
        }
        let list = list_skills(&cfg);
        assert!(list.iter().all(|s| s.enabled));
        assert!(list.iter().all(|s| !s.description.is_empty()));
    }

    #[test]
    fn explicit_enabled_set_disables_the_rest() {
        let cfg = AgentConfig {
            enabled_skills: Some(vec!["solidifai-modeling".to_string()]),
            auto_provision_skills: true,
        };
        assert!(is_skill_enabled(&cfg, "solidifai-modeling"));
        assert!(!is_skill_enabled(&cfg, "solidifai-debugging"));
        assert!(!is_skill_enabled(&cfg, "using-solidifai"));
    }

    #[test]
    fn save_then_load_round_trips() {
        let dot = tmp_dot("rt");
        let cfg = AgentConfig {
            enabled_skills: Some(vec!["using-solidifai".to_string()]),
            auto_provision_skills: false,
        };
        save(&dot, &cfg).expect("save");
        assert_eq!(load(&dot), cfg);
        let _ = fs::remove_dir_all(&dot);
    }

    #[test]
    fn load_missing_file_is_default() {
        let dot = tmp_dot("missing");
        assert_eq!(load(&dot), AgentConfig::default());
        let _ = fs::remove_dir_all(&dot);
    }

    #[test]
    fn serializes_to_camel_case_contract() {
        let v = serde_json::to_value(SkillInfo {
            name: "solidifai-modeling".into(),
            description: "Model parts".into(),
            enabled: true,
        })
        .unwrap();
        assert_eq!(v["name"], "solidifai-modeling");
        assert_eq!(v["description"], "Model parts");
        assert_eq!(v["enabled"], true);

        let c = serde_json::to_value(AgentConfig {
            enabled_skills: Some(vec!["x".into()]),
            auto_provision_skills: false,
        })
        .unwrap();
        assert_eq!(c["enabledSkills"][0], "x");
        assert_eq!(c["autoProvisionSkills"], false);
    }

    #[test]
    fn missing_file_is_default() {
        let dir = tmp_dot("missing2");
        assert_eq!(load(&dir), AgentConfig::default());
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn save_writes_version_and_round_trips() {
        let dir = tmp_dot("rt2");
        let cfg = AgentConfig {
            enabled_skills: Some(vec!["solidifai-modeling".to_string()]),
            auto_provision_skills: false,
        };
        save(&dir, &cfg).unwrap();
        let on_disk: Value =
            serde_json::from_str(&fs::read_to_string(dir.join("agent-config.json")).unwrap())
                .unwrap();
        assert_eq!(on_disk["version"], 1);
        assert_eq!(on_disk["autoProvisionSkills"], false);
        assert_eq!(load(&dir), cfg);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_file_without_version_migrates() {
        let dir = tmp_dot("legacy");
        // v0 file: no version key, with NON-default data so this proves the data
        // survived migration (not merely that a version stamp was added).
        fs::write(
            dir.join("agent-config.json"),
            r#"{"enabledSkills":["solidifai-modeling"],"autoProvisionSkills":false}"#,
        )
        .unwrap();
        let loaded = load(&dir);
        assert_eq!(
            loaded.enabled_skills,
            Some(vec!["solidifai-modeling".to_string()])
        );
        assert!(!loaded.auto_provision_skills);
        let on_disk: Value =
            serde_json::from_str(&fs::read_to_string(dir.join("agent-config.json")).unwrap())
                .unwrap();
        assert_eq!(on_disk["version"], 1);
        assert_eq!(on_disk["autoProvisionSkills"], false);
        assert_eq!(on_disk["enabledSkills"][0], "solidifai-modeling");
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn corrupt_file_is_backed_up_not_wiped() {
        let dir = tmp_dot("corrupt2");
        fs::write(dir.join("agent-config.json"), "{ broken").unwrap();
        assert_eq!(load(&dir), AgentConfig::default());
        let has_bak = fs::read_dir(&dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .any(|e| e.file_name().to_string_lossy().ends_with(".bak"));
        assert!(has_bak);
        let _ = fs::remove_dir_all(&dir);
    }
}
