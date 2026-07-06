# stand-cradle playbook

A stand, dock, or cradle that holds a device up at an angle — a phone stand, a tablet dock, a
headset cradle, a controller charging stand. The job is to present the device at a usable viewing
or charging angle on a base wide enough that it never tips over, with a clear path for the cable and
no sharp edge against the device's case. Numbers come from the lenses below — this playbook composes
them, it does not restate them.

## Scope

A **stand / dock / cradle** that holds a device at an angle: a phone or tablet stand, a charging
dock, a controller or headset cradle, a desktop display stand. The device leans back against a rest
at a chosen **viewing/use angle**, a **base** keeps it upright and stable, a **cable** reaches the
device, and the surfaces the device touches are relieved so they don't mar it. Use this when the
part's job is *to hold something else up at an angle*. If the part is the held device's own case,
use `handheld-enclosure.md`; if it's a box with a lid, use `container-lid.md`; if it bolts one rigid
thing to another, use `bracket-mount.md`.

## Lenses it pulls

- [support-stability](../references/support-stability.md#decision-rules) — **stability and
  tip-over**: the base footprint must be wide enough (and the stand low/heavy enough) that the
  loaded centre of gravity stays inside the base so it can't topple. The base / CoG / tip-over
  rules are owned here.
- [structure](../references/structure.md#decision-rules) — the **cantilevered rest braced/filleted
  at its root** so it doesn't snap where it meets the base. The load-path and root-fillet rules are
  owned here.
- [ergonomics](../references/ergonomics.md#decision-rules) — the **viewing/use angle** and reach:
  the device should sit at a comfortable angle for how it's used (glanced at, typed on, watched),
  and any control or port on the cradled device must stay reachable. Human-posture and reach
  dimensions are owned here.
- [affordance-usability](../references/affordance-usability.md#decision-rules) — **cable access**:
  the cable must have an obvious, unobstructed route in to the device and a clear exit, grouped to
  one side/face so it isn't pinched between the device and the rest. How the part presents the
  device and its port is owned here.
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — **soft, relieved
  device-contact edges** in one radius family (no raw edge against the device's case), a relieved /
  weighted base so a block doesn't look like it's sinking into the desk, and a deliberate stance.
  The contact-edge *size* and which surfaces count as touched are human-dimension calls owned by
  [ergonomics](../references/ergonomics.md#decision-rules).
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens** (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that process). The [manufacturability hub](../references/manufacturability.md) routes by process.

## Default recipe

Defaults, each traceable to a lens — adjust to the device and the use, don't invent past these:

- **A base footprint wide enough that the centre of gravity stays inside it.** A leaned-back device
  pushes the combined centre of gravity *backward and up*; the base must extend far enough behind
  (and be low/heavy) that a vertical line down from that CoG lands well inside the base, so the stand
  can't tip — the tip-over call is owned by
  [support-stability](../references/support-stability.md#decision-rules), and bracing the rest's
  cantilever root by [structure](../references/structure.md#decision-rules). Wider and lower is more stable; keep the
  base deeper than the device leans back.
- **A cradle angle suited to viewing/use.** Lean the rest back to the angle the use wants — a
  near-upright lean for a glanced-at phone, a shallower lean for a tablet you type on or watch — so
  the device sits at a comfortable viewing/use angle and its controls stay reachable
  ([ergonomics](../references/ergonomics.md#decision-rules)). State the angle you assumed.
- **A cable routing channel.** Cut a **slot/channel** that carries the cable under the device and out
  to a chosen exit side, so the cable reaches the port without being pinched between the device and
  the rest and the stand still sits flat — group the route to one side/face per
  [affordance-usability](../references/affordance-usability.md#decision-rules). Size the slot so the
  connector and cable clear it.
- **A front lip / shelf the device rests against** so it can't slide off the front, sized to catch
  the device's bottom edge without covering a front-face control.
- **Soft, relieved device-contact edges, one radius family.** Break/relieve every edge the device's
  case or a hand touches so nothing is sharp against it
  ([aesthetics-form](../references/aesthetics-form.md#decision-rules), with the touched-edge rule and
  size owned by [ergonomics](../references/ergonomics.md#decision-rules)); reuse one radius, and
  fillet the cantilevered rest root for stiffness
  ([structure](../references/structure.md#decision-rules)).

### Runnable starter

A parametric stand: a wide, low **base** for stability, an **angled back rest** the device leans
into, a **front lip** so it can't slide off, and a **cable slot** cut up through the base and out the
back so the cord reaches the device's port. It stays **one solid** (a stand is a single part,
not an assembly). Tweak with `set_params(...)` — widen `base_w` / lower the CoG for more stability,
change `angle` for the viewing angle, size `cable_w` to the connector.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Locations,
    Mode,
    Rotation,
    fillet,
)
from solidifai import show

PARAMS = {
    "base_l":  {"value": 120.0, "min": 70.0,  "max": 220.0, "step": 1.0, "unit": "mm", "desc": "Base length (X)"},
    "base_w":  {"value": 120.0, "min": 70.0,  "max": 220.0, "step": 1.0, "unit": "mm", "desc": "Base depth (Y) — wider = more stable"},
    "base_h":  {"value": 12.0,  "min": 6.0,   "max": 30.0,  "step": 1.0, "unit": "mm", "desc": "Base thickness (Z) — lower CoG"},
    "rest_t":  {"value": 10.0,  "min": 4.0,   "max": 20.0,  "step": 0.5, "unit": "mm", "desc": "Back-rest thickness"},
    "rest_h":  {"value": 95.0,  "min": 40.0,  "max": 160.0, "step": 1.0, "unit": "mm", "desc": "Back-rest height"},
    "angle":   {"value": 20.0,  "min": 5.0,   "max": 45.0,  "step": 1.0, "unit": "deg","desc": "Lean from vertical (viewing angle)"},
    "lip_h":   {"value": 14.0,  "min": 6.0,   "max": 30.0,  "step": 1.0, "unit": "mm", "desc": "Front-lip height (catches the device)"},
    "lip_t":   {"value": 8.0,   "min": 4.0,   "max": 16.0,  "step": 0.5, "unit": "mm", "desc": "Front-lip thickness"},
    "cable_w": {"value": 18.0,  "min": 8.0,   "max": 30.0,  "step": 1.0, "unit": "mm", "desc": "Cable slot width (>= connector)"},
    "edge_r":  {"value": 3.0,   "min": 0.5,   "max": 8.0,   "step": 0.5, "unit": "mm", "desc": "Device-contact edge fillet"},
}


def build(base_l, base_w, base_h, rest_t, rest_h, angle, lip_h, lip_t, cable_w, edge_r):
    # Rest sits in from the back edge so its lean stays over the base; the lip
    # sits in from the front. The device leans back into the rest, bottom on the lip.
    rest_y = -base_w / 2 + rest_t / 2 + 10.0
    lip_y = base_w / 2 - lip_t / 2 - 10.0
    span = base_l * 0.7  # rest/lip span most of the base width, not all of it

    with BuildPart() as p:
        # Wide, low base footprint -> the loaded centre of gravity stays inside it.
        Box(base_l, base_w, base_h, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Angled back rest the device leans into, tilted back from vertical.
        with Locations((0, rest_y, base_h)):
            with Locations(Rotation(angle, 0, 0)):
                Box(span, rest_t, rest_h, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Front lip so the device can't slide off the front of the cradle.
        with Locations((0, lip_y, base_h)):
            Box(span, lip_t, lip_h, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Cable routing slot: a channel cut up through the base, running under the
        # device and out the back behind the rest, so the cord isn't pinched.
        with Locations((0, -base_w / 4, base_h / 2)):
            Box(cable_w, base_w / 2 + rest_t + 20.0, base_h, mode=Mode.SUBTRACT)

        # Soften the vertical device-contact edges -> one radius family, nothing sharp.
        fillet(p.edges().filter_by(Axis.Z), radius=edge_r)

    show(p.part, name="Cradle")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

If the cable exits the **side** rather than the back, rotate the slot or run it to a side edge; if
the device is heavy (a tablet), widen and lower the base further and fillet/gusset the rest root so
the cantilever doesn't crack ([structure](../references/structure.md#decision-rules)).

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **What's the device's size and weight?** A phone, a tablet, and a headset want very different
  cradle widths, rest heights, and — because a heavier, taller device pushes the centre of gravity
  back and up — a wider, lower, heavier base to stay stable
  ([support-stability](../references/support-stability.md#questions-that-matter)). Sets the whole footprint.
- **What use angle?** Glanced at (near-upright), watched, or typed on (shallower)? The lean drives
  the rest angle and how far back the base must reach
  ([ergonomics](../references/ergonomics.md#questions-that-matter)).
- **Which side does the cable exit?** Back or a side, and which port — sets where the cable channel
  runs and where it breaks out so the cable isn't pinched
  ([affordance-usability](../references/affordance-usability.md#questions-that-matter)).

## Verify checklist

- **Assert (reasoned from geometry / known-by-construction):** the **base footprint contains the
  loaded centre of gravity** — reason it from the geometry you built (the base extends far enough
  behind the lean that a vertical from the combined device-plus-stand CoG falls inside the base, and
  the base is low/heavy enough not to tip). `get_model_info()` gives the stand's own bounding box,
  volume, and mass, but **not** the device's mass or the combined CoG, so the tip-over margin is a
  geometric argument plus the assumed device weight, **not** a value measured back — say so
  ([support-stability](../references/support-stability.md#verify)). The **cable slot width ≥ the connector** and the
  **rest root is filleted** are known-by-construction (you set them).
- **Visual:** `capture_views(["right", "iso"])` (a side view reads the **angle** and the cable path
  directly). Confirm the device would sit at the **intended viewing/use angle**
  ([ergonomics](../references/ergonomics.md#verify)), the **cable has a clear, unpinched route** in
  and a visible exit ([affordance-usability](../references/affordance-usability.md#verify)), the base
  looks **wide and grounded** (not tippy or top-heavy), and the **device-contact edges are relieved**
  in one radius family with nothing sharp where the case rests
  ([aesthetics-form](../references/aesthetics-form.md#verify)).

## Common failure modes

- **Tips over** — a base too narrow/shallow or too tall and light for a leaned-back (especially
  heavy) device puts the centre of gravity outside the footprint and it topples. Widen, lower, and
  deepen the base until the CoG sits well inside it
  ([support-stability](../references/support-stability.md#decision-rules)).
- **Wrong angle** — too upright and the screen glares or the device slides; too far back and it
  won't stay or is awkward to view/use. Set the lean to the actual use and state it
  ([ergonomics](../references/ergonomics.md#decision-rules)).
- **Cable pinched or no exit** — no channel (the cord is crushed between device and rest, or props
  the device off the rest) or a slot too small for the connector. Cut a routing channel sized to the
  connector with a clear exit on the chosen side
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **Sharp device-contact edges** — a raw edge where the rest or lip meets the device's case scratches
  it and reads as un-designed. Relieve every contact edge in one radius family
  ([aesthetics-form](../references/aesthetics-form.md#decision-rules); size and which-surfaces from
  [ergonomics](../references/ergonomics.md#decision-rules)).
