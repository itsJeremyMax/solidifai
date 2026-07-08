"""The build worker must contain native kernel crashes and runaway builds.

These are the guarantees behind "the engine can't segfault": a build that makes
OpenCascade crash the *process* (a fillet as large as a shelled wall) or that
runs forever must fail as a clean error, leave the engine alive, keep the last
good model, and let the very next build succeed.
"""

import json
import tempfile
from pathlib import Path

import pytest

from solidifai_engine.worker import KernelCrash, SessionProxy

CHANNEL = """
from solidifai import show
from build123d import *
with BuildPart() as bp:
    Box(40, 40, 10)
    Hole(radius=3)
show(bp.part, name="p")
"""

# fillet radius == the 3 mm shelled wall thickness -> native SIGSEGV in OCC
SEGFAULT = """
from solidifai import show
from build123d import *
with BuildPart() as bp:
    Box(90, 81, 23, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = bp.faces().sort_by(Axis.Z)[-1]
    offset(amount=-3.0, openings=top)
    fillet(bp.faces().sort_by(Axis.Z)[-1].edges(), 3.0)
show(bp.part, name="p")
"""

HANG = """
from solidifai import show
from build123d import Box
import time
time.sleep(30)
show(Box(10, 10, 10), name="p")
"""


@pytest.fixture
def proxy(tmp_path):
    (tmp_path / ".solidifai").mkdir()
    p = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"), model_path=str(tmp_path / "model.py")
    )
    yield p
    p.close()


def test_normal_build_and_capture(proxy):
    assert proxy.execute_script(CHANNEL)["ok"] is True
    # capture renders offscreen inside the worker
    proxy.capture_views(["iso"])
    assert proxy.get_model_info()["valid"] is True


def test_native_crash_is_contained_and_recovers(proxy):
    # a good build first, so there is a last-good model to fall back to
    assert proxy.execute_script(CHANNEL)["ok"] is True
    good_bbox = proxy.get_model_info()["bbox"]

    # the segfaulting build must raise a clean KernelCrash, not kill the test
    with pytest.raises(KernelCrash):
        proxy.execute_script(SEGFAULT)

    # engine recovered: the last-good model is intact and a new build works
    assert proxy.get_model_info()["bbox"] == good_bbox
    assert proxy.execute_script(CHANNEL)["ok"] is True


def test_runaway_build_times_out_and_recovers(tmp_path):
    (tmp_path / ".solidifai").mkdir()
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"),
        model_path=str(tmp_path / "model.py"),
        timeout=1.5,
    )
    try:
        with pytest.raises(KernelCrash):
            proxy.execute_script(HANG)
        # worker was killed + respawned; a fresh build succeeds
        assert proxy.execute_script(CHANNEL)["ok"] is True
    finally:
        proxy.close()


def test_worker_configures_resolver_before_startup(tmp_path):
    """A workspace default material must apply to the startup build. The worker
    has to point the resolver at the workspace BEFORE it reloads the model, or
    mass/material read as the PLA built-in instead of the workspace default."""
    (tmp_path / ".solidifai").mkdir()
    (tmp_path / "materials.json").write_text(
        json.dumps(
            {
                "default": "shopsteel",
                "materials": [{"id": "shopsteel", "label": "Shop Steel", "base": "steel"}],
            }
        )
    )
    (tmp_path / "model.py").write_text(
        "from solidifai import show\nfrom build123d import Box\nshow(Box(10, 10, 10), name='p')\n"
    )
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"), model_path=str(tmp_path / "model.py")
    )
    try:
        info = proxy.get_model_info()
        # steel density ~7.85, not PLA 1.24
        assert info["mass"]["density"] == pytest.approx(7.85, rel=2e-2)
        assert info["mass"]["material"].lower() != "pla"
    finally:
        proxy.close()
