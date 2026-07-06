import json

from solidifai_engine.assembly import manifest as m


def test_load_round_trips(tmp_path):
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "base",
                        "kind": "part",
                        "source": "parts/base.py",
                        "attach": "base_frame",
                        "inputs": ["body_w", "wall"],
                    },
                    {
                        "id": "hinge",
                        "kind": "assembly",
                        "source": "hinge/",
                        "attach": "hinge_frame",
                        "inputs": ["body_w"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    man = m.load_manifest(str(tmp_path))
    assert man.skeleton == "skeleton.py"
    assert [c.id for c in man.children] == ["base", "hinge"]
    assert man.children[0].kind == "part"
    assert man.children[0].inputs == ["body_w", "wall"]
    assert man.children[1].kind == "assembly"


def test_missing_manifest_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        m.load_manifest(str(tmp_path))


def test_bad_child_kind_raises(tmp_path):
    import pytest

    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": None,
                "children": [{"id": "x", "kind": "widget", "source": "parts/x.py"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="kind"):
        m.load_manifest(str(tmp_path))


def test_write_then_load(tmp_path):
    man = m.Manifest(
        skeleton=None,
        children=[
            m.ChildEntry(id="solo", kind="part", source="parts/solo.py", attach=None, inputs=[]),
        ],
    )
    m.write_manifest(str(tmp_path), man)
    again = m.load_manifest(str(tmp_path))
    assert again.children[0].id == "solo"
    assert again.skeleton is None


# -- Fix 1: containment + id validation at the manifest chokepoint -----------
# PoC: a hand-edited child source "../EVIL.py" makes graph.build_node read+exec
# code OUTSIDE the workspace (and flatten embeds it). Validate at load_manifest,
# the single chokepoint every consumer passes through, so it fails loudly.


def test_escaping_source_raises(tmp_path):
    import pytest

    node = tmp_path / "ws"
    node.mkdir()
    (node / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": None,
                "children": [{"id": "evil", "kind": "part", "source": "../evil.py"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="escapes"):
        m.load_manifest(str(node))


def test_bad_child_id_raises(tmp_path):
    import pytest

    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": None,
                "children": [{"id": "../evil", "kind": "part", "source": "parts/x.py"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid id"):
        m.load_manifest(str(tmp_path))


def test_legitimate_sources_still_load(tmp_path):
    # the two legitimate source shapes (parts/<id>.py and <id>/) both stay inside
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {"id": "base", "kind": "part", "source": "parts/base.py"},
                    {"id": "hinge", "kind": "assembly", "source": "hinge/"},
                ],
            }
        ),
        encoding="utf-8",
    )
    man = m.load_manifest(str(tmp_path))
    assert [c.id for c in man.children] == ["base", "hinge"]


def test_build_node_refuses_escaping_source_instead_of_exec(tmp_path):
    """End-to-end: graph.build_node on the malicious manifest raises loudly and
    NEVER executes the out-of-root file (its side-effect file must be absent)."""
    import pytest

    from solidifai_engine.assembly import graph

    node = tmp_path / "ws"
    node.mkdir()
    # an out-of-root payload that, if exec'd, would write a marker beside itself
    marker = tmp_path / "PWNED"
    evil = tmp_path / "evil.py"
    evil.write_text(
        "from solidifai import show\n"
        "from build123d import Box\n"
        f"open({str(marker)!r}, 'w').write('x')\n"
        "def build(inputs):\n"
        "    show(Box(1, 1, 1))\n",
        encoding="utf-8",
    )
    (node / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": None,
                "children": [{"id": "evil", "kind": "part", "source": "../evil.py"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes"):
        graph.build_node(str(node), params={}, parent=None)
    assert not marker.exists(), "the out-of-root file was executed"
