---
name: solidifai-assemblies
description: Author a multi-part assembly as a skeleton (shared dimensions and frames) plus independent parts, wire them up with the assembly tools, and verify fit and motion. Use when the design is genuinely more than one part working together, asks for fasteners (screws, bolts, nuts, washers), wants a clearance/counterbore/tapped hole sized for a bolt, needs parts mated (concentric, coincident, a set distance apart), or asks whether something clears or jams through its motion (a hinge, a lid, a slider, a pivot). Covers the skeleton + parts authoring tools, the solidifai.hardware library, and the check_interferences (static) and check_motion (range-of-motion) checks.
license: MIT
---

# solidifai assemblies

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

This skill owns the nested assembly model: a `skeleton.py` of shared dimensions and frames plus
an independently authored `parts/<id>.py` per part, composed by the engine.
**solidifai-modeling** owns a single part; this skill owns genuinely multi-part work. Units are
millimetres; +Z is up.

## When to use

- The design is genuinely **more than one part** working together: a hinge, a geared mechanism,
  anything where independently authored parts share dimensions.
- The user asks for fasteners (screws, bolts, nuts, washers), a hole sized for a bolt, parts
  mated a set way, or whether something clears or jams through its motion.
- A **mechanism** (it moves, latches, springs, or meshes) gets a grounding pass first
  (**solidifai-grounding**).
- A **packaging** build: the internal layout is the skeleton. Layout frames and shared dims from
  the grounding inventory become the skeleton scalars and frames; each internal component is a
  **reference volume** part (`role="reference"`, shown for layout but never printed); the shell,
  lid, and brackets are the printed parts. Derive the envelope with the `internal-layout` lens and
  the `integrated-device` playbook (solidifai-product-design). A rectangular packed envelope is
  shared as scalars; an irregular footprint is published as a profile (below).
- **Skip when:** one part, or one coupled parametric body (a bracket, a knob, a few bodies that
  always move together): that is one `execute_script`; hand back to **solidifai-modeling**.

## The procedure

1. **State the pause-tier build brief** before you commit geometry (AGENTS.md "State the build
   brief"): its parts are the skeleton parts, its key_dims are skeleton scalars, its interfaces
   are the attach frames and clearances.
2. **Set the skeleton** with `set_skeleton(code)`: the shared design the parts build against.
3. **Set each part** with `set_part(id, code, attach=..., inputs=[...])`.
4. **Inspect and adjust the wiring** with the tree tools.
5. **Verify** fit and motion on the composed result.

### The model

- The **skeleton** owns the shared design. Its `PARAMS` are the sliders; its `build(...)`
  publishes named **scalars** (shared numbers like `body_w`, `wall`), named **frames** (rigid
  placements, build123d `Location`s), and named **joints** (how children are meant to move, for
  the motion check). It is the single source of truth for everything two parts must agree on.
- The skeleton can also publish named **geometry**: `s.profile("seat", <2D sketch/face/wire>)`
  for a shared profile, or `s.shape("boss", <solid>)` for a shared solid. A part declares the
  ones it reads as `shape_inputs`, and they arrive in the same `inputs` dict (`inputs["seat"]`).
- Each **part** lives in `parts/<id>.py` and defines `def build(inputs):`. It reads only the
  skeleton scalars it declared, builds in its own local frame, and `show()`s its solids.
- The engine owns `assembly.json`; the authoring tools maintain it for you, never hand-edit it.

Parts depend only on the skeleton, never on each other; the engine can build them in any order
and rebuild just the one you changed.

### Published profiles: only when the shared thing is geometry

- A number or a placement (a diameter, a wall thickness, a bolt-circle radius, where a part sits)
  stays a **scalar** or a **frame**. A round press-fit is one shared diameter; do not publish a
  profile for it.
- A bespoke outline the parts would otherwise each rebuild by hand (a gasket groove, a sealing
  rim with a notch, a cam path, an irregular mating face) is a **published profile**. Define it
  once in the skeleton with `s.profile(...)`; the mating part reads it and `offset()`s it by the
  fit clearance. Both parts then move together by construction.

Example: a base and a lid that must seal along the same rim.

```python
# doctest: +SKIP  (fragment -- needs: from build123d import BuildSketch, add, offset)
# skeleton.py
s.scalar("fit", 0.2)
s.profile("seat", rim_profile(...))      # rounded rim + cable notch, defined ONCE

# parts/base.py  (shape_inputs=["seat"])
with BuildSketch():
    add(inputs["seat"])

# parts/lid.py   (shape_inputs=["seat"], inputs=["fit"])
with BuildSketch():
    add(offset(inputs["seat"], amount=inputs["fit"]))   # lip grown to seat over the base
```

Sign rule: a positive offset grows the profile (a lip that wraps over the base's outside); a
negative offset shrinks it (a plug that drops inside the opening). Pick the sign from how your
part meets the seat.

Author the wiring with `set_part(..., shape_inputs=["seat"])`. `check_interfaces` flags a
`shape_inputs` name the skeleton does not publish (`missing_shape_input`).

### Worked example: a two-part enclosure

**1. Set the skeleton** with `set_skeleton(code)`. It declares `PARAMS`, then `build(...)`
returns a `skeleton()` carrying the shared scalars and frames:

```python
# doctest: +SKIP  (skeleton.py: runs in assembly mode via set_skeleton, not execute_script)
from solidifai import skeleton
from build123d import Location

PARAMS = {
    "body_w": {"value": 60.0, "min": 30.0, "max": 120.0, "step": 1.0, "unit": "mm", "desc": "Body width"},
    "body_h": {"value": 30.0, "min": 15.0, "max": 90.0,  "step": 1.0, "unit": "mm", "desc": "Body height"},
    "wall":   {"value": 2.4,  "min": 1.2,  "max": 5.0,   "step": 0.2, "unit": "mm", "desc": "Wall"},
}

def build(body_w, body_h, wall):
    s = skeleton()
    s.scalar("body_w", body_w)        # shared numbers the parts may read
    s.scalar("body_h", body_h)
    s.scalar("wall", wall)
    s.frame("base_frame", Location((0, 0, 0)))      # where the base sits
    s.frame("lid_frame", Location((0, 0, body_h)))  # the lid, body_h above it
    return s
```

**2. Set each part** with `set_part(id, code, attach=<frame>, inputs=[<scalars>])` (`attach` a
skeleton frame or `None` for the node origin; `inputs` the scalars its `build(inputs)` reads):

```python
# doctest: +SKIP  (parts/base.py: build(inputs) runs against skeleton inputs, not execute_script)
from solidifai import show
from build123d import BuildPart, Box

def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Base")
```

`parts/lid.py` is the same shape 3 mm thick, `show()`n as `"Lid"`.

The tool calls, in order:

```
set_skeleton(<skeleton code above>)
set_part("base", <base code>, attach="base_frame", inputs=["body_w", "wall"])
set_part("lid",  <lid code>,  attach="lid_frame",  inputs=["body_w", "wall"])
```

Each `set_part` rebuilds only that part and recomposes; parts appear in the viewport as
`<id>/<show-name>` (`base/Base`, `lid/Lid`).

**Reference parts (packaging).** An internal component is a part whose `build()` shows a
`role="reference"` body (`show(p.part, name="ref: SBC", color=..., role="reference")`), attached
to its layout frame and reading its envelope dims; the mechanics (ghosted, excluded from export
and DFM, still seen by `check_interferences()`) live in **solidifai-modeling**. Wire it like any
part: `set_part("ref-sbc", <ref code>, attach="sbc_frame", inputs=["sbc_l", "sbc_w", "sbc_h"])`.

For **several** independent parts, use **solidifai-orchestration** (`begin_round`, one
`set_part` per part, one worker each per **solidifai-delegation**, then `end_round` composes
once) instead of authoring them one slow `set_part` at a time.

**3. Inspect and edit the tree:**

- `get_assembly_tree()` returns the whole structure (skeleton params, published scalars and
  frames, every child's `attach`/`inputs`); read it before you wire a part.
- `get_part_info("base")` returns one part's source, wiring, and last-build solid count.
- `attach("lid", "other_frame")` moves a part to a different frame. This is a **recompose, not a
  rebuild**: the frame is not part of the geometry cache key.
- `set_inputs("lid", ["body_w", "body_h", "wall"])` changes which scalars a part reads. Inputs
  **are** part of the cache key, so this rebuilds the part.
- `add_subassembly("hinge", attach="hinge_frame", inputs=["body_w"])` nests a sub-mechanism: a
  child node with its own skeleton and parts.
- `remove_part("lid")` drops a child and deletes its source.
- `build_part("base")` builds one part in isolation and reports its result (valid, solids, bbox).

A part `id` is a simple name (`^[A-Za-z0-9_-]+$`); it becomes the part's filename.

### Instancing: N identical parts are one part

Four wheels, six bolts, a row of standoffs: that is ONE part definition placed at several frames,
never N copies of the file. Define the part once, publish a frame per placement in the skeleton,
and call `set_occurrences(id, [...])`:

```python
# doctest: +SKIP  (assembly-mode tool calls; skeleton publishes the four wheel frames)
set_part("wheel", <wheel code>, attach="wheel_fl", inputs=["wheel_dia", "hub_dia"])
set_occurrences("wheel", [
    {"frame": "wheel_fl", "mirror": None},
    {"frame": "wheel_fr", "mirror": "yz"},   # right side, a mirrored pair
    {"frame": "wheel_rl", "mirror": None},
    {"frame": "wheel_rr", "mirror": "yz"},
])
```

- Each occurrence is `{"frame": <skeleton frame or null>, "mirror": <null/"xy"/"yz"/"zx">}`; a
  mirrored occurrence is reflected about that local plane, for a left/right handed pair. The
  engine separates mirrored occurrences in the BOM and drawings for you.
- The part builds **once** and is placed at each occurrence, so this is a cheap **recompose**, not
  N rebuilds. `attach` stays the primary occurrence (`occurrences[0]`).
- Occurrence bodies are named `wheel`, `wheel@2`, `wheel@3` ...; a feature on one is `wheel@2/bore`.
  `set_feature` on any occurrence drives the shared param, so every occurrence moves together. Each
  body is distinct for `check_interferences` and `check_motion`.

### Hardware

`solidifai.hardware` has ISO metric fasteners and auto-sized holes (sizes M2 to M8). Screw and
hole threads are plain cylinders at the correct fit diameters (fit-accurate, the FDM default);
when the thread itself is the deliverable, `hardware.external_thread` /
`hardware.internal_thread_cutter` build a real ISO helical thread (see solidifai-modeling).

```python
from build123d import Box, Pos
from solidifai import show, hardware

# a plate with a counterbored M3 hole, and the screw seated in it
plate = Box(30, 30, 6) - Pos(0, 0, 6) * hardware.counterbore("M3", depth=6)
show(plate, name="Plate")
show(Pos(0, 0, 6) * hardware.socket_head_cap_screw("M3", 10), name="Screw")
show(Pos(0, 0, -2.4) * hardware.hex_nut("M3"), name="Nut")
```

- `socket_head_cap_screw(size, length)`, `hex_nut(size)`, `washer(size)` build parts.
- `clearance_hole(size, depth, fit)` (fit = close / medium / coarse), `counterbore(size,
  depth)`, `tap_hole(size, depth)` build cutters to **subtract** from a part.
- `hardware.dims(size)` returns the exact numbers; `hardware.sizes()` lists the set.
- Pick the hole by intent: `clearance_hole` for a bolt that passes through, `tap_hole`
  for a hole you'll thread, `counterbore` to sink a socket head flush.

In an assembly, the screw and the part with its hole are usually separate parts, each reading
the fastener size from one skeleton scalar so they always match.

### Joints: declare how parts move

Declare a joint for every moving interface so the motion check knows the intent. In the skeleton
`build(...)`, `s.joint(name, kind, frame, axis=?, limits=?, between=[moving, ground])`:

```python
# doctest: +SKIP  (inside the skeleton build(...))
s.frame("hinge_axis", Location((0, body_d, lid_h)))
s.joint("hinge", "revolute", "hinge_axis", axis=(1, 0, 0), limits=[0, 110],
        between=["lid", "base"])
```

- `kind` is `rigid` (no DOF), `revolute` (rotates about the axis), `slider` (translates along it),
  `cylindrical` (both), `planar`, or `ball`. `frame` is a published frame at the joint location;
  `axis` is a local vector (default +Z); `limits` is `[lo, hi]` in degrees (rotary) or mm (linear);
  `between` names the two child ids `[moving, ground]`.
- Joints are declared **intent** for motion checking, not a constraint solver: parts are still
  placed by their `attach` frame. `check_interfaces` validates the joint wiring.

### Fit and motion checks

Run these once the parts compose.

- **Static fit** with `check_interferences` (the AGENTS.md tool table has the read): an
  intended press-fit is fine; an unintended overlap or a floating lump is a defect.
- **Motion** with `check_motion`. Prefer joint mode, `check_motion(joint="hinge")`: it sweeps the
  joint's first `between` child through its declared limits and reports `firstCollision` and how
  far it moves clear (`clearThrough`). Or drive a part directly, `check_motion(part, kind,
  axis_origin, axis_dir, start, stop)`, with `kind="revolute"` (rotate degrees about the axis, a
  hinge or lid) or `kind="prismatic"` (translate mm along it, a drawer or slider). Confirm a lid
  opens to 110 degrees, or widen the clearance if it jams early. Run it in self-verify for any
  assembly with a declared non-rigid joint. Name parts clearly; the checks report by name.

## Anti-patterns

- Wrapping a lone part (or a handful of tightly coupled bodies that always move together) in a
  skeleton; that stays one `execute_script`.
- Hand-copying a part file N times for identical parts; define it once and place it with
  `set_occurrences` (one part, N occurrences).
- Hand-editing `assembly.json`; the authoring tools own it.
- A part importing or reading a sibling; parts read only the skeleton.
- Publishing a profile for a plain shared number; scalars are simpler and equally in sync.
- Rebuilding everything when one part failed: per-node isolation keeps that node's last-good
  geometry and the rest still composes; fix just that part (`get_part_info`, then `set_part`).

## Cross-references

- **solidifai-modeling** - the build mechanics of each individual part, and the
  reference-volume mechanics.
- **solidifai-orchestration** - author several independent parts in parallel under a round,
  compose once.
- **solidifai-delegation** - the worker contract for the per-part fan-out.
- **solidifai-grounding** - understand a mechanism before building it.
- **solidifai-self-verify** - confirm the finished assembly and size real clearances on
  purpose (the Fit check or `tolerance_stack`).
- **solidifai-debugging** - assembly build failures and per-node isolation.
