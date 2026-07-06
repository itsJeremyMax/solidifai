"""Offscreen renderer: build123d's tessellation of the current model -> labeled
PNGs from named or custom camera angles, for agent visual debugging.

This is the only engine module that imports ``vtkmodules``, and it takes raw
vertex/triangle arrays (build123d native, millimetre, Z-up) so it never imports
build123d itself. Rendering the tessellation directly -- rather than importing
the GLB -- keeps the Z-up axes exact: a ``vtkGLTFImporter`` would silently swap
to glTF's Y-up frame and mislabel named views.
"""

from __future__ import annotations

import math
import re

import vtkmodules.vtkRenderingFreeType  # noqa: F401  (registers font/text rendering)
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401  (registers the OpenGL2 render backend)
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkFiltersCore import vtkFeatureEdges, vtkPolyDataNormals
from vtkmodules.vtkIOImage import vtkPNGWriter
from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkRenderer,
    vtkRenderWindow,
    vtkTextActor,
    vtkWindowToImageFilter,
)

VIEW_SIZE = 512
BACKGROUND = (0.12, 0.12, 0.14)
EDGE_FEATURE_ANGLE = 30.0
HIGHLIGHT_COLOR = (1.0, 0.55, 0.0)  # orange accent for named feature overlays
CAP_COLOR = (0.93, 0.18, 0.80)  # magenta fill for section cut (cap) faces

# name -> (camera direction from center, view-up). Z-up convention.
_FACE_VIEWS = {
    "top": ((0, 0, 1), (0, 1, 0)),
    "bottom": ((0, 0, -1), (0, 1, 0)),
    "front": ((0, -1, 0), (0, 0, 1)),
    "back": ((0, 1, 0), (0, 0, 1)),
    "right": ((1, 0, 0), (0, 0, 1)),
    "left": ((-1, 0, 0), (0, 0, 1)),
}


def _corner_views() -> dict:
    """The 8 octant isometrics, named by the three half-spaces."""
    out = {}
    for fb, y in (("front", -1), ("back", 1)):
        for tb, z in (("top", 1), ("bottom", -1)):
            for lr, x in (("right", 1), ("left", -1)):
                out[f"{fb}-{tb}-{lr}"] = ((x, y, z), (0, 0, 1))
    return out


_NAMED_VIEWS = {**_FACE_VIEWS, **_corner_views(), "iso": ((1, -1, 1), (0, 0, 1))}

_CUSTOM_RE = re.compile(r"^az(-?\d+)_el(-?\d+)$")


def _resolve(spec: str):
    """Return ``(direction, view_up, label)`` for a view spec, or raise
    ValueError naming the valid vocabulary."""
    if spec in _NAMED_VIEWS:
        direction, up = _NAMED_VIEWS[spec]
        return direction, up, spec.upper()
    m = _CUSTOM_RE.match(spec)
    if m:
        az = math.radians(float(m.group(1)))
        el = math.radians(float(m.group(2)))
        direction = (
            math.cos(el) * math.sin(az),
            -math.cos(el) * math.cos(az),
            math.sin(el),
        )
        return direction, (0, 0, 1), spec
    valid = ", ".join(sorted(_NAMED_VIEWS))
    raise ValueError(f"unknown view {spec!r}; valid names: {valid}; or az<deg>_el<deg>")


def _build_polydata(vertices: list, triangles: list) -> vtkPolyData:
    """A vtkPolyData triangle mesh from raw (x,y,z) verts + (i,j,k) tris."""
    pts = vtkPoints()
    for x, y, z in vertices:
        pts.InsertNextPoint(x, y, z)
    cells = vtkCellArray()
    for tri in triangles:
        cells.InsertNextCell(3)
        for idx in tri:
            cells.InsertCellPoint(idx)
    pd = vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    return pd


def _fmt_mm(v: float) -> str:
    """Dim-label number at 0.1 mm resolution, trailing zeros trimmed.
    Whole-mm rounding lied about thin parts (a 1.6 mm washer captioned "2 mm")."""
    return f"{v:.1f}".rstrip("0").rstrip(".")


FOCUS_MARGIN = 0.15  # breathing room around a focus target (fraction of frame)


def _focus_camera(bounds, direction, view_angle_deg: float = 30.0, margin: float = FOCUS_MARGIN):
    """Camera ``(focal_point, position)`` framing ``bounds`` (xmin,ymin,zmin,
    xmax,ymax,zmax) from ``direction``: the target's bounding sphere subtends
    the view angle shrunk by ``margin``, so the target fills most of the frame
    with ~15% slack and the rest of the model stays visible around it."""
    xmin, ymin, zmin, xmax, ymax, zmax = bounds
    center = ((xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2)
    r = math.dist((xmin, ymin, zmin), (xmax, ymax, zmax)) / 2 or 1.0
    n = math.sqrt(sum(c * c for c in direction)) or 1.0
    dist = (r * (1 + margin)) / math.sin(math.radians(view_angle_deg / 2))
    position = tuple(center[i] + (direction[i] / n) * dist for i in range(3))
    return center, position


def _add_axes_inset(win: vtkRenderWindow):
    """A small bottom-right inset showing an RGB axis triad. Returns its
    renderer; sync the inset camera's direction to the main view each frame."""
    axes = vtkAxesActor()
    axes.AxisLabelsOff()
    inset = vtkRenderer()
    inset.SetViewport(0.78, 0.0, 1.0, 0.22)
    inset.SetBackground(*BACKGROUND)
    inset.InteractiveOff()
    inset.AddActor(axes)
    win.AddRenderer(inset)
    return inset


def render_views(
    vertices: list,
    triangles: list,
    out_dir: str,
    views: list,
    groups: list | None = None,
    highlight_mesh=None,
    size: int = VIEW_SIZE,
    cap_mesh=None,
    focus_bounds=None,
    focus_label: str | None = None,
) -> list:
    """Render each view spec of the mesh to ``out_dir/<name>.png``.

    ``groups`` (optional) is ``[(vertices, triangles, (r, g, b)), ...]`` — one
    display-sRGB-colored surface per object. When given, the gray surface actor
    is replaced by one colored actor per group; ``vertices``/``triangles`` (the
    union mesh) still drive the feature edges, bounds and camera. When ``None``,
    a single uniform-gray actor renders the whole mesh (clay mode).

    ``highlight_mesh`` (optional) is ``(vertices, triangles)`` for an accent
    overlay. When non-empty, a second surface actor colored ``HIGHLIGHT_COLOR``
    (orange) is added to the renderer on top of the base mesh. This is purely
    additive — all existing actors (edges, triad, labels) are unchanged.

    ``size`` is the square render edge in pixels (default ``VIEW_SIZE``);
    labels and edge widths scale with it so a 4x render is not captioned in
    4x-smaller relative type.

    ``cap_mesh`` is ``(vertices, triangles)`` for section cut faces, rendered
    as one extra actor in ``CAP_COLOR`` (magenta) so the exposed cross-section
    reads as filled material, not a hollow shell.

    ``focus_bounds`` (xmin,ymin,zmin,xmax,ymax,zmax) reframes every view's
    camera tight onto that region (~15% margin) while ALL actors still render,
    so the close-up keeps its surrounding context; ``focus_label`` names it in
    the caption.

    Resolves ALL specs first (raising on the first bad one) so a bad spec writes
    no files. Returns ``[{name, path, width, height}, ...]``.
    """
    resolved = [(spec, *_resolve(spec)) for spec in views]  # validate-all-first

    pd = _build_polydata(vertices, triangles)  # union mesh: drives edges + bounds

    ren = vtkRenderer()
    ren.SetBackground(*BACKGROUND)

    def _surface(poly):
        norm = vtkPolyDataNormals()
        norm.SetInputData(poly)
        norm.SetFeatureAngle(EDGE_FEATURE_ANGLE)
        norm.Update()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(norm.GetOutputPort())
        mapper.ScalarVisibilityOff()
        actor = vtkActor()
        actor.SetMapper(mapper)
        return actor

    # Surface actor(s): one colored actor per object when groups are given (the
    # gray actor is omitted), else a single uniform-gray actor over the union.
    if groups:
        for gverts, gtris, rgb in groups:
            actor = _surface(_build_polydata(gverts, gtris))
            actor.GetProperty().SetColor(*rgb)
            ren.AddActor(actor)
    else:
        actor = _surface(pd)
        actor.GetProperty().SetColor(0.82, 0.82, 0.85)
        ren.AddActor(actor)

    # Feature-edge overlay from the raw mesh (sharp topology), so silhouettes,
    # holes, and creases read crisply over the shading.
    edges = vtkFeatureEdges()
    edges.SetInputData(pd)
    edges.BoundaryEdgesOn()
    edges.FeatureEdgesOn()
    edges.SetFeatureAngle(EDGE_FEATURE_ANGLE)
    edges.ManifoldEdgesOff()
    edges.NonManifoldEdgesOff()
    edge_mapper = vtkPolyDataMapper()
    edge_mapper.SetInputConnection(edges.GetOutputPort())
    edge_mapper.ScalarVisibilityOff()
    edge_actor = vtkActor()
    edge_actor.SetMapper(edge_mapper)
    edge_actor.GetProperty().SetColor(0.05, 0.05, 0.07)
    edge_actor.GetProperty().SetLineWidth(1.5 * (size / VIEW_SIZE))
    ren.AddActor(edge_actor)

    # Optional accent overlay: a second surface actor for highlighted features,
    # colored HIGHLIGHT_COLOR (orange). Purely additive — does not replace any
    # existing actor.
    if highlight_mesh is not None:
        hverts, htris = highlight_mesh
        if hverts and htris:
            h_actor = _surface(_build_polydata(hverts, htris))
            h_actor.GetProperty().SetColor(*HIGHLIGHT_COLOR)
            ren.AddActor(h_actor)

    # Section cap faces: the cross-section material exposed by a plane cut,
    # filled in CAP_COLOR so solid regions read as solid. Additive, like the
    # highlight actor.
    if cap_mesh is not None:
        cverts, ctris = cap_mesh
        if cverts and ctris:
            cap_actor = _surface(_build_polydata(cverts, ctris))
            cap_actor.GetProperty().SetColor(*CAP_COLOR)
            ren.AddActor(cap_actor)

    win = vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetSize(size, size)
    scale = size / VIEW_SIZE  # 1.0 at the default; keeps captions readable at 2048

    b = pd.GetBounds()  # (xmin,xmax,ymin,ymax,zmin,zmax) — real mm extent
    center = ((b[0] + b[1]) / 2.0, (b[2] + b[3]) / 2.0, (b[4] + b[5]) / 2.0)
    diag = math.dist((b[0], b[2], b[4]), (b[1], b[3], b[5])) or 1.0

    cam = ren.GetActiveCamera()

    dims = f"{_fmt_mm(b[1] - b[0])} × {_fmt_mm(b[3] - b[2])} × {_fmt_mm(b[5] - b[4])} mm"
    label = vtkTextActor()
    label_prop = label.GetTextProperty()
    label_prop.SetFontSize(max(10, round(18 * scale)))
    label_prop.SetColor(0.9, 0.9, 0.92)
    label_prop.SetFontFamilyToCourier()
    label.SetDisplayPosition(round(12 * scale), round(10 * scale))
    ren.AddActor2D(label)

    inset = _add_axes_inset(win)
    inset_cam = inset.GetActiveCamera()

    out = []
    for spec, direction, up, label_text in resolved:
        n = math.sqrt(sum(c * c for c in direction)) or 1.0
        d = [c / n for c in direction]
        cam.SetViewUp(*up)
        if focus_bounds is not None:
            f_center, f_pos = _focus_camera(focus_bounds, d)
            cam.SetFocalPoint(*f_center)
            cam.SetPosition(*f_pos)
        else:
            cam.SetFocalPoint(*center)
            cam.SetPosition(*(center[i] + d[i] * diag * 2 for i in range(3)))
        cam.SetViewAngle(30)
        ren.ResetCameraClippingRange()

        # Point the inset triad the same way the main camera looks.
        px, py, pz = cam.GetPosition()
        fx, fy, fz = cam.GetFocalPoint()
        inset_cam.SetFocalPoint(0, 0, 0)
        inset_cam.SetViewUp(*cam.GetViewUp())
        inset_cam.SetPosition(px - fx, py - fy, pz - fz)
        inset.ResetCamera()

        caption = f"{label_text} · {dims}"
        if focus_label:
            caption = f"{label_text} · FOCUS {focus_label} · {dims}"
        label.SetInput(caption)
        win.Render()

        w2i = vtkWindowToImageFilter()
        w2i.SetInput(win)
        w2i.Update()
        path = f"{out_dir}/{spec}.png"
        writer = vtkPNGWriter()
        writer.SetFileName(path)
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Write()
        out.append({"name": spec, "path": path, "width": size, "height": size})

    # Tear down the offscreen GL pipeline explicitly; relying on Python GC to free
    # VTK's ref-counted C++ render window leaks driver/GPU memory over many captures.
    ren.RemoveAllViewProps()
    inset.RemoveAllViewProps()
    win.RemoveRenderer(ren)
    win.RemoveRenderer(inset)
    win.Finalize()
    return out


def capture_smoke(out_dir: str) -> list[str]:
    """Render the 'iso' view of a unit box to out_dir; return written paths.
    A minimal offscreen-render smoke test for the bundled/subset VTK."""
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    tris = [
        (0, 1, 5),
        (0, 5, 4),
        (1, 2, 6),
        (1, 6, 5),
        (2, 3, 7),
        (2, 7, 6),
        (3, 0, 4),
        (3, 4, 7),
        (0, 3, 2),
        (0, 2, 1),
        (4, 5, 6),
        (4, 6, 7),
    ]
    results = render_views(verts, tris, out_dir, ["iso"])
    return [r["path"] for r in results]
