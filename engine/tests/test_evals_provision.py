"""The eval provisioner must replicate what the app writes into a workspace."""

import json
from pathlib import Path

from evals.provision import (
    MCP_SERVER_NAME,
    TEMPLATES_DIR,
    USING_SOLIDIFAI_DIRECTIVE,
    provision_workspace,
)


def test_provision_replicates_app_workspace(tmp_path):
    ws = provision_workspace(tmp_path / "ws", "/opt/py")
    agents = (ws / "AGENTS.md").read_text(encoding="utf-8")
    assert agents == (TEMPLATES_DIR / "AGENTS.md").read_text(encoding="utf-8")
    assert (ws / "CLAUDE.md").is_file()
    assert (ws / ".claude/skills/using-solidifai/SKILL.md").is_file()
    assert (ws / ".claude/skills/solidifai-modeling/SKILL.md").is_file()
    assert (ws / ".solidifai/artifacts").is_dir()

    mcp = json.loads((ws / ".mcp.json").read_text(encoding="utf-8"))
    server = mcp["mcpServers"][MCP_SERVER_NAME]
    assert server["command"] == "/opt/py"
    assert server["args"] == ["-m", "solidifai_mcp"]
    assert server["env"]["SOLIDIFAI_ENGINE_SOCK"] == str(ws / ".solidifai/engine.sock")
    # The app marks its generated config files; mirror that for byte-parity.
    assert mcp["//"].startswith("solidifai-managed")

    settings = json.loads((ws / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["enabledMcpjsonServers"] == [MCP_SERVER_NAME]
    assert settings["//"].startswith("solidifai-managed")
    hook = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert str(ws / ".solidifai/using-solidifai-directive.md") in hook
    assert '"/opt/py" -c' in hook

    directive = (ws / ".solidifai/using-solidifai-directive.md").read_text(encoding="utf-8")
    assert directive == USING_SOLIDIFAI_DIRECTIVE


def test_provisioned_skills_are_byte_identical_to_canonical_templates(tmp_path):
    ws = provision_workspace(tmp_path / "ws", "/opt/py")
    source = TEMPLATES_DIR / "skills"

    for template in source.rglob("*"):
        if template.is_file():
            relative = template.relative_to(source)
            assert (ws / ".claude" / "skills" / relative).read_bytes() == template.read_bytes()


def test_hook_command_matches_provision_rs_byte_for_byte(tmp_path):
    # provision.rs session_start_hook_command() renders exactly this; the eval
    # workspace must hand Claude the identical SessionStart hook.
    ws = provision_workspace(tmp_path / "ws", "/opt/py")
    settings = json.loads((ws / ".claude/settings.json").read_text(encoding="utf-8"))
    hook = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    directive = ws / ".solidifai/using-solidifai-directive.md"
    assert hook == (
        '"/opt/py" -c "import pathlib,sys; '
        "sys.stdout.write(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\" "
        f'"{directive}"'
    )


def test_directive_matches_provision_rs_byte_for_byte():
    # Verbatim mirror of provision.rs USING_SOLIDIFAI_DIRECTIVE (Rust `\` line
    # continuations join lines), so the hook injects identical context.
    assert USING_SOLIDIFAI_DIRECTIVE == (
        "solidifai CAD workspace: do this first.\n"
        "\n"
        "Before you reply, take any action, or invoke any other skill, invoke the "
        "`using-solidifai` skill. It orients you to this workspace and the `solidifai-cad` "
        "engine that every other solidifai skill drives. This holds even when the request "
        "looks simple or maps cleanly to modeling or product design: those skills assume "
        "you have already read using-solidifai.\n"
        "\n"
        "If your harness has no skill mechanism, read "
        "`.claude/skills/using-solidifai/SKILL.md` first instead, then continue.\n"
    )


def test_provision_is_idempotent(tmp_path):
    provision_workspace(tmp_path / "ws", "/opt/py")
    ws = provision_workspace(tmp_path / "ws", "/opt/py")

    # The key invariants must survive a re-provision, not just file existence.
    assert (ws / "AGENTS.md").is_file()
    directive = ws / ".solidifai/using-solidifai-directive.md"
    assert directive.read_text(encoding="utf-8") == USING_SOLIDIFAI_DIRECTIVE

    mcp = json.loads((ws / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["mcpServers"][MCP_SERVER_NAME]["command"] == "/opt/py"

    settings = json.loads((ws / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["enabledMcpjsonServers"] == [MCP_SERVER_NAME]
    hook = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert str(directive) in hook


def test_reprovision_removes_stale_skills(tmp_path):
    # provision.rs write_skills_tree drops previously-provisioned skill dirs that
    # are no longer in the embedded set; the eval provisioner must match so a
    # reused workspace never carries skills the app would have removed.
    ws = provision_workspace(tmp_path / "ws", "/opt/py")
    stale = ws / ".claude/skills/obsolete-skill/SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("STALE", encoding="utf-8")

    provision_workspace(ws, "/opt/py")

    assert not stale.parent.exists(), "stale skill dir must be removed on re-provision"
    assert (ws / ".claude/skills/using-solidifai/SKILL.md").is_file()
    assert (ws / ".claude/skills/solidifai-modeling/SKILL.md").is_file()


def test_server_name_matches_the_app_and_templates():
    # Skills/AGENTS.md reference the `solidifai-cad` server by name; a different
    # eval server name would break every tool reference in the skills.
    assert MCP_SERVER_NAME == "solidifai-cad"
    assert MCP_SERVER_NAME in (TEMPLATES_DIR / "AGENTS.md").read_text(encoding="utf-8")


def test_provisioned_agents_carry_capability_triage_and_honest_limits(tmp_path):
    ws = provision_workspace(tmp_path / "ws", "/opt/py")
    agents = (ws / "AGENTS.md").read_text(encoding="utf-8").lower()

    assert "get_engine_capabilities" in agents
    assert "assess_design_plan" in agents
    assert "simple prismatic" in agents and "build now" in agents
    for token in (
        "parametric",
        "b-rep",
        "sculpt",
        "subd",
        "mesh push-pull",
        "direct nurbs",
        "constraint solver",
        "continuous collision proof",
        "fea",
        "non-fdm",
    ):
        assert token in agents
