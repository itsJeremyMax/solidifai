"""Client for the host's control channel.

Rust owns the write side of host config (manufacturing-profile.json, reference-
library.json); the engine delegates the agent's writes to it over a local IPC
endpoint (ipc.py) whose path the host passes in ``SOLIDIFAI_CONTROL_SOCK``.
Same newline-delimited JSON framing as the engine RPC. Read-only access stays
local."""

from __future__ import annotations

import json
import os
import sys
from typing import BinaryIO

from solidifai_engine import ipc

ENV_SOCK = "SOLIDIFAI_CONTROL_SOCK"

# Bound the whole roundtrip, mirroring the host's own 30s read / 10s write
# limits: a wedged host must fail the agent's tool call, not hang the session.
_TIMEOUT_S = 15.0


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
    conn.settimeout(_TIMEOUT_S)
    try:
        conn.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
    except TimeoutError as exc:
        raise ControlError("the app did not respond in time") from exc
    except OSError as exc:
        raise ControlError(f"control channel failed: {exc}") from exc
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


class OverrideChannel:
    """Parent-only connection to the host's private override endpoint."""

    def __init__(self, transport: dict[str, str]):
        self._transport = transport

    @classmethod
    def from_stdin(cls) -> OverrideChannel:
        try:
            return cls(read_override_bootstrap(sys.stdin.buffer))
        finally:
            # The bootstrap pipe is closed before SessionProxy creates workers.
            os.close(sys.stdin.fileno())

    def consume(self, nonce: str, *, workspace_id: str, build_id: int, format: str) -> dict:
        try:
            conn = _connect_private_transport(self._transport)
            conn.settimeout(_TIMEOUT_S)
            req = {
                "op": "consume_export_override",
                "nonce": nonce,
                "workspaceId": workspace_id,
                "buildId": build_id,
                "format": format,
            }
            conn.sendall((json.dumps(req) + "\n").encode("utf-8"))
            response = b""
            while b"\n" not in response:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                response += chunk
            parsed = json.loads(response.decode("utf-8").splitlines()[0]) if response else {}
            return parsed if isinstance(parsed, dict) else {"ok": False}
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return {"ok": False}
        finally:
            if "conn" in locals():
                conn.close()

    def close(self) -> None:
        self._transport = {}


class OverrideBootstrapError(RuntimeError):
    """The host did not provide a valid one-shot private bootstrap frame."""


def read_override_bootstrap(stream: BinaryIO) -> dict[str, str]:
    header = _read_exact(stream, 4)
    size = int.from_bytes(header, "big")
    if size == 0 or size > 16 * 1024:
        raise OverrideBootstrapError("invalid override bootstrap frame")
    try:
        payload = json.loads(_read_exact(stream, size))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OverrideBootstrapError("invalid override bootstrap frame") from error
    transport = payload.get("transport") if isinstance(payload, dict) else None
    if not isinstance(transport, dict):
        raise OverrideBootstrapError("invalid override bootstrap frame")
    kind = transport.get("kind")
    if kind == "unix" and isinstance(transport.get("path"), str) and transport["path"]:
        return {"kind": kind, "path": transport["path"]}
    if (
        kind == "tcp"
        and isinstance(transport.get("address"), str)
        and transport["address"]
        and isinstance(transport.get("token"), str)
        and transport["token"]
    ):
        return {"kind": kind, "address": transport["address"], "token": transport["token"]}
    raise OverrideBootstrapError("invalid override bootstrap frame")


def _connect_private_transport(transport: dict[str, str]):
    """Connect only from the trusted engine parent; workers receive no transport."""
    if transport.get("kind") == "unix":
        return ipc.connect(transport["path"])
    if transport.get("kind") == "tcp":
        address = transport["address"]
        host, _, port = address.rpartition(":")
        import socket

        conn = socket.create_connection((host, int(port)))
        conn.sendall(f"{transport['token']}\n".encode())
        return conn
    raise OSError("private override transport unavailable")


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = stream.read(size - len(chunks))
        if not chunk:
            raise OverrideBootstrapError("missing override bootstrap frame")
        chunks.extend(chunk)
    return bytes(chunks)
