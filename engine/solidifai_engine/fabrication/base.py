"""Provider abstraction + shared data types for the fabrication subsystem.

Pure data — no OCC, no build123d, no I/O. Additional providers (remote
fulfillment, other slicers) implement FabricationProvider and plug in without
touching session.py or server.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class InstallInfo:
    """Result of probing the local machine for a slicer executable."""

    found: bool
    version: str | None = None
    executable: str | None = None


@dataclass
class Estimate:
    """Weight / cost / time estimate for a print job.

    ``source`` is either ``"approx"`` (geometric fallback) or ``"slice"``
    (from a real slicer run). ``to_dict()`` omits None fields so callers
    get clean JSON without needing to filter manually.
    """

    source: str
    timeSeconds: float | None = None
    filamentGrams: float | None = None
    filamentLengthMm: float | None = None
    cost: float | None = None
    currency: str = "USD"
    note: str | None = None
    layerCount: int | None = None
    supportUsed: bool | None = None
    heightMm: float | None = None
    fitsBed: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise, dropping any field whose value is None."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Capabilities:
    """Static capabilities reported by a provider (informational only)."""

    processes: list[str]
    materials: list[str]
    maxBuildSize: tuple[float, float, float]


@dataclass
class Destination:
    """A named printer / fulfillment target stored in destinations.json."""

    id: str
    name: str
    kind: str  # "local" | "remote"
    provider: str  # e.g. "orca"
    printerProfile: str | None = None
    filamentProfile: str | None = None
    processProfile: str | None = None
    connection: Any = None


@runtime_checkable
class FabricationProvider(Protocol):
    """Minimal interface every fabrication provider must satisfy.

    Providers are not required to implement all methods meaningfully —
    ``submit`` in particular is a stub for most local providers.
    """

    def detect(self) -> InstallInfo: ...

    def profiles(self) -> list[dict[str, Any]]: ...

    def quote(
        self,
        model_path: str,
        profile: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]: ...

    def open_in_app(self, model_path: str, destination: Destination) -> dict[str, Any]: ...

    def capabilities(self) -> Capabilities: ...

    def submit(
        self,
        model_path: str,
        destination: Destination,
        options: dict[str, Any],
    ) -> dict[str, Any]: ...
