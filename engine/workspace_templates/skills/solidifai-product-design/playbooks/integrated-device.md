# integrated-device playbook

A self-contained device built around several internal components: a cyberdeck, handheld console,
mini-PC, drone body, battery pack, camera rig. The job is to pack the components so they fit,
clear, cool, and are serviceable, then wrap a shell derived from their envelope. Numbers come from
the lenses below -- this playbook composes them, it does not restate them.

Requires the grounding **component inventory** (real component dimensions and connector faces) as input; if it is absent, run **solidifai-grounding** first.

## Scope

A **multi-component device**: a self-contained product whose shape is driven by several internal
components rather than a single board. Think cyberdeck, handheld Linux console, mini-PC, drone
body, battery pack, camera rig. Several concerns dominate: **packing** the components so they fit
and clear each other, **cooling** any component that dissipates real power, **port layout** that
surfaces all connectors on the right faces, and **service access** so the device can be opened and
a battery or card swapped. The shell is derived from the component inventory, not chosen first.

This playbook is specifically for devices with several internal components, not one. If it is a
single board in a box, use `electronics-enclosure.md`. If it is held and thumb-operated around a
screen, use `handheld-enclosure.md`. If it just stores loose contents, use `container-lid.md`.

## Lenses it pulls

- [internal-layout](../references/internal-layout.md#decision-rules) -- the spine of this
  playbook: the inside-out five-step method (INVENTORY -> LAYOUT -> RESERVE -> DERIVE -> WRAP),
  the reservation numbers (component-to-component clearance, cable routing, airflow channel,
  service access, fastener land), and the wrap arithmetic that derives the outer shell from the
  packed envelope.
- [thermal-ventilation](../references/thermal-ventilation.md#decision-rules) -- whether the device
  needs passive vents, a fan, or a heatsink boss; the open-area target for a vent pattern; and
  low-inlet / high-outlet placement so convection sweeps the hottest components. Every airflow
  decision is owned here.
- [affordance-usability](../references/affordance-usability.md#decision-rules) -- port and
  connector layout: group ports by function, put them on one oriented face where you can, and size
  each cutout to the real connector footprint so nothing is guessed.
- [structure](../references/structure.md#decision-rules) -- mounts and bosses: a standoff or
  mounting post under each component that cannot float, a wall thick enough to anchor a
  self-tapping screw, a boss that won't crack under vibration.
- [serviceability-assembly](../references/serviceability-assembly.md#decision-rules) -- getting in
  and back out: lid access for a battery swap or reflash, captive hardware, and a single assembly
  direction so everything drops in one way.
- [fits-tolerances](../references/fits-tolerances.md#decision-rules) -- the lid fit and the
  component-to-wall clearance: a lip that locates without rattling, a pilot hole sized for a
  self-tapping screw to bite. Each clearance comes from here, not a guessed number.
- [support-stability](../references/support-stability.md#decision-rules) -- it sits on a desk,
  hangs on a strap, or mounts to a panel: a flat stable base or a secure mount, center of mass
  inside the footprint so it does not tip when a stiff cable pulls.
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) -- one radius family of
  filleted outer edges and a seam tucked on an edge rather than across a show face, so a utility
  device still reads as designed.

## Default recipe

Inside-out order, each step traceable to a lens:

1. **Build the component inventory** from grounding -- real datasheet dimensions for each
   component, including connector plug depth on the face it lives on. Never approximate
   ([internal-layout](../references/internal-layout.md#decision-rules)).
2. **Lay the components out as reference volumes** in 3D -- decide the packing arrangement
   (stacked flat, side-by-side, L-shaped) from which faces carry connectors, what needs airflow,
   and what must be reached in service
   ([internal-layout](../references/internal-layout.md#decision-rules)).
3. **Reserve clearance, cable routing, airflow, and service space** alongside each component and
   in each path between them -- use the reservation defaults from
   [internal-layout](../references/internal-layout.md#data--defaults) for component-to-component
   gap and cable bend; size the airflow channel from
   [thermal-ventilation](../references/thermal-ventilation.md#decision-rules); size the service
   opening from [serviceability-assembly](../references/serviceability-assembly.md#decision-rules).
4. **Derive the packed envelope** -- the tightest axis-aligned box that contains all the
   reference component volumes ([internal-layout](../references/internal-layout.md#principle)).
5. **Wrap the shell** -- outer size = packed envelope (components) + clearance + other reservations
   + 2 * wall (one wall per side), where wall comes from the manufacturing profile. Component-to-
   wall clearance is one of the reservations the internal-layout lens folds into its
   `packed_envelope`, so its `packed_envelope + 2 * wall` and this expanded form are the same thing
   ([internal-layout](../references/internal-layout.md#data--defaults)).
6. **Provision mounts under each component and port cutouts sized to the real connectors** --
   standoff geometry from [structure](../references/structure.md#decision-rules); cutout sizing
   from [affordance-usability](../references/affordance-usability.md#decision-rules) and
   [fits-tolerances](../references/fits-tolerances.md#decision-rules).
7. **Close with a serviceable lid** -- snap-fit or screw-boss lid per
   [serviceability-assembly](../references/serviceability-assembly.md#decision-rules) with the
   mating clearance from [fits-tolerances](../references/fits-tolerances.md#decision-rules).

### Runnable starter

A parametric shell with an SBC and a battery packed side-by-side. Each internal component is
shown as a reference volume with `role="reference"`: the engine ghosts it in the viewport,
excludes it from export and DFM automatically, and still counts it in `check_interferences()`
so the containment layout check works. `show_internals` is an optional viewport toggle to
declutter; it is not the export mechanism. The outer shell derives its size from the packed
component envelope plus clearance plus wall, so the cavity tracks the contents automatically.
Tweak with `set_params(...)`.

> The wall, clearance, and fillet values below are illustrative starting points. For a real build,
> read the workspace defaults first with `get_manufacturing_profile()` and use its `design.wallMm`,
> the `fits` clearance for the selected fit, and `design.filletMm` in place of these literals.

```python
from build123d import Align, Axis, Box, BuildPart, Locations, Mode, fillet, offset
from solidifai import show

PARAMS = {
    "sbc_l":         {"value": 85.0, "min": 30.0, "max": 200.0, "step": 1.0,  "unit": "mm", "desc": "SBC length"},
    "sbc_w":         {"value": 56.0, "min": 20.0, "max": 150.0, "step": 1.0,  "unit": "mm", "desc": "SBC width"},
    "sbc_h":         {"value": 18.0, "min": 5.0,  "max": 60.0,  "step": 1.0,  "unit": "mm", "desc": "SBC stack height"},
    "batt_l":        {"value": 70.0, "min": 20.0, "max": 200.0, "step": 1.0,  "unit": "mm", "desc": "Battery length"},
    "batt_w":        {"value": 40.0, "min": 20.0, "max": 150.0, "step": 1.0,  "unit": "mm", "desc": "Battery width"},
    "batt_h":        {"value": 12.0, "min": 5.0,  "max": 60.0,  "step": 1.0,  "unit": "mm", "desc": "Battery height"},
    "gap":           {"value": 4.0,  "min": 1.0,  "max": 20.0,  "step": 0.5,  "unit": "mm", "desc": "Component-to-component gap"},
    "clear":         {"value": 1.5,  "min": 0.3,  "max": 5.0,   "step": 0.1,  "unit": "mm", "desc": "Component-to-wall clearance"},
    "wall":          {"value": 2.4,  "min": 1.2,  "max": 4.0,   "step": 0.2,  "unit": "mm", "desc": "Shell wall"},
    "fillet_r":      {"value": 3.0,  "min": 0.5,  "max": 10.0,  "step": 0.5,  "unit": "mm", "desc": "Outer corner radius"},
    "show_internals": {"value": 1.0, "min": 0.0,  "max": 1.0,   "step": 1.0,  "unit": "",   "desc": "Show reference components in the viewport (a layout toggle)"},
}


def build(sbc_l, sbc_w, sbc_h, batt_l, batt_w, batt_h, gap, clear, wall, fillet_r, show_internals):
    # Step 4: derive packed envelope from the component inventory.
    pack_l = sbc_l + gap + batt_l
    pack_w = max(sbc_w, batt_w)
    pack_h = max(sbc_h, batt_h)

    # Step 5: wrap -- outer = packed envelope + 2 * clear + 2 * wall.
    inner_l = pack_l + 2 * clear
    inner_w = pack_w + 2 * clear
    inner_h = pack_h + 2 * clear
    out_l = inner_l + 2 * wall
    out_w = inner_w + 2 * wall
    out_h = inner_h + 2 * wall
    floor = wall + clear

    # X-positions of the two components within the pack.
    sbc_x = -pack_l / 2 + sbc_l / 2
    batt_x = pack_l / 2 - batt_l / 2

    # Shell: hollowed solid, open top for a serviceable lid.
    with BuildPart() as shell:
        Box(out_l, out_w, out_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
        fillet(shell.edges().filter_by(Axis.Z), radius=fillet_r)
        top = shell.faces().sort_by(Axis.Z)[-1]
        offset(amount=-wall, openings=top)

        # Step 6: port cutout through the +X face (SBC connectors).
        with Locations((out_l / 2, 0, floor + sbc_h / 2)):
            Box(2 * wall + 2.0, sbc_w * 0.6, sbc_h * 0.5, mode=Mode.SUBTRACT)

    show(shell.part, name="Shell", material="abs")

    # Step 2: reference component volumes -- visible when show_internals is on.
    if show_internals >= 1.0:
        with BuildPart() as sbc:
            with Locations((sbc_x, 0, floor + sbc_h / 2)):
                Box(sbc_l, sbc_w, sbc_h)
        show(sbc.part, name="ref: SBC", color=(0.20, 0.55, 0.95), role="reference")

        with BuildPart() as batt:
            with Locations((batt_x, 0, floor + batt_h / 2)):
                Box(batt_l, batt_w, batt_h)
        show(batt.part, name="ref: Battery", color=(0.95, 0.75, 0.20), role="reference")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

The lid is a separate part -- model it as its own drop-in solid with the canonical mating
clearance ([solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models)) and
`show()` it alongside the shell; exploded view is a built-in viewport control, so do not add
an explode parameter.

## Questions that matter

Ask only these, and only if guessing wrong is expensive -- otherwise default and state it:

- **What are the components and their real dimensions?** The inside-out method only works from
  real numbers. If they are not known, grounding to find them is the first step, not optional
  ([internal-layout](../references/internal-layout.md#questions-that-matter)).
- **Which faces carry connectors?** The answer locks the orientation of the layout and the
  placement of every cutout. If the device has only one sensible connector face, default to it
  and state the assumption.
- **Does it run hot / need a fan?** Forks the design: a working SBC or compute module wants open
  vents or a fan ([thermal-ventilation](../references/thermal-ventilation.md#decision-rules)).
  Default to passive vents for a light load; ask when the thermal budget is genuinely tight.

## Verify checklist

- **Visual** -- `capture_views(["top", "<connector-face>", "iso"])` with `show_internals` on
  (so the reference volumes are visible in the render). Confirm: every component reference
  volume (shown with `role="reference"`, so it is ghosted but visible) is seated inside the
  cavity with visible clearance on each side; every port cutout lines up with the connector
  face it serves; no component pokes through a wall
  ([internal-layout](../references/internal-layout.md#verify),
  [affordance-usability](../references/affordance-usability.md#verify)).
- **Assert (known-by-construction)** -- cavity inner dimensions = packed envelope + 2 * clearance;
  mounts are present under each component that cannot float; port cutouts are sized to the real
  connector footprint; each wall is >= the active process minimum wall (see manufacturability).
  These are set by construction; true minimum wall on freeform geometry is not recoverable from
  `get_model_info()` -- say so.
- **Assert (computed)** -- `get_model_info()` bounding box = packed envelope + 2 * clearance +
  2 * wall (i.e. outer = packed envelope + 2 * (clear + wall)); `valid` and `manifold` are both
  true ([internal-layout](../references/internal-layout.md#verify)).
- **Supported against gravity** -- center of mass sits inside the footprint (it does not tip when
  a cable pulls); `check_interferences()` comes back clean: components are `adjacent` or `clear`
  (never `overlap`), nothing is `disjoint` / floating, nothing interpenetrates a wall
  ([support-stability](../references/support-stability.md#verify),
  [internal-layout](../references/internal-layout.md#verify)).

## Common failure modes

- **Hollow shell with no contents modeled** -- the cavity is invented rather than derived; the
  real components may not fit. Always place reference volumes first, then derive the envelope.
- **Cavity guessed instead of derived from the inventory** -- a guessed outer box produces a
  cavity that does not close around the real parts. Work inside-out: layout -> reserve -> derive
  -> wrap ([internal-layout](../references/internal-layout.md#principle)).
- **Components collide or overlap a wall** -- a layout that does not account for
  component-to-component gap or component-to-wall clearance. Use the reservation numbers from
  [internal-layout](../references/internal-layout.md#data--defaults) and verify with
  `check_interferences()`.
- **Ports invented instead of read off the connector face** -- an opening that does not match the
  real connector blocks the plug or leaves a ragged gap. Derive each cutout from the connector's
  actual position and size on the component reference volume
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **No service access so the device cannot be opened** -- a lid with no clearance, or no lid at
  all. Give the lid the canonical mating gap
  ([fits-tolerances](../references/fits-tolerances.md#decision-rules)) and plan for at least one
  component that must come out
  ([serviceability-assembly](../references/serviceability-assembly.md#decision-rules)).
