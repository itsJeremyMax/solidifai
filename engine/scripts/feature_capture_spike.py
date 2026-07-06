# engine/scripts/feature_capture_spike.py
"""Spike: can we capture the geometry a feature() block produces?

Run:  cd engine && uv run python scripts/feature_capture_spike.py

Confirms (a) active-builder access via Builder._get_context() and (b) a
per-block topology delta for hole / fillet / chamfer / boolean-subtract.
Decision recorded at the bottom of this file: face/edge SET-DIFF vs boolean
SOLID-DELTA.
"""

from build123d import (
    Axis,
    Box,
    Builder,
    BuildPart,
    Cylinder,
    Hole,
    Locations,
    Mode,
    chamfer,
    fillet,
)


def hole_block(p):
    with Locations((0, 0)):
        Hole(radius=5)


def fillet_block(p):
    fillet(p.edges().filter_by(Axis.Z), radius=3)


def chamfer_block(p):
    top = p.faces().sort_by(Axis.Z)[-1]
    chamfer(top.edges(), length=2)


def boolean_block(p):
    Cylinder(radius=6, height=40, mode=Mode.SUBTRACT)


def capture(label, block):
    with BuildPart() as p:
        Box(40, 40, 20)
        faces_before = set(p.faces())
        edges_before = set(p.edges())
        solid_before = p.part
        block(p)
        ctx = Builder._get_context()
        new_faces = set(p.faces()) - faces_before
        new_edges = set(p.edges()) - edges_before
        print(f"\n[{label}] active ctx = {type(ctx).__name__}")
        print(f"  new faces: {len(new_faces)}   new edges: {len(new_edges)}")
        for f in new_faces:
            print(f"    face geom={f.geom_type} area={round(f.area, 2)}")
        try:
            delta = solid_before - p.part  # removed material (subtractive ops)
            print(f"  boolean solid-delta volume = {round(delta.volume, 2)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  boolean solid-delta failed: {exc}")


for label, block in [
    ("hole", hole_block),
    ("fillet", fillet_block),
    ("chamfer", chamfer_block),
    ("boolean_subtract", boolean_block),
]:
    capture(label, block)

# === SPIKE DECISION (observed results — build123d 0.10.0) =====================
#
# Active-builder access:  Builder._get_context() -> BuildPart   [confirm: YES]
#   Every capture() call returned type(ctx).__name__ == "BuildPart".
#
# Observed results per op kind:
#
#   hole:
#     new faces: 3   new edges: 3
#       CYLINDER  area=628.32   <- hole wall (discriminating geom_type)
#       PLANE     area=1521.46  <- top face (annular, replaces original)
#       PLANE     area=1521.46  <- bottom face (replaces original)
#     boolean solid-delta volume = 1570.80  (pi*5^2*20 ≈ 1570.8 ✓)
#
#   fillet:
#     new faces: 10   new edges: 24
#       4 × CYLINDER area=94.25  <- fillet roll surfaces
#       6 × PLANE (side + top replacements)
#     boolean solid-delta volume = 154.51  (corner material removed)
#
#   chamfer:
#     new faces: 9   new edges: 16
#       4 × PLANE area=107.48   <- chamfer bevels (all PLANE — no CYLINDER)
#       5 × PLANE (side + top replacements)
#     boolean solid-delta volume = 309.33
#
#   boolean_subtract:
#     new faces: 3   new edges: 3
#       CYLINDER  area=753.98   <- subtracted cylinder wall
#       PLANE     area=1486.9 × 2  <- top/bottom caps
#     boolean solid-delta volume = 2261.95  (pi*6^2*40 ≈ 2261.9 ✓)
#
# Capture mechanism chosen:  HYBRID
#
# Rationale: SET-DIFF is the primary mechanism — it works for every op kind,
#   yields the exact replacement faces with correct geom_type tags (CYLINDER
#   discriminates hole walls and fillet rolls; all-PLANE discriminates chamfer
#   bevels), and requires no additional geometry construction.  BOOLEAN-DELTA
#   is used as a supplementary signal for subtractive ops (hole, boolean_subtract)
#   where volume is well-defined and non-zero; for fillet/chamfer it also
#   produces a non-zero volume, confirming it is computable but less semantically
#   useful.  The chosen approach leads with face/edge set-diff and optionally stores the
#   delta volume for subtractive ops to support future mass-property queries.
# =============================================================================
