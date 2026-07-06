"""Agent import path end to end over a real engine socket."""

import os
import tempfile
import threading
import time

import solidifai
import solidifai_mcp.server as mcp_bridge
from solidifai_engine.exports import export as engine_export
from solidifai_engine.server import Server

_MODEL = (
    "from build123d import Box\n"
    "import solidifai\n"
    "solidifai.show(Box(20, 20, 20), name='Body', material='pla')\n"
)


def test_import_reference_over_socket(tmp_path):
    # Make the STL source BEFORE the server starts (don't touch the shared
    # registry once the server thread is live).
    from build123d import Box

    src = tmp_path / "pcb.stl"
    solidifai.reset_registry()
    solidifai.show(Box(8, 8, 8))
    engine_export("stl", str(src))
    solidifai.reset_registry()

    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(_MODEL, encoding="utf-8")
    # AF_UNIX paths are capped (~104 chars on macOS); keep the socket short and
    # outside the deep pytest tmp tree.
    sock = os.path.join(tempfile.mkdtemp(), "e.sock")
    artifacts = str(root / ".solidifai" / "artifacts")
    srv = Server(sock, artifacts, model_path=str(root / "model.py"))
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    for _ in range(100):
        if os.path.exists(sock):
            break
        time.sleep(0.05)

    prev = os.environ.get(mcp_bridge.ENV_SOCK)
    os.environ[mcp_bridge.ENV_SOCK] = sock
    try:
        res = mcp_bridge.forward("import_reference", {"path": str(src), "name": "PCB"})
        assert res["ok"] is True
        assert res["import"]["id"] == "pcb"

        info = mcp_bridge.forward("get_model_info", {})
        roles = {o["name"]: o.get("role") for o in info["objects"]}
        assert roles.get("Body") == "part"
        assert any(r == "reference" for r in roles.values())

        listed = mcp_bridge.forward("list_imports", {})
        assert len(listed["imports"]) == 1

        rem = mcp_bridge.forward("remove_import", {"id": "pcb"})
        assert rem["ok"] is True
        info2 = mcp_bridge.forward("get_model_info", {})
        assert all(o.get("role") != "reference" for o in info2["objects"])
    finally:
        if prev is None:
            os.environ.pop(mcp_bridge.ENV_SOCK, None)
        else:
            os.environ[mcp_bridge.ENV_SOCK] = prev
        srv.shutdown()
        thread.join(timeout=5)
