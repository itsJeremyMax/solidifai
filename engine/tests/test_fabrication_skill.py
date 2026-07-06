"""Presence and content checks for the solidifai-fabrication skill."""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ENGINE_ROOT / "workspace_templates" / "skills" / "solidifai-fabrication" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert SKILL_PATH.exists(), f"SKILL.md not found at {SKILL_PATH}"


def test_frontmatter_name(skill_text: str):
    assert "name: solidifai-fabrication" in skill_text


def test_mentions_fab_estimate(skill_text: str):
    assert "fab_estimate" in skill_text


def test_mentions_fab_orient(skill_text: str):
    assert "fab_orient" in skill_text


def test_mentions_fab_open(skill_text: str):
    assert "fab_open" in skill_text


def test_no_em_dashes(skill_text: str):
    assert "—" not in skill_text, "SKILL.md contains an em dash"


def test_cross_links_solidifai_modeling(skill_text: str):
    assert "solidifai-modeling" in skill_text


def test_cross_links_solidifai_self_verify(skill_text: str):
    assert "solidifai-self-verify" in skill_text
