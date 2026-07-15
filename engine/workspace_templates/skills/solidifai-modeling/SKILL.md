---
name: solidifai-modeling
description: Build, model, modify, resize, or export the geometry of any physical part in this solidifai CAD workspace, such as mounts, brackets, enclosures/cases, adapters, fixtures, knobs, gears, plates, flanges, mechanical parts. Use whenever the user asks to make, build, change, parametrize, or export a 3D model. Covers building geometry, parametric sliders, edge selection, holes/bolt circles, shelling enclosures, multi-part assemblies, and exporting STEP/STL/glTF/BREP/3MF through the solidifai-cad MCP server so it renders live in the app's 3D viewport. (Design judgment on a human-facing part, ergonomics, control placement, printability, proportion, is solidifai-product-design.)
license: MIT
---

# solidifai modeling

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

This skill is the single-part build loop: write Python, run it through the `solidifai-cad`
MCP server, and whatever you `show()` appears in the viewport in real time. Units are
**millimetres**. **solidifai-product-design** owns what makes a human-facing part good; this
skill owns how to build it. build123d is your internal toolkit; never name it to the user
(AGENTS.md carries the Sol voice).

## When to use

- The user asks to make, build, change, parametrize, resize, or export any physical part: a
  mount, bracket, enclosure, knob, gear, plate, flange, fixture.
- **Skip when:** the design is genuinely several independently-authored parts that share
  dimensions; that is **solidifai-assemblies**. Do not skeleton-wrap a lone part or a coupled
  body.

## The procedure

1. **State a stream-tier build brief** (AGENTS.md "State the build brief"): what it is, the
   few functional dims (the PARAMS you'll define), and the process/material from the profile;
   record it with `propose_build`. A fully-specified or pure-geometry part skips this. Ground a mechanism,
   multi-part product, or image reproduction first (**solidifai-grounding**); bring in
   **solidifai-product-design** when a person holds, wears, operates, or sees the part and
   design is open. Apply AGENTS.md's risk matrix before committing an unknown that affects fit,
   interface, load, motion, material, safety, or compliance.
2. **Build.** Call `execute_script`; it rebuilds the model, updates the viewport, and
   auto-saves your code to `model.py`. Before picking dimensions, read
   `get_manufacturing_profile()` and use it for wall, fillet/edge-break, min feature, and mating
   clearance, never a guess; don't copy the examples' literal numbers when the profile says
   otherwise.
3. **Verify.** Call `get_model_info()` and check bounding box / volume / `valid` / `manifold`
   before telling the user it's done. Then actually look: `capture_views(["iso"])` (or
   `layout="grid"` for several angles); how to read them is in **solidifai-self-verify** "What
   to look for in the views".
4. **Iterate.** For a parametric model, tweak with `set_params({"size": 30})` instead of
   resending the whole script; retarget a named feature with `set_feature`. To **delete a
   feature or reorder operations**, edit the script (remove or move that block) and re-run
   `execute_script`: the script is the feature tree, so editing it is the delete/reorder
   operation. Otherwise send a new `execute_script`.

### Rules

- Every script: `from solidifai import show`, build geometry, then `show(part, name="...")`.
  **Nothing renders unless you `show()` it.** Drive the engine only through the
  `solidifai-cad` MCP tools (the full rule is in AGENTS.md).
- Optional `show(part, name=..., material="steel", color=(r,g,b))` sets the viewport finish +
  density; `color` (0..1 linear) overrides the base color only. The default comes from the
  workspace: call `list_materials` for the available names and the default, and name a
  specific material only when the user asks for one.
- **Don't hand-edit `model.py`**; `execute_script` saves it for you (an edited file needs
  `run_file("model.py")` to take effect).
- Prefer the **builder API** (`with BuildPart() as p: ...`, `show(p.part, ...)`).
- A named real-world object (board, cell, connector) gets its dims from
  `lookup_reference` or the grounding hard rule, never from memory.

### Minimal model

```python
from build123d import BuildPart, Box, Hole
from solidifai import show

with BuildPart() as p:
    Box(20, 20, 20)
    Hole(radius=2.5)  # 5 mm-diameter through-hole

show(p.part, name="Block")
```

### Parametric model (exposes UI sliders)

Define a module-level `PARAMS = {name: {value, min, max, step, unit, desc?}}` and a
`def build(**params)` that calls `show(...)`. The app renders a slider per numeric parameter
(with `desc` as a one-line subtitle); tweak with `set_params({...})`. End the script by
calling `build(...)` with the defaults so it renders on load.

```python
from build123d import BuildPart, Box, Hole
from solidifai import show

PARAMS = {
    "size":     {"value": 20.0, "min": 5.0, "max": 100.0, "step": 1.0, "unit": "mm", "desc": "Cube edge"},
    "hole_dia": {"value": 5.0,  "min": 1.0, "max": 20.0,  "step": 0.5, "unit": "mm", "desc": "Through hole"},
}

def build(size, hole_dia):
    with BuildPart() as p:
        Box(size, size, size)
        Hole(radius=hole_dia / 2)
    show(p.part, name="Block")

if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

### Naming & describing parameters

Each parameter appears in the Inspector as a slider labelled by its key, with `desc` beneath
it; make both pull their weight:

- **Names (the keys)** become the slider label (title-cased: `bore_dia` to "Bore Dia") and the
  `build()` arguments, so they must be `snake_case` and distinct: `bore_dia` and
  `mount_hole_dia`, not `dia1`/`dia2`.
- **Descriptions** (`"desc"`, optional) are a few plain words for what the parameter controls;
  sentence-case, no trailing period. Omit `desc` when the name already says it.

| key | desc | verdict |
|-----|------|---------|
| `corner_r` | `"Corner radius parameter"` | ✗ cryptic key; desc just restates it |
| `corner_radius` | `"Edge rounding"` | ✓ clear key; desc adds the intent |
| `length` | (none) | ✓ self-explanatory; no desc needed |

### Make features targetable

Wrap an operation in `with feature("name", driven_by="param"):` to give it a stable name bound
to its driving parameter, so you can retarget it later without re-sending the script.

```python
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

PARAMS = {"bore_dia": {"value": 12.0, "min": 4.0, "max": 30.0, "step": 1.0, "unit": "mm"}}

def build(bore_dia):
    with BuildPart() as p:
        Box(40, 40, 12)
        with feature("center_bore", driven_by="bore_dia"):
            with Locations((0, 0)):
                Hole(radius=bore_dia / 2)
    show(p.part, name="Plate")

if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

`feature()` only records metadata; it never changes geometry. To change a named feature, call
`set_feature("center_bore", {"bore_dia": 20})` (the keys are its `driven_by` params); it
rebuilds like `set_params`.

`inspect_features()` lists every targetable feature; `feature_at((x, y, z))` goes the other way,
resolving a point in model space (mm, Z-up) to the feature there so you can retarget a spot
picked in the viewport.

### Standard hardware: ask, don't recall

Dims for screws, inserts, nuts, and bearings live in the engine; never type a remembered
number. In scripts, `std` returns plain mm values (resolving the profile's fit) and `hardware`
builds the matching geometry; from chat, `lookup_standard` / `lookup_reference` answer the same.

```python
from build123d import Box, Cylinder, Pos
from solidifai import show, std

dia = std.clearance_hole("M3")  # ISO 273 diameter, resolved via the profile fit
boss = std.insert("M3")["hole_dia"]  # heat-set insert install hole
plate = Box(30, 20, 5) - Cylinder(dia / 2, 20) - Pos(10, 0, 0) * Cylinder(boss / 2, 20)
show(plate, name="plate")
```

Coverage is M2 to M8 (heat-set inserts only M2 to M5).

Threads default to **fit-diameter cylinders** (a clearance or tap-drill hole), the right call for
FDM; for a real joint use a heat-set insert, captive nut, or tapped pilot. When the thread itself
is the deliverable (a threaded rod, printed nut, jar lid), `hardware.external_thread(size,
length)` / `hardware.internal_thread_cutter(size, depth)` build a real ISO helical thread (coarse
pitch from `std.thread_pitch`); they are heavy geometry, so use them only then. Cookbook §11
carries all of these.

### Bevels and screw holes that don't fight you

Thin geometry breaks two ops (fixes in cookbook §6 and §7). A fillet/chamfer over ~half the local
wall fails the build, so use `safe_fillet` / `safe_chamfer` (from `solidifai`), which clamp to
what fits. And `Hole()` is fragile on thin walls/ledges, so subtract a cutter for placed holes:
`part - Pos(x, y, 0) * hardware.clearance_hole("M3", depth)`.

### Multi-part models

Model each genuinely separate part (a lid and base, a bolt and nut) as its own `show()` object
so it keeps its color/material and stays inspectable. This one-script pattern fits a few parts
authored together; independently authored parts sharing a skeleton are **solidifai-assemblies**.

**Name and color each part** so the assembly is legible in the viewport and in `capture_views`:

```python
# doctest: +SKIP  (fragment: base/lid not defined; see the runnable example below)
show(base, name="Base", material="abs")
show(lid,  name="Lid",  material="abs", color=(0.2, 0.4, 0.9))
```

Exploded view is a built-in viewport control; don't add an `explode` parameter. To review the
fit yourself, capture `capture_views(["iso", "front"], explode=70)` (render-only; it never
changes the saved model).

**Mating parts need a real clearance gap** so they aren't coincident or interfering. Use the
workspace fit clearance from `get_manufacturing_profile()` (the `fits` value for the selected
`design.fit`); fall back to the manufacturability reference's per-process clearance only when
the profile doesn't apply. Confirm the built gap: `measure_between` the two mating features
(`query_faces` gives face ids to aim at) and check the number against that clearance instead of
eyeballing; `thickness_at([x,y,z])` checks a local wall against the profile min-wall.

In an assembly, when two parts must agree on a shape rather than a number, the skeleton
publishes it with `s.profile(...)`; see **solidifai-assemblies**.

### Reference volumes (inside-out packaging)

For a containment object (a cyberdeck, mini-PC, battery pack, or any device whose shape is
driven by what goes inside it), place each internal component as a **reference volume**
before deriving the shell: a plain box at the component's layout position, shown with
`role="reference"`, a distinct `color=`, and a `name=` starting with `"ref: "`.

```python
# doctest: +SKIP
with BuildPart() as sbc:
    with Locations((sbc_x, 0, floor + sbc_h / 2)):
        Box(sbc_l, sbc_w, sbc_h)
show(sbc.part, name="ref: SBC", color=(0.20, 0.55, 0.95), role="reference")
```

`role="reference"` marks a body as context, not printed geometry: the engine ghosts it and
**excludes it from `export(...)` and the manufacturing checks (DFM, mass, stress, min-wall)
automatically**, so you never strip components out before exporting. It stays a real solid
`check_interferences()` counts, so layout defects (a collision, a wall breakout) surface as
overlaps for self-verify. A `show_internals` PARAM (a 0/1 toggle gating the reference `show()`
calls) declutters the viewport. The shell derives from the packed envelope plus clearance plus
wall, so it tracks its contents.

See `examples/packaging-layout.py` for the full pattern; the design judgment (packing, ports,
thermal) is the **integrated-device** playbook and **internal-layout** lens in
`solidifai-product-design`.

## Anti-patterns

- Treating a functional, safety, or compliance unknown as a low-risk assumption instead of
  asking the focused question required by AGENTS.md.
- Fragmenting one monolithic part into fake pieces, or fusing parts that are meant to come
  apart.
- Hand-editing `model.py` and expecting the viewport to change without `run_file`.
- Copying an example's literal dimensions when the manufacturing profile says otherwise.

## Cross-references

- **solidifai-product-design** - what makes a part good (ergonomics, control placement,
  printability, proportion); this skill is how to build, that one is what to design.
- **solidifai-grounding** - understand a mechanism, assembly, or image before building it.
- **solidifai-self-verify** - confirm it's right before saying it's done.
- **solidifai-debugging** - when a build fails or nothing shows.
- **solidifai-assemblies** - skeleton + parts authoring for genuinely multi-part designs.
- **`references/build123d-cookbook.md`** - the API patterns: primitives, sketch
  extrude/revolve/loft/sweep, fillet/chamfer with edge selection, holes/counterbores, bolt
  circles, booleans, shells, transforms, split/draft/text, and threads/fasteners. Read it for
  a forgotten API.
- **`references/organic-forms.md`** - curved, flowing, hand-friendly shapes: lofting,
  sweeping along splines, revolved silhouettes, fillet-blending, freeform
  `make_surface` + thicken, and where the B-rep kernel fights back. For vases, grips, and
  doubly-curved shells.
- **`references/workflow.md`** - the MCP tools in detail, the iterate loop, exporting, and
  why you don't hand-edit `model.py`.
- **`examples/`** - complete, runnable parametric models to copy and adapt:
  - `bracket.py` - rounded plate, chamfered edge, central bore, corner holes (the default).
  - `enclosure.py` - box hollowed with a shell + a lid lip.
  - `flanged-mount.py` - flange + boss + bore + bolt circle.
  - `parametric-knob.py` - a revolved profile with flutes and a filleted rim.
  - `exploded-enclosure.py` - a two-part base + drop-in lid (the Explode slider spreads them).
  - `packaging-layout.py` - inside-out packaging: reference volumes gated by `show_internals`,
    shell from the packed envelope.
  - `spline-vase.py` - a spline silhouette revolved + shelled into a vessel.
  - `lofted-grip.py` - oval sections lofted into a waisted grip.
