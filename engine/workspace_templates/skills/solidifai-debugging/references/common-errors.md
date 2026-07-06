# Common solidifai build errors → cause → fix

Error signatures you'll see from `execute_script`, what causes them, and the corrected code. The
broken snippets are marked as illustrations; the **fixed** snippets are real, runnable models.

---

## "nothing to render: registry is empty"

**Cause:** the script never called `show(...)`, so there's nothing to put in the viewport.

```python
# doctest: +SKIP
# BROKEN: builds geometry but never shows it -> empty registry
from build123d import BuildPart, Box
with BuildPart() as p:
    Box(20, 20, 20)
# (no show())
```

**Fix:** always end by showing the part.

```python
from build123d import BuildPart, Box
from solidifai import show

with BuildPart() as p:
    Box(20, 20, 20)

show(p.part, name="Block")  # <- the fix
```

---

## `NameError` / `ImportError` for a build123d name

**Cause:** the symbol isn't imported (or is misspelled). build123d has no implicit globals.

```python
# doctest: +SKIP
# BROKEN: Cylinder and show were never imported
from build123d import BuildPart
with BuildPart() as p:
    Cylinder(radius=8, height=10)   # NameError: Cylinder
show(p.part, name="x")              # NameError: show
```

**Fix:** import every name you use, including `show`.

```python
from build123d import BuildPart, Cylinder
from solidifai import show

with BuildPart() as p:
    Cylinder(radius=8, height=10)

show(p.part, name="Pin")
```

---

## `chamfer()` got an unexpected keyword `radius`

**Cause:** `chamfer` takes `length=`, not `radius=`. (`fillet` takes `radius=`.)

```python
# doctest: +SKIP
chamfer(top.edges(), radius=2)   # TypeError: unexpected keyword 'radius'
```

**Fix:** use `length=` for chamfer, `radius=` for fillet.

```python
from build123d import BuildPart, Box, Axis, chamfer
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 20)
    top = p.faces().sort_by(Axis.Z)[-1]
    chamfer(top.edges(), length=2)   # <- length, not radius

show(p.part, name="Chamfered")
```

---

## Fillet/chamfer raises (OCP failure) or makes an invalid solid

**Cause:** the radius/length is too large for the edge (it would eat past a neighbouring face), or
the edge selection was empty/wrong.

```python
# doctest: +SKIP
# BROKEN: a 15 mm corner fillet on a 30 mm-wide plate has no room. A corner radius
# can't exceed half the shorter footprint dimension (here 30 / 2 = 15), so this
# raises "Failed creating a fillet with radius of 15, try a smaller value".
with BuildPart() as p:
    Box(40, 30, 6)
    fillet(p.edges().filter_by(Axis.Z), radius=15)
```

**Fix:** shrink the radius (well under the smallest adjacent dimension) and confirm the selection
isn't empty.

```python
from build123d import BuildPart, Box, Axis, fillet
from solidifai import show

with BuildPart() as p:
    Box(40, 30, 6)
    fillet(p.edges().filter_by(Axis.Z), radius=2)   # <- fits the geometry

show(p.part, name="RoundedPlate")
```

After it builds, call `get_model_info()` and confirm `valid` / `manifold` are `true`.

---

## Revolve fails or produces a self-intersecting solid

**Cause:** the profile crosses the rotation axis, or it isn't a single closed face. The profile
must lie on one side of the axis and be closed with `make_face()`.

```python
# doctest: +SKIP
# BROKEN: profile straddles x=0, so revolving about Z self-intersects
with BuildPart() as p:
    with BuildSketch(Plane.XZ):
        with BuildLine():
            Polyline((-5, 0), (15, 0), (15, 10), (-5, 10), close=True)  # crosses x=0
        make_face()
    revolve(axis=Axis.Z)
```

**Fix:** keep the whole profile on the +X side of the Z axis.

```python
from build123d import BuildPart, BuildSketch, BuildLine, Polyline, make_face, revolve, Plane, Axis
from solidifai import show

with BuildPart() as p:
    with BuildSketch(Plane.XZ):
        with BuildLine():
            Polyline((2, 0), (15, 0), (15, 10), (2, 10), close=True)   # all x >= 0
        make_face()
    revolve(axis=Axis.Z)

show(p.part, name="Turned")
```

---

## `offset`/shell builds an invalid solid (no real cavity)

**Cause:** the (negative) wall is too thick for the part, or the `openings` face is wrong, so the
inner cavity is degenerate. This often does not raise: the build returns, but `get_model_info()`
reports `valid: false` and the part has no real hollow. Treat a `valid: false` shell as a defect to
fix, the same as an outright failure.

```python
# doctest: +SKIP
# INVALID: 20 mm walls on a 40 mm-wide box leave no cavity. This builds, but
# get_model_info() reports valid: false (the walls eat the whole interior).
with BuildPart() as p:
    Box(60, 40, 30)
    top = p.faces().sort_by(Axis.Z)[-1]
    offset(amount=-20, openings=top)
```

**Fix:** use a realistic wall (a few mm) and the correct open face.

```python
from build123d import BuildPart, Box, Axis, Align, offset
from solidifai import show

with BuildPart() as p:
    Box(60, 40, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = p.faces().sort_by(Axis.Z)[-1]
    offset(amount=-2.4, openings=top)   # <- sensible wall

show(p.part, name="Case")
```

---

## Empty viewport but `ok: true`

**Cause 1:** you edited `model.py` as a file instead of using `execute_script`. A bare file edit
renders nothing — call `run_file("model.py")` to build it, or just use `execute_script`.

**Cause 2:** you `show()`-ed an empty/None object. Show the actual part: `show(p.part, name=...)`
from a `BuildPart`, or the result solid from the algebra API.

```python
from build123d import BuildPart, Box
from solidifai import show

with BuildPart() as p:
    Box(20, 20, 20)

show(p.part, name="Block")   # p.part, not p
```

---

## `cannot connect to engine`

**Cause:** the solidifai engine is still starting up (or restarting). This isn't a code error.
Wait for the status to settle and retry the same tool call.
