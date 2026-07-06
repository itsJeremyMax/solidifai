"""Presence and content checks for the solidifai-delegation skill and its cross-references."""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILLS = ENGINE_ROOT / "workspace_templates" / "skills"
SKILL_PATH = SKILLS / "solidifai-delegation" / "SKILL.md"
ACCEPTANCE_PATH = SKILLS / "solidifai-delegation" / "references" / "acceptance-scenarios.md"
AGENTS_PATH = ENGINE_ROOT / "workspace_templates" / "AGENTS.md"
USING_PATH = SKILLS / "using-solidifai" / "SKILL.md"
GROUNDING_PATH = SKILLS / "solidifai-grounding" / "SKILL.md"
PRODUCT_PATH = SKILLS / "solidifai-product-design" / "SKILL.md"
SELF_VERIFY_PATH = SKILLS / "solidifai-self-verify" / "SKILL.md"
ORCH_PATH = SKILLS / "solidifai-orchestration" / "SKILL.md"
ASSEM_PATH = SKILLS / "solidifai-assemblies" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


# -- the new skill ----------------------------------------------------------


def test_skill_file_exists():
    assert SKILL_PATH.exists(), f"SKILL.md not found at {SKILL_PATH}"


def test_frontmatter_name(skill_text: str):
    assert "name: solidifai-delegation" in skill_text


def test_defines_worker_neutrally(skill_text: str):
    # The harness-neutral term and the three things a harness might call it.
    assert "worker" in skill_text
    assert "subagent" in skill_text
    assert "teammate" in skill_text
    assert "parallel task" in skill_text


def test_states_single_writer_rule(skill_text: str):
    assert "one writer" in skill_text or "single writer" in skill_text


def test_names_the_three_scout_kinds(skill_text: str):
    assert "grounding scout" in skill_text.lower()
    assert "design scout" in skill_text.lower()
    assert "verify scout" in skill_text.lower()


def test_states_graceful_degradation(skill_text: str):
    # Same end-state with or without workers.
    assert "inline" in skill_text
    assert "identical" in skill_text or "same end-state" in skill_text


def test_decompose_or_inline_gate(skill_text: str):
    assert "decompose" in skill_text


def test_internal_not_announced_to_user(skill_text: str):
    assert "Sol" in skill_text


def test_no_em_dashes(skill_text: str):
    assert "—" not in skill_text, "SKILL.md contains an em dash"


# -- acceptance scenarios ---------------------------------------------------


def test_acceptance_scenarios_exist():
    assert ACCEPTANCE_PATH.exists(), f"acceptance scenarios not found at {ACCEPTANCE_PATH}"


def test_acceptance_scenarios_cover_parity_and_safety():
    text = ACCEPTANCE_PATH.read_text(encoding="utf-8")
    assert "Parity" in text  # same end-state with/without workers
    assert "Safety" in text  # the single-writer / no-scout-writes invariants
    assert "—" not in text, "acceptance scenarios contain an em dash"


# -- cross-references from the rest of the skill set ------------------------


def test_agents_md_routes_to_delegation():
    text = AGENTS_PATH.read_text(encoding="utf-8")
    assert "Working as a team" in text
    assert "solidifai-delegation" in text
    assert "one writer" in text or "single writer" in text


def test_using_solidifai_routes_to_delegation():
    text = USING_PATH.read_text(encoding="utf-8")
    assert "solidifai-delegation" in text


def test_grounding_links_delegation_scout():
    text = GROUNDING_PATH.read_text(encoding="utf-8")
    assert "solidifai-delegation" in text
    assert "grounding scout" in text.lower()


def test_product_design_links_delegation_scout():
    text = PRODUCT_PATH.read_text(encoding="utf-8")
    assert "solidifai-delegation" in text
    assert "design scout" in text.lower()


def test_self_verify_links_delegation_scout():
    text = SELF_VERIFY_PATH.read_text(encoding="utf-8")
    assert "solidifai-delegation" in text
    assert "verify scout" in text.lower()


def test_orchestration_links_delegation_and_uses_worker():
    text = ORCH_PATH.read_text(encoding="utf-8")
    assert "solidifai-delegation" in text
    assert "worker" in text


def test_assemblies_links_delegation():
    text = ASSEM_PATH.read_text(encoding="utf-8")
    assert "solidifai-delegation" in text
