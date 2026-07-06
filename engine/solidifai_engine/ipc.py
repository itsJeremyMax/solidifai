"""Cross-platform local IPC endpoints (the Rust twin is src-tauri/src/ipc.rs).

Unix: an AF_UNIX socket at the given path, owner-only (mode 0600). Windows has
no AF_UNIX support in CPython, so there the *path* is a small file holding
``127.0.0.1:<port>\\n<token>``: the listener binds a loopback TCP port and
writes the file, and clients read it, connect, and send the token as their
first line (a bare loopback port would be reachable by any local process).
ACLs on the pointer file gate access the way socket modes do on unix, because
every endpoint lives in a user-owned directory: the host computes all socket
paths (control and per-workspace engine endpoints) under its app config dir,
never under the user-chosen workspace root. Readiness semantics match unix:
the path appears once the listener is up.

The TCP flavor works on every platform (``force_tcp``), so unix-run tests
exercise the exact code Windows runs.
"""

from __future__ import annotations

import os
import secrets
import socket


def use_tcp() -> bool:
    return os.name == "nt" or not hasattr(socket, "AF_UNIX")


def bind(path: str, *, force_tcp: bool = False) -> tuple[socket.socket, str | None]:
    """Bind a listener for *path*. Returns ``(socket, expected_token)``; the
    socket is bound but not yet listening (callers set listen/timeouts). The
    token is None on the unix path, where the socket mode is the access
    control; on TCP every client must send it as its first line."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(path):
        os.unlink(path)  # stale endpoint from a previous run
    if force_tcp or use_tcp():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()
        token = secrets.token_hex(16)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"{host}:{port}\n{token}\n")
        os.replace(tmp, path)  # atomic: a reader never sees half a file
        return sock, token
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(path)
    os.chmod(path, 0o600)
    return sock, None


def connect(path: str, *, force_tcp: bool = False) -> socket.socket:
    """Connect to the listener at *path*. On TCP the token line has already
    been sent when this returns, so callers just speak the JSON protocol."""
    if force_tcp or use_tcp():
        with open(path, encoding="utf-8") as f:
            addr = f.readline().strip()
            token = f.readline().strip()
        host, _, port = addr.rpartition(":")
        conn = socket.create_connection((host, int(port)))
        if token:
            conn.sendall(f"{token}\n".encode())
        return conn
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.connect(path)
    return conn
