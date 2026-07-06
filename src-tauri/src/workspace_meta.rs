//! Per-workspace `workspace.json`: the workspace's own record of itself (name,
//! description, tags) plus a staged name proposal. Canonical source of truth;
//! the Rust registry only caches it. Written by the engine when Sol acts; by
//! Rust when the user acts on a closed workspace.
//!
//! On-disk keys are camelCase so Python, Rust (serde), and TS all share one format.
//! Normalization is kept byte-for-byte identical to engine/solidifai_engine/workspace_metadata.py.

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::store;

pub const MAX_TAGS: usize = 12;
pub const MAX_TAG_LEN: usize = 24;
pub const MAX_DESC_LEN: usize = 280;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Meta {
    pub schema: u32,
    pub name: String,
    pub created_at: i64,
    pub description: String,
    pub description_source: String,
    pub tags: Vec<String>,
    pub tags_source: String,
    pub proposed_name: Option<String>,
    pub proposed_name_dismissed: Option<String>,
}

impl Default for Meta {
    fn default() -> Self {
        Self {
            schema: 1,
            name: String::new(),
            created_at: 0,
            description: String::new(),
            description_source: "sol".into(),
            tags: Vec::new(),
            tags_source: "sol".into(),
            proposed_name: None,
            proposed_name_dismissed: None,
        }
    }
}

/// Normalize tags to match Python's workspace_metadata.normalize_tags exactly:
/// trim → lowercase → truncate to MAX_TAG_LEN chars (not bytes) → skip empty →
/// dedupe order-preserving → cap at MAX_TAGS.
pub fn normalize_tags(tags: &[String]) -> Vec<String> {
    let mut seen: Vec<String> = Vec::new();
    for t in tags {
        let s: String = t.trim().to_lowercase().chars().take(MAX_TAG_LEN).collect();
        if s.is_empty() || seen.contains(&s) {
            // still check cap after skip (matches Python: cap check after append)
            if seen.len() >= MAX_TAGS {
                break;
            }
            continue;
        }
        seen.push(s);
        if seen.len() >= MAX_TAGS {
            break;
        }
    }
    seen
}

/// Normalize description to match Python: trim then truncate to MAX_DESC_LEN chars.
pub fn normalize_description(d: &str) -> String {
    d.trim().chars().take(MAX_DESC_LEN).collect()
}

/// Read `root/workspace.json`; on any error return `Meta::default()`. Never panics.
pub fn load(root: &Path) -> Meta {
    let path = root.join("workspace.json");
    let text = match std::fs::read_to_string(&path) {
        Ok(t) => t,
        Err(_) => return Meta::default(),
    };
    serde_json::from_str::<Meta>(&text).unwrap_or_default()
}

/// Atomically write `meta` to `root/workspace.json`.
pub fn write(root: &Path, m: &Meta) -> Result<(), String> {
    let value = serde_json::to_value(m).map_err(|e| e.to_string())?;
    store::write_json_atomic(root, "workspace.json", &value)
}

/// Apply a user UI edit: update description/tags, mark provenance, persist.
pub fn apply_user_edit(
    root: &Path,
    description: Option<String>,
    tags: Option<Vec<String>>,
) -> Result<Meta, String> {
    let mut m = load(root);
    if let Some(d) = description {
        m.description = normalize_description(&d);
        m.description_source = "user".into();
    }
    if let Some(t) = tags {
        m.tags = normalize_tags(&t);
        m.tags_source = "user".into();
    }
    write(root, &m)?;
    Ok(m)
}

/// Set the canonical workspace name (user rename / accept proposal). Clears any
/// pending proposal. Returns `Err` when `name` is blank.
pub fn set_name(root: &Path, name: &str) -> Result<Meta, String> {
    let s = name.trim();
    if s.is_empty() {
        return Err("workspace name cannot be empty".into());
    }
    let mut m = load(root);
    m.name = s.to_string();
    m.proposed_name = None;
    write(root, &m)?;
    Ok(m)
}

/// Move the staged proposal into `proposedNameDismissed` and clear it.
pub fn dismiss(root: &Path) -> Result<Meta, String> {
    let mut m = load(root);
    if let Some(p) = m.proposed_name.take() {
        m.proposed_name_dismissed = Some(p);
    }
    // proposed_name is already None after take() (or was already None)
    write(root, &m)?;
    Ok(m)
}

/// Extract the fields the registry uses to cache workspace metadata.
/// Returns `(description, tags, proposed_name, name, created_at, meta_synced_at)`.
/// Empty description maps to `None` so the registry omits the key.
pub fn to_cache(
    m: &Meta,
    mtime_ms: Option<i64>,
) -> (
    Option<String>,
    Vec<String>,
    Option<String>,
    String,
    i64,
    Option<i64>,
) {
    let description = if m.description.is_empty() {
        None
    } else {
        Some(m.description.clone())
    };
    (
        description,
        m.tags.clone(),
        m.proposed_name.clone(),
        m.name.clone(),
        m.created_at,
        mtime_ms,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn tmp(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "sf-wm-{tag}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn write_default(dir: &Path, name: &str, created: i64) {
        let m = Meta {
            name: name.into(),
            created_at: created,
            ..Default::default()
        };
        write(dir, &m).unwrap();
    }

    fn set_proposal_for_test(dir: &Path, proposed: &str) {
        let mut m = load(dir);
        m.proposed_name = Some(proposed.into());
        write(dir, &m).unwrap();
    }

    #[test]
    fn default_has_sol_sources_and_schema_one() {
        let m = Meta::default();
        assert_eq!(m.schema, 1);
        assert_eq!(m.description_source, "sol");
        assert_eq!(m.tags_source, "sol");
    }

    #[test]
    fn missing_file_loads_default() {
        let dir = tmp("missing");
        let m = load(&dir);
        assert_eq!(m, Meta::default());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn write_round_trips_camel_case() {
        let dir = tmp("round");
        let m = Meta {
            name: "Gearbox".into(),
            tags: vec!["gears".into()],
            ..Default::default()
        };
        write(&dir, &m).unwrap();
        let raw: serde_json::Value =
            serde_json::from_str(&std::fs::read_to_string(dir.join("workspace.json")).unwrap())
                .unwrap();
        assert_eq!(raw["descriptionSource"], "sol");
        assert_eq!(raw["name"], "Gearbox");
        assert_eq!(load(&dir), m);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn normalize_tags_parity() {
        let out = normalize_tags(&[
            "  Gears ".into(),
            "gears".into(),
            "ENCLOSURE".into(),
            "".into(),
            "x".repeat(40),
        ]);
        assert_eq!(out[0], "gears");
        assert!(out.contains(&"enclosure".to_string()));
        assert!(out.iter().all(|t| t.chars().count() <= 24));
        // dedupe collapsed Gears/gears
        assert_eq!(out.iter().filter(|t| *t == "gears").count(), 1);
    }

    #[test]
    fn normalize_tags_caps_at_twelve() {
        let many: Vec<String> = (0..30).map(|i| format!("t{i}")).collect();
        assert_eq!(normalize_tags(&many).len(), 12);
    }

    #[test]
    fn normalize_description_caps() {
        assert_eq!(normalize_description("  hi  "), "hi");
        assert_eq!(normalize_description(&"x".repeat(500)).chars().count(), 280);
    }

    #[test]
    fn user_patch_marks_source_user_and_persists() {
        let dir = tmp("user-patch");
        write_default(&dir, "Name", 1);
        apply_user_edit(
            &dir,
            Some("typed".into()),
            Some(vec!["a".into(), "a".into()]),
        )
        .unwrap();
        let m = load(&dir);
        assert_eq!(m.description, "typed");
        assert_eq!(m.description_source, "user");
        assert_eq!(m.tags, vec!["a".to_string()]);
        assert_eq!(m.tags_source, "user");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn set_name_clears_proposal_and_rejects_empty() {
        let dir = tmp("set-name");
        write_default(&dir, "Old", 1);
        set_proposal_for_test(&dir, "Cycloidal Drive");
        set_name(&dir, "Cycloidal Drive").unwrap();
        let m = load(&dir);
        assert_eq!(m.name, "Cycloidal Drive");
        assert!(m.proposed_name.is_none());
        assert!(set_name(&dir, "   ").is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn dismiss_records_dismissed() {
        let dir = tmp("dismiss");
        write_default(&dir, "Old", 1);
        set_proposal_for_test(&dir, "Cycloidal Drive");
        dismiss(&dir).unwrap();
        let m = load(&dir);
        assert!(m.proposed_name.is_none());
        assert_eq!(
            m.proposed_name_dismissed.as_deref(),
            Some("Cycloidal Drive")
        );
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn to_cache_maps_empty_description_to_none() {
        let m = Meta::default();
        let (desc, _tags, _p, _n, _c, synced) = to_cache(&m, Some(9));
        assert_eq!(desc, None);
        assert_eq!(synced, Some(9));
    }
}
