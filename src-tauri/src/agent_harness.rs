//! Native coding-harness metadata and workspace configuration renderers.
//!
//! The provisioner owns managed-file writes; this module owns the adapter-specific
//! paths and content so adding a harness does not grow another provisioner match.

use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use parking_lot::Mutex;
use serde::Serialize;
use serde_json::json;

use crate::provision::MANAGED_MARKER;

const CLAUDE_MD: &str = include_str!("../../engine/workspace_templates/CLAUDE.md");
const GEMINI_MD: &str = include_str!("../../engine/workspace_templates/GEMINI.md");

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum HarnessId {
    Codex,
    ClaudeCode,
    OpenCode,
    GeminiCli,
    CopilotCli,
    Pi,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum HarnessState {
    Ready,
    NotInstalled,
    NeedsSetup,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HarnessStatus {
    pub id: HarnessId,
    pub display_name: String,
    pub state: HarnessState,
    pub remediation: Option<String>,
    pub user_owned_paths: Vec<String>,
}

/// Startup-cached harness readiness. Status checks do not execute agent CLIs;
/// the Pi extension probe only runs when the user explicitly refreshes support.
pub struct HarnessStatusState(pub Mutex<Vec<HarnessStatus>>);

impl Default for HarnessStatusState {
    fn default() -> Self {
        Self(Mutex::new(Vec::new()))
    }
}

impl HarnessStatusState {
    pub fn statuses(&self) -> Vec<HarnessStatus> {
        self.0.lock().clone()
    }

    pub fn replace(&self, statuses: Vec<HarnessStatus>) {
        *self.0.lock() = statuses;
    }
}

/// Injectable boundary around direct PATH lookup and the one explicit Pi probe.
pub trait HarnessProbe {
    fn executable_on_path(&self, executable: &str) -> bool;
    fn run(&self, executable: &str, args: &[&str]) -> Result<Vec<u8>, String>;
}

struct SystemHarnessProbe;

impl HarnessProbe for SystemHarnessProbe {
    fn executable_on_path(&self, executable: &str) -> bool {
        executable_on_path(executable)
    }

    fn run(&self, executable: &str, args: &[&str]) -> Result<Vec<u8>, String> {
        let output = Command::new(executable)
            .args(args)
            .output()
            .map_err(|error| format!("failed to run {executable}: {error}"))?;
        if output.status.success() {
            Ok(output.stdout)
        } else {
            Err(format!("{executable} exited with {}", output.status))
        }
    }
}

/// Readiness safe to cache at startup. This only inspects PATH entries.
pub fn detect_path_only() -> Vec<HarnessStatus> {
    detect_with(&SystemHarnessProbe, false)
}

/// Explicit readiness refresh. Pi is the only harness that needs a command
/// invocation: `pi list` confirms its MCP extension is installed.
pub fn detect_explicit() -> Vec<HarnessStatus> {
    detect_with(&SystemHarnessProbe, true)
}

/// Adapter paths that exist in a workspace but no longer carry the managed
/// marker. These are annotations only; detection never mutates user files.
pub fn user_owned_paths(id: HarnessId, workspace_root: &Path) -> Vec<String> {
    adapter(id)
        .outputs("", "")
        .into_iter()
        .filter_map(|output| {
            let path = workspace_root.join(&output.path);
            fs::read_to_string(path)
                .ok()
                .filter(|content| !content.contains(MANAGED_MARKER))
                .map(|_| output.path.to_string_lossy().into_owned())
        })
        .collect()
}

fn detect_with(probe: &impl HarnessProbe, probe_pi_extension: bool) -> Vec<HarnessStatus> {
    adapter_registry()
        .iter()
        .map(|adapter| {
            let installed = probe.executable_on_path(adapter.executable);
            let (state, remediation) = if !installed {
                (HarnessState::NotInstalled, None)
            } else if adapter.id == HarnessId::Pi && probe_pi_extension {
                let extension_present = probe
                    .run("pi", &["list"])
                    .ok()
                    .and_then(|output| String::from_utf8(output).ok())
                    .is_some_and(|output| contains_pi_mcp_extension(&output));
                if extension_present {
                    (HarnessState::Ready, None)
                } else {
                    (
                        HarnessState::NeedsSetup,
                        Some("pi install npm:pi-mcp-extension".to_string()),
                    )
                }
            } else {
                (HarnessState::Ready, None)
            };

            HarnessStatus {
                id: adapter.id,
                display_name: adapter.display_name.to_string(),
                state,
                remediation,
                user_owned_paths: Vec::new(),
            }
        })
        .collect()
}

fn contains_pi_mcp_extension(output: &str) -> bool {
    output
        .split(|character: char| !(character.is_ascii_alphanumeric() || character == '-'))
        .any(|token| token == "pi-mcp-extension")
}

fn executable_on_path(executable: &str) -> bool {
    let executable_path = Path::new(executable);
    if executable_path.components().count() > 1 {
        return is_executable_file(executable_path);
    }

    env::var_os("PATH")
        .as_deref()
        .map(env::split_paths)
        .into_iter()
        .flatten()
        .any(|directory| executable_path_exists(&directory, executable))
}

fn executable_path_exists(directory: &Path, executable: &str) -> bool {
    let candidate = directory.join(executable);
    if is_executable_file(&candidate) {
        return true;
    }

    #[cfg(windows)]
    if Path::new(executable).extension().is_none() {
        let extensions = env::var_os("PATHEXT").unwrap_or_else(|| ".COM;.EXE;.BAT;.CMD".into());
        return env::split_paths(&extensions).any(|extension| {
            directory
                .join(format!("{executable}{}", extension.display()))
                .is_file()
        });
    }

    false
}

#[cfg(unix)]
fn is_executable_file(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;

    path.is_file()
        && fs::metadata(path).is_ok_and(|metadata| metadata.permissions().mode() & 0o111 != 0)
}

#[cfg(not(unix))]
fn is_executable_file(path: &Path) -> bool {
    path.is_file()
}

pub struct AdapterOutput {
    pub path: PathBuf,
    pub content: String,
}

pub struct HarnessAdapter {
    pub id: HarnessId,
    pub display_name: &'static str,
    pub executable: &'static str,
    pub skill_root: Option<&'static str>,
    pub render: fn(&str, &str) -> Vec<AdapterOutput>,
    pub render_instructions: fn() -> Vec<AdapterOutput>,
}

impl HarnessAdapter {
    /// MCP-bearing configuration which requires a resolved engine interpreter.
    pub fn mcp_outputs(&self, interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
        (self.render)(interpreter, socket)
    }

    /// Non-MCP instruction files which are useful before the engine is ready.
    pub fn instruction_outputs(&self) -> Vec<AdapterOutput> {
        (self.render_instructions)()
    }

    /// All adapter-owned outputs. Provisioning uses the more specific methods so
    /// it can defer only MCP configuration while the engine interpreter is absent.
    pub fn outputs(&self, interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
        self.mcp_outputs(interpreter, socket)
            .into_iter()
            .chain(self.instruction_outputs())
            .collect()
    }
}

const ADAPTERS: [HarnessAdapter; 6] = [
    HarnessAdapter {
        id: HarnessId::Codex,
        display_name: "Codex",
        executable: "codex",
        skill_root: Some(".agents/skills"),
        render: render_codex,
        render_instructions: no_instruction_outputs,
    },
    HarnessAdapter {
        id: HarnessId::ClaudeCode,
        display_name: "Claude Code",
        executable: "claude",
        skill_root: Some(".claude/skills"),
        render: render_claude_code,
        render_instructions: render_claude_instructions,
    },
    HarnessAdapter {
        id: HarnessId::OpenCode,
        display_name: "OpenCode",
        executable: "opencode",
        skill_root: Some(".opencode/skills"),
        render: render_opencode,
        render_instructions: no_instruction_outputs,
    },
    HarnessAdapter {
        id: HarnessId::GeminiCli,
        display_name: "Gemini CLI",
        executable: "gemini",
        skill_root: Some(".gemini/skills"),
        render: render_gemini_cli,
        render_instructions: render_gemini_instructions,
    },
    HarnessAdapter {
        id: HarnessId::CopilotCli,
        display_name: "Copilot CLI",
        executable: "copilot",
        skill_root: Some(".agents/skills"),
        render: render_copilot_cli,
        render_instructions: no_instruction_outputs,
    },
    HarnessAdapter {
        id: HarnessId::Pi,
        display_name: "Pi",
        executable: "pi",
        skill_root: Some(".agents/skills"),
        render: render_pi,
        render_instructions: no_instruction_outputs,
    },
];

pub fn adapter_registry() -> &'static [HarnessAdapter] {
    &ADAPTERS
}

pub fn adapter(id: HarnessId) -> &'static HarnessAdapter {
    adapter_registry()
        .iter()
        .find(|candidate| candidate.id == id)
        .expect("every HarnessId has a registered adapter")
}

/// All distinct skill roots in adapter display order.
pub fn skill_roots() -> Vec<&'static str> {
    adapter_registry()
        .iter()
        .filter_map(|adapter| adapter.skill_root)
        .fold(Vec::new(), |mut roots, root| {
            if !roots.contains(&root) {
                roots.push(root);
            }
            roots
        })
}

fn output(path: &str, content: impl Into<String>) -> AdapterOutput {
    AdapterOutput {
        path: PathBuf::from(path),
        content: content.into(),
    }
}

fn managed_json(value: serde_json::Value) -> String {
    let mut value = value;
    value["//"] = serde_json::Value::String(format!(
        "{MANAGED_MARKER}: generated by solidifai; safe to overwrite"
    ));
    pretty(&value)
}

fn mcp_server(interpreter: &str, socket: &str) -> serde_json::Value {
    json!({
        "command": interpreter,
        "args": ["-m", "solidifai_mcp"],
        "env": { "SOLIDIFAI_ENGINE_SOCK": socket },
    })
}

fn render_codex(interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
    vec![output(
        ".codex/config.toml",
        codex_config_toml(interpreter, socket),
    )]
}

fn render_claude_code(interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
    vec![
        output(
            ".mcp.json",
            managed_json(json!({
                "mcpServers": { "solidifai-cad": mcp_server(interpreter, socket) },
            })),
        ),
        output(
            ".claude/settings.json",
            managed_json(json!({
                "enabledMcpjsonServers": ["solidifai-cad"],
                "hooks": {
                    "SessionStart": [{
                        "hooks": [{
                            "type": "command",
                            "command": claude_session_start_hook(interpreter),
                        }]
                    }]
                }
            })),
        ),
    ]
}

fn render_claude_instructions() -> Vec<AdapterOutput> {
    vec![output("CLAUDE.md", CLAUDE_MD)]
}

fn claude_session_start_hook(interpreter: &str) -> String {
    format!(
        "\"{interpreter}\" -c \"import pathlib; print(pathlib.Path('AGENTS.md').read_text(encoding='utf-8'), end='')\""
    )
}

fn render_opencode(interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
    let value = json!({
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "solidifai-cad": {
                "type": "local",
                "command": [interpreter, "-m", "solidifai_mcp"],
                "environment": { "SOLIDIFAI_ENGINE_SOCK": socket },
                "enabled": true,
            }
        },
        "instructions": ["AGENTS.md"],
    });
    vec![output(
        "opencode.json",
        format!(
            "// {MANAGED_MARKER}: generated by solidifai; safe to overwrite\n{}",
            pretty(&value)
        ),
    )]
}

fn render_gemini_cli(interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
    vec![output(
        ".gemini/settings.json",
        managed_json(json!({
            "mcpServers": { "solidifai-cad": mcp_server(interpreter, socket) },
        })),
    )]
}

fn render_gemini_instructions() -> Vec<AdapterOutput> {
    vec![output("GEMINI.md", GEMINI_MD)]
}

fn render_copilot_cli(interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
    vec![output(
        ".github/mcp.json",
        managed_json(json!({
            "mcpServers": {
                "solidifai-cad": {
                    "type": "local",
                    "command": interpreter,
                    "args": ["-m", "solidifai_mcp"],
                    "env": { "SOLIDIFAI_ENGINE_SOCK": socket },
                    "tools": ["*"],
                }
            }
        })),
    )]
}

fn render_pi(interpreter: &str, socket: &str) -> Vec<AdapterOutput> {
    vec![output(
        ".pi/mcp.json",
        managed_json(json!({
            "mcpServers": { "solidifai-cad": mcp_server(interpreter, socket) },
        })),
    )]
}

fn no_instruction_outputs() -> Vec<AdapterOutput> {
    Vec::new()
}

fn codex_config_toml(interpreter: &str, socket: &str) -> String {
    let interpreter = toml_escape(interpreter);
    let socket = toml_escape(socket);
    format!(
        "# {MANAGED_MARKER}: generated by solidifai; safe to overwrite\n\
         \n\
         [mcp_servers.solidifai-cad]\n\
         command = \"{interpreter}\"\n\
         args = [\"-m\", \"solidifai_mcp\"]\n\
         \n\
         [mcp_servers.solidifai-cad.env]\n\
         SOLIDIFAI_ENGINE_SOCK = \"{socket}\"\n"
    )
}

fn toml_escape(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

fn pretty(value: &serde_json::Value) -> String {
    let mut content = serde_json::to_string_pretty(value).expect("JSON value is serializable");
    content.push('\n');
    content
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;
    #[cfg(unix)]
    use std::fs;
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;
    use std::path::PathBuf;

    use super::{
        adapter, adapter_registry, detect_with, is_executable_file, skill_roots, HarnessId,
        HarnessProbe, HarnessState,
    };

    const PY: &str = "/abs/python";
    const SOCK: &str = "/abs/engine.sock";

    #[cfg(unix)]
    #[test]
    fn detect_path_requires_an_executable_file() {
        let dir = tempfile::tempdir().unwrap();
        let executable = dir.path().join("pi");
        fs::write(&executable, "#!/bin/sh\n").unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(!is_executable_file(&executable));

        fs::set_permissions(&executable, fs::Permissions::from_mode(0o755)).unwrap();
        assert!(is_executable_file(&executable));
    }

    struct StubProbe {
        installed: Vec<&'static str>,
        pi_list: Result<Vec<u8>, String>,
        calls: RefCell<Vec<(String, Vec<String>)>>,
    }

    impl HarnessProbe for StubProbe {
        fn executable_on_path(&self, executable: &str) -> bool {
            self.installed.contains(&executable)
        }

        fn run(&self, executable: &str, args: &[&str]) -> Result<Vec<u8>, String> {
            self.calls.borrow_mut().push((
                executable.to_string(),
                args.iter().map(ToString::to_string).collect(),
            ));
            self.pi_list.clone()
        }
    }

    #[test]
    fn detect_path_only_does_not_probe_pi_extensions() {
        let probe = StubProbe {
            installed: vec!["gemini", "pi"],
            pi_list: Ok(b"installed: another-extension\n".to_vec()),
            calls: RefCell::default(),
        };

        let statuses = detect_with(&probe, false);
        let status = |id| statuses.iter().find(|status| status.id == id).unwrap();

        assert_eq!(status(HarnessId::GeminiCli).state, HarnessState::Ready);
        assert_eq!(status(HarnessId::Pi).state, HarnessState::Ready);
        assert_eq!(
            status(HarnessId::CopilotCli).state,
            HarnessState::NotInstalled
        );
        assert!(
            probe.calls.borrow().is_empty(),
            "PATH detection must not run pi"
        );
    }

    #[test]
    fn detect_explicit_refresh_requires_the_pi_mcp_extension() {
        let probe = StubProbe {
            installed: vec!["pi"],
            pi_list: Ok(b"installed: another-extension\n".to_vec()),
            calls: RefCell::default(),
        };

        let statuses = detect_with(&probe, true);
        let pi = statuses
            .iter()
            .find(|status| status.id == HarnessId::Pi)
            .unwrap();

        assert_eq!(pi.state, HarnessState::NeedsSetup);
        assert_eq!(
            pi.remediation.as_deref(),
            Some("pi install npm:pi-mcp-extension")
        );
        assert_eq!(
            probe.calls.borrow().as_slice(),
            [("pi".to_string(), vec!["list".to_string()])]
        );
    }

    #[test]
    fn detect_explicit_refresh_treats_failed_or_undecodable_pi_list_as_needs_setup() {
        for pi_list in [Err("pi exited unsuccessfully".to_string()), Ok(vec![0xff])] {
            let probe = StubProbe {
                installed: vec!["pi"],
                pi_list,
                calls: RefCell::default(),
            };

            let status = detect_with(&probe, true)
                .into_iter()
                .find(|status| status.id == HarnessId::Pi)
                .unwrap();

            assert_eq!(status.state, HarnessState::NeedsSetup);
            assert_eq!(
                status.remediation.as_deref(),
                Some("pi install npm:pi-mcp-extension")
            );
        }
    }

    #[test]
    fn agent_harness_registry_has_the_native_harnesses_in_display_order() {
        assert_eq!(
            adapter_registry().iter().map(|a| a.id).collect::<Vec<_>>(),
            vec![
                HarnessId::Codex,
                HarnessId::ClaudeCode,
                HarnessId::OpenCode,
                HarnessId::GeminiCli,
                HarnessId::CopilotCli,
                HarnessId::Pi,
            ],
        );
        assert!(adapter(HarnessId::GeminiCli)
            .outputs(PY, SOCK)
            .iter()
            .any(|o| o.path == PathBuf::from(".gemini/settings.json")));
    }

    #[test]
    fn agent_harness_registry_exposes_every_distinct_skill_root() {
        assert_eq!(
            skill_roots(),
            vec![
                ".agents/skills",
                ".claude/skills",
                ".opencode/skills",
                ".gemini/skills",
            ]
        );
    }

    #[test]
    fn agent_harness_mcp_renderers_are_parseable_and_preserve_the_stdio_contract() {
        let cases = [
            (HarnessId::Codex, ".codex/config.toml"),
            (HarnessId::ClaudeCode, ".mcp.json"),
            (HarnessId::OpenCode, "opencode.json"),
            (HarnessId::GeminiCli, ".gemini/settings.json"),
            (HarnessId::CopilotCli, ".github/mcp.json"),
            (HarnessId::Pi, ".pi/mcp.json"),
        ];

        for (id, path) in cases {
            let output = adapter(id)
                .outputs(PY, SOCK)
                .into_iter()
                .find(|output| output.path == PathBuf::from(path))
                .unwrap_or_else(|| panic!("{id:?} is missing {path}"));
            assert!(
                output.content.contains("solidifai-managed"),
                "{path} must be managed"
            );

            if id == HarnessId::Codex {
                let value: toml::Value = toml::from_str(&output.content).expect("valid TOML");
                let server = &value["mcp_servers"]["solidifai-cad"];
                assert_eq!(server["command"].as_str(), Some(PY));
                assert_eq!(server["args"][0].as_str(), Some("-m"));
                assert_eq!(server["args"][1].as_str(), Some("solidifai_mcp"));
                assert_eq!(server["env"]["SOLIDIFAI_ENGINE_SOCK"].as_str(), Some(SOCK));
                continue;
            }

            let body = output
                .content
                .lines()
                .filter(|line| !line.trim_start().starts_with("//"))
                .collect::<Vec<_>>()
                .join("\n");
            let value: serde_json::Value = serde_json::from_str(&body).expect("valid JSON");
            let server = match id {
                HarnessId::OpenCode => &value["mcp"]["solidifai-cad"],
                _ => &value["mcpServers"]["solidifai-cad"],
            };
            let command = if id == HarnessId::OpenCode {
                &server["command"][0]
            } else {
                &server["command"]
            };
            let args = if id == HarnessId::OpenCode {
                &server["command"]
            } else {
                &server["args"]
            };
            let env = if id == HarnessId::OpenCode {
                &server["environment"]
            } else {
                &server["env"]
            };
            assert_eq!(command, PY, "{path} command");
            let module_start = usize::from(id == HarnessId::OpenCode);
            assert_eq!(args[module_start], "-m", "{path} -m argument");
            assert_eq!(args[module_start + 1], "solidifai_mcp", "{path} module");
            assert_eq!(env["SOLIDIFAI_ENGINE_SOCK"], SOCK, "{path} socket");
        }
    }

    #[test]
    fn agent_harness_claude_settings_inject_rendered_agents_at_session_start() {
        let settings = adapter(HarnessId::ClaudeCode)
            .outputs(PY, SOCK)
            .into_iter()
            .find(|output| output.path == PathBuf::from(".claude/settings.json"))
            .expect("Claude Code settings output");
        let value: serde_json::Value = serde_json::from_str(&settings.content).expect("valid JSON");
        let command = value["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            .as_str()
            .expect("SessionStart command");
        assert!(command.contains(PY), "hook uses the resolved interpreter");
        assert!(
            command.contains("AGENTS.md"),
            "hook injects workspace instructions"
        );
    }
}
