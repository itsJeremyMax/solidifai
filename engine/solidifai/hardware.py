"""Standard ISO metric hardware for solidifai models: socket-head cap screws,
hex nuts, flat washers, auto-sized hole cutters (clearance / counterbore / tap),
and real modeled ISO metric threads.

Threads are represented by plain cylinders at the correct fit diameters by
default, so the parts are fit-accurate and manifold without slow, fragile modeled
helices. When the thread itself is the point (a threaded rod, a printed nut, a
jar lid), ``external_thread`` and ``internal_thread_cutter`` build a real ISO 68-1
60-degree helical thread; these are heavy geometry, so reach for them only when a
represented cylinder will not do. All parts are Z-up, millimetres, and centered on
the Z axis. Subtract the hole cutters from a part to make a correctly-sized hole.

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

from build123d import (
    Align,
    BuildLine,
    BuildSketch,
    Cone,
    Cylinder,
    Helix,
    Location,
    Plane,
    Polyline,
    RegularPolygon,
    extrude,
    make_face,
    sweep,
)

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
    min_depth = t["head_height"] + 0.2
    if depth < min_depth:
        raise ValueError(
            f"counterbore depth {depth} is shallower than the {size} head recess; "
            f"use at least {min_depth} so the head pocket does not overshoot the bore."
        )
    # Resolve the bore through the same profile-aware path as clearance_hole so a
    # tight/normal/loose workspace gets the matching bore, not a hardcoded medium.
    from solidifai_engine import standards as _std

    bore_dia = _std.clearance_hole(size, workspace_root=workspace_root())
    bore = Cylinder(bore_dia / 2, depth, align=(Align.CENTER, Align.CENTER, Align.MAX))
    # The head recess must open the SAME way as the bore (downward from the cut
    # face at Z=0), or subtracting from a top-referenced plate leaves the recess
    # in the air above the part and cuts a plain hole with no head pocket.
    recess = Cylinder(
        t["head_dia"] / 2 + 0.2,
        t["head_height"] + 0.2,
        align=(Align.CENTER, Align.CENTER, Align.MAX),
    )
    return bore + recess


def tap_hole(size: str, depth: float):
    """A cylinder cutter at the tapping-drill diameter (for a threaded hole)."""
    t = dims(size)
    return Cylinder(t["tap_drill"] / 2, depth, align=(Align.CENTER, Align.CENTER, Align.CENTER))


# -- real modeled ISO metric threads ------------------------------------------
#
# Construction: a blank cylinder at the major radius minus a helical 60-degree
# V-groove swept along a Helix. Groove subtraction (rather than fusing a swept
# rib to a core) is what OCC handles robustly at M2..M8: it stays a single valid,
# manifold solid, where fuse-and-clip leaves free edges (non-manifold) and a plain
# helical intersect returns empty. The groove mouth is 0.42*pitch so a flat crest
# survives (a full-pitch mouth self-intersects and erases the thread at M2). The
# helix spans exactly 0..length with no overrun, which keeps the lead-in chamfer
# from severing a thin end sliver.
#
# ISO 68-1 basic profile: fundamental triangle height H = pitch*sqrt(3)/2. External
# minor d3 = d - 1.2269*P (rounded-root form); internal minor D1 = d - 1.0825*P.

_THREAD_MOUTH = 0.42  # groove half-mouth as a fraction of pitch; leaves an ISO-like crest flat


def _thread_dims(size: str) -> tuple[float, float, float]:
    """(nominal major d, coarse pitch P, external minor d3) in mm for a size."""
    dims(size)  # validate with the familiar error message
    from solidifai_engine import standards as _std

    d = float(size[1:])
    p = _std.thread_pitch(size)
    d3 = d - 1.2269 * p  # ISO external minor (rounded root)
    return d, p, d3


def _lead_in_ring(major_r: float, cham: float, z_base: float, top: bool):
    """A conical ring cutter that bevels one end of a threaded shaft. Subtracting
    it trims the outer corner into a 45-degree lead-in so the thread starts into a
    mate. The inner cone crosses the crest transversally (never tangent) so the
    boolean stays clean."""
    outer = major_r + 1.0
    ring = Cylinder(outer, cham, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(
        Location((0, 0, z_base))
    )
    r0, r1 = (outer + cham, major_r - cham) if top else (major_r - cham, outer + cham)
    cone = Cone(r0, r1, cham, align=(Align.CENTER, Align.CENTER, Align.MIN)).moved(
        Location((0, 0, z_base))
    )
    return ring - cone


def _thread_solid(major_r: float, minor_r: float, pitch: float, length: float, lead_in: bool):
    """The shared groove-subtraction thread body, base at Z=0 rising to +length."""
    depth = major_r - minor_r
    blank = Cylinder(major_r, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    helix = Helix(pitch=pitch, height=length, radius=major_r)
    profile_plane = Plane(origin=helix @ 0, z_dir=helix % 0)
    root = depth + 0.05 * pitch  # carry the groove root just past the minor radius
    with BuildSketch(profile_plane) as groove_profile:
        with BuildLine():
            Polyline(
                (0.05 * pitch, -_THREAD_MOUTH * pitch),
                (-root, 0.0),
                (0.05 * pitch, _THREAD_MOUTH * pitch),
                close=True,
            )
        make_face()
    thread = blank - sweep(groove_profile.sketch, path=helix, is_frenet=True)
    if lead_in:
        # Both chamfers must fit within the length without meeting in the middle.
        cham = min(depth, 0.6 * pitch, 0.45 * length)
        thread = (
            thread
            - _lead_in_ring(major_r, cham, 0.0, top=False)
            - _lead_in_ring(major_r, cham, length - cham, top=True)
        )
    return thread


def external_thread(size: str, length: float, lead_in: bool = True):
    """A real ISO metric external thread (a threaded stud/rod segment), ISO 68-1
    60-degree profile at the coarse pitch for ``size`` (M2..M8). Base at Z=0, rising
    +length along +Z, centered on the Z axis. ``lead_in`` bevels both ends (default
    on) so it starts cleanly into a nut or an internal_thread_cutter hole.

    Slow: a swept helix is heavy geometry (roughly 0.4-1 s to build, thousands of
    triangles). Prefer the represented cylinder (socket_head_cap_screw, tap_hole,
    a plain Cylinder) unless the thread itself is the point. Print advice: FDM
    resolves threads from about M6 up acceptably; below that print a smooth boss and
    use a heat-set insert or a tapped/press-fit fastener instead.

        rod = hardware.external_thread("M6", 12)
    """
    d, p, d3 = _thread_dims(size)
    return _thread_solid(d / 2, d3 / 2, p, length, lead_in)


def internal_thread_cutter(size: str, depth: float, clearance: float = 0.1, lead_in: bool = True):
    """A subtraction body that cuts a real ISO metric internal thread into a hole:
    ``part = part - Pos(x, y, z) * hardware.internal_thread_cutter(size, depth)``.
    Base at Z=0, rising +depth along +Z. The cutter is an oversized male thread
    form (every radius grown by ``clearance`` mm), so subtracting it leaves a female
    thread with a uniform radial running clearance against the matching
    ``external_thread``. That is a nominal 6H/6g-style fit, not a certified
    tolerance class: internal major ~ d + 2*clearance, internal minor ~ D1 +
    2*clearance. Default clearance 0.1 mm is a normal running fit; loosen it for FDM.
    ``lead_in`` countersinks both ends of the cut so a screw enters easily.

    Slow, like external_thread; only model an internal thread when the part is a
    real nut, threaded insert body, or lid. For a printed blind hole prefer a
    heat-set insert (std.insert) or a tap_hole pilot.

        nut = hardware.hex_nut("M6") - hardware.internal_thread_cutter("M6", 5.2)
    """
    d, p, d3 = _thread_dims(size)
    return _thread_solid(d / 2 + clearance, d3 / 2 + clearance, p, depth, lead_in)
