"""Regression tests for the audit pipeline/export correctness fixes.

These cover the compound child-theft family (A/B), export-from-snapshot (C/G),
the diff double-build (D), failed-build param preservation (E), and mirrored
mass properties (F). Each was empirically reproduced before the fix.
"""

import json

import pytest
from build123d import import_brep

import solidifai
from solidifai_engine.session import Session

# -- shared scripts ---------------------------------------------------------

CUBE = "from solidifai import show\nfrom build123d import Box\nshow(Box(10, 10, 10), name='p')\n"

# Same live shape object shown twice: a natural way to duplicate a body.
DUP = (
    "from solidifai import show\n"
    "from build123d import Box\n"
    "b = Box(10, 10, 10)\n"
    "show(b, name='left')\n"
    "show(b, name='right')\n"
)

# shows a small box then raises: leaves partial geometry in the live registry
BAD = (
    "from solidifai import show\n"
    "from build123d import Box\n"
    "show(Box(2, 2, 2), name='p')\n"
    "raise ValueError('boom')\n"
)

# Parametric, __main__-guarded (registry empty on exec, engine builds it).
GOOD_PARAM = (
    "from solidifai import show\n"
    "from build123d import Box\n"
    'PARAMS = {"size": {"value": 20.0, "min": 5.0, "max": 50.0, "step": 1.0, "unit": "mm"}}\n'
    "def build(size):\n"
    "    show(Box(size, size, size), name='cube')\n"
    'if __name__ == "__main__":\n'
    "    build(**{k: v['value'] for k, v in PARAMS.items()})\n"
)

# Conventional tail: build(**defaults) runs at module level (registry populated
# on exec), so any explicit rebuild that forgets to reset doubles the geometry.
CONV = (
    "from solidifai import show\n"
    "from build123d import Box\n"
    'PARAMS = {"size": {"value": 20.0, "min": 5.0, "max": 50.0, "step": 1.0, "unit": "mm"}}\n'
    "def build(size):\n"
    "    show(Box(size, size, size), name='cube')\n"
    "build(**{k: v['value'] for k, v in PARAMS.items()})\n"
)

# left at x in [-25,-15]; mirrored right at x in [15,25]. Negative-determinant
# solid -> the compound's own signed volume/COM come out wrong.
MIRROR_PAIR = (
    "from solidifai import show\n"
    "from build123d import Box, Pos, mirror, Plane\n"
    "left = Pos(-20, 0, 0) * Box(10, 10, 10)\n"
    "right = mirror(left, Plane.YZ)\n"
    "show(left, name='left')\n"
    "show(right, name='right')\n"
)


def _session(tmp_path) -> Session:
    (tmp_path / ".solidifai").mkdir(exist_ok=True)
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    return Session(artifacts, model_path=str(tmp_path / "model.py"))


def _exported_volume(tmp_path, name: str) -> float:
    path = tmp_path / "exports" / name
    return float(import_brep(str(path)).volume)


# -- Finding A: compound child-theft corrupts the snapshot ------------------


def test_export_does_not_empty_model_snapshot(tmp_path):
    s = _session(tmp_path)
    assert s.execute_script(CUBE)["ok"] is True
    vol = s._model.volume
    assert vol == pytest.approx(1000.0)

    assert s.export("brep", "out.brep")["ok"] is True

    # Before the fix, export wrapped the live registry shapes in a fresh Compound,
    # reparenting them out of self._model and leaving it empty.
    assert s._model.volume == pytest.approx(vol)
    # And the snapshot is still tessellatable (the capture_views failure mode).
    verts, _ = s._model.tessellate(0.5)
    assert len(verts) > 0


# -- Finding B: showing the same shape twice ---------------------------------


def test_show_same_shape_twice_builds(tmp_path):
    s = _session(tmp_path)
    res = s.execute_script(DUP)
    assert res["ok"] is True, res
    info = s.get_model_info()
    assert len(info["objects"]) == 2
    assert info["volume"] == pytest.approx(2000.0)  # both instances count


# -- Finding C: export reads the last-good snapshot, not the live registry ---


def test_export_uses_last_good_snapshot(tmp_path):
    s = _session(tmp_path)
    assert s.execute_script(CUBE)["ok"] is True  # 10mm cube, vol 1000
    assert s.execute_script(BAD)["ok"] is False  # live registry now holds a 2mm box

    assert s.export("brep", "out.brep")["ok"] is True
    # The exported geometry is the last-good cube (1000), not the partial 2mm box (8).
    assert _exported_volume(tmp_path, "out.brep") == pytest.approx(1000.0)


# -- Finding D: conventional-script diff must not double-build ---------------


def test_diff_against_conventional_script_not_doubled(tmp_path):
    s = _session(tmp_path)
    assert s.execute_script(CONV)["ok"] is True  # 20mm cube, vol 8000

    d = s.diff_against(0)
    assert d["ok"] is True, d
    assert d["checkpointVolume"] == pytest.approx(8000.0)  # not 16000
    assert d["currentVolume"] == pytest.approx(8000.0)
    # The non-destructive diff must leave the live registry rebuilt exactly once.
    assert len(list(solidifai._registry())) == 1


# -- Finding E: a failed build preserves last-good parametric state ----------


def test_failed_build_preserves_parametric_state(tmp_path):
    s = _session(tmp_path)
    assert s.execute_script(GOOD_PARAM)["ok"] is True
    assert s.get_params()["values"] == {"size": 20.0}

    assert s.execute_script(BAD)["ok"] is False

    # get_params/set_params still see the last-good parametric model.
    assert s.get_params()["values"] == {"size": 20.0}
    assert s.set_params({"size": 30.0})["ok"] is True


# -- Finding F: mirrored parts contribute their full volume/COM --------------


def test_mirrored_pair_mass_properties(tmp_path):
    s = _session(tmp_path)
    assert s.execute_script(MIRROR_PAIR)["ok"] is True
    info = s.get_model_info()
    assert info["volume"] == pytest.approx(2000.0)  # not 1000 (mirror cancels)
    com = info["centerOfMass"]
    assert com[0] == pytest.approx(0.0, abs=1e-4)  # symmetric pair -> x = 0


# -- Finding G: assembly workspaces can render and export --------------------


def _assembly_workspace(tmp_path):
    (tmp_path / "parts").mkdir()
    (tmp_path / "skeleton.py").write_text(
        "from solidifai import skeleton\n"
        "from build123d import Location\n"
        'PARAMS = {"body_w": {"value": 40.0, "min": 10, "max": 80, "step": 1, "unit": "mm"},\n'
        '          "wall": {"value": 2.0, "min": 1, "max": 5, "step": 0.5, "unit": "mm"}}\n'
        "def build(body_w, wall):\n"
        '    s = skeleton(); s.scalar("body_w", body_w); s.scalar("wall", wall)\n'
        '    s.frame("base_frame", Location((0, 0, 0)))\n'
        '    s.frame("lid_frame", Location((0, 0, 20)))\n'
        "    return s\n",
        encoding="utf-8",
    )
    for pid, nm in (("base", "Base"), ("lid", "Lid")):
        (tmp_path / "parts" / f"{pid}.py").write_text(
            "from solidifai import show\n"
            "from build123d import BuildPart, Box\n"
            "def build(inputs):\n"
            "    with BuildPart() as p:\n"
            '        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])\n'
            f'    show(p.part, name="{nm}")\n',
            encoding="utf-8",
        )
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
                        "id": "lid",
                        "kind": "part",
                        "source": "parts/lid.py",
                        "attach": "lid_frame",
                        "inputs": ["body_w", "wall"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_assembly_can_export_and_render(tmp_path):
    _assembly_workspace(tmp_path)
    s = _session(tmp_path)
    assert s._is_assembly_mode() is True
    assert s._build_assembly(params={})["ok"] is True

    # Export used to bail with "no model loaded" (it gated on self.code, which the
    # assembly path never sets); now it exports the composed snapshot.
    assert s.export("brep", "out.brep")["ok"] is True
    # Two 40x40x2 boxes = 6400 mm^3 total.
    assert _exported_volume(tmp_path, "out.brep") == pytest.approx(6400.0)

    assert s.render()["ok"] is True
