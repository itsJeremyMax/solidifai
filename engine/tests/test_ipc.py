"""The cross-platform IPC layer, exercised in TCP mode (the Windows transport)
on whatever unix runs the suite, so the code Windows executes is CI-covered."""

import json
import os
import socket
import threading
import time

from sockpath import short_socket_path

from solidifai_engine import ipc
from solidifai_engine.server import Server


def test_bind_writes_pointer_file_and_connect_round_trips(tmp_path):
    path = str(tmp_path / "ep.sock")
    listener, token = ipc.bind(path, force_tcp=True)
    assert token and len(token) == 32
    with open(path, encoding="utf-8") as f:
        addr_line, token_line = f.read().splitlines()
    assert addr_line.startswith("127.0.0.1:")
    assert token_line == token

    listener.listen(1)

    def serve():
        conn, _ = listener.accept()
        with conn:
            buf = b""
            while b"\n" not in buf:
                buf += conn.recv(1024)
            line, rest = buf.split(b"\n", 1)
            assert line.decode() == token  # client's first line is the token
            while b"\n" not in rest:
                rest += conn.recv(1024)
            conn.sendall(b"echo:" + rest)

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    c = ipc.connect(path, force_tcp=True)  # sends the token line itself
    c.sendall(b"hello\n")
    got = c.recv(1024)
    c.close()
    t.join(timeout=5)
    assert got == b"echo:hello\n"


def test_unix_bind_is_owner_only(tmp_path):
    path = short_socket_path(tmp_path, "ep.sock")
    listener, token = ipc.bind(path)
    assert token is None
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    listener.close()


def _tcp_send(sock_path, request, *, raw_first_line=None):
    """One RPC round-trip over the TCP transport. raw_first_line replaces the
    token handshake to test rejection."""
    if raw_first_line is not None:
        with open(sock_path, encoding="utf-8") as f:
            addr = f.readline().strip()
        host, _, port = addr.rpartition(":")
        c = socket.create_connection((host, int(port)))
        c.sendall(raw_first_line + b"\n")
    else:
        c = ipc.connect(sock_path, force_tcp=True)
    buf = b""
    try:
        c.sendall((json.dumps(request) + "\n").encode("utf-8"))
        while b"\n" not in buf:
            chunk = c.recv(4096)
            if not chunk:
                break
            buf += chunk
    except (ConnectionResetError, BrokenPipeError):
        # A rejected client can see RST instead of clean EOF, depending on
        # whether its bytes were still in flight when the server dropped it.
        pass
    c.close()
    return json.loads(buf.decode("utf-8").splitlines()[0]) if buf else None


def test_server_over_tcp_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(ipc, "use_tcp", lambda: True)
    sock_path = str(tmp_path / "engine.sock")
    artifacts = str(tmp_path / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    server = Server(sock_path, artifacts)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            ipc.connect(sock_path, force_tcp=True).close()
            break
        except OSError:
            time.sleep(0.02)
    try:
        resp = _tcp_send(sock_path, {"id": 1, "method": "ping"})
        assert resp == {"id": 1, "ok": True, "result": "pong"}
        # A client with the wrong token gets dropped without a response.
        assert _tcp_send(sock_path, {"id": 2, "method": "ping"}, raw_first_line=b"wrong") is None
    finally:
        server.shutdown()
