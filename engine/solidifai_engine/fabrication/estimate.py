"""Geometric fallback estimate — weight and cost from mesh measurements alone.

Used when no slicer is installed or as a quick pre-flight check. The result
carries ``source="approx"`` so the UI can prompt users to install a slicer
for a more precise slice-based estimate.
"""

from __future__ import annotations

from solidifai_engine.fabrication.base import Estimate

_NOTE = "approximate; install OrcaSlicer for print time and exact filament"


def geometric(
    volume_mm3: float,
    density_g_cm3: float,
    wall_mm: float,
    surface_mm2: float,
    infill: float,
    price_per_kg: float,
) -> Estimate:
    """Estimate filament weight and cost from geometry, no slicer needed.

    Args:
        volume_mm3:     Total solid volume in mm^3.
        density_g_cm3:  Material density in g/cm^3 (e.g. 1.24 for PLA).
        wall_mm:        Shell wall thickness in mm.
        surface_mm2:    Total surface area in mm^2 (used to size the shell).
        infill:         Infill fraction 0.0–1.0.
        price_per_kg:   Filament price in USD per kg.

    Returns:
        Estimate with source="approx", filamentGrams, cost, and a note.
    """
    # Shell volume: surface × wall thickness, clamped so it never exceeds the
    # total volume (handles thin parts where wall already fills the body).
    wall_volume = min(surface_mm2 * wall_mm, volume_mm3)
    core = max(0.0, volume_mm3 - wall_volume)

    # Effective printed volume: full shell + infill fraction of the core
    eff = wall_volume + infill * core

    # Convert mm^3 → cm^3 (÷1000) then multiply by density (g/cm^3)
    grams = eff / 1000.0 * density_g_cm3
    cost = grams / 1000.0 * price_per_kg

    return Estimate(
        source="approx",
        timeSeconds=None,
        filamentGrams=round(grams, 4),
        cost=round(cost, 6),
        note=_NOTE,
    )
