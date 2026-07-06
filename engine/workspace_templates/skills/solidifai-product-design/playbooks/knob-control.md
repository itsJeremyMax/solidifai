# knob-control playbook

A dial, knob, button, or small control turned or pressed by the fingers — not wrapped by a fist.
The job is a control sized for **fingertip purchase**, textured so the fingers don't slip, and
honest about what it does: a setting knob points and detents, a button presses and springs back.
Numbers come from the lenses below — this playbook composes them, it does not restate them.

## Scope

A **small control operated by the fingers**: a rotary knob or dial (volume, a stove burner, a
potentiometer cap), a pushbutton, or a small selector — anything turned by the thumb-and-fingertips
(a **precision grip**, not a fist) or pressed by a fingertip. It mounts to a **shaft or interface**
(a D-shaft, a knurled pot shaft, a switch plunger) and, if it sets a value, carries an **indicator**.
Use this when the part is a fingertip-operated control. If it's a fist-wrapped handle or lever you
twist for torque, use `grip-handle.md`; if the control is one feature on a held device that also
carries a grip and ports, use `handheld-enclosure.md`.

## Lenses it pulls

- [ergonomics](../references/ergonomics.md#decision-rules) — the **precision-grip Ø** band a
  fingertip-turned control needs for purchase, and the **pressable-control minimum** (finger-pad
  size) plus comfortable size for a button. Every finger dimension is owned here; this playbook
  links, it does not restate the numbers.
- [affordance-usability](../references/affordance-usability.md#decision-rules) — **Fitts's law**
  (a bigger, closer control is faster to hit) and **feedback**: a setting knob needs a detent or a
  hard stop and an indicator mark; a button needs felt travel. A control with no felt or seen
  response reads as broken even when it works.
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — keep the knurl or flutes a
  consistent, **honest functional texture** (not random decoration), break the touched top edge in
  one radius family, and give the knob a deliberate Ø:height proportion rather than an accidental
  stub or tower.
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens** (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that process). The [manufacturability hub](../references/manufacturability.md) routes by process.

## Default recipe

Defaults, each traceable to a lens — adjust to the finger and the interface, don't invent past these:

- **Knob Ø in the precision-grip band.** A fingertip-turned knob sits in the **precision-grip Ø
  band** (thumb + fingertips, not a fist) from
  [ergonomics](../references/ergonomics.md#data--defaults). Below the band the fingers can't pinch
  it firmly to turn; far above it you're back in handle territory. Link to that band, don't pick a
  new number.
- **Knurl or flutes for grip.** A turned control needs **surface texture** so the fingertips
  transmit torque without slipping — flutes (a polar pattern of grooves) or a knurl, which also
  signifies "turn me" ([affordance-usability](../references/affordance-usability.md#decision-rules),
  texture-for-purchase owned by [ergonomics](../references/ergonomics.md#decision-rules)). Model
  flutes as a polar pattern of subtracted cylinders around the rim.
- **A detent + indicator if it sets a value.** A knob that selects a setting needs an **indicator**
  (a pointer rib, a printed line, a flatted skirt) so the value reads at a glance, and ideally a
  **detent or hard stop** so positions are felt, not guessed
  ([affordance-usability](../references/affordance-usability.md#decision-rules)). An on/off or
  continuous knob can skip the indicator; a *setting* knob without one is the classic failure.
- **Buttons sized ≥ the finger-pad minimum, with travel.** A pressable control is at least the
  **pressable-control minimum** (finger-pad size), comfortable size by default, from
  [ergonomics](../references/ergonomics.md#data--defaults), and it must have **real travel and
  relief** — a cap that moves and springs back — so the press is felt. A flush, immovable pad reads
  as broken.
- **A shaft bore that matches the interface.** Cut a **blind bore** up from the bottom sized for the
  shaft it presses onto (a round press-fit, or a D / flatted / splined profile to key the rotation),
  with a small press-fit clearance. Keep the knob **one solid** — the bore is subtracted from the
  body, not a separate part.

### Runnable starter

A parametric fluted knob: a precision-grip cylinder with a polar pattern of subtracted grooves for
finger purchase, a softened top edge, a raised **indicator rib** so the setting reads, and a blind
**shaft bore** up from the bottom to press onto the drive shaft. Tweak with `set_params(...)`. Every
feature is clamped to stay inside the body, so if a groove, bore, or fillet would be too large for
the chosen diameter it is shrunk rather than dropped — the result stays one valid, manifold solid.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Cylinder,
    GeomType,
    Locations,
    Mode,
    PolarLocations,
    fillet,
)
from solidifai import show

PARAMS = {
    "knob_dia":    {"value": 14.0, "min": 8.0,  "max": 24.0, "step": 0.5, "unit": "mm", "desc": "Knob Ø (precision-grip band)"},
    "knob_h":      {"value": 14.0, "min": 8.0,  "max": 30.0, "step": 0.5, "unit": "mm", "desc": "Knob height"},
    "flute_count": {"value": 14,   "min": 6,    "max": 30,   "step": 1,   "unit": "",   "desc": "Number of flutes (grip)"},
    "flute_dia":   {"value": 2.4,  "min": 1.0,  "max": 5.0,  "step": 0.2, "unit": "mm", "desc": "Flute groove Ø"},
    "shaft_dia":   {"value": 6.2,  "min": 3.0,  "max": 12.0, "step": 0.1, "unit": "mm", "desc": "Shaft bore Ø (+ press-fit clearance)"},
    "shaft_depth": {"value": 10.0, "min": 4.0,  "max": 24.0, "step": 0.5, "unit": "mm", "desc": "Shaft bore depth (blind)"},
    "top_r":       {"value": 2.0,  "min": 0.5,  "max": 5.0,  "step": 0.5, "unit": "mm", "desc": "Top rim fillet radius"},
}


def build(knob_dia, knob_h, flute_count, flute_dia, shaft_dia, shaft_depth, top_r):
    r = knob_dia / 2.0
    # Clamp every feature inside the body so the build stays one valid + manifold solid.
    flute_dia = min(flute_dia, knob_dia / 4.0)
    shaft_dia = min(shaft_dia, knob_dia - 4.0)
    shaft_depth = min(shaft_depth, knob_h - 2.0)
    top_r = min(top_r, r - 1.0, knob_h / 2 - 0.5)

    with BuildPart() as p:
        # Knob body: a precision-grip cylinder on the bed (bottom at z = 0).
        Cylinder(radius=r, height=knob_h, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Flutes: a polar pattern of cylinders subtracted from the rim for finger purchase.
        with PolarLocations(radius=r, count=int(flute_count)):
            Cylinder(
                radius=flute_dia / 2.0,
                height=knob_h * 2,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )

        # Break the top rim so the edge a finger rides isn't sharp (one radius family).
        top_edge = p.edges().filter_by(GeomType.CIRCLE).sort_by(Axis.Z)[-1]
        fillet(top_edge, radius=top_r)

        # Indicator rib on top: a raised pointer so the setting reads at a glance.
        with Locations((r * 0.55, 0, knob_h)):
            Box(r * 0.6, 2.0, 1.6, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Shaft bore: a blind hole up from the bottom to press onto the drive shaft.
        bottom = p.faces().sort_by(Axis.Z)[0]
        with Locations(bottom):
            Cylinder(
                radius=shaft_dia / 2.0,
                height=shaft_depth,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    show(p.part, name="Knob")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

To **key** the rotation against a flatted (D-profile) pot shaft, intersect the bore with a box to
flatten one side, or swap the bore cylinder for a D-shaped sketch. For a **pushbutton** instead of a
knob, drop the flutes and the bore, size the cap to the finger-pad minimum, and add a thin skirt with
real travel/relief over a plunger rather than a shaft press-fit (see
[ergonomics](../references/ergonomics.md#decision-rules) and
[affordance-usability](../references/affordance-usability.md#decision-rules)).

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **Turned or pressed?** A rotary knob wants a precision-grip Ø, finger texture, and a shaft bore; a
  button wants a finger-pad-sized cap with travel and relief. This picks the whole recipe.
- **Precise setting, or just on/off?** A knob that **sets a value** needs an indicator and ideally a
  detent / hard stop; an on/off or continuous control can skip the indicator. This decides whether
  the indicator is mandatory ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **What shaft / interface does it mount to?** A round press-fit, a D / flatted shaft, a splined pot
  shaft, or a switch plunger — sets the bore diameter and whether it must be keyed to stop slipping.

## Verify checklist

- **Assert (computed / known-by-construction):** the modeled **knob Ø is within the precision-grip
  band** — you set the diameter, so it's known-by-construction, and the disc Ø also reads back from
  the `get_model_info()` bounding box (the flutes only notch the rim, so the bounding box stays the
  nominal Ø). For a button, the **cap's smallest dimension ≥ the pressable-control minimum**
  (finger-pad size). Both bands are owned by [ergonomics](../references/ergonomics.md#verify).
- **Assert (known-by-construction):** the **shaft bore** is blind (doesn't break the top) and the
  knob is **one solid** — the bore and flutes are subtracted from the body, so `valid` and `manifold`
  are both true from `get_model_info()`; a true minimum wall around the bore on this geometry is not
  recoverable from `get_model_info()`, so report it known-by-construction.
- **Visual:** `capture_views(["iso", "top"])` and confirm the **flutes/knurl read as a grip** the
  fingers could turn (finger purchase, not a smooth slippery disc), a **clear indicator/pointer** is
  visible on a setting knob, and the Ø:height proportion looks like a deliberate knob rather than an
  accidental stub or tower ([affordance-usability](../references/affordance-usability.md#verify),
  [aesthetics-form](../references/aesthetics-form.md#verify)).
- **Seated on its shaft, one body** — the knob hangs on a shaft, so run `check_interferences()` to
  confirm it stays a single connected solid (nothing `disjoint`/floating) and that, when shown with
  the shaft, the bore reads as `adjacent` (a press/clearance fit) rather than an unintended `overlap`
  ([support-stability](../references/support-stability.md#verify)).

## Common failure modes

- **Too small to grip** — a knob below the precision-grip band gives the fingertips nothing to pinch
  and turn. Keep the Ø in the band ([ergonomics](../references/ergonomics.md#data--defaults)); a
  button below the finger-pad minimum is missed as often as hit.
- **No tactile purchase** — a smooth, untextured disc slips in the fingers under any real torque.
  Add knurl or flutes so the fingers transmit the turn
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **No indicator on a setting knob** — a value-setting knob with no pointer, line, or flat leaves the
  user guessing where it's pointed; the position can't be read at a glance. Give a setting knob a
  visible indicator and ideally a detent ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **A button with no travel** — a flush, immovable pad gives no feedback and reads as broken even
  when it works. Give a button real travel and relief — a cap that moves and springs back
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
