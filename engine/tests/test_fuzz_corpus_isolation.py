"""The engine survives every crash/hang the fuzz audit found.

Each script below is a minimized reproducer for a distinct root cause the fuzzer
surfaced -- 4 native SIGSEGV crashes and 6 runaway hangs in OpenCascade. The
guarantee under test is not that any particular one is caught statically, but
that NONE of them can kill the engine: after running each, a trivial build must
still succeed. This is the regression net behind "the engine can't segfault."
"""

import contextlib

import pytest

from solidifai_engine.worker import SessionProxy

TRIVIAL = (
    "from solidifai import show\nfrom build123d import Box\nshow(Box(10, 10, 10), name='ok')\n"
)

# (id, script) — minimized reproducers from the fuzz corpus (native crashes + hangs).
CORPUS = [
    (
        "offset_nonfinite",
        "from build123d import *\nfrom solidifai import show\n"
        "show(offset(Cylinder(5, 10), amount=float('nan')))\n",
    ),
    (
        "extrude_taper_nonfinite",
        "from build123d import *\nfrom solidifai import show\n"
        "show(extrude(Rectangle(10, 10).face(), amount=5, taper=float('nan')))\n",
    ),
    (
        "text_zero_fontsize",
        "from build123d import *\nfrom solidifai import show\nshow(Text('A', font_size=0))\n",
    ),
    (
        "fillet_knife_edge",
        "from solidifai import show\nfrom build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Box(20, 20, 10)\n"
        "    with Locations(bp.faces().sort_by(Axis.Z)[-1]):\n"
        "        Hole(radius=10.0000001)\n"
        "    fillet(bp.edges().filter_by(Axis.Z), radius=1.0)\n"
        "show(bp.part, name='p')\n",
    ),
    (
        "nonfinite_mesh",
        "from build123d import *\nfrom solidifai import show\nshow(Sphere(float('nan')))\n",
    ),
    (
        "boolean_coincident",
        "from build123d import *\nfrom solidifai import show\n"
        "holes = Compound([Cylinder(1, 20) for _ in range(150)])\n"
        "show(Box(10, 10, 10) - holes)\n",
    ),
    (
        "dense_holes",
        "from solidifai import show\nfrom build123d import *\n"
        "with BuildPart() as bp:\n"
        "    Box(120, 120, 4)\n"
        "    with Locations(bp.faces().sort_by(Axis.Z)[-1]):\n"
        "        with GridLocations(3, 3, 30, 30):\n"
        "            Hole(radius=0.6)\n"
        "show(bp.part, name='grille')\n",
    ),
    (
        "count_explosion",
        "from build123d import *\nfrom solidifai import show\n"
        "with BuildPart() as bp:\n"
        "    with BuildSketch():\n"
        "        with PolarLocations(10, 1_000_000):\n"
        "            Circle(0.1)\n"
        "    extrude(amount=1)\n"
        "show(bp.part)\n",
    ),
    (
        "sweep_selfintersect",
        "from build123d import *\nfrom solidifai import show\n"
        "path = Helix(pitch=2, height=40, radius=3)\n"
        "prof = Plane(origin=(3, 0, 0), z_dir=(0, 1, 0)) * Circle(2.5)\n"
        "show(sweep(prof, path=path))\n",
    ),
    (
        "mesh_tolerance_blowup",
        "from build123d import *\nfrom solidifai import show\n"
        "s = Sphere(1e6)\nexport_stl(s, '/tmp/fuzz_s.stl', tolerance=1e-6)\nshow(s)\n",
    ),
]


@pytest.fixture
def proxy(tmp_path):
    (tmp_path / ".solidifai").mkdir()
    p = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"),
        model_path=str(tmp_path / "model.py"),
        timeout=6.0,  # bound the hangs so the test is quick
        hard_timeout=6.0,
    )
    yield p
    p.close()


@pytest.mark.parametrize("case_id, script", CORPUS, ids=[c[0] for c in CORPUS])
def test_engine_survives_fuzz_reproducer(proxy, case_id, script):
    # Run the nasty script: it may crash the worker, hang past the timeout, or
    # (if the kernel got lucky) even succeed. Whatever happens, it must not take
    # the engine down. A contained KernelCrash is the expected path.
    with contextlib.suppress(Exception):
        proxy.execute_script(script)
    # The engine is alive and usable: a fresh build succeeds.
    assert proxy.execute_script(TRIVIAL)["ok"] is True, f"engine dead after {case_id}"
