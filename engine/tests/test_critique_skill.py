"""Content guard for the solidifai-critique skill (Phase 3, tiered adversarial critique).

Pins the contract: runs after self-verify's gates pass and before presenting;
tier depths (skip none / stream one combined-lens critic / pause two critics);
both pause-tier critic personas; the ranked-defect output shape; the
fix-or-justify disposition rule; and the no-workers self-critique degradation.
Wiring pins (AGENTS routing + tier sentence, self-verify handoff, delegation
scout) are appended in later tasks. Anchored to phrases, never line numbers."""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ENGINE_ROOT / "workspace_templates"
SKILL_PATH = TEMPLATES / "skills" / "solidifai-critique" / "SKILL.md"
SELF_VERIFY_PATH = TEMPLATES / "skills" / "solidifai-self-verify" / "SKILL.md"
DELEGATION_PATH = TEMPLATES / "skills" / "solidifai-delegation" / "SKILL.md"
AGENTS_PATH = TEMPLATES / "AGENTS.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    # Explicit utf-8: OCC/lib3mf can flip the process locale mid-suite.
    return SKILL_PATH.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert SKILL_PATH.is_file(), f"SKILL.md not found at {SKILL_PATH}"


def test_frontmatter(skill_text: str):
    assert "name: solidifai-critique" in skill_text
    assert "license: MIT" in skill_text


def test_runs_after_gates_before_presenting(skill_text: str):
    low = skill_text.lower()
    assert "gates pass" in low
    assert "before you present" in low
    # Critique reviews a passing model; it never replaces the checks.
    assert "never instead" in low or "not a substitute" in low


def test_tier_depths(skill_text: str):
    low = skill_text.lower()
    assert "skip" in low and "stream" in low and "pause" in low
    assert "one critic" in low
    assert "two critics" in low
    assert "combined lens" in low


def test_critic_contract_shape(skill_text: str):
    low = skill_text.lower()
    assert "read-only" in low
    assert "fresh context" in low or "fresh-context" in low
    assert "ranked" in low
    for token in ("critical", "major", "minor", "suggested_fix"):
        assert token in skill_text, f"critic contract missing: {token}"


def test_inputs_are_the_phase2_pack(skill_text: str):
    # Build brief + hi-res grid + sections/close-ups + check outputs.
    assert "get_build_brief" in skill_text
    assert "resolution=1024" in skill_text
    assert "section=" in skill_text
    assert "focus=" in skill_text
    for tool in ("measure", "analyze_dfm", "check_interferences", "check_requirements"):
        assert tool in skill_text, f"critique pack missing check output: {tool}"


def test_industrial_designer_persona(skill_text: str):
    low = skill_text.lower()
    assert "industrial designer" in low
    for token in ("proportion", "detail density", "finish", "product story"):
        assert token in low, f"industrial-designer lens missing: {token}"


def test_dfm_engineer_persona(skill_text: str):
    low = skill_text.lower()
    assert "mechanical engineer" in low
    for token in ("fits", "load path", "assembly logic", "printab"):
        assert token in low, f"dfm-engineer lens missing: {token}"


def test_critics_find_problems_not_approve(skill_text: str):
    low = skill_text.lower()
    assert "find problems" in low
    assert "do not approve" in low


def test_disposition_fix_or_justify(skill_text: str):
    low = skill_text.lower()
    assert "justif" in low  # justify / justification
    assert "never silently" in low
    # Minors are Sol's judgment, not mandatory fixes.
    assert "your judgment" in low or "your call" in low


def test_degradation_self_critique(skill_text: str):
    low = skill_text.lower()
    assert "self-critique" in low
    assert "fresh" in low and "captures" in low
    assert "weaker" in low
    assert "never present a self-critique as an independent" in low


def test_single_writer_preserved(skill_text: str):
    low = skill_text.lower()
    assert "one engine writer" in low or "single writer" in low


def test_no_em_dashes(skill_text: str):
    assert "—" not in skill_text, "SKILL.md contains an em dash"


def test_agents_routes_and_tier_wires_critique():
    text = AGENTS_PATH.read_text(encoding="utf-8")
    # Routing-table row.
    assert "`solidifai-critique`" in text
    # Tier wiring: the brief's tier sets the critique depth.
    low = text.lower()
    assert "critique depth" in low
    assert "one combined-lens critic" in low
    assert "two critics" in low


def test_disposition_one_voice_reply(skill_text: str):
    # Sim-driven (Sim A Stage 3): the user-facing reply reports what the review
    # found, never the critics/workers mechanism that found it.
    low = skill_text.lower()
    assert "one voice" in low
    assert 'words "critic"' in low  # the lexical ban on mechanism words
    assert "naming critics, workers, or subagents" in low


def test_self_verify_hands_off_to_critique():
    text = SELF_VERIFY_PATH.read_text(encoding="utf-8")
    assert "solidifai-critique" in text
    low = text.lower()
    assert "critique" in low and "present" in low


def test_delegation_lists_critique_critic_as_scout():
    text = DELEGATION_PATH.read_text(encoding="utf-8")
    low = text.lower()
    assert "critique critic" in low
    assert "solidifai-critique" in text
