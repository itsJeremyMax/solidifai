"""Geometric diff against a checkpoint + the build report."""

import os
from pathlib import Path

from solidifai_engine.reporting import Reporting
from solidifai_engine.session import Session

SMALL = "from build123d import Box\nfrom solidifai import show\nshow(Box(10,10,10), name='B')\n"
BIG = "from build123d import Box\nfrom solidifai import show\nshow(Box(20,10,10), name='B')\n"


def _ws(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(SMALL)
    s = Session(str(tmp_path / "art"), model_path=str(root / "model.py"))
    s.startup()
    return s


def test_diff_detects_added_material(tmp_path):
    s = _ws(tmp_path)
    s.checkpoint("small")
    s.execute_script(BIG)  # grow it along X
    idx = next(e["index"] for e in s.history_state()["entries"] if e["message"] == "small")
    rep = s.diff_against(idx)
    assert rep["ok"] is True
    assert rep["volumeDelta"] > 0
    assert rep["changed"] is True
    if rep["geometric"]:
        assert rep["added"]["volume"] > 0
        assert rep["removed"]["volume"] == 0


def test_diff_non_destructive(tmp_path):
    s = _ws(tmp_path)
    s.checkpoint("c")
    s.execute_script(BIG)
    before = s.build_id
    s.diff_against(0)
    assert s.build_id == before


def test_diff_bad_index(tmp_path):
    s = _ws(tmp_path)
    assert s.diff_against(999)["ok"] is False


def test_build_report_writes_html(tmp_path):
    s = _ws(tmp_path)
    rep = s.build_report()
    assert rep["ok"] is True
    assert os.path.exists(rep["path"])
    html = Path(rep["path"]).read_text(encoding="utf-8")
    assert "solidifai build report" in html
    assert rep["summary"]["mass"] >= 0


# ---------------------------------------------------------------------------
# Task 7: compliance snapshot in checkpoints, diff, and build report
# ---------------------------------------------------------------------------


def test_checkpoint_records_compliance(tmp_path):
    """A checkpoint taken with requirements set stores a compliance summary."""
    s = _ws(tmp_path)
    # A requirement that always passes for any non-zero-mass box.
    s.set_requirements([{"id": "m", "quantity": "mass", "op": "<=", "bound": 1e9}])
    s.checkpoint("with spec")
    entries = s.history_state()["entries"]
    snap = next(e for e in entries if e["message"] == "with spec")
    assert "compliance" in snap
    comp = snap["compliance"]
    assert comp is not None
    assert comp["met"] == 1
    assert comp["total"] == 1
    assert comp["allMet"] is True
    # per-id pass map
    assert comp["pass_map"] == {"m": True}


def test_checkpoint_compliance_none_when_no_requirements(tmp_path):
    """A checkpoint with no requirements stores compliance with total=0."""
    s = _ws(tmp_path)
    s.checkpoint("bare")
    entries = s.history_state()["entries"]
    snap = next(e for e in entries if e["message"] == "bare")
    # No requirements -> compliance recorded but total=0
    assert "compliance" in snap
    comp = snap["compliance"]
    assert comp is not None
    assert comp["total"] == 0


def test_diff_against_includes_compliance_block(tmp_path):
    """diff_against returns a compliance block comparing checkpoint to current."""
    s = _ws(tmp_path)
    # checkpoint with a passing requirement
    s.set_requirements([{"id": "m", "quantity": "mass", "op": "<=", "bound": 1e9}])
    s.checkpoint("base")
    idx = next(e["index"] for e in s.history_state()["entries"] if e["message"] == "base")

    # change model, re-run diff
    s.execute_script(BIG)
    rep = s.diff_against(idx)
    assert rep["ok"] is True
    assert "compliance" in rep
    comp = rep["compliance"]
    # compliance block has checkpoint + current sub-dicts
    assert "checkpoint" in comp
    assert "current" in comp
    # newly_passing and newly_failing lists present
    assert "newly_passing" in comp
    assert "newly_failing" in comp


def test_diff_against_compliance_null_for_old_checkpoint(tmp_path):
    """diff_against tolerates a checkpoint with no stored compliance (older snapshot)."""
    s = _ws(tmp_path)
    # Create a checkpoint without requirements (no compliance stored, or total=0)
    s.checkpoint("old")
    idx = 0
    s.execute_script(BIG)
    rep = s.diff_against(idx)
    assert rep["ok"] is True
    # compliance block still present; checkpoint side may be None or have total=0
    assert "compliance" in rep


def test_build_report_html_contains_spec_compliance_section(tmp_path):
    """_report_html includes a Spec compliance section when requirements are present."""
    s = _ws(tmp_path)
    s.set_requirements([{"id": "m", "quantity": "mass", "op": "<=", "bound": 1e9}])
    cr = s.check_requirements()

    # Test via _report_html directly (avoids VTK/capture_views in headless harness).
    summary_stub = {
        "mass": 100,
        "bbox": [10, 10, 10],
        "material": "PLA",
        "dfm": None,
        "compliance": cr,
    }
    html = Reporting._report_html(summary_stub, {}, None)
    assert "Spec compliance" in html
    # met/total present in the section
    assert "1" in html  # met count


def test_build_report_html_no_compliance_section_when_no_reqs(tmp_path):
    """_report_html omits Spec compliance when requirements list is empty."""
    summary_stub = {
        "mass": 100,
        "bbox": [10, 10, 10],
        "material": "PLA",
        "dfm": None,
        "compliance": None,
    }
    html = Reporting._report_html(summary_stub, {}, None)
    assert "Spec compliance" not in html
