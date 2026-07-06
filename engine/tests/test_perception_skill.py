"""Phase 2 perception: the self-verify skill must direct stream/pause-tier
loops to section views and hi-res close-ups. Anchored to phrases, not line
numbers, so it survives the Phase 1 template refactor."""

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1]
    / "workspace_templates"
    / "skills"
    / "solidifai-self-verify"
    / "SKILL.md"
)
AGENTS = Path(__file__).resolve().parents[1] / "workspace_templates" / "AGENTS.md"


def _skill() -> str:
    # Explicit utf-8: OCC/lib3mf can flip the process locale mid-suite.
    return SKILL.read_text(encoding="utf-8")


def test_self_verify_directs_section_views_for_internal_geometry():
    t = _skill()
    assert "section" in t
    assert "internal geometry" in t


def test_self_verify_directs_hires_close_ups_of_interfaces():
    t = _skill()
    assert "focus" in t
    assert "1024" in t
    assert "interface" in t


def test_self_verify_tiering_skip_unchanged():
    t = _skill().lower()
    # Deeper looks are tied to the stream/pause tiers; skip-tier stays cheap.
    assert "stream" in t and "pause" in t
    assert "skip" in t


def test_agents_tool_table_names_new_params():
    t = AGENTS.read_text(encoding="utf-8")
    assert "resolution" in t and "section" in t and "focus" in t
