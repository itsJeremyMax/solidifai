"""Introspect whether a build123d shape carries an OCC triangulation (mesh).

Used to verify incremental tessellation: the B1 NodeCache stores the same
shape objects across re-renders, so unchanged parts share TShape data with
the placed copies that export_gltf meshes. Same shape identity = same
tessellation parameters = no geometric rebuild on cache hits.

Note: export_gltf calls BRepTools.Clean_s after writing, which removes the
active triangulation from all TShapes (including shared originals). Use
`ensure_meshed` to bake a triangulation before introspecting.
"""

from __future__ import annotations

from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopLoc import TopLoc_Location


def _triangulations(shape):
    """Yield each face's active Poly_Triangulation (skipping unset faces)."""
    for face in shape.faces():
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face.wrapped, loc)
        if tri is not None:
            yield tri


def is_meshed(shape) -> bool:
    """True if any face of the shape carries an active triangulation."""
    for _tri in _triangulations(shape):
        return True
    return False


def triangle_count(shape) -> int:
    """Total triangles across the shape's meshed faces (0 if unmeshed)."""
    return sum(tri.NbTriangles() for tri in _triangulations(shape))


def ensure_meshed(
    shape,
    linear_deflection: float = 1e-3,
    angular_deflection: float = 0.1,
) -> None:
    """Bake a triangulation onto *shape* if it does not already have one.

    Mirrors the deflection defaults used by render_to / export_gltf so the
    resulting triangle counts are stable and comparable across calls.
    """
    BRepMesh_IncrementalMesh(
        shape.wrapped, linear_deflection, True, angular_deflection, True
    ).Perform()
