"""Standard ISO metric hardware for solidifai models: socket-head cap screws,
hex nuts, flat washers, and auto-sized hole cutters (clearance / counterbore /
tap).

Threads are represented by plain cylinders at the correct fit diameters, so the
parts are fit-accurate and manifold without slow, fragile modeled helices. All
parts are Z-up, millimetres, and centered on the Z axis. Subtract the hole
cutters from a part to make a correctly-sized hole.

    from solidifai import hardware, show
    plate = Box(30, 30, 5) - hardware.clearance_hole("M3", depth=5)
    show(plate, name="Plate")
    show(Pos(0, 0, 5) * hardware.socket_head_cap_screw("M3", 12), name="Screw")

All dimensions come from ``solidifai_engine.standards`` (the single home for
hardware data: ISO 4762 cap-screw heads, ISO 4032 hex nuts, ISO 7089 washers,
ISO 273 clearance series, coarse-pitch tap drills). Moving onto standards also
corrected the M5/M6/M8 nut thicknesses to true ISO 4032 values (4.7/5.2/6.8;
the old table shipped the thinner DIN 934 numbers) and replaced approximate
close/coarse clearance formulas with the exact ISO 273 series.
"""

from __future__ import annotations

from build123d import Align, Cylinder, RegularPolygon, extrude

from .imports import workspace_root

# Built lazily from solidifai_engine.standards so `import solidifai` stays
# light; key names are kept for any existing model.py reading dims().
_TABLE: dict[str, dict[str, float]] | None = None


def _table() -> dict[str, dict[str, float]]:
    global _TABLE
    if _TABLE is None:
        from solidifai_engine import standards as _std

        _TABLE = {
            size: {
                "d": _std.screw(size)["thread_dia"],
                "head_dia": _std.screw(size)["head_dia"],  # ISO 4762
                "head_height": _std.screw(size)["head_height"],
                "nut_width": _std.nut(size)["width_af"],  # ISO 4032
                "nut_thickness": _std.nut(size)["thickness"],
                "clearance_close": _std.ISO273_CLEARANCE[size]["close"],
                "clearance_medium": _std.ISO273_CLEARANCE[size]["medium"],
                "clearance_coarse": _std.ISO273_CLEARANCE[size]["coarse"],
                "tap_drill": _std.pilot_hole(size),
                "washer_od": _std.washer(size)["od"],  # ISO 7089
                "washer_id": _std.washer(size)["id"],
                "washer_t": _std.washer(size)["thickness"],
            }
            for size in _std.sizes()
        }
    return _TABLE


def sizes() -> list:
    """The supported size designations (M2 .. M8)."""
    return list(_table())


def dims(size: str) -> dict:
    """Raw dimension dict (mm) for a size. Raises ValueError on an unknown size."""
    table = _table()
    if size not in table:
        raise ValueError(f"unknown size {size!r}; supported: {', '.join(table)}")
    return dict(table[size])


def socket_head_cap_screw(size: str, length: float):
    """Socket-head cap screw (ISO 4762 head envelope) with a plain shaft of
    ``length`` mm. The under-head face is at Z=0; the head rises above it, the
    shaft hangs below. Head drive recess is not modeled."""
    t = dims(size)
    head = Cylinder(
        t["head_dia"] / 2, t["head_height"], align=(Align.CENTER, Align.CENTER, Align.MIN)
    )
    shaft = Cylinder(t["d"] / 2, length, align=(Align.CENTER, Align.CENTER, Align.MAX))
    return head + shaft


def hex_nut(size: str):
    """Hex nut (ISO 4032 across-flats + thickness) with a clearance bore."""
    t = dims(size)
    # across-flats = nut_width -> inradius = nut_width/2 (major_radius is the
    # circumradius, so use minor radius via major_radius=False).
    body = extrude(RegularPolygon(t["nut_width"] / 2, 6, major_radius=False), t["nut_thickness"])
    bore = Cylinder(
        t["d"] / 2, t["nut_thickness"] * 3, align=(Align.CENTER, Align.CENTER, Align.CENTER)
    )
    return body - bore


def washer(size: str):
    """Flat washer (ISO 7089): an annulus, OD/ID/thickness per the table."""
    t = dims(size)
    outer = Cylinder(t["washer_od"] / 2, t["washer_t"])
    inner = Cylinder(t["washer_id"] / 2, t["washer_t"] * 3)
    return outer - inner


def clearance_hole(size: str, depth: float, fit: str | None = None):
    """A cylinder cutter at the exact ISO 273 clearance diameter. ``fit`` is
    close / medium / coarse (or the profile names tight / normal / loose);
    ``fit=None`` resolves the workspace manufacturing profile's fit setting.
    Subtract from a part."""
    dims(size)  # validate the size with the familiar error message
    from solidifai_engine import standards as _std

    dia = _std.clearance_hole(size, fit, workspace_root=workspace_root())
    return Cylinder(dia / 2, depth, align=(Align.CENTER, Align.CENTER, Align.CENTER))


def counterbore(size: str, depth: float):
    """A stepped cutter: a clearance bore of ``depth`` plus a head recess sized
    for the socket head, opening upward. Subtract from a part."""
    t = dims(size)
    bore = Cylinder(t["clearance_medium"] / 2, depth, align=(Align.CENTER, Align.CENTER, Align.MAX))
    recess = Cylinder(
        t["head_dia"] / 2 + 0.2,
        t["head_height"] + 0.2,
        align=(Align.CENTER, Align.CENTER, Align.MIN),
    )
    return bore + recess


def tap_hole(size: str, depth: float):
    """A cylinder cutter at the tapping-drill diameter (for a threaded hole)."""
    t = dims(size)
    return Cylinder(t["tap_drill"] / 2, depth, align=(Align.CENTER, Align.CENTER, Align.CENTER))
