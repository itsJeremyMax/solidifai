# build123d cookbook (solidifai engine, build123d 0.10.0)

Patterns verified against the installed engine. Every fenced block below builds a valid, manifold
solid. Copy one, adapt the numbers, wrap it with `show(...)`, and run it via `execute_script`.

Conventions: build with the **builder API** (`with BuildPart() as p:`), result is `p.part`. Units
are mm. `from solidifai import show` and call `show(p.part, name="...")` — nothing renders
otherwise.

---

## 1. Primitives (3D)

`Box(length, width, height)`, `Cylinder(radius, height)`, `Sphere(radius)`,
`Cone(bottom_radius, top_radius, height)`. Each takes `align=` and `mode=`. Show separate bodies
with separate `show(...)` calls (one fused `BuildPart` of disjoint lumps would be non-manifold):

```python
from build123d import Box, Cylinder, Cone, Pos
from solidifai import show

show(Box(30, 20, 10), name="Box")
show(Pos(30, 0, 0) * Cylinder(radius=8, height=10), name="Cylinder")
show(Pos(60, 0, 0) * Cone(bottom_radius=8, top_radius=2, height=14), name="Cone")
```

> **Sphere quirk (build123d 0.10.0):** any solid with a full spherical surface — a bare
> `Sphere(r)`, or a boolean that leaves a sphere/spherical cavity intact (`Box - Sphere`,
> `Box + Sphere`) — reports `is_manifold == False` because of the sphere's polar seam, so
> `get_model_info()` shows `manifold: false` even though `valid` is `true`. For a clean manifold
> result, remove the seam region, e.g. intersect to a partial sphere (`Sphere(r) & Box(...)` for a
> dome). Avoid shipping a full bare sphere as a printable body.

### Aligning to the build plane

By default a primitive is centered on the origin. Use `align=` to seat it. To put the **bottom on
the XY plane** (z = 0), align `MIN` on Z:

```python
from build123d import BuildPart, Box, Align
from solidifai import show

with BuildPart() as p:
    Box(20, 20, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))  # bottom at z=0

show(p.part, name="OnPlane")
```

`Align` values: `CENTER`, `MIN`, `MAX`, `NONE`.

---

## 2. Sketch → extrude

Draw a 2D sketch in `BuildSketch`, then `extrude(amount=...)`. Sketch shapes:
`Rectangle(width, height)`, `RectangleRounded(width, height, radius)`, `Circle(radius)`,
`RegularPolygon(radius, side_count)`, `SlotOverall(width, height)`.

```python
from build123d import BuildPart, BuildSketch, RectangleRounded, extrude
from solidifai import show

with BuildPart() as p:
    with BuildSketch():
        RectangleRounded(60, 40, radius=8)
    extrude(amount=6)

show(p.part, name="Plate")
```

A regular hex prism and an overall slot:

```python
from build123d import BuildPart, BuildSketch, RegularPolygon, SlotOverall, Locations, extrude
from solidifai import show

with BuildPart() as p:
    with BuildSketch():
        RegularPolygon(radius=12, side_count=6)
    extrude(amount=10)
    with Locations((35, 0)):
        with BuildSketch():
            SlotOverall(width=30, height=12)
        extrude(amount=10)

show(p.part, name="HexAndSlot")
```

---

## 3. Revolve (lathe parts)

Draw a half-profile on a **vertical plane** entirely on one side of the rotation axis, then
`revolve(axis=Axis.Z)`. The axis must not cross the profile interior. Build the closed profile
with `BuildLine` + `Polyline` + `make_face`.

```python
from build123d import (
    BuildPart, BuildSketch, BuildLine, Polyline, make_face, revolve, Plane, Axis,
)
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XZ):
        with BuildLine():
            Polyline((0, 0), (15, 0), (15, 8), (10, 14), (0, 14), close=True)
        make_face()
    revolve(axis=Axis.Z)

show(p.part, name="Turned")
```

---

## 4. Loft (blend between sections)

`loft()` blends two or more sketches on parallel planes. Offset a plane with `Plane.XY.offset(d)`.

```python
from build123d import BuildPart, BuildSketch, Rectangle, Circle, Plane, loft
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XY):
        Rectangle(40, 40)
    with BuildSketch(Plane.XY.offset(30)):
        Circle(12)
    loft()

show(p.part, name="Lofted")
```

---

## 5. Sweep (profile along a path)

Draw a path with `BuildLine`, a cross-section sketch, then `sweep()`.

```python
from build123d import BuildPart, BuildLine, Polyline, BuildSketch, Circle, Plane, sweep
from solidifai import show

with BuildPart() as p:
    with BuildLine():
        Polyline((0, 0, 0), (0, 0, 40), (0, 30, 40))
    with BuildSketch(Plane.XY):
        Circle(4)
    sweep()

show(p.part, name="Swept")
```

---

## 6. Fillet & chamfer (with edge selection)

`fillet(edges, radius=...)` rounds; `chamfer(edges, length=...)` bevels. **`chamfer` uses
`length=`, not `radius=`.** The skill is selecting the right edges:

- `p.edges()` — all edges. `p.faces()` — all faces; a face has `.edges()`.
- `.filter_by(Axis.Z)` — keep edges parallel to an axis (e.g. the 4 vertical edges of a box).
- `.sort_by(Axis.Z)` — order by position along an axis; `[-1]` is highest, `[0]` lowest.
- `.group_by(Axis.Z)` — bucket by level; `[0]` is the lowest group, `[-1]` the highest.

Round the four vertical edges of a box:

```python
from build123d import BuildPart, Box, Axis, fillet
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 20)
    fillet(p.edges().filter_by(Axis.Z), radius=4)

show(p.part, name="RoundedSides")
```

Chamfer just the top face's outline:

```python
from build123d import BuildPart, Box, Axis, chamfer
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 20)
    top = p.faces().sort_by(Axis.Z)[-1]
    chamfer(top.edges(), length=2)

show(p.part, name="ChamferedTop")
```

Fillet only the bottom group of edges:

```python
from build123d import BuildPart, Box, Axis, fillet
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 20)
    fillet(p.edges().group_by(Axis.Z)[0], radius=3)

show(p.part, name="RoundedBottom")
```

---

## 7. Holes, counterbores, countersinks

Inside `BuildPart`, `Hole`/`CounterBoreHole`/`CounterSinkHole` cut from the current locations
(default `Mode.SUBTRACT`). With no `depth`, a `Hole` goes all the way through.

- `Hole(radius, depth=None)`
- `CounterBoreHole(radius, counter_bore_radius, counter_bore_depth, depth=None)`
- `CounterSinkHole(radius, counter_sink_radius, depth=None, counter_sink_angle=82)`

Place holes on the top face so they start at the surface:

```python
from build123d import BuildPart, Box, Axis, Locations, CounterBoreHole
from solidifai import show

with BuildPart() as p:
    Box(50, 50, 12)
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        CounterBoreHole(radius=2.5, counter_bore_radius=4.5, counter_bore_depth=3)

show(p.part, name="Counterbore")
```

---

## 8. Patterns: grid & polar (bolt circles)

- `GridLocations(x_spacing, y_spacing, x_count, y_count)` — a rectangular grid.
- `PolarLocations(radius, count)` — evenly around a circle (a bolt circle).
- `Locations(*points_or_faces)` — explicit spots, or seat a sub-pattern on a face.

Nest a grid inside a face's locations:

```python
from build123d import BuildPart, Box, Axis, Locations, GridLocations, Hole
from solidifai import show

with BuildPart() as p:
    Box(60, 60, 8)
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        with GridLocations(40, 40, 2, 2):
            Hole(radius=2.5)

show(p.part, name="GridHoles")
```

A 6-hole bolt circle on a disc:

```python
from build123d import BuildPart, Cylinder, Axis, Locations, PolarLocations, Hole
from solidifai import show

with BuildPart() as p:
    Cylinder(radius=30, height=8)
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        with PolarLocations(radius=22, count=6):
            Hole(radius=2)

show(p.part, name="BoltCircle")
```

---

## 9. Booleans (add / subtract)

Inside `BuildPart`, the default `mode=Mode.ADD` fuses; `mode=Mode.SUBTRACT` carves. Subtract a
cylinder from a box:

```python
from build123d import BuildPart, Box, Cylinder, Mode
from solidifai import show

with BuildPart() as p:
    Box(40, 40, 20)
    Cylinder(radius=8, height=40, mode=Mode.SUBTRACT)

show(p.part, name="Drilled")
```

The **algebra API** does the same with operators (`+`, `-`, `&`) and `Pos(...)` / `Rot(...)` to
place operands — handy for quick boolean math:

```python
from build123d import Box, Cylinder, Pos
from solidifai import show

part = Box(40, 40, 20) - Pos(0, 0, 0) * Cylinder(radius=8, height=40)

show(part, name="DrilledAlgebra")
```

---

## 10. Shell an enclosure (hollow with an open face)

There is no top-level `shell()` verb. Hollow a solid with `offset(amount=-wall, openings=face)` —
negative amount hollows; `openings` is the face(s) to leave open.

```python
from build123d import BuildPart, Box, Axis, Align, offset
from solidifai import show

with BuildPart() as p:
    Box(60, 40, 25, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    offset(amount=-2, openings=top)  # 2 mm walls, top open

show(p.part, name="Shell")
```

See `examples/enclosure.py` for a full case with a lid lip.

---

## 11. Threads & fasteners

The engine has `Helix` and `sweep` but **no thread classes** (`IsoThread`, `TrapezoidalThread`,
`AcmeThread`, …) and **no `bd_warehouse`/`cq_warehouse`**. For 3D-printed parts you usually
**don't model threads at all** — fine printed threads are weak and rarely print cleanly. Reach
for the manifold-clean fastener features below; use a modeled helical thread (F) only for a
cosmetic/visual or large-pitch case.

**Internal threads** on a printed part come from a heat-set insert (C), a captive nut (D), or
tapping a pilot hole (E) — not a modeled internal helix.

### A. Bolt / screw clearance hole

`Hole(radius=d/2)` cut from a face (through by default; pass `depth=` for blind). Common metric
clearance diameters (mm):

| Size | Close | Normal | Free |
|------|-------|--------|------|
| M3   | 3.2   | 3.4    | 3.6  |
| M4   | 4.3   | 4.5    | 4.8  |
| M5   | 5.3   | 5.5    | 5.8  |
| M6   | 6.4   | 6.6    | 7.0  |

```python
from build123d import BuildPart, Box, Axis, Align, Locations, Hole
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        Hole(radius=4.5 / 2)   # M4 normal-fit clearance

show(p.part, name="ClearanceHole")
```

### B. Counterbore for a socket-head cap screw

`CounterBoreHole` recesses the head flush (see also §7). Socket-head cap screw (DIN 912) head
diameters (mm): M3 5.5, M4 7.0, M5 8.5, M6 10.0; counterbore depth ≈ head height (roughly
0.7–1× nominal) plus a little.

```python
from build123d import BuildPart, Box, Axis, Align, Locations, CounterBoreHole
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        CounterBoreHole(radius=4.5 / 2, counter_bore_radius=7.0 / 2, counter_bore_depth=4.4)

show(p.part, name="Counterbore")
```

### C. Heat-set insert boss

The durable way to get threads in an FDM part: a boss with a blind hole sized for the insert.
The hole diameter is ≈ insert OD − 0.1–0.2 mm — **check the insert's datasheet**; typical
recommended holes (mm): M3 ~4.0, M4 ~5.6, M5 ~6.4, M6 ~8.1.

```python
from build123d import BuildPart, Box, Cylinder, Axis, Align, Locations, Hole
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 4, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        Cylinder(radius=5.0, height=8, align=(Align.CENTER, Align.CENTER, Align.MIN))  # boss
    seat = p.faces().sort_by(Axis.Z)[-1]
    with Locations(seat):
        Hole(radius=5.6 / 2, depth=7)   # M4 heat-set insert seat (blind)

show(p.part, name="InsertBoss")
```

### D. Captive hex-nut pocket

A hex pocket holds a standard nut while a bolt clears through to it. Build the hex with
`RegularPolygon(radius=AF/2, side_count=6, major_radius=False)` — with `major_radius=False`,
`radius` is the across-flats half-width — then `extrude(..., mode=Mode.SUBTRACT)`. Hex-nut
across-flats (mm): M3 5.5, M4 7.0, M5 8.0, M6 10.0; add ~0.2–0.4 mm clearance and make the
pocket ≈ nut thickness deep.

```python
from build123d import (
    BuildPart, Box, BuildSketch, RegularPolygon, Axis, Align, Locations, Hole, extrude, Mode,
)
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))
    side = p.faces().sort_by(Axis.Y)[0]
    with BuildSketch(side):
        RegularPolygon(radius=(7.0 + 0.3) / 2, side_count=6, major_radius=False)  # M4 nut + clr
    extrude(amount=-4, mode=Mode.SUBTRACT)
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        Hole(radius=4.5 / 2)   # bolt clearance through

show(p.part, name="CaptiveNutPocket")
```

### E. Tapped-hole pilot

If you'll cut threads with a tap, leave a blind hole at the tap-drill diameter. Coarse-pitch
tap drills (mm): M3 (0.5) → 2.5, M4 (0.7) → 3.3, M5 (0.8) → 4.2, M6 (1.0) → 5.0.

```python
from build123d import BuildPart, Box, Axis, Align, Locations, Hole
from solidifai import show

with BuildPart() as p:
    Box(30, 30, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    with Locations(top):
        Hole(radius=3.3 / 2, depth=10)   # M4 coarse tap-drill (3.3 mm)

show(p.part, name="TappedPilot")
```

### F. Modeled helical thread (cosmetic / visual)

A thread profile swept along a `Helix`. The tooth bites into the core so the thread fuses into
one solid, and an intersect-clip squares the ends.

> **⚠ Manifold caveat (build123d 0.10.0):** this builds a **valid** solid but reports
> `manifold: false`. A swept-helix thread can't be capped cleanly at its run-out without an
> `end_finishes` helper (the engine has no `IsoThread`/`bd_warehouse`), so free edges remain at
> the ends — much like the `Sphere` polar-seam note in §1. Use a modeled thread for
> **visualization, large-pitch features (jar lids, bottle caps, lead screws), or STEP hand-off
> to other CAD** — *not* for a functional FDM fastener. For printed threads use a heat-set
> insert (C), a captive nut (D), or a tapped-hole pilot (E).

```python
# doctest: +NONMANIFOLD
from build123d import (
    BuildPart, Cylinder, BuildLine, Helix, BuildSketch, Polyline, make_face,
    Plane, Align, Mode, sweep,
)
from solidifai import show

pitch, length, major_dia = 3.0, 18.0, 18.0   # mm — coarse pitch for a visible thread
maj_r = major_dia / 2
depth = 0.61 * pitch          # thread height
core_r = maj_r - depth        # minor radius
bite, extra = 1.0, pitch      # tooth overlap into core; helix overrun past each end

with BuildPart() as p:
    Cylinder(core_r, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with BuildLine() as path:
        Helix(pitch=pitch, height=length + 2 * extra, radius=core_r)
    profile_plane = Plane(origin=path.line @ 0, z_dir=path.line % 0)
    with BuildSketch(profile_plane):
        with BuildLine():
            Polyline((-bite, -pitch / 2), (depth, 0.0), (-bite, pitch / 2), close=True)
        make_face()
    sweep(path=path.line, is_frenet=True)
    # square the ends; this leaves the thread valid but non-manifold (see caveat above)
    Cylinder(maj_r, length, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.INTERSECT)

show(p.part, name="CosmeticThread")
```

---

## 12. Planes & axes reference

- **Planes**: `Plane.XY` (default), `Plane.XZ`, `Plane.YZ`; `Plane.XY.offset(d)` shifts along the
  normal; you can also pass a face to `BuildSketch(face)` to sketch on it.
- **Axes**: `Axis.X`, `Axis.Y`, `Axis.Z` — used for `revolve(axis=...)`, `filter_by`, `sort_by`,
  `group_by`.

---

## Always verify

After building, call `get_model_info()` and confirm `valid` and `manifold` are `true` and the
bounding box matches intent. If a build errors, read the traceback and see the
**solidifai-debugging** skill.
