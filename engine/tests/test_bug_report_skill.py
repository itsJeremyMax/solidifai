"""Presence and content checks for the solidifai-bug-report skill and its wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILLS = ENGINE_ROOT / "workspace_templates" / "skills"
SKILL_PATH = SKILLS / "solidifai-bug-report" / "SKILL.md"
DEBUG_PATH = SKILLS / "solidifai-debugging" / "SKILL.md"
AGENTS_PATH = ENGINE_ROOT / "workspace_templates" / "AGENTS.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_skill_file_exists():
    assert SKILL_PATH.exists()


def test_frontmatter_name(skill_text: str):
    assert "name: solidifai-bug-report" in skill_text


def test_invokes_using_solidifai_first(skill_text: str):
    assert "using-solidifai" in skill_text


def test_only_report_issue_builds_the_url(skill_text: str):
    assert "report_issue" in skill_text
    lowered = skill_text.lower()
    assert "never" in lowered and "url" in lowered  # "never hand-assemble the URL"


def test_states_consent_and_public(skill_text: str):
    lowered = skill_text.lower()
    assert "public" in lowered
    assert "never" in lowered and ("submit" in lowered or "file" in lowered)


def test_lists_what_not_to_include(skill_text: str):
    lowered = skill_text.lower()
    assert "secret" in lowered or "sensitive" in lowered
    assert "file contents" in lowered or "proprietary" in lowered


def test_triggers_on_repeated_failure_and_user_request(skill_text: str):
    lowered = skill_text.lower()
    assert "repeated" in lowered or "again" in lowered
    assert "product" in lowered  # genuine product defect, not user/model error


def test_debugging_skill_points_here():
    assert "solidifai-bug-report" in DEBUG_PATH.read_text(encoding="utf-8")


def test_agents_md_lists_skill():
    assert "solidifai-bug-report" in AGENTS_PATH.read_text(encoding="utf-8")
