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
   few functional dims (the PARAMS you are about to define), and the process/material from the
   profile. A fully-specified or pure-geometry part skips even this. Ground a mechanism,
   multi-part product, or image reproduction first (**solidifai-grounding**); bring in
   **solidifai-product-design** when a person holds, wears, operates, or sees the part and
   design is open; neither is stalling (AGENTS.md "model it now").
2. **Build.** Call `execute_script`; it rebuilds the model, updates the viewport, and
   auto-saves your code to `model.py`. Before you pick dimensions, read
   `get_manufacturing_profile()` and use it for wall thickness, fillet/edge-break, minimum
   feature size, and mating clearance; never a guess, and don't copy the literal numbers from
   the examples below when the profile says otherwise.
3. **Verify.** Call `get_model_info()` and check bounding box / volume / `valid` / `manifold`
   before telling the user it's done. Then actually look: `capture_views(["iso"])` (or
   `layout="grid"` for several angles in one image); how to read the images is in
   **solidifai-self-verify** "What to look for in the views".
4. **Iterate.** For a parametric model, tweak with `set_params({"size": 30})` instead of
   resending the whole script. Otherwise send a new `execute_script`.

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

- **Names (the keys)** become the slider label (title-cased: `bore_dia` becomes "Bore Dia")
  and are the `build()` argument names, so they must be `snake_case` identifiers. Keep them
  clear and distinct: prefer `corner_radius` over `corner_r`; with both a central bore and
  mounting holes, `bore_dia` and `mount_hole_dia`, not `dia1`/`dia2` or a bare `hole_dia`.
- **Descriptions** (`"desc"`, optional) are a few plain words (~1-4) saying what the
  parameter controls or where it is; sentence-case, no trailing period. Don't restate the
  name; omit `desc` when the name already says everything.

| key | desc | verdict |
|-----|------|---------|
| `corner_r` | `"Corner radius parameter"` | ✗ cryptic key; desc just restates it |
| `corner_radius` | `"Edge rounding"` | ✓ clear key; desc adds the intent |
| `bore_dia` | `"Center hole"` | ✓ |
| `length` | (none) | ✓ self-explanatory; no desc needed |

### Make features targetable

Wrap an operation in `with feature("name", driven_by="param"):` to give it a stable name
bound to its driving parameter. `inspect_features()` then lists every named feature and which
parameter changes it, so you can retarget it with `set_params` without re-sending the script.

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

### Standard hardware: ask, don't recall

Dims for screws, inserts, nuts, and bearings live in the engine; never type a
remembered number. In scripts, `std` returns plain mm values and resolves the
profile's fit for you; `hardware` builds the matching geometry. From chat, the
`lookup_standard` / `lookup_reference` tools answer the same questions.

```python
from build123d import Box, Cylinder, Pos
from solidifai import show, std

dia = std.clearance_hole("M3")  # ISO 273 diameter, resolved via the profile fit
boss = std.insert("M3")["hole_dia"]  # heat-set insert install hole
plate = Box(30, 20, 5) - Cylinder(dia / 2, 20) - Pos(10, 0, 0) * Cylinder(boss / 2, 20)
show(plate, name="plate")
```

Coverage is M2 to M8 (heat-set inserts only M2 to M5).

### Bevels and screw holes that don't fight you

Thin geometry breaks two ops (fixes in cookbook §6 and §7). A fillet/chamfer over ~half the local
wall fails the build, so use `safe_fillet` / `safe_chamfer` (from `solidifai`), which clamp to
what fits. And `Hole()` is fragile on thin walls/ledges (holes "cap out" or lose symmetry), so
subtract a cutter for placed holes: `part - Pos(x, y, 0) * hardware.clearance_hole("M3", depth)`.

### Multi-part models

Model each genuinely separate part (a lid and a base, a bolt and a nut, a gear on a shaft) as
its own `show()` object so it keeps its color/material and stays individually inspectable.
This one-script pattern fits a few parts you author together; independently authored parts
sharing a skeleton are **solidifai-assemblies**.

**Name and color each part** so the assembly is legible in the viewport and in `capture_views`:

```python
# doctest: +SKIP  (fragment: base/lid not defined; see the runnable example below)
show(base, name="Base", material="abs")
show(lid,  name="Lid",  material="abs", color=(0.2, 0.4, 0.9))
```

Exploded view is a built-in viewport control for multi-part models; do not add an `explode`
parameter. To review the fit yourself, capture an exploded render with
`capture_views(["iso", "front"], explode=70)` (render-only; it never changes the saved model).

**Mating parts need a real clearance gap** so they aren't coincident or interfering. Use the
workspace's fit clearance from `get_manufacturing_profile()` (the `fits` value for the
selected `design.fit`); fall back to the per-process clearance in the manufacturability
reference only when the profile doesn't apply.

In an assembly (not a single `execute_script`), when two parts must agree on a shape rather
than a number, the skeleton publishes it with `s.profile(...)`; see **solidifai-assemblies**.

### Reference volumes (inside-out packaging)

For a containment object (a cyberdeck, mini-PC, battery pack, or any device whose shape is
driven by what goes inside it), place each internal component as a **reference volume**
before deriving the shell: a plain box at the component's layout position, shown with
`role="reference"`, a distinct `color=`, and a `name=` starting with `"ref: "`.

`role="reference"` marks a body as context rather than printed geometry, and the engine acts
on it for you: a reference body is ghosted in the viewport, is **excluded from `export(...)`
and from the manufacturing checks (DFM, mass, stress, min-wall) automatically**, and is still
counted by `check_interferences()`. You never strip components out before exporting; they
cannot enter the output file.

```python
# doctest: +SKIP
with BuildPart() as sbc:
    with Locations((sbc_x, 0, floor + sbc_h / 2)):
        Box(sbc_l, sbc_w, sbc_h)
show(sbc.part, name="ref: SBC", color=(0.20, 0.55, 0.95), role="reference")
```

Reference bodies are real solids `check_interferences()` still sees, so layout defects
(components colliding, a component poking through a wall) show up as overlaps and self-verify
can confirm every component is seated with clearance. A `show_internals` PARAM (a 0/1 toggle
gating the reference `show()` calls) is an optional viewport-decluttering convenience, not
needed for a clean export. The shell size derives from the packed component envelope plus
clearance plus wall, so the enclosure tracks the contents.

See the runnable example `examples/packaging-layout.py` for the full pattern. For the design
judgment (packing arrangement, port placement, thermal decisions), see the
**integrated-device** playbook and the **internal-layout** lens in `solidifai-product-design`.

## Anti-patterns

- Describing a part in prose, or stalling on questions, instead of building it with stated
  assumptions.
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
- **`references/build123d-cookbook.md`** - the API patterns: primitives, sketches +
  extrude/revolve/loft/sweep, fillet/chamfer with edge selection, holes & counterbores, bolt
  circles, booleans, shelling enclosures. Read this when you need an API you don't remember.
- **`references/organic-forms.md`** - curved, flowing, hand-friendly shapes: lofting,
  sweeping along splines, revolved spline silhouettes, fillet-blending, freeform
  `make_surface` + thicken, and where the B-rep kernel fights back. Read this for vases /
  grips / horns / pebbles / doubly-curved shells.
- **`references/workflow.md`** - the MCP tools in detail, the iterate loop, exporting, and
  why you don't hand-edit `model.py`.
- **`examples/`** - complete, runnable parametric models to copy and adapt:
  - `bracket.py` - rounded plate, chamfered edge, central bore, corner holes (the default).
  - `enclosure.py` - box hollowed with a shell + a lid lip.
  - `flanged-mount.py` - flange + boss + bore + bolt circle.
  - `parametric-knob.py` - a revolved (lathe) profile with flutes and a filleted rim.
  - `exploded-enclosure.py` - a two-part base + drop-in lid assembly (the viewport's Explode
    slider spreads the parts interactively).
  - `packaging-layout.py` - inside-out packaging: reference component volumes gated by
    `show_internals`, with the shell derived from the packed envelope.
  - `spline-vase.py` - an organic spline silhouette revolved + shelled into a thin vessel.
  - `lofted-grip.py` - oval cross-sections lofted into a waisted ergonomic grip.
