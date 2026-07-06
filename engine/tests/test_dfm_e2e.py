"""End-to-end: the agent path for analyze_dfm over a real UNIX socket.

Spins up the engine Server in a thread, then calls it through the MCP bridge's
`forward` (the same transport every agent tool uses): execute a thin part, then
analyze_dfm, and confirm the structured report comes back across the socket.
"""

import os
import tempfile
import threading
import time

import solidifai_mcp.server as mcp_bridge
from solidifai_engine.server import Server


def test_analyze_dfm_over_socket():
    d = tempfile.mkdtemp()
    sock = os.path.join(d, "engine.sock")
    srv = Server(sock, os.path.join(d, "artifacts"))
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    # Wait for the server to bind the socket before connecting.
    for _ in range(100):
        if os.path.exists(sock):
            break
        time.sleep(0.05)

    prev = os.environ.get(mcp_bridge.ENV_SOCK)
    os.environ[mcp_bridge.ENV_SOCK] = sock
    try:
        mcp_bridge.forward(
            "execute_script",
            {
                "code": "from build123d import Box\nimport solidifai\n"
                "solidifai.show(Box(20, 20, 0.6), name='Plate', material='pla')\n",
            },
        )
        rep = mcp_bridge.forward("analyze_dfm", {"process": None})
        assert rep["ok"] is True
        part = rep["parts"][0]
        assert part["partId"] == "plate"
        assert part["process"] == "fdm"
        assert any(v["rule"] == "wall_thickness" for v in part["violations"])
        assert rep["summary"]["critical"] >= 1
    finally:
        if prev is None:
            os.environ.pop(mcp_bridge.ENV_SOCK, None)
        else:
            os.environ[mcp_bridge.ENV_SOCK] = prev
        srv.shutdown()
        thread.join(timeout=5)
