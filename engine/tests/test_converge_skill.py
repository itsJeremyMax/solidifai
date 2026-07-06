"""Structural guard for the solidifai-converge agent skill.

Confirms the skill file exists, has valid frontmatter, and has substantive content.
Snippet build validity is not checked here because this skill has no runnable code
examples (it documents MCP tool calls, not build123d scripts).
"""

from __future__ import annotations

import re
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ENGINE_ROOT / "workspace_templates" / "skills" / "solidifai-converge"
SKILL_MD = SKILL_DIR / "SKILL.md"


def _frontmatter(text: str) -> dict[str, str]:
    """Parse the YAML frontmatter block between the opening and closing `---` lines."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^(\w+):\s*(.+)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
    return fields


def test_skill_dir_exists():
    assert SKILL_DIR.is_dir(), f"skill directory missing: {SKILL_DIR}"


def test_skill_md_exists():
    assert SKILL_MD.is_file(), f"SKILL.md missing: {SKILL_MD}"


def test_skill_name_frontmatter():
    text = SKILL_MD.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm.get("name") == "solidifai-converge", (
        f"expected name 'solidifai-converge', got {fm.get('name')!r}"
    )


def test_skill_has_description():
    text = SKILL_MD.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    desc = fm.get("description", "")
    assert len(desc) > 40, "description is too short or missing"


def test_skill_has_license():
    text = SKILL_MD.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm.get("license") == "MIT"


def test_skill_body_is_nontrivial():
    text = SKILL_MD.read_text(encoding="utf-8")
    # Strip frontmatter to get body length
    parts = text.split("---", 2)
    body = parts[2] if len(parts) >= 3 else ""
    assert len(body.strip()) > 500, "skill body is too short to be useful"


def test_skill_covers_converge_to_spec():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "converge_to_spec" in text, "skill must document the converge_to_spec tool"


def test_skill_covers_check_requirements():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "check_requirements" in text, "skill must document check_requirements"


def test_skill_covers_execute_script():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "execute_script" in text, "skill must reference geometry editing via execute_script"


def test_skill_no_em_dashes():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "—" not in text, "skill contains an em dash -- remove it"


def test_skill_cross_links_self_verify():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "solidifai-self-verify" in text, "skill must cross-link solidifai-self-verify"


def test_skill_cross_links_modeling():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "solidifai-modeling" in text, "skill must cross-link solidifai-modeling"


def test_skill_cross_links_explore():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "solidifai-explore" in text, "skill must cross-link solidifai-explore"
