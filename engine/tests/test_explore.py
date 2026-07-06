"""Generative exploration: non-destructive parameter sweep + optimize."""

from solidifai_engine.session import Session

PARAM_BOX = """
from build123d import BuildPart, Box
from solidifai import show
PARAMS = {"size": {"value": 20, "min": 5, "max": 40, "step": 1, "unit": "mm"}}
def build(size):
    with BuildPart() as p:
        Box(size, size, size)
    show(p.part, name="Cube")
"""


def _sess(tmp_path):
    s = Session(str(tmp_path))
    s.execute_script(PARAM_BOX)
    return s


def test_sweep_mass_increases_with_size(tmp_path):
    s = _sess(tmp_path)
    rep = s.sweep("size", [10, 20, 30])
    assert rep["ok"] is True
    assert len(rep["variants"]) == 3
    masses = [v["mass"] for v in rep["variants"]]
    assert masses[0] < masses[1] < masses[2]
    assert rep["variants"][1]["bbox"][0] == 20.0
    assert rep["unit"] == "mm"


def test_sweep_is_non_destructive(tmp_path):
    s = _sess(tmp_path)
    before_build = s.build_id
    before_val = s.get_params()["values"]["size"]
    s.sweep("size", [10, 30])
    assert s.build_id == before_build
    assert s.get_params()["values"]["size"] == before_val


def test_sweep_bad_value_marks_row(tmp_path):
    s = _sess(tmp_path)
    rep = s.sweep("size", [10, 0])  # size 0 -> build raises
    ok = {v["value"]: v["ok"] for v in rep["variants"]}
    assert ok[10] is True
    assert ok[0] is False


def test_sweep_non_parametric_errors(tmp_path):
    s = Session(str(tmp_path))
    s.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(10,10,10),name='C')\n"
    )
    assert s.sweep("size", [1])["ok"] is False


def test_sweep_unknown_param_errors(tmp_path):
    assert _sess(tmp_path).sweep("nope", [1])["ok"] is False


def test_optimize_min_mass_with_size_constraint(tmp_path):
    s = _sess(tmp_path)
    rep = s.optimize("size", objective="min_mass", steps=7, constraints={"max_size": [25, 25, 25]})
    assert rep["ok"] is True
    assert rep["best"] is not None
    assert rep["best"]["bbox"][0] <= 25 + 1e-6  # feasible
    feasible_masses = [v["mass"] for v in rep["evaluated"] if v["ok"] and v["bbox"][0] <= 25 + 1e-6]
    assert rep["best"]["mass"] == min(feasible_masses)


def test_optimize_infeasible_returns_no_best(tmp_path):
    s = _sess(tmp_path)
    rep = s.optimize("size", objective="min_mass", steps=5, constraints={"max_size": [1, 1, 1]})
    assert rep["ok"] is True
    assert rep["best"] is None
    assert rep["feasibleCount"] == 0
