"""Regression tests for the session-group correctness fixes from the deep audit."""

import json
import tempfile
from pathlib import Path

import pytest

from solidifai_engine.session import Session

# A parametric model using the conventional __main__ guard (registry stays empty
# on exec, so the engine builds it with the declared defaults).
GOOD_PARAM = (
    "from solidifai import show\n"
    "from build123d import Box\n"
    'PARAMS = {"size": {"value": 20.0, "min": 5.0, "max": 50.0, "step": 1.0, "unit": "mm"}}\n'
    "def build(size):\n"
    "    show(Box(size, size, size), name='cube')\n"
    'if __name__ == "__main__":\n'
    "    build(**{k: v['value'] for k, v in PARAMS.items()})\n"
)

# Off-convention: a module-level build() with a non-default literal arg.
BUILD_ONCE_NONDEFAULT = (
    "from solidifai import show\n"
    "from build123d import Box\n"
    'PARAMS = {"size": {"value": 20.0, "min": 5.0, "max": 50.0, "step": 1.0, "unit": "mm"}}\n'
    "def build(size):\n"
    "    show(Box(size, size, size), name='cube')\n"
    "build(size=50)\n"
)

GOOD = "from solidifai import show\nfrom build123d import Box\nshow(Box(10, 10, 10), name='p')\n"
# shows a small box then raises: leaves partial geometry in the live registry
BAD = (
    "from solidifai import show\n"
    "from build123d import Box\n"
    "show(Box(2, 2, 2), name='p')\n"
    "raise ValueError('boom')\n"
)


def _session(tmp: Path) -> Session:
    (tmp / ".solidifai").mkdir(exist_ok=True)
    return Session(str(tmp / ".solidifai" / "artifacts"), model_path=str(tmp / "model.py"))


def test_render_after_failed_build_keeps_last_good(tmp_path):
    """render() must re-render the last-good snapshot, not the partial geometry a
    failed build left in the live registry (which would clobber last-good and
    flip last_ok back to True)."""
    s = _session(tmp_path)
    assert s.execute_script(GOOD)["ok"] is True
    good_vol = s.get_model_info()["volume"]  # 1000
    good_build = s.build_id

    assert s.execute_script(BAD)["ok"] is False  # registry now holds the 2mm box
    assert s.last_ok is False

    r = s.render()
    assert r["ok"] is True
    info = s.get_model_info()
    assert info["volume"] == good_vol  # 1000, NOT 8 (the failed 2mm box)
    # model.json on disk reflects the last-good model too
    data = json.loads((tmp_path / ".solidifai" / "artifacts" / "model.json").read_text())
    assert data["volume"] == good_vol
    assert s.build_id == good_build + 1


def test_render_after_failed_build_keeps_last_good_params(tmp_path):
    """B6: a re-render after a failed build must report the last-good PARAMS,
    not the empty block the failed build left in the live param state."""
    s = _session(tmp_path)
    assert s.execute_script(GOOD_PARAM)["ok"] is True
    assert s.get_params()["values"] == {"size": 20.0}

    assert s.execute_script(BAD)["ok"] is False  # resets live param state

    assert s.render()["ok"] is True
    data = json.loads((tmp_path / ".solidifai" / "artifacts" / "model.json").read_text())
    assert data["params"]["values"]["size"] == 20.0  # snapshot, not wiped to {}


def test_module_level_build_nondefault_args_reports_actual_values(tmp_path):
    """build-once: a module-level build(size=50) is reported with size=50 (matching
    the geometry), not the PARAMS default of 20, and the kernel still runs once."""
    s = _session(tmp_path)
    assert s.execute_script(BUILD_ONCE_NONDEFAULT)["ok"] is True
    assert s.get_model_info()["volume"] == pytest.approx(125000.0)  # 50mm cube
    assert s.get_params()["values"]["size"] == 50.0
