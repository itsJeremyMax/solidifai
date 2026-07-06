"""Presence and content checks for the surfaced build brief and its cross-references."""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILLS = ENGINE_ROOT / "workspace_templates" / "skills"
AGENTS_PATH = ENGINE_ROOT / "workspace_templates" / "AGENTS.md"
USING_PATH = SKILLS / "using-solidifai" / "SKILL.md"
GROUNDING_PATH = SKILLS / "solidifai-grounding" / "SKILL.md"
MODELING_PATH = SKILLS / "solidifai-modeling" / "SKILL.md"
PRODUCT_PATH = SKILLS / "solidifai-product-design" / "SKILL.md"
ORCH_PATH = SKILLS / "solidifai-orchestration" / "SKILL.md"
ASSEM_PATH = SKILLS / "solidifai-assemblies" / "SKILL.md"
DELEG_PATH = SKILLS / "solidifai-delegation" / "SKILL.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_agents_md_has_build_brief_section():
    text = _read(AGENTS_PATH)
    assert "State the build brief" in text
    assert "Parts and why" in text
    # the three tiers must all be named
    for tier in ("Skip", "Stream", "Pause"):
        assert tier in text
    # forward-reference to the eventual engine tool
    assert "propose_build" in text


def test_agents_brief_section_is_outside_the_managed_profile_region():
    text = _read(AGENTS_PATH)
    start = text.index("<!-- solidifai-profile:start")
    end = text.index("<!-- solidifai-profile:end -->")
    region = text[start:end]
    assert "State the build brief" not in region, (
        "brief section must not sit in the managed profile region"
    )


def test_brief_is_cross_referenced_in_skills():
    assert "build brief" in _read(USING_PATH)
    assert "build brief" in _read(GROUNDING_PATH)
    assert "pause" in _read(GROUNDING_PATH).lower()
    assert "build brief" in _read(MODELING_PATH)
    assert "build brief" in _read(PRODUCT_PATH)
    for p in (ORCH_PATH, ASSEM_PATH, DELEG_PATH):
        assert "build brief" in _read(p), f"{p.name} should reference the build brief"


def test_no_em_dashes_in_new_brief_copy():
    # project convention: user-facing copy avoids em dashes
    section = _read(AGENTS_PATH)
    start = section.index("### State the build brief")
    end = section.index("### Single part or assembly?")
    assert "—" not in section[start:end]


def test_agents_directs_calling_propose_build():
    # the brief section must direct Sol to CALL propose_build now (not the stale
    # "once the engine exposes it" future-tense), and the MCP tools table must
    # list both build-brief tools so they are discoverable.
    text = _read(AGENTS_PATH)
    start = text.index("### State the build brief")
    end = text.index("### Single part or assembly?")
    brief_section = text[start:end]
    assert "propose_build" in brief_section
    assert "Once the engine exposes" not in brief_section, (
        "stale future-tense conditional must be gone"
    )
    # both tools appear in the file (via the MCP tools table)
    assert "propose_build" in text
    assert "get_build_brief" in text


def test_self_verify_checks_the_brief():
    text = (SKILLS / "solidifai-self-verify" / "SKILL.md").read_text(encoding="utf-8")
    assert "get_build_brief" in text
    assert "conformance" in text.lower()
    # uses the right dim sources, not inspect_features
    assert "get_params" in text
