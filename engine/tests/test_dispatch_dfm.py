"""The socket server dispatches analyze_dfm to the session."""

import os
import tempfile

from solidifai_engine.server import Server


def _server() -> Server:
    d = tempfile.mkdtemp()
    return Server(os.path.join(d, "engine.sock"), os.path.join(d, "artifacts"))


def test_dispatch_analyze_dfm_no_model():
    srv = _server()
    out = srv._dispatch("analyze_dfm", {})
    assert out["ok"] is False
    assert "no model" in out["error"]


def test_dispatch_analyze_dfm_with_process():
    srv = _server()
    srv._dispatch(
        "execute_script",
        {
            "code": "from build123d import Box\nimport solidifai\n"
            "solidifai.show(Box(20,20,0.6), name='P', material='pla')\n",
        },
    )
    out = srv._dispatch("analyze_dfm", {"process": "fdm"})
    assert out["ok"] is True
    assert out["parts"][0]["process"] == "fdm"
