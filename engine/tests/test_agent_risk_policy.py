"""Behavioral instruction contract for risk handling in canonical agent templates."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ENGINE_ROOT / "workspace_templates"
AGENTS = TEMPLATES / "AGENTS.md"
SKILLS = TEMPLATES / "skills"
RISK_SKILLS = (
    "solidifai-grounding",
    "solidifai-product-design",
    "solidifai-self-verify",
    "solidifai-modeling",
)
MANAGED_MARKDOWN = (AGENTS, TEMPLATES / "CLAUDE.md", *SKILLS.rglob("*.md"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture
def canonical_texts() -> dict[str, str]:
    return {
        "agents": _read(AGENTS),
        **{name: _read(SKILLS / name / "SKILL.md") for name in RISK_SKILLS},
    }


def test_risk_matrix_routes_unknowns_by_consequence(canonical_texts: dict[str, str]):
    text = canonical_texts["agents"].lower()

    for risk, examples, action in (
        ("low", ("visual styling", "organization", "reversible detail"), "assume"),
        ("functional", ("fit", "interface", "load", "motion", "material"), "ask"),
        ("safety", ("structural safety", "human contact", "heat", "pressure"), "ask"),
        ("compliance", ("regulatory", "certification"), "never claim certification"),
    ):
        assert risk in text
        assert all(example in text for example in examples)
        assert action in text

    assert "ask one focused question" in text
    assert "unless explicitly delegated" in text
    assert "record the assumption" in text
    assert "disposition" in text
    assert "statement" in text


def test_managed_markdown_has_no_conflicting_assumption_or_clarification_rule():
    forbidden = re.compile(
        r"(?:don't|do not|never)\s+(?:ask|quiz|block|wait|stall)[^.\n]*(?:clarif|question)"
        r"|assum(?:e|ption)[^.\n]*(?:anything|any dimension|everything)"
        r"[^.\n]*(?:unspecified|didn't specify)",
        re.I,
    )

    for path in MANAGED_MARKDOWN:
        text = _read(path)
        assert not forbidden.search(text), (
            f"{path.relative_to(TEMPLATES)} conflicts with risk routing"
        )


def test_low_risk_momentum_is_the_only_unquestioned_assumption_path():
    text = _read(AGENTS).lower()

    assert "low-risk reversible design moving" in text
    assert "ask one focused question" in text


def test_self_verify_uses_conformance_findings_as_a_repair_loop(
    canonical_texts: dict[str, str],
):
    text = canonical_texts["solidifai-self-verify"].lower()

    assert "get_conformance" in text
    assert "findingids" in text
    assert "stable id" in text
    assert text.count("get_conformance") >= 2
    assert "unknown is not pass" in text
    assert "unsupported" in text
    assert "required reference" in text


def test_export_contract_is_readiness_gated_and_fails_closed(
    canonical_texts: dict[str, str],
):
    text = canonical_texts["agents"].lower()

    assert "get_readiness" in text
    assert "strict export" in text
    assert "blocked" in text
    assert "findingids" in text
    assert "host-mediated" in text
