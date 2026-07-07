//! Global + workspace custom instructions: the sole writer (Rust) of
//! `custom-instructions.json`. Mirrors `manufacturing.rs` for file I/O and
//! layered (global <= workspace) resolution, but the payload is plain
//! user-authored text rather than a structured profile. The text is woven into
//! each workspace's `AGENTS.md` at provision time (see `provision.rs`), so the
//! two scopes layer ADDITIVELY: both appear, global first, then workspace.

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::store;

const FILE: &str = "custom-instructions.json";

/// On-disk shape: a single `text` field (empty by default). Kept minimal so the
/// stored file is just the user's words plus the managed round-trip.
#[derive(Serialize, Deserialize, Default)]
struct Doc {
    #[serde(default)]
    text: String,
}

/// The custom-instructions text stored at one layer dir ("" if missing/corrupt).
pub fn read_text(dir: &Path) -> String {
    match store::read_json(dir, FILE) {
        store::ReadResult::Ok(v) => serde_json::from_value::<Doc>(v)
            .map(|d| d.text)
            .unwrap_or_default(),
        _ => String::new(),
    }
}

/// Write `{ text }` to `<dir>/custom-instructions.json`. Trailing whitespace is
/// trimmed; internal formatting is preserved verbatim.
pub fn write_text(dir: &Path, text: &str) -> Result<(), String> {
    let doc = Doc {
        text: text.trim_end().to_string(),
    };
    let value =
        serde_json::to_value(&doc).map_err(|e| format!("failed to serialize {FILE}: {e}"))?;
    store::write_json_atomic(dir, FILE, &value)
}

/// Render the markdown that goes BETWEEN the custom-region markers in AGENTS.md.
///
/// Global (from `config_dir`) and workspace (from `root`) text layer ADDITIVELY:
/// both appear, global first, then workspace, separated by a blank line. The
/// `## Custom instructions` heading is emitted only when there is content, so a
/// fully-blank state renders nothing (the surrounding markers stay empty).
pub fn render_block(config_dir: &Path, root: &Path) -> String {
    let global = read_text(config_dir);
    let workspace = read_text(root);
    let global = global.trim();
    let workspace = workspace.trim();
    if global.is_empty() && workspace.is_empty() {
        return String::new();
    }
    let body = [global, workspace]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n");
    format!("## Custom instructions\n\n{body}")
}

// -- Tauri commands (GUI-facing) --------------------------------------------

use tauri::{AppHandle, State};

use crate::provision::WorkspaceState;
use crate::workspaces::config_dir;

#[tauri::command]
pub fn get_global_custom_instructions(app: AppHandle) -> Result<String, String> {
    Ok(read_text(&config_dir(&app)?))
}

#[tauri::command]
pub fn set_global_custom_instructions(app: AppHandle, text: String) -> Result<(), String> {
    write_text(&config_dir(&app)?, &text)
}

#[tauri::command]
pub fn get_workspace_custom_instructions(
    state: State<'_, WorkspaceState>,
) -> Result<String, String> {
    let root = state.focused_root().ok_or("no workspace is open")?;
    Ok(read_text(&root))
}

#[tauri::command]
pub fn set_workspace_custom_instructions(
    state: State<'_, WorkspaceState>,
    text: String,
) -> Result<(), String> {
    let root = state.focused_root().ok_or("no workspace is open")?;
    write_text(&root, &text)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(tag: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("custom-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    #[test]
    fn missing_reads_as_empty() {
        let dir = tmp("missing");
        assert_eq!(read_text(&dir), "");
    }

    #[test]
    fn write_read_round_trip_preserves_internal_formatting() {
        let dir = tmp("round");
        write_text(&dir, "line one\n\n  indented line\ntrailing   \n\n").unwrap();
        // Trailing whitespace trimmed; internal formatting kept verbatim.
        assert_eq!(read_text(&dir), "line one\n\n  indented line\ntrailing");
    }

    #[test]
    fn render_block_both_empty_is_blank() {
        let cfg = tmp("rb-empty-cfg");
        let ws = tmp("rb-empty-ws");
        assert_eq!(render_block(&cfg, &ws), "");
    }

    #[test]
    fn render_block_global_only() {
        let cfg = tmp("rb-g-cfg");
        let ws = tmp("rb-g-ws");
        write_text(&cfg, "prefer metric units").unwrap();
        let block = render_block(&cfg, &ws);
        assert!(block.starts_with("## Custom instructions\n\n"));
        assert!(block.contains("prefer metric units"));
        assert_eq!(block.matches("## Custom instructions").count(), 1);
    }

    #[test]
    fn render_block_workspace_only() {
        let cfg = tmp("rb-w-cfg");
        let ws = tmp("rb-w-ws");
        write_text(&ws, "this project uses PETG").unwrap();
        let block = render_block(&cfg, &ws);
        assert!(block.starts_with("## Custom instructions\n\n"));
        assert!(block.contains("this project uses PETG"));
    }

    #[test]
    fn render_block_both_global_before_workspace_single_heading() {
        let cfg = tmp("rb-both-cfg");
        let ws = tmp("rb-both-ws");
        write_text(&cfg, "GLOBAL_TEXT").unwrap();
        write_text(&ws, "WORKSPACE_TEXT").unwrap();
        let block = render_block(&cfg, &ws);
        let g = block.find("GLOBAL_TEXT").unwrap();
        let w = block.find("WORKSPACE_TEXT").unwrap();
        assert!(g < w, "global must appear before workspace");
        assert_eq!(block.matches("## Custom instructions").count(), 1);
        assert_eq!(
            block,
            "## Custom instructions\n\nGLOBAL_TEXT\n\nWORKSPACE_TEXT"
        );
    }
}
