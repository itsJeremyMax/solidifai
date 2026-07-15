"""RPC compatibility metadata shared between the engine and Rust host shell.

The Rust supervisor probes ``protocol_info()`` before startup and accepts engines
whose protocol ranges overlap its supported range. This keeps protocol 12 clients
working while allowing protocol 13 capabilities to be negotiated explicitly.
``PROTOCOL_VERSION`` remains available for legacy probes.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

PROTOCOL_VERSION = 13
MIN_COMPATIBLE_PROTOCOL = 12

CAP_BUILD_BRIEF_V2 = "build_brief_v2"
CAP_CONFORMANCE = "conformance"
CAP_READINESS = "readiness"
CAP_PUBLICATION_METADATA = "publication_metadata"
CAP_STRICT_EXPORT = "strict_export"
CAP_OPERATIONS = "operations"

CAPABILITIES = frozenset(
    {
        CAP_BUILD_BRIEF_V2,
        CAP_CONFORMANCE,
        CAP_READINESS,
        CAP_PUBLICATION_METADATA,
        CAP_STRICT_EXPORT,
        CAP_OPERATIONS,
    }
)


def protocol_info() -> dict[str, object]:
    """The protocol versions and optional features this engine supports."""
    return {
        "minProtocol": MIN_COMPATIBLE_PROTOCOL,
        "maxProtocol": PROTOCOL_VERSION,
        "capabilities": sorted(CAPABILITIES),
    }


def negotiate(
    client_protocol: int,
    client_capabilities: Iterable[str],
    *,
    required: Iterable[str] = (),
) -> dict[str, Any]:
    """Statelessly select shared capabilities for one client request."""
    client_capabilities = set(client_capabilities)
    shared_capabilities = CAPABILITIES & client_capabilities
    enabled = sorted(shared_capabilities)
    missing = sorted(set(required) - shared_capabilities)
    compatible = MIN_COMPATIBLE_PROTOCOL <= client_protocol <= PROTOCOL_VERSION and not missing
    return {
        "compatible": compatible,
        "enabledCapabilities": enabled if compatible else [],
        "missingCapabilities": missing,
    }
