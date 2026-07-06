# container-lid playbook

A box, case, or canister and the lid that closes it — the job is two parts that actually come
apart and reliably go back together. The base holds the contents at a manufacturable wall; the lid
seats with a real clearance gap and a chosen closure (snap, friction, or thread) and gives the
fingers something to grip when opening. Numbers come from the lenses below — this playbook
composes them, it does not restate them.

## Scope

A **container + lid**: a hollow base (box, case, canister, battery compartment) closed by a
removable **lid** through a defined **closure** — a **snap-fit** (tool-free, repeated, latches
shut), a **friction/press fit** (a lip that holds by interference alone), or a **threaded** screw
cap. The two parts must mate with a real gap and must separate; the lid needs a **finger relief**
so a hand can open it. Use this when the part is fundamentally *a thing to keep contents in and
get back into*. If it's held *and* operated (controls, ports), that's `handheld-enclosure.md`; if
it's mostly a thing to grab, that's `grip-handle.md`.

## Lenses it pulls

- [manufacturability](../references/manufacturability.md#data--defaults) — the **minimum wall for
  the active process** and default wall, the canonical **mating clearance for the active process** for the lid lip (linked, not a
  number invented here), and the **closure strategy** itself
  ([snap-fit vs. friction vs. threaded](../references/manufacturability.md#decision-rules), with
  the snap-fit root-fillet and, on layered processes, the pull-along-the-layers rules). The closure
  *strategy* is chosen at the hub; the mating-clearance *number* is the canonical one owned by
  solidifai-modeling (linked from the hub, not invented here).
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens** (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that process). The manufacturability hub above routes by process.
- [affordance-usability](../references/affordance-usability.md#decision-rules) — **how it opens and
  closes**: the lid must signify which way it comes off (a thumb scallop, a tab, a knurled cap),
  the relief must be reachable, and the closure should give feedback (a snap's click, a thread's
  seat) so the user knows it's shut.
- [structure](../references/structure.md#decision-rules) — **lip and rim stiffness**: a thin
  sealing lip or a snap cantilever needs a filleted root so it doesn't crack, and a tall rim wants
  enough section (or a return flange) not to splay open when the lid is pressed on.
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — one **radius family** across
  base and lid, the **seam tucked on the rim edge** rather than across a show face, and a
  deliberate proportion so the lid reads as part of the same object, not a mismatched cap.
- [sealing-ingress](../references/sealing-ingress.md#decision-rules) — only if the contents must
  stay dry/dust-free (gasket or tongue-and-groove to an IP target; note you then can't vent it).

## Default recipe

Defaults, each traceable to a lens — adjust to the contents and the closure, don't invent past
these:

- **Walls ≥ the active process's minimum.** Use the default-part wall from
  [manufacturability](../references/manufacturability.md#data--defaults) (a real container wall,
  not a one-bead shell); never below the active process's minimum wall. A wall that
  takes the lid's lip or a snap should sit at the load-bearing end of that range.
- **Lid lip with a real clearance gap.** A drop-in or snap lid plugs into the opening with the
  canonical **mating clearance for the active process** from
  [manufacturability](../references/manufacturability.md#data--defaults) — link to that home, don't
  pick a new number. Use the *tight* end for a press/friction lip that should hold by interference,
  the *loose* end for an easy lift-off lid that should locate but not jam. **Never model the lip
  coincident with the rim.**
- **Pick one closure and fit it right**, per
  [manufacturability](../references/manufacturability.md#decision-rules):
  - **Snap-fit** — tool-free, repeated open/close, latches shut with a felt click. A cantilever
    snap or a continuous lip bump needs a **filleted root** (the snap root-fillet rule is owned by
    manufacturability); on layered processes (FDM) it should be pulled roughly **along the layers** so it doesn't
    delaminate.
  - **Friction / press fit** — simplest; the lip holds by interference alone, so it lives at the
    *tight* end of the canonical clearance. Trades a clean look for a firmer pull to open.
  - **Threaded** — a screw cap for a sealed or frequently-opened canister; on FDM prefer a
    coarse/large-pitch modeled thread (fine FDM threads are weak), and give the threads their
    own clearance per manufacturability.
- **A finger relief to open.** Give the lid a **thumb scallop, a pull tab, or a knurled/flatted
  grip** so a hand can break the seal — a flush lid with a tight fit and nothing to grip cannot be
  opened. Make it a visible signifier of how it comes off
  ([affordance-usability](../references/affordance-usability.md#decision-rules)); the grip-edge
  size and which surfaces count as touched are human-dimension calls owned by ergonomics via that
  lens.
- **Filleted touched edges, one radius family** across base and lid
  ([aesthetics-form](../references/aesthetics-form.md#decision-rules)); fillet a thin lip's root for
  stiffness ([structure](../references/structure.md#decision-rules)).

This is a **two-part model**: `show()` the **base and the lid separately**, each with its own
`name=`, so they stay distinct and inspectable. **Don't add an `explode` parameter** — exploded
view is a built-in viewport control. To check the fit yourself, capture an exploded render with
`capture_views(["iso", "front"], explode=70)`: it spreads the parts for that one render without
changing the model. The full multi-part pattern is owned by **solidifai-modeling**:
[multi-part models](../../solidifai-modeling/SKILL.md#multi-part-models).

### Runnable starter

A parametric base (shelled box, top open) plus a **separate** drop-in lid: a flat cap over the rim
and a plug that drops into the opening with `clear` of gap on every side (the canonical mating
clearance — link to its home, don't re-pick the value), with a thumb-relief notch in the cap so it
can be lifted off. Each part is its own `show()` object and stays its own manifold solid; capture
an exploded render (`capture_views(..., explode=70)`) to confirm the fit. Tweak with `set_params(...)`.

> The wall value below is illustrative; for a real build, read `get_manufacturing_profile()` and use its `design.wallMm` in place of this literal.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Locations,
    Mode,
    offset,
)
from solidifai import show

PARAMS = {
    "length":  {"value": 70.0, "min": 30.0, "max": 200.0, "step": 1.0,  "unit": "mm", "desc": "Box length (X)"},
    "width":   {"value": 50.0, "min": 30.0, "max": 200.0, "step": 1.0,  "unit": "mm", "desc": "Box width (Y)"},
    "height":  {"value": 35.0, "min": 12.0, "max": 120.0, "step": 1.0,  "unit": "mm", "desc": "Box height (Z)"},
    "wall":    {"value": 2.4,  "min": 1.2,  "max": 6.0,   "step": 0.2,  "unit": "mm", "desc": "Wall thickness"},
    "clear":   {"value": 0.2,  "min": 0.1,  "max": 0.6,   "step": 0.05, "unit": "mm", "desc": "Lid lip clearance / side"},
}


def build(length, width, height, wall, clear):
    # Base: bottom-closed, top-open box hollowed to a uniform wall.
    with BuildPart() as base_b:
        Box(length, width, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        top = base_b.faces().sort_by(Axis.Z)[-1]
        offset(amount=-wall, openings=top)
    base = base_b.part

    # Lid: a flat cap over the rim + a plug that drops into the opening with
    # `clear` of gap on every side (the canonical mating clearance for the active process), and a
    # thumb-relief notch in one end of the cap so a finger can lift it off.
    plug_depth = min(6.0, height - wall - 1.0)
    inner_l = length - 2 * wall - 2 * clear
    inner_w = width - 2 * wall - 2 * clear
    relief = min(14.0, width * 0.4)  # finger scallop width
    with BuildPart() as lid_b:
        with Locations((0, 0, height)):
            Box(length, width, wall, align=(Align.CENTER, Align.CENTER, Align.MIN))  # cap
        with Locations((0, 0, height - plug_depth)):
            Box(inner_l, inner_w, plug_depth, align=(Align.CENTER, Align.CENTER, Align.MIN))  # plug
        # Thumb relief: notch the +Y edge of the cap so a finger can grip under it.
        with Locations((0, width / 2, height + wall / 2)):
            Box(relief, 2 * wall, 2 * wall, mode=Mode.SUBTRACT)
    lid = lid_b.part

    show(base, name="Base", material="petg")
    show(lid,  name="Lid",  material="petg", color=(0.85, 0.5, 0.2))


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **How should it open?** Snap-fit (tool-free, repeated, latches), friction/press (simplest, firm
  pull), or threaded (sealed-ish, twist on/off). This is the single decision that drives the whole
  closure and the lip fit; if it's unclear, default to a friction lid and say so.
- **Sealed or not?** A splash/dust seal wants a continuous lip and a tighter fit (or a thread/
  gasket land); an open organizer can take a loose lift-off lid. FDM parts aren't watertight
  by default — flag that if a real seal is needed.
- **One- or two-handed to open?** A one-handed pop (a snap with a thumb scallop) differs from a
  two-handed twist (a thread, or a press lid you brace and lift). Sets where and how big the finger
  relief goes.

## Verify checklist

- **Assert (known-by-construction)** — the lid lip clearance is **≥ the canonical mating value for the active process**
  ([manufacturability](../references/manufacturability.md#verify)); you *set* that gap, so you know
  it — not measured back from `get_model_info()`. Every wall is **≥ the active process's minimum wall**.
  The base and the lid plug are **non-coincident** by exactly that clearance.
- **Assert (computed)** — `get_model_info()` lists the base and the lid as **two separate objects**
  (not one fused body), and both report `valid` and `manifold` true. The base cavity ≥ the intended
  contents.
- **Visual** — `capture_views(...)` **assembled**, then **exploded** with
  `capture_views(["iso", "front"], explode=70)` (a render-time spread that never touches the model):
  confirm the lid actually seats on the rim with a visible gap (not interfering, not floating),
  the chosen closure reads correctly, and there is a **reachable finger relief** to open it
  ([affordance-usability](../references/affordance-usability.md#verify)). Check the edges share one
  radius family and the seam sits on the rim
  ([aesthetics-form](../references/aesthetics-form.md#verify)).
- **Stability + fit** — run `check_interferences()`: the lid and base should read `adjacent` (mating
  with the clearance gap), never `overlap` (the lip interpenetrating the wall), and each part should
  be a single body with nothing `disjoint`/floating. If the closed box must stand, confirm its base
  supports it ([support-stability](../references/support-stability.md#verify)).

## Common failure modes

- **Lid coincident or interfering with the rim** — a lip modeled with zero (or negative) gap won't
  close, or jams and cracks the wall. Give it the canonical mating clearance; never model the
  mating faces coincident ([manufacturability](../references/manufacturability.md#decision-rules)).
- **No way to grip it open** — a flush, tight lid with no scallop, tab, or knurl can't be opened by
  hand. Add a finger relief and make it a visible signifier of how it comes off
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **Wall too thin** — a one-bead container splits when handled or when the lid is pressed on. Keep
  walls ≥ the active process's minimum wall
  ([manufacturability](../references/manufacturability.md#data--defaults)); fillet a thin lip's root
  ([structure](../references/structure.md#decision-rules)).
- **Fused into one body when it must come apart** — modeling the base and lid as a single solid
  (or boolean-unioning them) means there's no lid at all. Keep them as **two separate `show()`
  objects** so they stay distinct and demonstrably separable; an exploded
  `capture_views(..., explode=70)` confirms they actually part
  ([multi-part guidance](../../solidifai-modeling/SKILL.md#multi-part-models)).
