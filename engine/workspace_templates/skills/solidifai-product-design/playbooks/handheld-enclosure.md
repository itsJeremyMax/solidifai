# handheld-enclosure playbook

A case or housing for a handheld device — something a person picks up, holds, and operates
one- or two-handed, carrying its own controls and ports. The job is a shell that fits the
device, breaks every grip edge, and presents each control and port reachable and pressable.
Numbers come from the lenses below — this playbook composes them, it does not restate them.

## Scope

A **case / enclosure for a handheld device**: a hollow shell that wraps an internal device
(a board, a battery, a screen) with a **grip** the hand wraps or holds, **controls** (buttons,
a dial) the operating hand reaches, and **ports** (USB, jack, switch) that pass through a wall.
Closed by a lid (snap-fit or screw-boss). Use this when the part is held *and* operated. If it's
purely a box to keep things in, use `container-lid.md`; if it's mostly a thing to grab, use
`grip-handle.md`.

## Lenses it pulls

- [ergonomics](../references/ergonomics.md#decision-rules) — grip Ø (power-grip band if the
  whole case is wrapped), the **pressable-control minimum** and comfortable button size, adjacent
  control spacing, the one-handed thumb-reach arc and max comfortable face width. Every control
  dimension is owned here.
- [affordance-usability](../references/affordance-usability.md#decision-rules) — **where** the
  controls and ports go: primary control under the natural thumb, ports grouped on one oriented
  face, nothing under the grip hand's footprint, every control a visible/feelable signifier.
- [manufacturability](../references/manufacturability.md#data--defaults) — wall minimum and
  default wall, the canonical **mating clearance for the active process** for the cavity and the lid (linked, not a
  number invented here), overhang/bridge limits, and the lid-closure strategy
  ([snap-fit vs. screw boss](../references/manufacturability.md#decision-rules)).
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens** (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that process). The manufacturability hub above routes by process.
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — one **radius family** of
  filleted outer edges (no sharp grip surfaces), a deliberate proportion (not an accidental
  near-cube), and a seam tucked on an edge rather than across a show face.

## Default recipe

Defaults, each traceable to a lens — adjust to the device, don't invent past these:

- **Walls 2–2.5 mm (illustrative range).** Default wall from the manufacturing profile (`design.wallMm`,
  via `get_manufacturing_profile()`); thick enough to carry a fastener, thin enough not to bloat the
  case. Never below the active process's minimum wall
  ([manufacturability](../references/manufacturability.md#data--defaults)).
- **Filleted outer edges, one radius family** — break every edge the hand grips so no grip
  surface is sharp ([aesthetics-form](../references/aesthetics-form.md#decision-rules), with the
  touched-edge rule owned by
  [ergonomics](../references/ergonomics.md#decision-rules)) (which edges are gripped; the break size
  is the manufacturing profile's edge-break default). A ~6 mm soft corner is a good start for grip
  radii; reuse it, don't give each edge its own value.
- **Internal cavity = device + clearance per side.** Use the canonical **mating clearance for the active process**
  (the loose-fit end of the range) from
  [manufacturability](../references/manufacturability.md#data--defaults) — link to that home, don't
  pick a new number. The shell's outer size is then `device + 2·(clearance + wall)`.
- **Lid with a real lip clearance** — a drop-in or snap-fit lid needs the same canonical mating
  gap (the tighter end of that range, for a lip that should locate, not rattle); pick **snap-fit** for
  tool-free repeated opening or **screw bosses** for a serviced, load-bearing closure, per
  [manufacturability](../references/manufacturability.md#decision-rules). Never model the lid
  coincident with the rim.
- **Button cutouts sized from the control's footprint** — at least the pressable-control minimum,
  comfortable size by default, from
  [ergonomics](../references/ergonomics.md#data--defaults); spaced if there are several. Place
  them under the operating thumb, off the grip footprint, per
  [affordance-usability](../references/affordance-usability.md#decision-rules).
- **Port openings = connector + ~0.5 mm** so the plug clears the wall and the cable seats; group
  ports on one oriented face
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).

### Runnable starter

A parametric hollow filleted shell with a top opening for the lid and one button cutout through a
side wall. Tweak with `set_params(...)`; outer size is derived from the device plus clearance plus
wall, so the cavity tracks the device automatically.

> The wall, clearance, and fillet values below are illustrative starting points. For a real build,
> read the workspace defaults first with `get_manufacturing_profile()` and use its `design.wallMm`,
> the `fits` clearance for the selected fit, and `design.filletMm` in place of these literals.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Locations,
    Mode,
    fillet,
    offset,
)
from solidifai import show

PARAMS = {
    "dev_l":    {"value": 80.0, "min": 30.0, "max": 200.0, "step": 1.0, "unit": "mm", "desc": "Device length (X)"},
    "dev_w":    {"value": 45.0, "min": 20.0, "max": 150.0, "step": 1.0, "unit": "mm", "desc": "Device width (Y)"},
    "dev_h":    {"value": 18.0, "min": 8.0,  "max": 80.0,  "step": 1.0, "unit": "mm", "desc": "Device height (Z)"},
    "wall":     {"value": 2.4,  "min": 1.2,  "max": 4.0,   "step": 0.2, "unit": "mm", "desc": "Shell wall"},
    "clear":    {"value": 0.3,  "min": 0.1,  "max": 0.6,   "step": 0.1, "unit": "mm", "desc": "Cavity clearance / side"},
    "fillet_r": {"value": 6.0,  "min": 1.0,  "max": 12.0,  "step": 0.5, "unit": "mm", "desc": "Outer corner radius"},
    "btn":      {"value": 12.0, "min": 8.0,  "max": 20.0,  "step": 0.5, "unit": "mm", "desc": "Button cutout size"},
}


def build(dev_l, dev_w, dev_h, wall, clear, fillet_r, btn):
    # Outer shell = device + clearance both sides + a wall both sides.
    out_l = dev_l + 2 * (clear + wall)
    out_w = dev_w + 2 * (clear + wall)
    out_h = dev_h + 2 * (clear + wall)

    with BuildPart() as p:
        # Solid outer box on the bed (bottom at z = 0).
        Box(out_l, out_w, out_h, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Round the four vertical edges -> no sharp grip surface.
        fillet(p.edges().filter_by(Axis.Z), radius=fillet_r)

        # Hollow to a uniform wall, leaving the top open for a drop-in lid.
        top = p.faces().sort_by(Axis.Z)[-1]
        offset(amount=-wall, openings=top)

        # Button cutout through the +X side wall, sized from the ergonomics lens.
        right = p.faces().sort_by(Axis.X)[-1]
        with Locations(right):
            Box(btn, btn, 4 * wall, mode=Mode.SUBTRACT)

    show(p.part, name="Case")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

The lid is a separate part — model it as its own solid (rim that drops into the opening with the
lip clearance above) and `show()` it alongside the case so the two stay distinct; don't add an
`explode` parameter (exploded view is a viewport control), and review the seam with an exploded
`capture_views(..., explode=70)` (see `solidifai-modeling` multi-part guidance).

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **What are the device's outer dimensions** (the thing going inside)? Sets the whole cavity; the
  shell is `device + 2·(clearance + wall)`.
- **Which faces carry the ports and buttons?** Drives the layout, the grip, and which wall gets
  cut — decide before filleting.
- **Pocket-carry or mounted?** Pocket-carry rewards a slim, fully-broken-edge form; mounted lets
  you add a flat face / boss and worry less about thickness.

## Verify checklist

- **Visual** — `capture_views(["front", "<control-face>"])` (the control face is whichever wall
  carries the buttons/ports). Confirm: every **button and port is reachable and unobstructed** by
  the grip hand, the **thumb reaches the primary control** without leaving the reach arc
  ([ergonomics](../references/ergonomics.md#verify),
  [affordance-usability](../references/affordance-usability.md#verify)), each control *reads* as a
  pressable affordance, and the outer edges share one radius family with no stray sharp grip edge
  ([aesthetics-form](../references/aesthetics-form.md#verify)).
- **Assert (known-by-construction)** — every wall is **≥ the active process's minimum wall**
  (see manufacturability) and the **cavity ≥ device + clearance** (you set both, so you know them; true minimum
  wall on freeform geometry is not recoverable from `get_model_info()` — say so). Each button
  cutout's smallest dimension is **≥ the finger-pad minimum**
  ([ergonomics](../references/ergonomics.md#verify)).
- **Assert (computed)** — `get_model_info()` bounding box matches `device + 2·(clearance + wall)`;
  `valid` and `manifold` are both true.
- **Supported against gravity** — if the case is set down rather than only held, confirm it rests
  stably (center of mass inside its footprint, not tippy); run `check_interferences()` so the body
  and lid come back `adjacent`/`clear` (never `overlap`) and nothing is `disjoint`/floating
  ([support-stability](../references/support-stability.md#verify)).

## Common failure modes

- **Buttons modeled flush or unpressable** — a cutout with no cap, no travel, or sized below the
  finger-pad minimum reads as broken. Give it a real opening and a pressable cap/relief
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **Ports blocked** — an opening behind the grip hand, on the face the case rests on, or too tight
  for the plug. Group ports on one oriented face and add ~0.5 mm clearance.
- **Walls too thin for the process** — a one-bead shell on a case that gets handled cracks. Keep walls
  ≥ the active process's minimum wall ([manufacturability](../references/manufacturability.md#data--defaults)).
- **Sharp edges on grip surfaces** — raw box edges bite the hand and read as un-designed. Fillet
  every touched edge in one radius family.
- **No lid clearance** — a lip modeled coincident with the rim won't close, or jams. Give the lid
  the canonical mating gap ([manufacturability](../references/manufacturability.md#decision-rules));
  never model mating faces coincident.
