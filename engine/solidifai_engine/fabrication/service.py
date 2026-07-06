"""Fabrication collaborator — session-level facade for the fabrication subsystem.

Delegates to a FabricationProvider (default: OrcaProvider) and the
fabrication.estimate / fabrication.orient modules. Wired into Session as
``self._fabrication`` following the same pattern as Analysis/Exploration/Reporting.

Never bumps buildId or flips last_ok — all methods are read-only w.r.t. the model.
Temp exports (for quote) go to a scratch path and are not saved. The open handoff
exports to a persistent path so the GUI can load the file after launch.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from typing import TYPE_CHECKING, Any

from solidifai_engine import destinations as destinations_mod
from solidifai_engine.fabrication import estimate as estimate_mod
from solidifai_engine.fabrication import orient as orient_mod
from solidifai_engine.fabrication.base import InstallInfo
from solidifai_engine.fabrication.orca import OrcaProvider

if TYPE_CHECKING:
    from solidifai_engine.session import Session

# Filament price fallback when no destination / profile specifies one.
_DEFAULT_PRICE_PER_KG = 25.0
_DEFAULT_DENSITY_G_CM3 = 1.24  # PLA


class Fabrication:
    def __init__(self, s: Session, provider=None) -> None:
        self.s = s
        # Injectable so tests pass a fake without touching the real OS.
        self._provider = provider if provider is not None else OrcaProvider()

    # ------------------------------------------------------------------
    # Detection + profiles
    # ------------------------------------------------------------------

    def fab_detect(self) -> dict[str, Any]:
        """Probe for a locally installed slicer. Never raises."""
        info: InstallInfo = self._provider.detect()
        result: dict[str, Any] = {"ok": True, "found": info.found}
        if info.version is not None:
            result["version"] = info.version
        if info.executable is not None:
            result["executable"] = info.executable
        return result

    def fab_profiles(self) -> dict[str, Any]:
        """Return printer + filament + process profile names from the installed slicer.

        Returns empty lists when no slicer is installed — never raises.
        """
        try:
            raw = self._provider.profiles()
        except Exception:  # noqa: BLE001
            raw = {}
        return {
            "ok": True,
            "printers": raw.get("printers", []),
            "filaments": raw.get("filaments", []),
            "processes": raw.get("processes", []),
        }

    # ------------------------------------------------------------------
    # Estimate
    # ------------------------------------------------------------------

    def fab_estimate(self, destination_id: str | None = None) -> dict[str, Any]:
        """Estimate print time / weight / cost for the current model.

        With a destination whose provider is detected: exports a temp 3MF and
        calls provider.quote() for a slice-based estimate.
        Without: falls back to geometric estimate from measure().
        """
        if self.s._objects is None:
            return {"ok": False, "error": "no model — run execute_script first"}

        # Resolve destination (may be None)
        dest = self._resolve_destination(destination_id) if destination_id else None

        # Slice path: destination exists + provider is found
        if dest is not None and self._provider.detect().found:
            return self._slice_estimate(dest)

        # Geometric fallback
        return self._geometric_estimate()

    def _resolve_destination(self, dest_id: str) -> dict | None:
        """Return the destination dict with matching id, or None."""
        for d in destinations_mod.load():
            if d.get("id") == dest_id:
                return d
        return None

    def _slice_estimate(self, dest: dict) -> dict[str, Any]:
        """Export a temp 3MF, call provider.quote(), return slice estimate."""
        tmp_path = self._export_temp_3mf()
        if tmp_path is None:
            return self._geometric_estimate()

        try:
            profile = {
                "printer": dest.get("printerProfile"),
                "filament": dest.get("filamentProfile"),
                "process": dest.get("processProfile"),
            }
            result = self._provider.quote(tmp_path, profile, {"price_per_kg": self._price_per_kg()})
        finally:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)

        if not result.get("ok"):
            # Quote failed — fall back to geometric so the user still gets a number
            return self._geometric_estimate()

        est_dict = result.get("estimate", {})
        return {"ok": True, "source": "slice", "estimate": est_dict}

    def _export_temp_3mf(self) -> str | None:
        """Export the current model to a temp 3MF file. Returns path or None."""
        try:
            from solidifai_engine.exports import export as exports_export

            fd, tmp_path = tempfile.mkstemp(suffix=".3mf", prefix="sf_fab_")
            os.close(fd)
            exports_export("3mf", tmp_path)
            return tmp_path
        except Exception:  # noqa: BLE001
            return None

    def _price_per_kg(self) -> float:
        """Filament price from the workspace manufacturing profile, else the default."""
        try:
            from solidifai_engine import manufacturing_profile

            root = getattr(self.s, "root", None)
            if root is None:
                return _DEFAULT_PRICE_PER_KG
            eff = manufacturing_profile.effective(root)
            price = (eff.get("fabrication") or {}).get("filamentCostPerKg")
            if isinstance(price, (int, float)) and price >= 0:
                return float(price)
        except Exception:  # noqa: BLE001 — price is advisory, never block a quote
            pass
        return _DEFAULT_PRICE_PER_KG

    def _geometric_estimate(self) -> dict[str, Any]:
        """Compute a geometric fallback estimate from measure() output."""
        try:
            measure = self.s.measure()
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": "measure() failed — cannot estimate"}

        if not measure.get("ok"):
            return {"ok": False, "error": measure.get("error", "measure failed")}

        # Gather aggregate values across all non-reference parts.
        total_volume = 0.0
        total_surface = 0.0
        total_mass = 0.0
        objects = self.s._objects or []
        parts = measure.get("parts", [])

        for _obj, part in zip(objects, parts, strict=False):
            if part.get("role") == "reference":
                continue
            total_volume += part.get("volume", 0.0)
            total_surface += part.get("area", 0.0)
            total_mass += part.get("mass", 0.0)

        if total_volume == 0.0:
            return {"ok": False, "error": "no printable volume found"}

        # Effective density: from measure's mass/volume ratio when available
        # (avoids a second materials lookup). Fall back to PLA default.
        density = _DEFAULT_DENSITY_G_CM3
        if total_volume > 0 and total_mass > 0:
            # mass is in grams, volume in mm³; density = g / cm³
            density = total_mass / (total_volume / 1000.0)

        est = estimate_mod.geometric(
            volume_mm3=total_volume,
            density_g_cm3=density,
            wall_mm=1.2,
            surface_mm2=total_surface,
            infill=0.2,
            price_per_kg=self._price_per_kg(),
        )
        return {"ok": True, "source": "approx", "estimate": est.to_dict()}

    # ------------------------------------------------------------------
    # Auto-orient
    # ------------------------------------------------------------------

    def fab_orient(self, overhang_deg: float = 45.0) -> dict[str, Any]:
        """Find the print orientation that minimises support material.

        Operates on the shown non-reference solids (Compound when multiple).
        Read-only: never bumps buildId.
        """
        objects = self.s._objects
        if not objects:
            return {"ok": False, "error": "no model — run execute_script first"}

        non_ref = [o for o in objects if getattr(o, "role", "part") != "reference"]
        if not non_ref:
            return {"ok": False, "error": "no printable parts (only reference imports)"}

        try:
            from build123d import Compound

            if len(non_ref) == 1:
                shape = non_ref[0].shape
            else:
                shape = Compound(children=[o.shape for o in non_ref])

            result = orient_mod.best_orientation(shape, overhang_deg=overhang_deg)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"orient failed: {exc}"}

        return {"ok": True, **result}

    # ------------------------------------------------------------------
    # App handoff
    # ------------------------------------------------------------------

    def fab_open(self, destination_id: str | None = None) -> dict[str, Any]:
        """Export the model to a persistent 3MF and open it in the detected slicer.

        Exports to ``exports/<name>-fab.3mf`` in the workspace so OrcaSlicer can
        load the file after the non-blocking launch. Returns ok=False when no
        slicer is installed or the export fails.
        """
        if self.s._objects is None:
            return {"ok": False, "error": "no model — run execute_script first"}

        info = self._provider.detect()
        if not info.found:
            return {"ok": False, "error": "no slicer detected — install OrcaSlicer to open"}

        export_path = self._export_fab_3mf()
        if export_path is None:
            return {"ok": False, "error": "export to 3MF failed"}

        result = self._provider.open_in_app(export_path)
        if not isinstance(result, dict):
            result = {"ok": True}
        result["path"] = export_path
        return result

    def _export_fab_3mf(self) -> str | None:
        """Export the current model to the workspace exports dir for slicer handoff.

        Writes ``exports/<name>-fab.3mf`` so the file persists after the slicer
        is launched. Returns the path or None on failure.
        """
        try:
            from solidifai_engine import scratch
            from solidifai_engine.exports import export as exports_export

            if self.s.root:
                base = os.path.join(self.s.root, "exports")
                name = os.path.basename(self.s.root)
            else:
                base = scratch.exports_dir(self.s.artifacts_dir)
                name = "model"

            slug = scratch.slug(name)
            path = os.path.join(base, f"{slug}-fab.3mf")
            os.makedirs(base, exist_ok=True)
            exports_export("3mf", path)
            return path
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    # Destinations CRUD passthrough
    # ------------------------------------------------------------------

    def list_destinations(self) -> dict[str, Any]:
        """Return all named destinations from the app-level store."""
        return {"ok": True, "destinations": destinations_mod.load()}

    def set_destinations(self, destinations: list) -> dict[str, Any]:
        """Validate and persist a full destinations list.

        Each entry must be a dict with at least ``id``, ``name``, and
        ``provider`` keys. Returns ok=False on the first invalid entry.
        """
        if not isinstance(destinations, list):
            return {"ok": False, "error": "destinations must be a list"}

        for i, dest in enumerate(destinations):
            if not isinstance(dest, dict):
                return {"ok": False, "error": f"entry {i} is not a dict"}
            for required in ("id", "name", "provider"):
                if required not in dest:
                    return {
                        "ok": False,
                        "error": f"entry {i} is missing required key '{required}'",
                    }

        destinations_mod.write(destinations)
        return {"ok": True, "count": len(destinations)}
