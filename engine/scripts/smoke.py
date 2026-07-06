"""Headless smoke test for the engine.

Spawns the RPC server as a subprocess, connects over the UNIX socket, executes a
script that builds a 20mm cube with a 5mm through-hole, prints the resulting
bbox and asserts the artifacts exist.

Run with:  uv run python scripts/smoke.py
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time

SCRIPT = """
from build123d import BuildPart, Box, Hole
from solidifai import show

with BuildPart() as p:
    Box(20, 20, 20)
    Hole(radius=2.5)  # 5mm diameter through-hole

show(p.part, name="Cube")
"""


def _recv_line(conn: socket.socket) -> dict:
    buf = b""
    while b"\n" not in buf:
        chunk = conn.recv(65536)
        if not chunk:
            break
        buf += chunk
    return json.loads(buf.decode("utf-8").splitlines()[0])


def _request(sock_path: str, request: dict) -> dict:
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(sock_path)
    c.sendall((json.dumps(request) + "\n").encode("utf-8"))
    resp = _recv_line(c)
    c.close()
    return resp


def main() -> int:
    workdir = tempfile.mkdtemp(prefix="solidifai-smoke-")
    sock_path = os.path.join(workdir, "engine.sock")
    artifacts = os.path.join(workdir, "artifacts")
    os.makedirs(artifacts, exist_ok=True)

    proc = subprocess.Popen(
        [sys.executable, "-m", "solidifai_engine", "--socket", sock_path, "--artifacts", artifacts]
    )
    try:
        # Wait for the server to bind the socket.
        for _ in range(300):
            if os.path.exists(sock_path):
                break
            time.sleep(0.02)
        else:
            print("FAIL: server did not create socket", file=sys.stderr)
            return 1

        pong = _request(sock_path, {"id": 1, "method": "ping"})
        assert pong == {"id": 1, "ok": True, "result": "pong"}, pong
        print("ping ->", pong["result"])

        resp = _request(
            sock_path,
            {"id": 2, "method": "execute_script", "params": {"code": SCRIPT}},
        )
        print("execute_script ->", resp)
        assert resp["ok"] is True, resp
        assert resp["result"]["buildId"] == 1, resp

        info = _request(sock_path, {"id": 3, "method": "get_model_info"})
        assert info["ok"] is True, info
        bbox = info["result"]["bbox"]["size"]
        print("bbox:", f"{bbox[0]:g} x {bbox[1]:g} x {bbox[2]:g}")
        assert [round(v) for v in bbox] == [20, 20, 20], bbox

        glb = os.path.join(artifacts, "model.glb")
        model_json = os.path.join(artifacts, "model.json")
        assert os.path.exists(glb), "missing model.glb"
        assert os.path.exists(model_json), "missing model.json"
        with open(glb, "rb") as f:
            assert f.read(4) == b"glTF", "model.glb is not binary glTF"
        print("artifacts:", glb, "+", model_json)

        print("SMOKE OK")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
