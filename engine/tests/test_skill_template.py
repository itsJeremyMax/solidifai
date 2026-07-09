"""Template contract for the workspace skills collection (Phase 1 refactor).

Every SKILL.md migrated to the shared template is listed in TEMPLATE_SKILLS;
each refactor task appends its skill so every commit stays green, and the final
task asserts the list covers the whole collection. Pinned here: frontmatter,
the using-solidifai opener line, exact H2 section set + order, the em-dash ban,
per-file word ceilings (the anti-rebloat ratchet), and the two Phase 1 quality
additions (detail-density checklist, dimensional-grounding hard rule)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILLS = ENGINE_ROOT / "workspace_templates" / "skills"
AGENTS = ENGINE_ROOT / "workspace_templates" / "AGENTS.md"

# Grown one rewrite task at a time; the final task asserts full coverage.
TEMPLATE_SKILLS: list[str] = [
    "using-solidifai",
    "solidifai-modeling",
    "solidifai-product-design",
    "solidifai-grounding",
    "solidifai-self-verify",
    "solidifai-assemblies",
    "solidifai-orchestration",
    "solidifai-delegation",
    "solidifai-converge",
    "solidifai-explore",
    "solidifai-debugging",
    "solidifai-history",
    "solidifai-fabrication",
    "solidifai-reverse-engineering",
    "solidifai-critique",
]

# using-solidifai IS the entry point: no opener line, and its router role
# allows the one extra H2 listed in EXTRA_H2.
OPENER_EXEMPT = {"using-solidifai"}
EXTRA_H2 = {"using-solidifai": ["## You are Sol"]}

OPENER = (
    "> Invoke the `using-solidifai` skill first if you have not already this "
    "session; it orients you to this workspace and the `solidifai-cad` engine "
    "every skill here drives."
)

REQUIRED_H2 = [
    "## When to use",
    "## The procedure",
    "## Anti-patterns",
    "## Cross-references",
]

WORD_CEILINGS = {
    "using-solidifai": 1100,
    "solidifai-modeling": 2000,
    "solidifai-product-design": 1650,
    # raised for Task 8: save_reference step + anti-pattern row (deliberate, not rebloat)
    "solidifai-grounding": 1600,
    # raised for the Phase 2 perception + Phase 3 critique additions, then again for the spatial
    # + joint-motion verify checks (measure_between/query_faces/thickness_at, check_motion joint
    # mode); deliberate, not rebloat
    "solidifai-self-verify": 1670,
    # raised for occurrences (set_occurrences instancing) + joints (s.joint / check_motion joint
    # mode), two new engine subsystems taught here; deliberate, not rebloat
    "solidifai-assemblies": 2140,
    "solidifai-orchestration": 1350,
    "solidifai-delegation": 1000,
    "solidifai-converge": 1000,
    "solidifai-explore": 690,
    "solidifai-debugging": 820,
    "solidifai-history": 700,
    "solidifai-reverse-engineering": 650,
    "solidifai-fabrication": 950,
    "solidifai-critique": 2000,  # three verbatim critic prompts; same ceiling as modeling
}


def _read(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _h2(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.startswith("## ")]


@pytest.mark.parametrize("name", TEMPLATE_SKILLS)
def test_frontmatter(name: str):
    text = _read(name)
    assert text.startswith("---\n")
    assert f"name: {name}" in text
    assert "license: MIT" in text


@pytest.mark.parametrize("name", TEMPLATE_SKILLS)
def test_opener_line(name: str):
    if name in OPENER_EXEMPT:
        pytest.skip("entry point itself")
    body = _read(name)
    assert OPENER in body, f"{name} missing the standard opener line"
    # Opener sits directly under the H1 title.
    lines = [ln for ln in body.splitlines() if ln.strip()]
    h1 = next(i for i, ln in enumerate(lines) if ln.startswith("# "))
    assert lines[h1 + 1].startswith("> Invoke the `using-solidifai`")


@pytest.mark.parametrize("name", TEMPLATE_SKILLS)
def test_exact_h2_set_and_order(name: str):
    have = _h2(_read(name))
    allowed = REQUIRED_H2 + EXTRA_H2.get(name, [])
    assert set(have) == set(allowed), f"{name} H2 drift: {have}"
    order = [h for h in have if h in REQUIRED_H2]
    assert order == REQUIRED_H2, f"{name} sections out of order: {order}"


@pytest.mark.parametrize("name", TEMPLATE_SKILLS)
def test_no_em_dashes(name: str):
    assert "—" not in _read(name), f"{name} contains an em dash"


@pytest.mark.parametrize("name", TEMPLATE_SKILLS)
def test_word_ceiling(name: str):
    words = len(_read(name).split())
    assert words <= WORD_CEILINGS[name], (
        f"{name} is {words} words (ceiling {WORD_CEILINGS[name]}); the refactor "
        "must shrink it, and later edits must not re-bloat it"
    )


def test_product_design_detail_density_checklist():
    text = (SKILLS / "solidifai-product-design" / "SKILL.md").read_text(encoding="utf-8")
    assert "### Finishing pass: detail density" in text
    low = text.lower()
    for token in ("edge-break", "slab", "rib", "draft", "seam", "proportion", "ratio"):
        assert token in low, f"detail-density checklist missing: {token}"


def test_grounding_dimensional_hard_rule():
    text = (SKILLS / "solidifai-grounding" / "SKILL.md").read_text(encoding="utf-8")
    assert "### Hard rule: verified dims for named objects" in text
    low = text.lower()
    assert "verified" in low and "before" in low
    assert "unverified" in low  # the no-web degradation path
    assert "never silently guess" in low
    assert "build brief" in low


ALL_SKILL_NAMES = sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def test_agents_routing_table_routes_every_skill():
    text = AGENTS.read_text(encoding="utf-8")
    assert "## Routing: which skill, when" in text
    start = text.index("## Routing: which skill, when")
    end = text.index("\n## ", start + 1)
    table = text[start:end]
    rows = [ln for ln in table.splitlines() if ln.startswith("|")]
    assert len(rows) >= 16  # header + separator + >=14 situations
    for name in ALL_SKILL_NAMES:
        assert f"`{name}`" in table, f"routing table missing {name}"


def test_agents_no_em_dashes():
    assert "—" not in AGENTS.read_text(encoding="utf-8")


def test_agents_word_ceiling():
    # Anti-rebloat ratchet on instruction prose. Exclude the structural
    # HTML-comment region markers (solidifai-managed / -profile / -custom): they
    # are a substitution mechanism, not words the agent reads, so they must not
    # eat into the prose budget.
    text = AGENTS.read_text(encoding="utf-8")
    prose = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # raised for the new spatial (measure_between/query_faces/thickness_at), instancing
    # (set_occurrences), and joint-motion (check_motion) tool-table rows; deliberate, not rebloat
    assert len(prose.split()) <= 3560


def test_template_covers_every_skill():
    assert sorted(TEMPLATE_SKILLS) == ALL_SKILL_NAMES


def test_agents_keeps_hard_directive_and_sol():
    text = AGENTS.read_text(encoding="utf-8")
    assert "**FIRST, before anything else: invoke the `using-solidifai` skill.**" in text
    assert "## You are Sol" in text
    assert "<!-- solidifai-profile:start" in text
    assert "<!-- solidifai-profile:end -->" in text


# -- Phase 4: lookup_standard / lookup_reference wiring -------------------------


def test_lookup_tools_in_agents_tool_table():
    text = AGENTS.read_text(encoding="utf-8")
    assert "`lookup_standard(query)`" in text
    assert "`lookup_reference(object)`" in text
    # Dead-link ratchet: the writable counterpart must be documented so the
    # learnable library is something Sol is told to grow, not just read.
    assert "`save_reference(" in text


def test_grounding_points_library_first():
    text = (SKILLS / "solidifai-grounding" / "SKILL.md").read_text(encoding="utf-8")
    # Scope to the hard-rule section so unrelated "web" mentions elsewhere in
    # the skill can't make this pass or fail by accident.
    start = text.index("### Hard rule: verified dims for named objects")
    section = text[start : start + 1600].lower()
    assert "lookup_reference" in section and "lookup_standard" in section
    assert section.index("lookup_reference") < section.index("web tools"), (
        "the library check must come before the web fallback"
    )
    # Dead-link ratchet: the web-verify branch must tell Sol to SAVE the verified
    # dims, or save_reference is a tool nothing instructs Sol to call.
    assert "save_reference" in section, (
        "grounding's web-verify branch must call save_reference for the verified entry"
    )


def test_modeling_documents_std_namespace():
    text = (SKILLS / "solidifai-modeling" / "SKILL.md").read_text(encoding="utf-8")
    assert "from solidifai import show, std" in text
    assert "std.clearance_hole" in text


def test_delegation_marks_lookups_scout_safe():
    text = (SKILLS / "solidifai-delegation" / "SKILL.md").read_text(encoding="utf-8")
    assert "lookup_standard" in text and "lookup_reference" in text
