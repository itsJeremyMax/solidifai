"""Validate every build123d snippet shipped in the workspace skills collection.

This is the regression guard that makes the Agent Skills docs trustworthy: an
LLM reads these files to model parts, so every runnable snippet MUST actually
build against the installed build123d. We:

1. Exec each ``examples/*.py`` through a real ``Session`` and assert the build
   succeeds and the resulting solid is valid + manifold.
2. Extract every fenced ```python block from the two ``SKILL.md`` files and all
   ``references/*.md`` files, and exec each block that calls ``show(...)``,
   asserting it builds (valid + manifold). Blocks tagged ``# doctest: +SKIP``
   (deliberately-broken "before" snippets / fragments) are skipped.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest

from solidifai_engine.session import Session

ENGINE_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ENGINE_ROOT / "workspace_templates" / "skills"

MODELING = SKILLS_ROOT / "solidifai-modeling"
DEBUGGING = SKILLS_ROOT / "solidifai-debugging"
USING = SKILLS_ROOT / "using-solidifai"
PRODUCT = SKILLS_ROOT / "solidifai-product-design"

EXAMPLE_FILES = sorted(
    [
        *MODELING.glob("examples/*.py"),
        *PRODUCT.glob("examples/*.py"),
    ]
)

MARKDOWN_FILES = sorted(
    [
        USING / "SKILL.md",
        MODELING / "SKILL.md",
        DEBUGGING / "SKILL.md",
        PRODUCT / "SKILL.md",
        *MODELING.glob("references/*.md"),
        *DEBUGGING.glob("references/*.md"),
        *PRODUCT.glob("references/*.md"),
        *PRODUCT.glob("playbooks/*.md"),
    ]
)

# A block whose first line carries this marker is an illustration, not runnable.
SKIP_MARKER = "# doctest: +SKIP"
# A block carrying this marker builds a VALID solid that is intentionally non-manifold
# (e.g. a cosmetic swept-helix thread): assert it builds + is valid, but not manifold.
NONMANIFOLD_MARKER = "# doctest: +NONMANIFOLD"

_FENCE_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _run(code: str) -> dict:
    """Execute a snippet through a throwaway Session in a temp artifacts dir."""
    with tempfile.TemporaryDirectory() as d:
        sess = Session(d)
        result = sess.execute_script(code)
        if result.get("ok"):
            result["_info"] = json.loads((Path(d) / "model.json").read_text())
        return result


def _python_blocks(md_path: Path) -> list[str]:
    return _FENCE_RE.findall(md_path.read_text(encoding="utf-8"))


def _assert_built(result: dict, label: str, *, require_manifold: bool = True) -> None:
    assert result["ok"] is True, f"{label} failed to build: {result.get('error')}"
    info = result["_info"]
    assert info["valid"] is True, f"{label} produced an invalid solid"
    if require_manifold:
        assert info["manifold"] is True, f"{label} produced a non-manifold solid"


def test_assert_built_respects_require_manifold():
    """A valid-but-non-manifold result is accepted only when manifold isn't required."""
    nonmanifold = {"ok": True, "_info": {"valid": True, "manifold": False}}
    _assert_built(nonmanifold, "synthetic", require_manifold=False)  # must not raise
    with pytest.raises(AssertionError):
        _assert_built(nonmanifold, "synthetic")  # default still requires manifold


# -- examples ---------------------------------------------------------------


def test_example_files_discovered():
    # Guard against an empty glob silently passing the whole suite.
    assert EXAMPLE_FILES, "no example *.py files found under solidifai-modeling/examples"


@pytest.mark.parametrize("example", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_builds(example: Path):
    _assert_built(_run(example.read_text(encoding="utf-8")), f"example {example.name}")


# -- markdown snippets ------------------------------------------------------


def _all_snippets() -> list[tuple[Path, int, str]]:
    items: list[tuple[Path, int, str]] = []
    for md in MARKDOWN_FILES:
        for i, block in enumerate(_python_blocks(md)):
            items.append((md, i, block))
    return items


SNIPPETS = _all_snippets()


def test_snippets_discovered():
    assert SNIPPETS, "no fenced python blocks found in the skill markdown"


@pytest.mark.parametrize(
    "md,index,block",
    SNIPPETS,
    ids=[f"{md.parent.name}/{md.name}#{i}" for (md, i, _) in SNIPPETS],
)
def test_markdown_snippet_builds(md: Path, index: int, block: str):
    if SKIP_MARKER in block:
        pytest.skip(f"{md.name}#{index} is marked +SKIP (illustration only)")
    if "show(" not in block:
        pytest.skip(f"{md.name}#{index} does not call show() (fragment)")
    require_manifold = NONMANIFOLD_MARKER not in block
    _assert_built(
        _run(block),
        f"{md.parent.name}/{md.name} block #{index}",
        require_manifold=require_manifold,
    )
