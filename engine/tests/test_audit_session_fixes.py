"""Regression tests for the session-group correctness fixes from the deep audit."""

import json
import tempfile
from pathlib import Path

from solidifai_engine.session import Session

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
