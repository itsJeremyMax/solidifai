"""create_drawing end to end over a real engine socket (agent path)."""

import os
import tempfile
import threading
import time

import solidifai_mcp.server as mcp_bridge
from solidifai_engine.server import Server

_MODEL = (
    "from build123d import Box\n"
    "import solidifai\n"
    "solidifai.show(Box(30, 20, 10), name='Block', material='aluminum')\n"
)


def test_create_drawing_over_socket(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(_MODEL, encoding="utf-8")
    sock = os.path.join(tempfile.mkdtemp(), "e.sock")  # short path (AF_UNIX cap)
    srv = Server(sock, str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    for _ in range(100):
        if os.path.exists(sock):
            break
        time.sleep(0.05)

    prev = os.environ.get(mcp_bridge.ENV_SOCK)
    os.environ[mcp_bridge.ENV_SOCK] = sock
    try:
        res = mcp_bridge.forward("create_drawing", {})
        assert res["ok"] is True
        assert res["files"]
        assert any(f.endswith(".svg") for f in res["files"])
    finally:
        if prev is None:
            os.environ.pop(mcp_bridge.ENV_SOCK, None)
        else:
            os.environ[mcp_bridge.ENV_SOCK] = prev
        srv.shutdown()
        thread.join(timeout=5)
