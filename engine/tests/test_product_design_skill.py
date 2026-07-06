"""Structural guard for the solidifai-product-design skill.

Every lens (references/*.md) and playbook (playbooks/*.md) must follow the fixed
template so the modeling agent always knows where to look, and every playbook's
lens cross-link must resolve to a real lens file. Snippet *build* validity is
covered separately by test_skill_examples.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILL = ENGINE_ROOT / "workspace_templates" / "skills" / "solidifai-product-design"
REFERENCES = SKILL / "references"
PLAYBOOKS = SKILL / "playbooks"

EXPECTED_LENSES = {
    "ergonomics.md",
    "affordance-usability.md",
    "manufacturability.md",
    "dfm-additive.md",
    "dfm-subtractive.md",
    "dfm-formative.md",
    "dfm-sheet.md",
    "structure.md",
    "support-stability.md",
    "aesthetics-form.md",
    "thermal-ventilation.md",
    "sealing-ingress.md",
    "fits-tolerances.md",
    "serviceability-assembly.md",
    "internal-layout.md",
}
EXPECTED_PLAYBOOKS = {
    "handheld-enclosure.md",
    "electronics-enclosure.md",
    "wearable.md",
    "grip-handle.md",
    "knob-control.md",
    "bracket-mount.md",
    "container-lid.md",
    "stand-cradle.md",
    "integrated-device.md",
}

LENS_HEADINGS = [
    "## Principle",
    "## Data & defaults",
    "## Decision rules",
    "## Questions that matter",
    "## Verify",
    "## Sources",
]
PLAYBOOK_HEADINGS = [
    "## Scope",
    "## Lenses it pulls",
    "## Default recipe",
    "## Questions that matter",
    "## Verify checklist",
    "## Common failure modes",
]

# Matches links like ](../references/ergonomics.md#grip) used inside playbooks.
_LENS_LINK_RE = re.compile(r"\]\(\.\./references/([a-z0-9-]+\.md)(?:#[a-z0-9-]+)?\)")


def _h2(md: Path) -> list[str]:
    return [
        ln.strip() for ln in md.read_text(encoding="utf-8").splitlines() if ln.startswith("## ")
    ]


def test_skill_dir_and_skillmd_present():
    assert (SKILL / "SKILL.md").is_file()
    assert "name: solidifai-product-design" in (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_all_lenses_present():
    actual = {p.name for p in REFERENCES.glob("*.md")}
    assert actual >= EXPECTED_LENSES, f"missing lenses: {EXPECTED_LENSES - actual}"


def test_all_playbooks_present():
    actual = {p.name for p in PLAYBOOKS.glob("*.md")}
    assert actual >= EXPECTED_PLAYBOOKS, f"missing playbooks: {EXPECTED_PLAYBOOKS - actual}"


@pytest.mark.parametrize("name", sorted(EXPECTED_LENSES))
def test_lens_has_required_headings(name):
    md = REFERENCES / name
    if not md.is_file():
        pytest.skip(f"{name} not authored yet")
    have = _h2(md)
    for req in LENS_HEADINGS:
        assert any(h.startswith(req) for h in have), f"{name} missing heading: {req}"


@pytest.mark.parametrize("name", sorted(EXPECTED_PLAYBOOKS))
def test_playbook_has_required_headings(name):
    md = PLAYBOOKS / name
    if not md.is_file():
        pytest.skip(f"{name} not authored yet")
    have = _h2(md)
    for req in PLAYBOOK_HEADINGS:
        assert any(h.startswith(req) for h in have), f"{name} missing heading: {req}"


@pytest.mark.parametrize("name", sorted(EXPECTED_PLAYBOOKS))
def test_playbook_lens_links_resolve(name):
    md = PLAYBOOKS / name
    if not md.is_file():
        pytest.skip(f"{name} not authored yet")
    for target in _LENS_LINK_RE.findall(md.read_text(encoding="utf-8")):
        assert (REFERENCES / target).is_file(), f"{name} links to missing lens {target}"
