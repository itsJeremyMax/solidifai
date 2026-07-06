"""Presence and content checks for the inside-out packaging feature.

Covers the new internal-layout lens, the integrated-device playbook, and the
enforcement hooks woven into grounding, modeling, assemblies, self-verify, and
AGENTS.md. Mirrors the style of test_delegation_skill.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILLS = ENGINE_ROOT / "workspace_templates" / "skills"
PRODUCT = SKILLS / "solidifai-product-design"
LENS_PATH = PRODUCT / "references" / "internal-layout.md"
PLAYBOOK_PATH = PRODUCT / "playbooks" / "integrated-device.md"
PRODUCT_SKILL = PRODUCT / "SKILL.md"
ELECTRONICS_PATH = PRODUCT / "playbooks" / "electronics-enclosure.md"
GROUNDING_PATH = SKILLS / "solidifai-grounding" / "SKILL.md"
MODELING_SKILL = SKILLS / "solidifai-modeling" / "SKILL.md"
PACKAGING_EXAMPLE = SKILLS / "solidifai-modeling" / "examples" / "packaging-layout.py"
ASSEM_PATH = SKILLS / "solidifai-assemblies" / "SKILL.md"
SELF_VERIFY_PATH = SKILLS / "solidifai-self-verify" / "SKILL.md"
AGENTS_PATH = ENGINE_ROOT / "workspace_templates" / "AGENTS.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# -- the lens ---------------------------------------------------------------


def test_lens_exists():
    assert LENS_PATH.exists(), f"internal-layout lens not found at {LENS_PATH}"


def test_lens_states_inside_out_order():
    text = _read(LENS_PATH).lower()
    # inventory -> layout -> reserve -> derive envelope -> wrap shell
    for token in ("inventory", "layout", "reserve", "envelope", "wrap"):
        assert token in text, f"lens missing inside-out step: {token}"


def test_lens_names_the_reservations():
    text = _read(LENS_PATH).lower()
    for token in ("clearance", "cable", "airflow", "service", "fastener"):
        assert token in text, f"lens missing reservation: {token}"


def test_lens_states_wrap_rule():
    # Outer extent is derived from the packed contents, not guessed.
    text = _read(LENS_PATH).lower()
    assert "wall" in text
    assert "derive" in text or "derived" in text


def test_lens_defers_numbers_not_restated():
    # The packaging lens links out for numbers that other lenses own.
    text = _read(LENS_PATH)
    assert "fits-tolerances.md" in text
    assert "thermal-ventilation.md" in text


def test_lens_no_em_dash():
    assert "—" not in _read(LENS_PATH), "internal-layout.md contains an em dash"


# -- the playbook -----------------------------------------------------------


def test_playbook_exists():
    assert PLAYBOOK_PATH.exists(), f"integrated-device playbook not found at {PLAYBOOK_PATH}"


def test_playbook_scope_names_the_class():
    text = _read(PLAYBOOK_PATH).lower()
    assert "cyberdeck" in text
    # several internal components, not one board
    assert "component" in text


def test_playbook_pulls_internal_layout_lens():
    text = _read(PLAYBOOK_PATH)
    assert "../references/internal-layout.md" in text


def test_playbook_models_reference_volumes():
    # The runnable starter places placeholder component volumes, then a shell.
    text = _read(PLAYBOOK_PATH)
    assert "ref:" in text  # the reference-volume naming convention
    assert "show_internals" in text


def test_playbook_no_em_dash():
    assert "—" not in _read(PLAYBOOK_PATH), "integrated-device.md contains an em dash"


# -- routing ----------------------------------------------------------------


def test_router_sends_device_class_to_playbook():
    text = _read(PRODUCT_SKILL).lower()
    assert "integrated-device" in text
    assert "cyberdeck" in text


def test_electronics_enclosure_hands_off_to_integrated_device():
    text = _read(ELECTRONICS_PATH)
    assert "integrated-device" in text


# -- modeling: reference volumes --------------------------------------------


def test_packaging_example_exists():
    assert PACKAGING_EXAMPLE.exists(), f"packaging-layout.py not found at {PACKAGING_EXAMPLE}"


def test_packaging_example_uses_reference_convention():
    text = _read(PACKAGING_EXAMPLE)
    assert "ref:" in text  # reference-volume naming convention
    assert "show_internals" in text  # the export toggle


def test_modeling_skill_documents_reference_volumes():
    text = _read(MODELING_SKILL).lower()
    assert "reference volume" in text or "reference body" in text
    assert "show_internals" in text
    assert "packaging-layout.py" in text


# -- grounding: contents inventory ------------------------------------------


def test_grounding_triggers_on_containment_objects():
    text = _read(GROUNDING_PATH).lower()
    assert "containment" in text or "contains components" in text or "holds components" in text


def test_grounding_produces_a_contents_inventory():
    text = _read(GROUNDING_PATH).lower()
    assert "inventory" in text
    # internal components named with real dimensions
    assert "internal component" in text or "components it holds" in text


def test_grounding_links_packaging_method():
    text = _read(GROUNDING_PATH)
    assert "internal-layout" in text or "integrated-device" in text


# -- assemblies: layout is the skeleton -------------------------------------


def test_assemblies_names_the_packaging_case():
    text = _read(ASSEM_PATH).lower()
    assert "internal layout" in text or "packaging" in text
    assert "skeleton" in text


def test_assemblies_no_em_dash_in_new_note():
    # assemblies SKILL.md is currently em-dash-free; keep your new note that way too.
    assert "—" not in _read(ASSEM_PATH), "assemblies SKILL.md contains an em dash"


# -- self-verify: containment gate ------------------------------------------


def test_self_verify_has_containment_gate():
    text = _read(SELF_VERIFY_PATH).lower()
    assert "containment" in text
    # the four checks
    assert "inventory" in text  # every component present
    assert "fit" in text or "fits" in text  # fits with clearance
    assert "check_interferences" in text  # no collision / no breakout
    assert "provision" in text  # mounts + port cutouts present


# -- AGENTS.md: build order -------------------------------------------------


def test_agents_states_inside_out_order():
    text = _read(AGENTS_PATH).lower()
    assert "inside-out" in text or "internals first" in text or "inside out" in text
    assert "containment" in text or "contains" in text


def test_agents_brief_includes_inventory():
    text = _read(AGENTS_PATH).lower()
    assert "inventory" in text


def test_agents_routes_to_packaging_skills():
    text = _read(AGENTS_PATH)
    assert "integrated-device" in text or "internal-layout" in text


# -- role="reference" is the consistent mechanism ---------------------------


def test_packaging_example_uses_reference_role():
    text = _read(PACKAGING_EXAMPLE)
    assert 'role="reference"' in text, "packaging-layout.py must mark components role=reference"


def test_playbook_starter_uses_reference_role():
    text = _read(PLAYBOOK_PATH)
    assert 'role="reference"' in text, "integrated-device starter must use role=reference"


def test_modeling_documents_reference_role_and_auto_export_exclusion():
    text = _read(MODELING_SKILL)
    assert 'role="reference"' in text
    low = text.lower()
    # the skill states export exclusion is automatic via role, not a manual toggle
    assert "export" in low and "reference" in low


def test_assemblies_components_are_reference_bodies_not_printed_parts():
    text = _read(ASSEM_PATH)
    assert 'role="reference"' in text
    low = text.lower()
    assert "reference volume" in low


def test_assemblies_shows_reference_part_example():
    # the assembly inside-out path is shown concretely, not just asserted
    text = _read(ASSEM_PATH)
    assert "ref-sbc" in text  # a reference component authored as an assembly part
    assert 'role="reference"' in text
