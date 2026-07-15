"""The socket server dispatches analyze_dfm to the session."""

import os
import tempfile

import pytest
from build123d import Box

from solidifai_engine.dfm import analyze_part
from solidifai_engine.server import Server
from solidifai_engine.worker import RemoteSessionError


def _server() -> Server:
    d = tempfile.mkdtemp()
    return Server(os.path.join(d, "engine.sock"), os.path.join(d, "artifacts"))


def test_dispatch_analyze_dfm_no_model():
    srv = _server()
    with pytest.raises(RemoteSessionError, match="no model"):
        srv._dispatch("analyze_dfm", {})


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


def test_non_fdm_dfm_is_truthfully_unsupported():
    assert analyze_part(Box(1, 1, 1), process="cnc") == {
        "process": "cnc",
        "evaluated": False,
        "reason": "unsupported_rule_pack",
        "violations": [],
    }


def test_missing_process_is_truthfully_unresolved():
    assert analyze_part(Box(1, 1, 1), process=None) == {
        "process": None,
        "evaluated": False,
        "reason": "unresolved_process",
        "violations": [],
    }


def test_unknown_explicit_process_is_unresolved_not_unsupported():
    assert analyze_part(Box(1, 1, 1), process="laser") == {
        "process": "laser",
        "evaluated": False,
        "reason": "unresolved_process",
        "violations": [],
    }
