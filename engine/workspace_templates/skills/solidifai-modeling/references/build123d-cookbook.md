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

### Thin walls: bevels that clamp instead of failing

A fillet or chamfer bigger than **~half the local wall width** is impossible: the kernel
rejects it and the whole build fails with `Failed creating a fillet/chamfer, try a smaller
value`. On a thin part (a 3 mm wall, a 2 mm rim) most "bevel the edges" sizes fail. Two rules:

- **Size the bevel under the wall.** Keep `radius`/`length` below half the thinnest wall the
  edge touches: a 3 mm wall takes at most ~1.4 mm, not 2 mm. Read the wall from
  `get_manufacturing_profile()` (the edge-break value is a good default) instead of guessing big.
- **Use the self-clamping helpers.** `safe_fillet` / `safe_chamfer` (from `solidifai`) apply the
  largest size that fits, up to what you asked for, and never fail the build on a too-large
  value. Drop-in for `fillet`/`chamfer` (same first two args, same builder behavior). Reach for
  them on thin or unfamiliar geometry so a bevel never costs you a rebuild.

```python
from build123d import BuildPart, Box, Axis, Align, Locations
from solidifai import show, safe_chamfer

with BuildPart() as p:
    Box(90, 81, 3, align=(Align.CENTER, Align.CENTER, Align.MIN))     # 3 mm floor
    with Locations((-43.5, 0, 0), (43.5, 0, 0)):
        Box(3, 81, 23, align=(Align.CENTER, Align.CENTER, Align.MIN))  # 3 mm walls
    safe_chamfer(p.edges().group_by(Axis.Z)[-1], 2.0)  # asks 2 mm, clamps to what the wall takes

show(p.part, name="ChanneledRim")
```

If even `min_radius`/`min_length` will not fit, the helper leaves the edge un-beveled rather
than failing, so the part still builds. When it clamps, say so plainly ("beveled the rim as far
as the 3 mm wall allows"); don't retry with random smaller numbers.

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

### Robust screw holes: subtract a cutter at an explicit position

`Hole()` drills into the face under the **current `Locations`**. That is clean on one flat
plate, but it is fragile when the face you land on does not cleanly span the hole (a thin wall,
a narrow ledge, a spot near an edge or the open end of a channel): the cut can no-op or fail, so
holes look like they "won't go in symmetrically" or "cap out at two of four." When you know
where a hole goes in model space, the reliable way is to **subtract a cylinder cutter at that
exact position** — placement is independent of face selection, so a symmetric layout stays
symmetric every time:

```python
from build123d import BuildPart, Box, Align, Locations, Pos
from solidifai import show, hardware

W, D, t = 90.0, 81.0, 3.0
with BuildPart() as bp:
    Box(W, D, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((-W/2 + t/2, 0, 0), (W/2 - t/2, 0, 0)):
        Box(t, D, 23, align=(Align.CENTER, Align.CENTER, Align.MIN))

part = bp.part
xs, ys = W/2 - 8, D/2 - 8
for (px, py) in ((xs, ys), (-xs, ys), (xs, -ys), (-xs, -ys)):
    part = part - Pos(px, py, 0) * hardware.clearance_hole("M3", t * 2)  # ISO clearance, profile fit

show(part, name="bracket")   # four symmetric mounting holes, valid + manifold
```

`hardware.clearance_hole(size, depth)` returns a cylinder at the exact ISO 273 clearance
diameter (resolved through the manufacturing profile's fit), so you never type a drill number.
`hardware.counterbore` and `hardware.tap_hole` are the counterbore and threaded-pilot cutters.
Rotate a cutter (`Rot(0, 90, 0) * ...`) to bore sideways through a wall. Keep a hole at least
one radius clear of any edge so it does not open a sliver.

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
for the manifold-clean fastener features below. When the thread itself is the point (a threaded
rod, a printed nut, a jar lid), `hardware.external_thread` / `hardware.internal_thread_cutter`
build a real ISO 60-degree helical thread for you (F); they are heavy geometry, so use them only
then.

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

### F. Real modeled ISO thread

When the thread itself is the deliverable, `hardware.external_thread(size, length)` and
`hardware.internal_thread_cutter(size, depth)` build a real ISO 68-1 60-degree helical thread at
the coarse pitch for M2..M8: a **valid, manifold, single solid** (a swept V-groove, not a fused
rib), with a lead-in chamfer on both ends by default so a screw starts into a nut. They are heavy
geometry (about a second to build), so prefer a plain cylinder at the fit diameter for a normal
FDM fastener; FDM only resolves threads from about M6 up. The external thread screws into the
internal cutter's hole with a normal running clearance.

```python
from build123d import Box, Pos
from solidifai import hardware, show

# External: a real ISO M6 threaded rod (60-degree profile, coarse 1.0 mm pitch).
rod = hardware.external_thread("M6", 12)
show(rod, name="ThreadedRod")

# Internal: subtract the cutter from a blind hole to leave a printable threaded boss/nut.
block = Box(16, 16, 6)
nut = block - Pos(0, 0, -3) * hardware.internal_thread_cutter("M6", 6)
show(Pos(24, 0, 0) * nut, name="ThreadedBoss")
```

---

## 12. Planes & axes reference

- **Planes**: `Plane.XY` (default), `Plane.XZ`, `Plane.YZ`; `Plane.XY.offset(d)` shifts along the
  normal; you can also pass a face to `BuildSketch(face)` to sketch on it.
- **Axes**: `Axis.X`, `Axis.Y`, `Axis.Z` — used for `revolve(axis=...)`, `filter_by`, `sort_by`,
  `group_by`.

---

## 13. Transforms & duplication (move, copy, mirror, scale)

Reposition, copy, mirror, or scale a solid you already built. In the algebra API a `Location`
(`Pos(...)`, `Rot(...)`) placed to the left of a shape returns a **placed copy** without touching
the original; `.moved(Location(...))` does the same from a shape.

```python
from build123d import Box, Pos, Rot, Location
from solidifai import show

base = Box(30, 20, 10)
show(base, name="Base")
show(Pos(50, 0, 0) * base, name="Shifted")                 # translate
show(Rot(0, 0, 45) * Pos(0, 50, 0) * base, name="Turned")  # rotate, then place
show(base.moved(Location((0, 0, 30))), name="Stacked")     # place by a Location
```

**Duplicate an instance** with `copy.copy` and place each copy independently. For a repeated
pattern fused into one body, use `GridLocations`/`PolarLocations` inside `BuildPart` (§8);
`copy.copy` + `Pos` gives separate instances you `show()` on their own.

```python
import copy
from build123d import Box, Pos
from solidifai import show

unit = Box(20, 20, 20)
show(unit, name="Original")
show(Pos(30, 0, 0) * copy.copy(unit), name="Clone")   # an independent duplicate
```

**Mirror a whole solid** with `mirror(part, about=Plane.YZ)` — the clean way to make a left-hand
variant from a right-hand part. `Plane.YZ`/`Plane.XZ`/`Plane.XY` pick the mirror plane.

```python
from build123d import BuildPart, Box, Cylinder, Align, Locations, mirror, Plane, Pos
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 10, align=(Align.MIN, Align.CENTER, Align.MIN))
    with Locations((30, 0, 10)):
        Cylinder(5, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))
right = p.part
show(right, name="RightHand")
show(Pos(0, 50, 0) * mirror(right, about=Plane.YZ), name="LeftHand")  # left-hand variant
```

**Scale** uniformly with `scale(part, f)` or per-axis with `scale(part, (sx, sy, sz))`.

```python
from build123d import Box, Pos, scale
from solidifai import show

base = Box(20, 20, 20)
show(base, name="Base")
show(Pos(40, 0, 0) * scale(base, 1.5), name="Bigger")           # 1.5x uniform
show(Pos(0, 40, 0) * scale(base, (2, 1, 1)), name="Stretched")  # 2x in X only
```

Scale is for a one-off "make it 1.5x taller" — **when a dimension is parametric, change its PARAM
with `set_params` instead.** Scale warps everything uniformly, so a scaled fastener hole or fillet
no longer matches a standard; a driven parameter resizes just what you meant.

---

## 14. Split, draft, and text

**Split** cuts a solid with a plane and keeps one side — halve a part for printing, or section a
body. `Keep.TOP`/`Keep.BOTTOM` pick the side, `Keep.BOTH` returns both; `bisect_by` takes any plane
(`Plane.XY.offset(d)` cuts off-center).

```python
from build123d import BuildPart, Box, split, Plane, Keep
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 20)
    split(bisect_by=Plane.XY, keep=Keep.TOP)   # keep the top half

show(p.part, name="TopHalf")
```

**Draft** tapers faces by an angle from a neutral plane — the pull taper a molded or cast part
needs. `filter_by(Axis.Z, reverse=True)` selects the vertical side faces; `neutral_plane` is the
face that keeps its size (here the base at z=0); `angle` is the draft in degrees. FDM prints don't
need draft, so reach for it only for a molding/casting hand-off.

```python
from build123d import BuildPart, Box, Align, Axis, Plane, draft
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    draft(p.faces().filter_by(Axis.Z, reverse=True), neutral_plane=Plane.XY, angle=5)

show(p.part, name="Drafted")
```

**Text** embosses or engraves lettering: sketch `Text` on a face, then `extrude` out (raised) or in
(recessed). Keep the raised/recessed depth ~1 mm or more so it survives the nozzle; `Text` also
takes `font=`, `font_style=`, and `rotation=` (run text along a side face).

```python
# raised lettering
from build123d import BuildPart, Box, BuildSketch, Text, Axis, Align, extrude
from solidifai import show

with BuildPart() as p:
    Box(60, 20, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    with BuildSketch(top):
        Text("SOL", font_size=10)
    extrude(amount=1.5)   # raised 1.5 mm above the face

show(p.part, name="Embossed")
```

```python
# recessed lettering
from build123d import BuildPart, Box, BuildSketch, Text, Axis, Align, extrude, Mode
from solidifai import show

with BuildPart() as p:
    Box(60, 20, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    with BuildSketch(top):
        Text("SOL", font_size=10)
    extrude(amount=-1.5, mode=Mode.SUBTRACT)   # engraved 1.5 mm into the face

show(p.part, name="Engraved")
```

---

## Always verify

After building, call `get_model_info()` and confirm `valid` and `manifold` are `true` and the
bounding box matches intent. If a build errors, read the traceback and see the
**solidifai-debugging** skill.
