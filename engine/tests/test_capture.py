"""Golden characterization of the capture mesh-assembly path, captured BEFORE
the capture.py extraction so the refactor is provably behavior-preserving.

Adapted from the task brief to the real Session API: scripts render via
`solidifai.show(...)` (there is no `render(...)` global), and
`Session.capture_views` takes the view list as `view_names`."""

import os

import pytest

from solidifai_engine.session import Session

CUBE = """
from build123d import Box
from solidifai import show

b = Box(20, 20, 20)
show(b, name="cube")
"""

TWO_PARTS = """
from build123d import Box, Pos
from solidifai import show

a = Box(10, 10, 10)
b = Pos(30, 0, 0) * Box(10, 10, 10)
show(a, name="a")
show(b, name="b")
"""


def _offscreen_or_skip():
    """Skip when offscreen GL can't initialize (headless CI), like test_views."""
    try:
        import vtkmodules.all as vtk

        win = vtk.vtkRenderWindow()
        win.SetOffScreenRendering(1)
        win.AddRenderer(vtk.vtkRenderer())
        win.SetSize(64, 64)
        win.Render()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"offscreen GL unavailable: {exc}")


def _session(tmp_path, script):
    s = Session(str(tmp_path))
    res = s.execute_script(script)
    assert res["ok"], res
    return s


def test_capture_separate_default_iso_writes_one_png(tmp_path):
    _offscreen_or_skip()
    s = _session(tmp_path, CUBE)
    res = s.capture_views()
    assert res["ok"] and res["layout"] == "separate"
    assert len(res["views"]) == 1
    assert os.path.exists(res["views"][0]["path"])


def test_capture_grid_writes_single_sheet(tmp_path):
    _offscreen_or_skip()
    s = _session(tmp_path, CUBE)
    res = s.capture_views(view_names=["iso", "front"], layout="grid")
    assert res["ok"] and res["layout"] == "grid"
    assert res["views"][0]["name"] == "contact_sheet"


def test_capture_explode_does_not_mutate_model(tmp_path):
    _offscreen_or_skip()
    s = _session(tmp_path, TWO_PARTS)
    before = s._model.volume
    res = s.capture_views(explode=40.0)
    assert res["ok"]
    assert s._model.volume == before  # explode renders copies, never mutates


def test_capture_bad_resolution_is_clean_error(tmp_path):
    # No GL: resolution is validated before any render.
    s = _session(tmp_path, CUBE)
    res = s.capture_views(resolution=99)
    assert not res["ok"] and "256..2048" in res["error"]


def test_capture_unknown_focus_lists_valid(tmp_path):
    # No GL: focus is resolved against the feature snapshot before any render.
    s = _session(tmp_path, CUBE)
    res = s.capture_views(focus="nonexistent_feature")
    assert not res["ok"] and "unknown focus feature" in res["error"]
