# electronics-enclosure playbook

A box for a board: a Raspberry Pi / SBC case, a project box, a sensor housing. The job is a
shell that mounts the board off the floor, passes each connector cleanly through a wall, and
moves enough air that a hot chip doesn't cook. Numbers come from the lenses below — this
playbook composes them, it does not restate them.

## Scope

A **board-in-a-box**: a hollow shell built around a populated circuit board — an SBC case
(Pi/Jetson), a generic project box, a sensor or controller housing. Three concerns dominate:
**mounting** the board on standoffs at its hole pattern (off the floor, screws captive),
**port cutouts** that line up with the connectors on the board's faces (USB/HDMI/Ethernet/
GPIO/SD/power), and **heat** — vents or a fan so a working SoC stays in range. Closed by a
lid (snap-fit or screw-boss). Use this when the part wraps a board. If it's held *and* thumb-
operated, use `handheld-enclosure.md`; if it just stores loose contents, use `container-lid.md`.
If it's a whole device built around several components (a cyberdeck, a mini-PC, a battery pack),
this single-board playbook is too small: use `integrated-device.md`, which lays the contents out
inside-out first.

## Lenses it pulls

- [thermal-ventilation](../references/thermal-ventilation.md#decision-rules) — the heat lens:
  whether the part needs passive vents, a fan, or a heatsink boss, the **open-area target** for
  a vent pattern, and **low-inlet / high-outlet** placement so convection actually sweeps the
  board. Every airflow decision is owned here.
- [dfm-additive](../references/dfm-additive.md#decision-rules) — the active **DFM family lens**
  (additive/FDM by default; swap to the subtractive/formative/sheet lens if the user names that
  process). Sets the self-supporting slot rule for vents and the printable minimum feature.
- [structure](../references/structure.md#decision-rules) — **standoffs and bosses**: a standoff
  tall enough to lift the board's pins off the floor, a wall thick enough to anchor a self-
  tapping screw, a fan/heatsink boss that won't crack.
- [manufacturability](../references/manufacturability.md#data--defaults) — the process + fastening
  hub: default wall and minimum wall, the **lid-closure strategy**
  ([snap-fit vs. screw boss](../references/manufacturability.md#decision-rules)), and which DFM
  family lens governs.
- [fits-tolerances](../references/fits-tolerances.md#decision-rules) — the **lid fit** and the
  **standoff-to-screw fit**: a lip that locates without rattling, a pilot hole sized for a self-
  tapping screw to bite. Each clearance comes from here, not from a guessed number.
- [serviceability-assembly](../references/serviceability-assembly.md#decision-rules) — **getting
  in and back out**: lid access for reflashing/rewiring, **captive screws**, and a single
  assembly direction so the board drops in one way.
- [affordance-usability](../references/affordance-usability.md#decision-rules) — the **port and
  connector layout**: group ports by function, put them on one oriented face where you can, and
  label what isn't obvious so the user plugs the right cable into the right hole.
- [sealing-ingress](../references/sealing-ingress.md#decision-rules) — **only when the box lives
  outdoors or must keep dust/water out**: a gasket groove and a sealed lid trade away the open
  vents, so this fork lands against thermal. Skip it for an indoor desk box.
- [aesthetics-form](../references/aesthetics-form.md#decision-rules) — one **radius family** of
  filleted outer edges and a **seam tucked on an edge** rather than across a show face, so a
  utility box still reads as designed.
- [support-stability](../references/support-stability.md#decision-rules) — it **sits on a desk or
  hangs on a wall**: a flat stable base, feet or a wall/DIN/VESA mount, center of mass inside the
  footprint so it doesn't tip when a stiff cable pulls.

## Default recipe

Defaults, each traceable to a lens — adjust to the board, don't invent past these:

- **Standoffs at the board's mounting-hole pattern**, tall enough to lift the board's solder
  pins off the floor, with a pilot hole sized for the screw to bite — geometry from
  [structure](../references/structure.md#decision-rules), the screw fit from
  [fits-tolerances](../references/fits-tolerances.md#decision-rules).
- **Internal cavity = board + components + clearance.** Size it to the board outline plus the
  tallest component stack plus the canonical board-to-wall gap from
  [fits-tolerances](../references/fits-tolerances.md#data--defaults); the shell's outer size is
  then `cavity + 2·wall`.
- **Port cutouts derived from the connector layout** — not invented, *read off the board*. Each
  opening is the connector footprint plus clearance, at the connector's real height on the face
  it lives on (USB/HDMI/Ethernet/GPIO/SD/power). Group them by function on one oriented face per
  [affordance-usability](../references/affordance-usability.md#decision-rules); the clearance is
  the connector fit from [fits-tolerances](../references/fits-tolerances.md#decision-rules).
- **Vent pattern sized to a thermal open-area target**, placed **low-inlet / high-outlet** so
  convection draws across the board, with each slot wide enough to print and narrow/oriented so
  it self-supports — open area and placement from
  [thermal-ventilation](../references/thermal-ventilation.md#decision-rules), the printable slot
  from [dfm-additive](../references/dfm-additive.md#decision-rules).
- **Optional fan or heatsink boss** when passive vents can't shed the load — a mounting boss
  that anchors the fastener without cracking, per
  [structure](../references/structure.md#decision-rules); the fan-vs-passive call is
  [thermal-ventilation](../references/thermal-ventilation.md#decision-rules)'s.
- **Lid with a real mating clearance** — a snap-fit lid for tool-free repeated access or screw
  bosses for a serviced closure, per
  [manufacturability](../references/manufacturability.md#decision-rules); the lip gap is the
  canonical mating clearance ([solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models),
  tightness from [fits-tolerances](../references/fits-tolerances.md#decision-rules)). Never model
  the lid coincident with the rim.
- **Captive lid hardware and one assembly direction** — screws that stay with the lid and a board
  that drops in one way, per
  [serviceability-assembly](../references/serviceability-assembly.md#decision-rules), so a field
  reflash doesn't shed loose parts.
- **A mount option** when it doesn't just sit on a desk — feet, or a wall / DIN-rail / VESA tab on
  a flat face, with the center of mass inside the footprint per
  [support-stability](../references/support-stability.md#decision-rules).

### Runnable starter

A parametric shell with a closed floor and open top, standoffs on a 2×2 grid at the board's hole
pitch (pilot-drilled), a low inlet band and a high outlet band of self-supporting vent slots
through both long walls (the stack effect — cool air in low, warm air out high), and one port
slot through the end wall above the board. Outer size derives from the board plus components plus
clearance plus wall, so the cavity tracks the board automatically. Tweak with `set_params(...)`.

> The wall, clearance, and fillet values below are illustrative starting points. For a real build,
> read the workspace defaults first with `get_manufacturing_profile()` and use its `design.wallMm`,
> the `fits` clearance for the selected fit, and `design.filletMm` in place of these literals.

```python
from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Cylinder,
    GridLocations,
    Locations,
    Mode,
    fillet,
    offset,
)
from solidifai import show

PARAMS = {
    "board_l":     {"value": 85.0, "min": 30.0, "max": 200.0, "step": 1.0, "unit": "mm", "desc": "Board length (X)"},
    "board_w":     {"value": 56.0, "min": 20.0, "max": 150.0, "step": 1.0, "unit": "mm", "desc": "Board width (Y)"},
    "stack_h":     {"value": 22.0, "min": 8.0,  "max": 80.0,  "step": 1.0, "unit": "mm", "desc": "Component stack height"},
    "wall":        {"value": 2.4,  "min": 1.2,  "max": 4.0,   "step": 0.2, "unit": "mm", "desc": "Shell wall"},
    "clear":       {"value": 1.0,  "min": 0.3,  "max": 3.0,   "step": 0.1, "unit": "mm", "desc": "Board-to-wall gap"},
    "standoff_h":  {"value": 5.0,  "min": 2.0,  "max": 14.0,  "step": 0.5, "unit": "mm", "desc": "Standoff height"},
    "pitch_x":     {"value": 58.0, "min": 10.0, "max": 190.0, "step": 0.5, "unit": "mm", "desc": "Mount-hole pitch X"},
    "pitch_y":     {"value": 49.0, "min": 10.0, "max": 140.0, "step": 0.5, "unit": "mm", "desc": "Mount-hole pitch Y"},
    "screw_dia":   {"value": 2.5,  "min": 1.5,  "max": 5.0,   "step": 0.1, "unit": "mm", "desc": "Standoff pilot dia"},
    "fillet_r":    {"value": 3.0,  "min": 0.5,  "max": 10.0,  "step": 0.5, "unit": "mm", "desc": "Outer corner radius"},
    "vent_w":      {"value": 2.0,  "min": 1.2,  "max": 5.0,   "step": 0.2, "unit": "mm", "desc": "Vent slot width"},
    "vent_n":      {"value": 6.0,  "min": 0.0,  "max": 16.0,  "step": 1.0, "unit": "",   "desc": "Vent slots per band"},
}


def build(board_l, board_w, stack_h, wall, clear, standoff_h, pitch_x, pitch_y,
          screw_dia, fillet_r, vent_w, vent_n):
    inner_l = board_l + 2 * clear
    inner_w = board_w + 2 * clear
    inner_h = stack_h + standoff_h
    out_l = inner_l + 2 * wall
    out_w = inner_w + 2 * wall
    out_h = inner_h + wall  # closed floor, open top for a lid

    with BuildPart() as p:
        # Outer shell on the bed (floor at z = 0).
        Box(out_l, out_w, out_h, align=(Align.CENTER, Align.CENTER, Align.MIN))
        fillet(p.edges().filter_by(Axis.Z), radius=fillet_r)
        top = p.faces().sort_by(Axis.Z)[-1]
        offset(amount=-wall, openings=top)  # hollow, open top

        # Standoffs on the inner floor at the board's hole pattern.
        with Locations((0, 0, wall)):
            with GridLocations(pitch_x, pitch_y, 2, 2):
                Cylinder(2 * screw_dia, standoff_h,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))
        # Pilot holes down each standoff (self-tapping screw).
        with Locations((0, 0, wall)):
            with GridLocations(pitch_x, pitch_y, 2, 2):
                Cylinder(screw_dia / 2, standoff_h,
                         align=(Align.CENTER, Align.CENTER, Align.MIN),
                         mode=Mode.SUBTRACT)

        # Vents: a LOW inlet band + a HIGH outlet band through both long (+/-Y) walls,
        # so cool air enters low and warm air leaves high (stack effect). Slots are short
        # and vertical so they self-support on FDM.
        if vent_n >= 1:
            span = out_l * 0.6
            band_h = inner_h * 0.22
            for z_frac in (0.18, 0.82):  # low inlet, high outlet
                with Locations((0, 0, wall + inner_h * z_frac)):
                    with GridLocations(span / vent_n, 0, int(vent_n), 1):
                        Box(vent_w, out_w + 2.0, band_h, mode=Mode.SUBTRACT)

        # Port slot through the +X end wall, above the board.
        with Locations((out_l / 2, 0, wall + standoff_h + 4.0)):
            Box(2 * wall + 2.0, inner_w * 0.5, 6.0, mode=Mode.SUBTRACT)

    show(p.part, name="Enclosure", material="abs")


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
```

The lid is a separate part — model it as its own drop-in solid with the canonical mating
clearance ([solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models)) and
`show()` it alongside the enclosure; exploded view is a built-in viewport control, so do not add
an explode parameter.

## Questions that matter

Ask only these, and only if guessing wrong is expensive — otherwise default and state it:

- **What's the board outline and its mounting-hole pattern?** Sets the cavity and the standoff
  grid; everything else hangs off the board.
- **Which faces carry which connectors?** Drives every port cutout — its position, its height,
  and which wall gets cut. Read the connectors off the board before you place a single opening.
- **Does it run hot / need a fan, and is it indoors or sealed?** Forks the design: hot + indoor
  wants open vents ([thermal-ventilation](../references/thermal-ventilation.md#decision-rules)),
  sealed/outdoor trades those for a gasketed lid
  ([sealing-ingress](../references/sealing-ingress.md#decision-rules)) and likely a fan.

## Verify checklist

- **Visual** — `capture_views(["top", "<port-face>", "iso"])` (the port face is whichever wall
  carries the connectors). Confirm: every **standoff sits under a board hole** and lifts the
  board clear of the floor, the **vents read low-in / high-out** with each slot intact, and each
  **port opening lines up with its connector** with nothing blocked
  ([thermal-ventilation](../references/thermal-ventilation.md#verify),
  [affordance-usability](../references/affordance-usability.md#verify)).
- **Assert (known-by-construction)** — the standoff grid matches the **board's hole pitch** and
  each standoff is **≥ the height that clears the board's pins**, every vent slot is **≥ the
  printable minimum width** ([dfm-additive](../references/dfm-additive.md#verify)) and the total
  open area meets the **thermal target** ([thermal-ventilation](../references/thermal-ventilation.md#verify)),
  every wall is **≥ the active process's minimum wall** (see manufacturability). You set these,
  so you know them; true minimum wall on freeform geometry isn't recoverable from
  `get_model_info()` — say so.
- **Assert (computed)** — `get_model_info()` bounding box matches `cavity + 2·wall`; `valid` and
  `manifold` are both true.
- **Supported against gravity** — the center of mass sits **inside the footprint** (it doesn't
  tip when a cable pulls), and `check_interferences()` comes back clean: the board rests
  `adjacent` on its standoffs, the lid is `adjacent`/`clear` (never `overlap`), and nothing is
  `disjoint`/floating ([support-stability](../references/support-stability.md#verify)).

## Common failure modes

- **Sealed box, hot SoC, no vents** — a closed shell around a working chip is an oven. Either
  open vents to the thermal target ([thermal-ventilation](../references/thermal-ventilation.md#decision-rules))
  or add a fan; only seal it when ingress genuinely outranks heat
  ([sealing-ingress](../references/sealing-ingress.md#decision-rules)).
- **Standoffs missing or too short** — the board's solder pins ground out on the floor and short,
  or the board flexes with no support. Stand it off at every mounting hole, tall enough to clear
  the pins ([structure](../references/structure.md#decision-rules)).
- **Ports at the wrong height or position** — an opening that doesn't line up with the connector
  blocks the plug. Derive each cutout from the connector's real location on the board, not a
  guess ([affordance-usability](../references/affordance-usability.md#decision-rules)).
- **Vents below the printable slot width** — slots narrower than the process can print fuse shut
  and the open area collapses. Keep each slot ≥ the printable minimum and self-supporting
  ([dfm-additive](../references/dfm-additive.md#decision-rules)).
- **Lid with no clearance** — a lip modeled coincident with the rim won't close, or jams. Give
  the lid the canonical mating gap
  ([solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models)); never model mating
  faces coincident.
- **Ports split across faces** — connectors that belong together scattered over three walls force
  the user to spin the box to find each cable. Group them by function on one oriented face
  ([affordance-usability](../references/affordance-usability.md#decision-rules)).
