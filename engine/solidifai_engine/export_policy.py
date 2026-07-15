"""Pure strict-export policy and host override verification contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

OverrideVerifier = Callable[..., Mapping[str, Any]]


def decide_export(
    readiness: Mapping[str, object], *, strict_readiness: bool, override: bool = False
) -> dict:
    blocked = strict_readiness and readiness.get("level") != "ready" and not override
    return {"allowed": not blocked, "reason": "readiness_blocked" if blocked else None}


def verify_override(
    verifier: OverrideVerifier | None,
    nonce: str | None,
    *,
    workspace_id: str,
    build_id: int,
    format: str,
) -> dict:
    """Ask the host to consume an opaque scoped nonce; callers never authorize themselves."""
    if verifier is None or not isinstance(nonce, str) or not nonce:
        return {"ok": False}
    result = verifier(nonce, workspace_id=workspace_id, build_id=build_id, format=format)
    if (
        isinstance(result, Mapping)
        and result.get("ok") is True
        and isinstance(result.get("nonceId"), str)
    ):
        return dict(result)
    return {"ok": False}
