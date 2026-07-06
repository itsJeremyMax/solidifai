"""views.py must capture a view using only narrowed vtkmodules imports."""

import importlib
import pathlib


def test_views_imports_no_vtkmodules_all():
    src = importlib.import_module("solidifai_engine.views").__file__
    text = pathlib.Path(src).read_text(encoding="utf-8")
    assert "import vtkmodules.all" not in text, "views.py must not import vtkmodules.all"


def test_view_capture_produces_image(tmp_path):
    from solidifai_engine import views

    out = views.capture_smoke(str(tmp_path))
    assert out and all(pathlib.Path(p).exists() for p in out), "expected captured view files"
