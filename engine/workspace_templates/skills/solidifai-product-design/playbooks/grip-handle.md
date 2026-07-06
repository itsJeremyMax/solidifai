# grip-handle playbook

A handle, lever, or tool grip — something a hand wraps a fist around and holds, pulls, or turns.
The job is a graspable shaft that fits the closed hand, breaks every end edge so nothing bites,
gives torque purchase when the grip is twisted, and braces its root so the handle doesn't snap
off where it meets the rest of the part. Numbers come from the lenses below — this playbook
composes them, it does not restate them.

## Scope

A **grip / handle / lever** you wrap a hand around: the cylindrical (or oval) shaft of a tool
handle, a pull, a lever arm, a bar grip. Held in a **power grip** (full fist, not fingertips) and
either pulled/pushed or twisted for torque. Use this when the part is mostly *a thing to grab*. If
it's a small control turned by the fingertips (a dial or knob), use `knob-control.md`; if the grip
is one feature on a held device that also carries controls and ports, use `handheld-enclosure.md`;
if the focus is the mounting bracket the handle bolts to, use `bracket-mount.md`.

## Lenses it pulls

- [ergonomics](../references/ergonomics.md#decision-rules) — the **power-grip cylinder Ø** band a
  closed fist wraps comfortably, and the grip **length** a full hand needs (set from hand breadth).
  Every hand dimension is owned here; this playbook links, it does not restate the numbers.
- [affordance-usability](../references/affordance-usability.md#decision-rules) — **orientation and
  feedback**: the handle should read as graspable and only fit the hand one obvious way, with a
  texture/flat that tells the hand how it's held and gives torque purchase when it's turned.
- [structure](../references/structure.md#decision-rules) — the **handle-root load**: a held handle
  is a cantilever, so the corner where it meets its base is a stress riser that must be filleted (or
  gusseted) per the internal-corner rule, sized to the wall it joins.
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — break every end edge in **one
  radius family**, keep the shaft a deliberate proportion (a clean length:Ø, not an accidental
  stub), and let any knurl/flat be an honest functional texture rather than decoration.
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens** (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that process). The [manufacturability hub](../references/manufacturability.md) routes by process.

## Default recipe

Defaults, each traceable to a lens — adjust to the hand and the load, don't invent past these:

- **Grip Ø in the power-grip band.** A fist-wrapped handle sits in the **power-grip cylinder band**
  (~38 mm is a good default optimum) from
  [ergonomics](../references/ergonomics.md#data--defaults). Below the band the hand can't close
  firmly; above it the fingers can't wrap. Link to that band, don't pick a new number.
- **Length ≥ a full hand's breadth.** The grip must be at least the **hand breadth across the
  knuckles** (size to the ~95th-percentile breadth so the largest hand still fits) from
  [ergonomics](../references/ergonomics.md#decision-rules) — a short stub leaves fingers hanging off
  the end. Two-handed grips get roughly double.
- **Filleted ends, one radius family.** Round the free end (and any shoulder the palm or web of the
  thumb rides over) so no grip surface is sharp
  ([aesthetics-form](../references/aesthetics-form.md#decision-rules), with the touched-edge rule
  owned by [ergonomics](../references/ergonomics.md#decision-rules)). Reuse one end radius; don't
  give each edge its own value.
- **Knurl or a flat for torque if it's turned.** A grip that's *twisted* (a tap handle, a valve
  lever, a screwdriver) needs a **texture or a flat** so the hand transmits torque without slipping
  — a signifier that also tells the hand its orientation
  ([affordance-usability](../references/affordance-usability.md#decision-rules)). A grip only
  pulled/pushed can stay smooth.
- **Gusset / fillet at the load root.** The handle is a cantilever; fillet the **internal corner
  where the shaft meets its base** (radius ≥ ~0.5× the joined wall) and add a gusset if the lever
  arm is long or the load is high, per
  [structure](../references/structure.md#decision-rules). Never leave the root a sharp notch — that
  is where a handled part cracks.

### Runnable starter

A parametric filleted grip cylinder standing on a base plate, with the **free end rounded** and the
**handle-root corner filleted** (the load corner). Tweak with `set_params(...)`. The two fillets
are clamped to stay inside their geometry — if a radius would be too large for the diameter or base,
it is reduced rather than dropped, so the build stays valid and manifold.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Cylinder,
    GeomType,
    Locations,
    fillet,
)
from solidifai import show

PARAMS = {
    "grip_dia":  {"value": 38.0,  "min": 30.0, "max": 50.0,  "step": 1.0, "unit": "mm", "desc": "Grip Ø (power-grip band)"},
    "grip_len":  {"value": 110.0, "min": 80.0, "max": 160.0, "step": 1.0, "unit": "mm", "desc": "Grip length (>= hand breadth)"},
    "base_l":    {"value": 70.0,  "min": 40.0, "max": 140.0, "step": 1.0, "unit": "mm", "desc": "Base length (X)"},
    "base_w":    {"value": 50.0,  "min": 30.0, "max": 120.0, "step": 1.0, "unit": "mm", "desc": "Base width (Y)"},
    "base_h":    {"value": 10.0,  "min": 5.0,  "max": 25.0,  "step": 1.0, "unit": "mm", "desc": "Base plate thickness"},
    "end_r":     {"value": 8.0,   "min": 1.0,  "max": 18.0,  "step": 0.5, "unit": "mm", "desc": "Grip end fillet radius"},
    "root_r":    {"value": 5.0,   "min": 1.0,  "max": 12.0,  "step": 0.5, "unit": "mm", "desc": "Root fillet radius (load corner)"},
}


def build(grip_dia, grip_len, base_l, base_w, base_h, end_r, root_r):
    r = grip_dia / 2.0
    # Keep each fillet inside its geometry; if one is too big, shrink it, don't drop it.
    end_r = min(end_r, r - 1.0, grip_len / 2 - 1.0)
    root_r = min(root_r, r - 1.0)

    with BuildPart() as p:
        # Base plate on the bed (bottom at z = 0); the grip roots into its top.
        Box(base_l, base_w, base_h, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Grip cylinder standing up from the base top face -> a power-grip shaft.
        with Locations((0, 0, base_h)):
            Cylinder(radius=r, height=grip_len, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Round the free top end so the grip is comfortable, not sharp.
        top_edge = p.edges().filter_by(GeomType.CIRCLE).sort_by(Axis.Z)[-1]
        fillet(top_edge, radius=end_r)

        # Fillet the handle-root circle where the grip meets the base -> the load corner.
        root_edge = p.edges().filter_by(GeomType.CIRCLE).sort_by(Axis.Z)[0]
        fillet(root_edge, radius=root_r)

    show(p.part, name="Grip")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

If the grip is **turned** for torque, add a knurl or a flat to the shaft (a shallow texture or a
milled flat, `mode=Mode.SUBTRACT`) so the hand doesn't slip; if it's only pulled, leave it smooth.
For a longer lever arm, gusset the root rather than just enlarging the fillet — see
[structure](../references/structure.md#decision-rules).

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **Gripped or turned?** A grip that transmits **torque** (twisted) needs a knurl or a flat for
  purchase and a stronger root; a grip only pulled/pushed can be smooth. This changes the surface
  and the root sizing.
- **One- or two-handed?** Sets the grip **length** — one hand needs ≥ a hand breadth, two hands need
  roughly double (and possibly a center relief between them).
- **How much load at the root, and from where?** A light pull and a body-weight lever want very
  different roots; an order-of-magnitude is enough to choose fillet-only vs. gusset, or to flag that
  a real structural check is needed ([structure](../references/structure.md#questions-that-matter)).

## Verify checklist

- **Assert (computed / known-by-construction):** the modeled **grip Ø is within the power-grip
  band** — you set the diameter, so it's known-by-construction, and a cylindrical grip's Ø also reads
  back from the `get_model_info()` bounding box (the grip's cross-section). The grip **length ≥ the
  hand-breadth minimum** (known from the dimension you set). Both bands are owned by
  [ergonomics](../references/ergonomics.md#verify).
- **Assert (known-by-construction):** the **root fillet** radius is ≥ ~0.5× the joined wall and the
  **free end is filleted** — you set both radii, so you know them; true min-radius on freeform
  geometry is not recoverable from `get_model_info()`, so say it's known-by-construction
  ([structure](../references/structure.md#verify)).
- **Visual:** `capture_views(["front", "iso"])` and confirm the grip looks a **comfortable length**
  for a full fist (fingers don't hang off the end), the **free end is rounded** (no sharp edge the
  palm hits), the **root is visibly filleted/gusseted** rather than a sharp notch, and any
  knurl/flat reads as a torque-purchase signifier
  ([affordance-usability](../references/affordance-usability.md#verify),
  [aesthetics-form](../references/aesthetics-form.md#verify)).
- **Held, and attached not floating** — the hand carries gravity, so the check is the joint: run
  `check_interferences()` so the grip and whatever it mounts to read as `adjacent` (a real press or
  bonded joint) rather than an unintended `overlap` or a `disjoint`/floating piece
  ([support-stability](../references/support-stability.md#verify)).

## Common failure modes

- **Grip too thin or too thick** — a shaft below the power-grip band can't be closed firmly; one
  above it the fingers can't wrap. Keep the Ø in the band
  ([ergonomics](../references/ergonomics.md#data--defaults)).
- **Too short for the hand** — a stub shorter than a hand breadth leaves fingers hanging off the
  end and is uncomfortable to hold. Size the length to ≥ hand breadth (≈ double for two hands).
- **Sharp ends** — a raw flat-cut end edge bites the palm and reads as un-designed. Fillet the free
  end (and any palm-riding shoulder) in one radius family
  ([aesthetics-form](../references/aesthetics-form.md#decision-rules)).
- **Weak unfilleted root** — a handle is a cantilever; a sharp internal corner at the root is a
  crack waiting to start, especially on brittle beams (FDM especially). Fillet it (radius ≥ ~0.5× the joined wall) and
  gusset a long or heavily-loaded arm ([structure](../references/structure.md#decision-rules)).
- **Smooth grip on a turned handle** — a polished shaft that has to transmit torque slips in the
  hand. Add a knurl or a flat for purchase
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
