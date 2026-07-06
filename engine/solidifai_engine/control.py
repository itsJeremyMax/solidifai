"""Client for the host's control channel.

Rust owns the write side of host config (manufacturing-profile.json, reference-
library.json); the engine delegates the agent's writes to it over a local IPC
endpoint (ipc.py) whose path the host passes in ``SOLIDIFAI_CONTROL_SOCK``.
Same newline-delimited JSON framing as the engine RPC. Read-only access stays
local."""

from __future__ import annotations

import json
import os

from solidifai_engine import ipc

ENV_SOCK = "SOLIDIFAI_CONTROL_SOCK"


class ControlError(RuntimeError):
    pass


def _sock_path() -> str:
    path = os.environ.get(ENV_SOCK)
    if not path:
        raise ControlError("the app is not reachable (control channel unavailable)")
    return path


def _roundtrip(req: dict) -> dict:
    """Send *req* to the host over the control socket and return the parsed response.
    Raises ControlError on transport failure or a host-side error."""
    try:
        conn = ipc.connect(_sock_path())
    except OSError as exc:
        raise ControlError(f"cannot reach the app: {exc}") from exc
    try:
        conn.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        conn.close()
    if not buf:
        raise ControlError("the app closed the connection without responding")
    resp = json.loads(buf.decode("utf-8").splitlines()[0])
    if not resp.get("ok"):
        raise ControlError(resp.get("error", "the app rejected the change"))
    return resp


def write(scope: str, workspace_root: str, values: dict, unset: list[str]) -> dict:
    """Ask the host to write the manufacturing profile. Returns the resolved
    profile; raises ControlError on transport failure or a host-side error."""
    resp = _roundtrip(
        {
            "op": "write_manufacturing_profile",
            "scope": scope,
            "workspace_root": workspace_root,
            "set": values or {},
            "unset": unset or [],
        }
    )
    return resp.get("profile") or {}


def write_reference(entry: dict) -> dict:
    """Ask the host to upsert a reference-library entry. Returns the updated
    library; raises ControlError when the app is unreachable or rejects it."""
    resp = _roundtrip({"op": "write_reference", "action": "upsert", "entry": entry})
    return resp.get("library") or {}
