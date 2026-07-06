# wearable playbook

A strap, clip, or housing **worn on the body** — something held against skin or clothing for an
extended time: a wrist cuff, an armband, a belt clip, a sensor housing. The job is a part that sits
comfortably against the body (no edge that bites), flexes where it must without cracking, fits a
range of bodies, and stays light enough to forget it's there. Numbers come from the lenses below —
this playbook composes them, it does not restate them.

## Scope

A **part worn on the body**: a band/strap that wraps a limb, a clip that grips a belt or pocket, or
a small housing strapped to skin (a tracker, a sensor). It has a **skin-contact surface** that must
be relieved, a **flex region** (the band itself, a living hinge, or a cantilever clip) that bends
in use, and usually some **size adjustment** so one part fits many wearers. Use this when the part
is worn against or on the body. If it's gripped in the hand rather than worn, use `grip-handle.md`;
if it's a static housing that isn't worn, use `handheld-enclosure.md`.

## Lenses it pulls

- [ergonomics](../references/ergonomics.md#decision-rules) — **body-contact comfort and percentile
  sizing**: design the **adjustment range** so the smallest wearer can still cinch it (reach/fit to
  the 5th percentile) and the largest can still close it (clearance to the 95th), and keep every
  surface that touches the body broken, not sharp. Which percentile drives reach vs. clearance, and
  the gloved/seasonal allowance, are owned here
  ([percentile method](../references/ergonomics.md#data--defaults)).
- [manufacturability](../references/manufacturability.md#decision-rules) — **flex and living
  hinges**: a band or clip that bends is a deliberately *thin* feature, and a tool-free closure is a
  **snap-fit** with a generous root fillet; on layered processes (FDM) pull it **along the layers**, not across them — the
  snap/cantilever and along-the-layers rules live in
  [manufacturability — fastener-strategy chooser](../references/manufacturability.md#decision-rules). The
  active process's minimum wall lives here too; a flex region goes *below* the default wall on purpose, but
  never so thin the process can't make it.
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens** (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that process). The manufacturability hub above routes by process.
- [structure](../references/structure.md#decision-rules) — **flex fatigue**: the bend region is the
  part most likely to crack. Keep flexural strain within the material's limit, **fillet the root of
  every hinge/clip** (radius ≥ ~0.5× the beam thickness) to kill the stress riser, and on layered processes (FDM) pull the flex
  **along the layers** so it doesn't delaminate
  ([snap/hinge root fillet](../references/structure.md#decision-rules)).
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — one **radius family** of
  relieved edges, a deliberate strap proportion (width-to-length that reads intentional, not a stray
  ribbon), and a clean, hidden seam — with the **touched-edge break** itself owned by
  [ergonomics](../references/ergonomics.md#decision-rules).

## Default recipe

Defaults, each traceable to a lens — adjust to the body site and material, don't invent past these:

- **Relieve every skin-contact surface.** Break the underside and both long edges of any band, the
  inside lip of any clip, and every corner the body meets — no raw sharp edge against skin. A small
  edge-break fillet in **one radius family**
  ([aesthetics-form](../references/aesthetics-form.md#decision-rules)); the break size is the
  manufacturing profile's edge-break default (`get_manufacturing_profile()`, `filletMm`), and
  which edges are skin-contact is the human-dimension context owned by
  [ergonomics](../references/ergonomics.md#decision-rules).
- **Balance strap thickness and width for flex vs. strength.** Thinner bends more easily but
  fatigues and tears sooner; wider spreads pressure (more comfort) but resists wrapping a tight
  curve. Start a worn band around **2–2.5 mm thick** and **15–22 mm wide**, then thin *only the flex
  region* below that if it must bend hard — never below the active process's minimum wall
  ([manufacturability](../references/manufacturability.md#data--defaults)). On layered processes (FDM), pull the bend **along the
  layers** ([structure](../references/structure.md#decision-rules)).
- **Size the adjustment range across percentiles.** A worn part fits a *population*, not one wrist —
  give it real adjustment (a slot-and-pin ladder, multiple holes, a sliding clip) sized so the
  **5th-percentile** wearer can cinch it down and the **95th-percentile** wearer can still close it
  ([ergonomics](../references/ergonomics.md#decision-rules), with the
  [percentile data](../references/ergonomics.md#data--defaults); add the **gloved/seasonal
  allowance** if it's worn over a sleeve). One fixed length fits almost nobody.
- **Fillet every flex/hinge root.** The bend region is the crack risk — give each living hinge or
  cantilever clip a root fillet **≥ ~0.5× its thickness** to relieve the stress riser, and keep the
  bending strain within the material's limit
  ([structure](../references/structure.md#decision-rules),
  [manufacturability](../references/manufacturability.md#data--defaults)).
- **Keep it lightweight — mass matters.** A worn part is felt every second; trim it to the thinnest
  manufacturable section that carries the load, prefer a narrow relieved band over a chunky slab, and
  **check the mass** from `get_model_info()` (you can actually measure this one). Heavy = it gets
  taken off and lost.

### Runnable starter

A parametric flat strap with softened plan corners, every skin-contact edge broken, and an
adjustment slot near one end so it can be pinned/clipped to length. It builds flat (easy to make,
the flex comes from wrapping it on the body); `set_params(...)` to fit the site — widen `band_w` for
a comfier armband, thin `band_t` for an easier wrap, lengthen the `slot_*` for more adjustment range.
The bounding box and the reported **mass** let you verify lightness directly.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Locations,
    Mode,
    fillet,
)
from solidifai import show

PARAMS = {
    "band_len":   {"value": 90.0, "min": 40.0, "max": 200.0, "step": 1.0, "unit": "mm", "desc": "Strap length"},
    "band_w":     {"value": 18.0, "min": 10.0, "max": 40.0,  "step": 1.0, "unit": "mm", "desc": "Strap width"},
    "band_t":     {"value": 2.4,  "min": 1.2,  "max": 4.0,   "step": 0.2, "unit": "mm", "desc": "Strap thickness"},
    "corner_r":   {"value": 8.0,  "min": 2.0,  "max": 9.0,   "step": 0.5, "unit": "mm", "desc": "Plan corner radius"},
    "slot_w":     {"value": 4.0,  "min": 2.0,  "max": 8.0,   "step": 0.5, "unit": "mm", "desc": "Adjustment slot width"},
    "slot_len":   {"value": 14.0, "min": 6.0,  "max": 30.0,  "step": 1.0, "unit": "mm", "desc": "Adjustment slot length"},
    "edge_break": {"value": 0.8,  "min": 0.4,  "max": 1.2,   "step": 0.1, "unit": "mm", "desc": "Skin-contact edge break"},
}


def build(band_len, band_w, band_t, corner_r, slot_w, slot_len, edge_break):
    with BuildPart() as p:
        # Flat strap blank on the bed; its underside (z = 0) is the skin side.
        Box(band_len, band_w, band_t, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Soften the plan corners -> no square end digs into the wrist.
        fillet(p.edges().filter_by(Axis.Z), radius=corner_r)

        # Break every top + skin-side perimeter edge so nothing sharp touches skin
        # (edge-break size from the manufacturing profile's edge-break default; one radius family).
        skin = p.faces().sort_by(Axis.Z)[0]
        top = p.faces().sort_by(Axis.Z)[-1]
        fillet(skin.edges() + top.edges(), radius=edge_break)

        # Adjustment slot toward one end -> a slot-and-pin ladder fits a range of wrists.
        with Locations((band_len / 2 - slot_len / 2 - corner_r, 0, 0)):
            Box(slot_len, slot_w, 3 * band_t, mode=Mode.SUBTRACT)

    show(p.part, name="Strap")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

For a closed cuff or a clip, model the flex region as its own thinned, root-filleted section (a
living hinge or a cantilever), on layered processes (FDM) keep the bend **along the layers**, and add a snap or buckle as
the closure ([manufacturability](../references/manufacturability.md#decision-rules)). A two-part
strap-plus-buckle is a multi-part design — `show()` each part separately (no `explode` parameter;
exploded view is a viewport control) and review the fit with an exploded
`capture_views(..., explode=70)` (see `solidifai-modeling` multi-part guidance).

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **Worn where** — wrist, arm, ankle, belt, or strapped to skin? Sets the contact circumference, the
  band width and length, and how much it must wrap (a wrist cuff curls tightly; a belt clip barely
  flexes).
- **What size range must it fit?** One person, or a population? Drives the **adjustment** mechanism
  and its span — size reach to the 5th percentile and closure to the 95th
  ([ergonomics](../references/ergonomics.md#decision-rules)); add the gloved/sleeve allowance if it's
  worn over clothing.
- **Rigid or flexible?** A rigid clip/housing wants stiffness and a snap closure; a flexible band
  wants a thinned, fatigue-resistant flex region. This decides whether you thin a hinge or brace a
  shell.

## Verify checklist

- **Visual** — `capture_views(["iso", "bottom"])` (the **bottom** is the skin side). Confirm **no
  sharp edge on any skin-contact surface** — the underside and both long edges are visibly broken in
  one radius family, with no stray square corner
  ([ergonomics](../references/ergonomics.md#verify),
  [aesthetics-form](../references/aesthetics-form.md#verify)) — and that the flex region looks thin
  enough to wrap and the hinge/clip root is filleted, not a sharp notch
  ([structure](../references/structure.md#verify)).
- **Assert (computed)** — read **mass** from `get_model_info()` and confirm it's within reason for a
  worn part (this one is genuinely *measured*, not known-by-construction); `valid` and `manifold` are
  both true; the bounding box matches the strap dimensions you set.
- **Assert (known-by-construction)** — the **flex region thickness is below the default wall but
  still ≥ the active process's minimum wall** so it bends without snapping yet stays manufacturable
  ([manufacturability](../references/manufacturability.md#verify)); every skin-contact edge carries
  the edge-break fillet; every hinge/clip root fillet is **≥ ~0.5× the beam thickness**
  ([structure](../references/structure.md#verify)). You *set* these, so you know them — say which
  checks are computed (mass, bbox, manifold) and which are known-by-construction.
- **Held by the body, nothing floating** — a worn part carries gravity through the strap/clasp, not
  a base, so confirm that interface closes and bears; run `check_interferences()` so the strap,
  clasp, and any insert read as `adjacent`/`clear` with nothing `disjoint`/floating or unintentionally
  overlapping ([support-stability](../references/support-stability.md#verify)).

## Common failure modes

- **Sharp skin-contact edges** — a raw box edge or square corner against the wrist chafes and reads
  as un-designed. Break the underside, both long edges, and every corner the body meets in one
  radius family ([ergonomics](../references/ergonomics.md#decision-rules),
  [aesthetics-form](../references/aesthetics-form.md#decision-rules)).
- **Too heavy** — a chunky slab worn all day gets taken off and lost. Trim to the thinnest manufacturable
  section that works, prefer a narrow relieved band, and check the reported **mass**.
- **No size adjustment** — one fixed length fits almost no one. Add a real adjustment range (slot
  ladder, hole set, sliding clip) sized to the 5th- and 95th-percentile wearer
  ([ergonomics](../references/ergonomics.md#decision-rules)).
- **A flex region that will fatigue / crack** — a thin bend with a sharp root, over-strained, or (on
  layered processes) bending *across* the layers delaminates and snaps after a few flexes. Fillet the root
  (≥ ~0.5× thickness), keep the strain within the material's limit, and on layered processes (FDM) pull the bend **along the
  layers** ([structure](../references/structure.md#decision-rules),
  [manufacturability](../references/manufacturability.md#data--defaults)).
