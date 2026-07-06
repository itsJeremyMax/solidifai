# organic & freeform shapes (solidifai engine, build123d 0.10.0)

Curved, flowing, hand-friendly forms — vases, grips, horns, pebbles, leaves, doubly-curved
shells. This is a companion to `build123d-cookbook.md`: that file has the base verbs
(revolve §3, loft §4, sweep §5, fillet §6); this one composes them into organic geometry and
flags where the B-rep kernel fights back.

**The engine is parametric B-rep (OpenCASCADE), not a sculptor.** There is no subdivision
surface, no mesh push/pull, no NURBS control-point editing. You don't *sculpt* an organic shape
here — you *compose* it from a few moves and round it off. Five moves cover almost everything:

| You want | Reach for | Below |
|----------|-----------|-------|
| A body that morphs between cross-sections (round base, square top) | **loft** stacked sketches | §1 |
| A teardrop, horn, or pointed dome | **loft to a point** | §2 |
| A tube / handle that follows a flowing path | **sweep** a profile along a spline | §3 |
| A horn / cornucopia whose section changes as it flows | **multi-section sweep** | §4 |
| A vase, bottle, cup, any turned silhouette | **revolve** a spline profile | §5 |
| A leaf, guitar pick, flat organic slab | **spline / Bezier outline → extrude** | §6 |
| To soften a hard part into a river-stone | **fillet hard** | §7 |
| To blend two bodies into one smooth mass | **union + fillet the seam** | §8 |
| A doubly-curved shell (dish, canopy, scoop) | **make_surface + thicken** | §9 |

Conventions match the base cookbook: builder API (`with BuildPart() as p:`), result is `p.part`,
units mm, `from solidifai import show`. Every block below builds a valid manifold solid except the
one marked otherwise. Copy a block, adapt the numbers, run it with `execute_script`.

---

## 1. Loft through stacked sections

`loft()` blends every pending sketch on parallel planes into one smooth body — the workhorse for a
shape that changes cross-section along its length. The sections don't have to match: a circle can
blend to an ellipse to a rounded rectangle. Order them along one axis with `Plane.XY.offset(d)`
and keep their centers roughly stacked so the blend doesn't shear.

```python
from build123d import BuildPart, BuildSketch, Circle, Ellipse, RectangleRounded, Plane, loft
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XY):
        Circle(18)
    with BuildSketch(Plane.XY.offset(22)):
        Ellipse(20, 12)
    with BuildSketch(Plane.XY.offset(48)):
        RectangleRounded(34, 22, 6)
    loft()

show(p.part, name="LoftStack")
```

`loft(ruled=True)` makes straight (faceted) transitions between layers instead of the default
smooth blend. Add more intermediate sketches to steer the silhouette — the blend only knows the
sections you give it.

---

## 2. Loft to a point (teardrop, horn, dome)

A loft can end at a **vertex** instead of a sketch, drawing the body to a tip. Pass the sections
explicitly with the `Vertex` first and/or last (the builder won't append a bare vertex to the
pending sketches, so list the sketches too):

```python
# doctest: +NONMANIFOLD
from build123d import BuildPart, BuildSketch, Circle, Plane, Vertex, loft
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XY) as base:
        Circle(20)
    with BuildSketch(Plane.XY.offset(18)) as waist:
        Circle(13)
    loft(sections=[base.sketch, waist.sketch, Vertex(0, 0, 42)])

show(p.part, name="LoftApex")
```

> **⚠ A true point is non-manifold.** An apex is a geometric singularity (a free vertex where the
> surface pinches to nothing), so this builds a **valid** solid that reports `manifold: false` —
> the same story as the `Sphere` polar seam in cookbook §1. Fine for a render or a STEP hand-off;
> **not** printable as-is. For a printable teardrop, loft to a *small circle* (e.g. `Circle(1.5)`)
> instead of a `Vertex` — the result is manifold and looks identical.

---

## 3. Sweep a profile along a flowing path

Draw the path with curves (`Spline`, `Bezier`, `RadiusArc`) instead of straight `Polyline`
segments, seat the cross-section on a plane normal to the path start, then `sweep()`. This is how
you get tubes, spouts, handles, and stems that actually flow. `path.line @ 0` is the start point
and `path.line % 0` is the start tangent — feed both to `Plane(...)` so the section starts square
to the path. `is_frenet=True` keeps the section from twisting as the path curves.

```python
from build123d import BuildPart, BuildLine, Spline, BuildSketch, Circle, Plane, sweep
from solidifai import show

with BuildPart() as p:
    with BuildLine() as path:
        Spline((0, 0, 0), (12, 0, 22), (-6, 0, 44), (10, 0, 64))
    with BuildSketch(Plane(origin=path.line @ 0, z_dir=path.line % 0)):
        Circle(5)
    sweep(is_frenet=True)

show(p.part, name="SweptSpline")
```

---

## 4. Multi-section sweep (the section morphs along the path)

`sweep(multisection=True)` sweeps **several** profiles along one path, blending between them as it
goes — a horn that starts wide, pinches, and flares again. Place each profile on a plane sampled
along the path with `path.line @ t` / `path.line % t` for `t` in `0..1`.

```python
from build123d import BuildPart, BuildLine, Spline, BuildSketch, Circle, Plane, sweep
from solidifai import show

with BuildPart() as p:
    with BuildLine() as path:
        Spline((0, 0, 0), (6, 0, 30), (0, 0, 60))
    with BuildSketch(Plane(origin=path.line @ 0, z_dir=path.line % 0)):
        Circle(13)
    with BuildSketch(Plane(origin=path.line @ 0.5, z_dir=path.line % 0.5)):
        Circle(4)
    with BuildSketch(Plane(origin=path.line @ 1, z_dir=path.line % 1)):
        Circle(9)
    sweep(multisection=True)

show(p.part, name="HornMulti")
```

---

## 5. Revolve a spline silhouette (vases, bottles, cups)

Revolve is cookbook §3; the organic move is to draw the half-profile's outer wall with a `Spline`
instead of straight segments, so the silhouette curves. Keep the profile on +X, close it back down
the axis, then `revolve(axis=Axis.Z)`.

```python
from build123d import (
    BuildPart, BuildSketch, BuildLine, Line, Spline, make_face, revolve, Plane, Axis,
)
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XZ):
        with BuildLine():
            Line((0, 0), (22, 0))                              # base radius
            Spline((22, 0), (30, 24), (13, 52), (19, 78))      # belly -> neck -> lip
            Line((19, 78), (0, 78))                            # across the top
            Line((0, 78), (0, 0))                              # down the axis
        make_face()
    revolve(axis=Axis.Z)

show(p.part, name="Vase")
```

**Hollow it into a vessel** with `offset` (cookbook §10): grab the top disk and leave it open. The
shelled body has ~1/4 the solid's volume — a real thin-walled vase, bottle, or cup.

```python
from build123d import (
    BuildPart, BuildSketch, BuildLine, Line, Spline, make_face, revolve, offset, Plane, Axis,
)
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XZ):
        with BuildLine():
            Line((0, 0), (22, 0))
            Spline((22, 0), (30, 24), (13, 52), (19, 78))
            Line((19, 78), (0, 78))
            Line((0, 78), (0, 0))
        make_face()
    revolve(axis=Axis.Z)
    top = p.faces().sort_by(Axis.Z)[-1]
    offset(amount=-2.5, openings=top)

show(p.part, name="BudVase")
```

See `examples/spline-vase.py` for the full parametric version (foot / belly / neck / mouth / wall
sliders).

---

## 6. Organic outline → extrude (flat organic shapes)

For a flat-but-curvy part — a leaf, a guitar pick, a teardrop tag — draw the outline with `Bezier`
or `Spline`, `mirror` for symmetry, `make_face`, then `extrude`. Draw only **one** flank and let
`mirror(about=Plane.YZ)` close the loop; don't draw an edge *on* the mirror axis or you get a
coincident-edge invalid face.

```python
from build123d import (
    BuildPart, BuildSketch, BuildLine, Bezier, mirror, make_face, extrude, Plane,
)
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XY):
        with BuildLine():
            Bezier((0, -42), (34, -20), (30, 26), (0, 42))   # right flank only
            mirror(about=Plane.YZ)                            # left flank closes the leaf
        make_face()
    extrude(amount=9)

show(p.part, name="Leaf")
```

---

## 7. Soften a prism into a pebble

The cheapest organic move: build a blocky part and round it *hard*. Fillet a radius that's a large
fraction of the part's thickness and the facets disappear into a river-stone. Here both end faces'
rims get an 8 mm round on a 22 mm-thick rounded-rect prism.

```python
from build123d import BuildPart, BuildSketch, RectangleRounded, extrude, Axis, fillet
from solidifai import show

with BuildPart() as p:
    with BuildSketch():
        RectangleRounded(70, 45, 18)
    extrude(amount=22)
    fillet(p.faces().filter_by(Axis.Z).edges(), radius=8)   # round top + bottom rims

show(p.part, name="Pebble")
```

Keep the radius below the local feature size (here < half the 22 mm height and < the 18 mm corner
radius). Push it past that and the fillet won't compute — see Limits below.

---

## 8. Blend two bodies with a fillet

To merge two solids into one smooth mass, fuse them (default `Mode.ADD`) and fillet the seam where
they meet. Selecting the seam: the intersection of two cylinders is **not** a circle, so
`filter_by(GeomType.CIRCLE, reverse=True)` keeps the non-circular seam edges and leaves the round
end caps alone.

```python
from build123d import BuildPart, Cylinder, GeomType, fillet
from solidifai import show

with BuildPart() as p:
    Cylinder(radius=12, height=52)                       # vertical trunk
    Cylinder(radius=9, height=44, rotation=(0, 90, 0))   # horizontal arm, fuses in
    seam = p.edges().filter_by(GeomType.CIRCLE, reverse=True)
    fillet(seam, radius=4)

show(p.part, name="BlendCross")
```

This is the B-rep stand-in for metaballs: overlapping primitives + a seam fillet gives a tendon-like
blend. The fillet radius is the soft part — start small, it's the first thing to fail (Limits §).

---

## 9. Freeform surface → thicken (advanced)

For a doubly-curved shell — a dish, a scoop, a canopy — build a non-planar `Face` with
`Face.make_surface(exterior, surface_points=...)` and `thicken` it into a solid. The exterior is a
closed boundary wire; the surface points pull the sheet into 3D between them.

```python
from build123d import BuildPart, BuildLine, Polyline, Face, thicken
from solidifai import show

with BuildLine() as edge:
    Polyline((-30, -30, 0), (30, -30, 0), (30, 30, 0), (-30, 30, 0), close=True)

surf = Face.make_surface(
    edge.wire(),
    surface_points=[(0, 0, 12), (16, 0, 8), (-16, 0, 8), (0, 16, 8), (0, -16, 8)],
)

with BuildPart() as p:
    thicken(surf, amount=3)

show(p.part, name="DomeShell")
```

> **This is the fragile path.** A *single* center point lets the fitted surface overshoot the
> boundary wildly (it ballooned to ~2× the footprint in testing). Constrain it with several points
> — mid-edge plus center — and keep the lift gentle. Reach for §1–§8 first; only use `make_surface`
> when a shape genuinely can't be lofted, swept, or revolved.

---

## Limits & gotchas

The kernel is exact B-rep, so organic work runs into a predictable set of walls:

- **No sculpting.** No subdivision surfaces, no mesh push/pull, no direct NURBS control-point
  editing. Compose from the moves above and round; if a shape truly needs free-surface sculpting,
  make it in a sculpt/SubD tool and import the STEP/mesh.
- **Loft section compatibility.** Sections blend cleanly when their outlines are consistently wound
  and their start points line up; a flipped or rotated section makes the loft twist or
  self-intersect. Stack centers, order along one axis, and add intermediate sketches to steer.
- **A true point/tip is non-manifold.** Lofting or sweeping to a `Vertex` (or a full `Sphere`,
  cookbook §1) leaves a singular point and reports `manifold: false` though `valid` is true. Loft
  to a small circle for a printable part.
- **Sweeps self-intersect on tight curvature.** If the path's radius of curvature is smaller than
  the profile, the tube folds through itself and the build fails or goes invalid. Shrink the
  profile, ease the path, or set `is_frenet=True`.
- **Fillets are the #1 failure on organic seams.** OCC builds a fillet by offsetting the adjacent
  surfaces; on a tight blend, a tiny face, or near-coincident geometry it throws `Standard_Failure`
  or yields an invalid solid (e.g. `ChFi3d_Builder: only 2 faces`). When a fillet fails: drop the
  radius, fillet fewer edges, or make the underlying blend smaller. A radius at or above the local
  feature size will not compute.
- **`make_surface` overshoots** with too few constraints and **multiplies faces** when thickened,
  which then chokes downstream booleans and fillets. Give it several surface points and keep
  curvature mild.

## Always verify

After building, call `get_model_info()` and confirm `valid` and `manifold` are `true` (or that a
non-manifold result is *intended*, per §2) and the bounding box matches intent. Organic shapes are
easy to get subtly wrong — a twisted loft, a self-intersected sweep, a ballooned surface — so also
`capture_views(["iso", "front"])` and actually look. If a build errors, read the traceback and see
the **solidifai-debugging** skill.

## Sources

- build123d operations — `loft`, `sweep`, `thicken`, `offset`:
  https://build123d.readthedocs.io/en/latest/operations.html
- build123d BuildLine curves — `Spline`, `Bezier`, `RadiusArc`:
  https://build123d.readthedocs.io/en/latest/build_line.html
- build123d direct API — `Face.make_surface`, `make_loft`, `sweep_multi`:
  https://build123d.readthedocs.io/en/latest/direct_api_reference.html
- OpenCASCADE modeling algorithms (the `BRepOffsetAPI` loft / pipe / fillet behind these verbs):
  https://dev.opencascade.org/doc/overview/html/
