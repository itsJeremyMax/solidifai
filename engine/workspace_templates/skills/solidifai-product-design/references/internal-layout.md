# internal-layout lens

Grounded judgment for **designing a containment object from its contents outward** -- a
cyberdeck, mini-PC shell, battery pack, drone body, electronics carrier, or any box whose
shape is driven by what lives inside it. All values mm. These are **packing rules of thumb,
not a verified structural or thermal analysis**: they give you a sane cavity and a derived
outer envelope, but real wall strength and thermal performance need the linked lenses and,
when they genuinely matter, a proper check.

This lens owns the **inside-out method** -- the ordered five-step process -- and the
**reservation numbers** that feed the wrap arithmetic (component-to-component clearance, cable
routing / bend space, internal airflow channel, and the outer-wall derivation formula). It does
**not** own component-to-wall clearance: that is owned by
[fits-tolerances](fits-tolerances.md#data--defaults), linked here, not restated. It does not own
the airflow open-area target: that lives in
[thermal-ventilation](thermal-ventilation.md#decision-rules), linked here, not restated. Fastener
land and boss sizing are owned by [structure](structure.md#decision-rules); service-access
geometry is owned by [serviceability-assembly](serviceability-assembly.md#decision-rules). Link
those; do not restate their numbers here.

## Principle

The enclosure is **computed from the contents, never guessed independently.** Work inside-out,
in this order:

1. **INVENTORY** the internal components with real dimensions (measure or look up the datasheet;
   never approximate a PCB as "about 100 x 80" when the spec says 85 x 56).
2. **LAYOUT** the components in 3D so they fit and clear each other -- decide the packing
   arrangement (stacked flat, side-by-side, L-shaped) from which faces carry connectors,
   what needs airflow, and what must be reached in service.
3. **RESERVE** space for everything that is not a component but still needs room: component-to-
   component clearance, cable routing and bend radius, internal airflow channels, service access
   paths, and fastener land.
4. **DERIVE** the packed envelope -- the tightest box that contains the layout and all its
   reservations.
5. **WRAP** the shell around that envelope: outer extent = packed envelope + reservations + wall
   (one wall thickness per side). Once the reservations are folded into the packed envelope, this
   is outer = packed envelope + 2 * wall (see Data & defaults).

The outer shape is downstream of the contents. If the layout changes, the envelope changes, and
the shell follows. Never start with an outer box and hope the contents fit; that is the wrong
direction and produces either wasted internal space or a cavity that does not close.

## Data & defaults

**Reservation numbers owned by this lens:**

| Quantity | Default starting band | Notes |
|---|---|---|
| Component-to-component clearance | **1.5-3 mm** between adjacent component bodies | The lower end (1.5 mm) is a tight but printable gap for still components (boards, cells); use 3 mm or more around anything that generates heat, vibrates, or whose connectors may be plugged in place. |
| Cable routing / bend space | **8-12 mm** reservation alongside a cable run; bend radius at least **3x the cable OD** | Reserve this as a channel volume, not a gap at the cable itself. Ribbon cables need a flat bend area; round cables need the 3x bend radius. If the exact cable is not yet chosen, 10 mm is a working default. |
| Internal airflow channel | no default, see link | Sized to heat and path, do not guess: see [thermal-ventilation](thermal-ventilation.md#decision-rules) for the open-area target and chimney direction; the channel volume follows from that area times the channel length. Present whenever the layout encloses anything that dissipates real power. |
| Service access clearance | See [serviceability-assembly](serviceability-assembly.md#decision-rules) for access-opening size and reach rules; this lens reserves the volume those rules require. | |
| Fastener land | See [structure](structure.md#decision-rules) for boss diameter, wall-thickness, and screw-boss geometry; this lens reserves the footprint those rules require at each fastener site. | |
| Component-to-wall clearance | See [fits-tolerances](fits-tolerances.md#data--defaults) -- the baseline mating clearance owned there (typically the per-process slip/press gap); this lens does not restate it. | |

**Wrap arithmetic (owned here):**

```
outer_x = packed_envelope_x + 2 * wall
outer_y = packed_envelope_y + 2 * wall
outer_z = packed_envelope_z + 2 * wall
```

where `packed_envelope` is the axis-aligned bounding box of all component volumes plus all
reservations, and `wall` is the shell wall thickness from the manufacturing profile (default
2.4 mm for FDM; see the DFM family lenses for the minimum holdable wall per process). One wall
per side, so the factor is 2 in each dimension.

**Component reference box:** model each component as a rectangular reference volume set to its
real datasheet envelope, plus its connectors' plug depth on the relevant face, shown with
`role="reference"` so it is ghosted in the viewport and excluded from export and DFM
automatically while still being seen by `check_interferences()`. The connector face needs real
geometry (the port cutout is sized to it); the remaining faces can be the rectangular envelope.
This is enough to derive the cavity correctly without over-modeling.

## Decision rules

- **Which face carries connectors -> that face is fixed, everything else derives from it.** Place
  connectors on the face that the user reaches most naturally (for a bench device: the front; for
  a wearable or handheld: away from the grip zone). Lock that face orientation first, then lay out
  the internal components relative to it.
- **Stack flat or side-by-side?** Stack flat (one board above another) when the footprint must be
  small and the height budget is generous; stack side-by-side when height is tight and footprint
  can grow. The connector-face rule usually decides this: if the connectors are on the short edge,
  boards likely stand on their side; if connectors are on the long face, boards likely lie flat.
- **What must be serviced -> place it last (nearest the opening).** The component that must be
  removed most often (a battery, an SD card, a fuse) goes nearest the access panel. Components
  that never move in service go deepest.
- **When does a component drive the outer dimension?** A component drives the dimension when its
  body plus its component-to-wall clearance is larger than the packed-plus-reservations sum. That
  is the bottleneck; size the outer wall to it, then check that the remaining components fit
  inside with their own clearances.
- **When does a reservation drive the outer dimension?** A reservation drives when it is larger
  than any single component -- a big cable bend radius, a wide airflow channel, or a long service
  reach. Identify the dominant reservation per axis before committing the layout.
- **Real component dimensions.** If the datasheet dimensions are not available, do a grounding
  pass (solidifai-grounding) before building. An approximate envelope produces a cavity that will
  not fit the real part.

## Questions that matter

- **What are the components and their real dimensions?** This is the one question that cannot be
  defaulted: the inside-out method only works from real numbers. If the dimensions are not known,
  grounding to find them is the first step, not an optional one.
- **Which faces carry connectors?** The answer locks the orientation of the layout and the
  placement of every cutout. If guessing wrong means re-cutting all the port holes, ask. If the
  part has only one sensible connector face (e.g. a USB-C on the short end), default to it and
  state the assumption.
- **What must be removable in service?** This determines what goes nearest the access opening. If
  everything is permanent (a fixed sensor housing), this answer is "nothing" and the layout can
  pack for volume. If a battery or card must come out, it drives the service-access reservation.

Ask only these when guessing wrong is expensive (a wrong-sized cavity wastes a print). For a
quick prototype where re-printing is fine, default the reservations and state them.

## Verify

- **Every inventoried component is present in the model.** Count the reference volumes set during
  INVENTORY and confirm each has a corresponding solid in the model. This is known-by-construction
  (you placed them), but verify you did not drop one when the layout was rearranged.
- **Each component fits inside the cavity with its reserved clearance.** Compute: cavity inner
  dimension - component outer dimension >= the clearance from the reservation table (plus the
  component-to-wall clearance from [fits-tolerances](fits-tolerances.md#data--defaults)).
  `get_model_info()` reports the bounding box of the assembled model; the per-component fit is
  known-by-construction from the layout parameters you set.
- **`check_interferences()` shows no component-pair overlap and no component poking through a
  wall.** Run it on the composed model. Adjacent (touching) is expected at connector faces where
  cutouts are sized to the connector; overlap (interpenetration) is a defect. A component solid
  that overlaps a wall solid means the cavity is undersized on that axis -- increase the
  reservation or the envelope.
- **The shell provisions its contents.** Port cutouts are present and sized to the real connector
  envelope (width + height from the datasheet, with the component-to-wall clearance from
  [fits-tolerances](fits-tolerances.md#data--defaults) as the cutout tolerance). Mount points or
  standoffs are present for every component that cannot float in the cavity. Cable channels are
  present and wide enough for the cable bend.
- **Wrap arithmetic closes.** Confirm outer_x = packed_envelope_x + 2 * wall (and y, z) from the
  model bounding box vs. the summed layout params. If they disagree, one dimension in the layout
  was not carried through to the shell.

Note: the interference check is computed (advisory, judge the flags); the fit and wrap checks are
known-by-construction from the parameters you set.

## Sources

- **IPC-7711/7721 and common SBC/SoC datasheet conventions** -- the practice of reserving a
  keep-out or clearance zone around each component and deriving the enclosure from the populated
  board envelope rather than from a guessed outer box. Used here as the conceptual basis for the
  INVENTORY -> LAYOUT -> RESERVE -> DERIVE -> WRAP sequence.
- **Cable assembly and wiring-harness guidelines** (IPC/WHMA-A-620, and common mechanical
  packaging practice) -- the 3x cable-OD minimum bend radius for round cables, and the
  convention of reserving a routed-channel volume rather than a gap at the cable body.
- **Cross-links (single source of truth -- linked, not restated):** component-to-wall clearance
  (the per-process slip gap) is owned by [fits-tolerances](fits-tolerances.md#data--defaults);
  airflow open-area target and chimney direction are owned by
  [thermal-ventilation](thermal-ventilation.md#decision-rules); fastener land and boss sizing are
  owned by [structure](structure.md#decision-rules); service-access geometry is owned by
  [serviceability-assembly](serviceability-assembly.md#decision-rules). This lens owns only the
  inside-out method and the component-to-component clearance and cable-routing numbers layered on top.
