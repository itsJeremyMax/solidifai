# affordance & usability lens

How a part communicates its own use: which control to reach for, where it lives, and whether the
hand can get to it. This lens owns **placement, prominence, grouping, and tactile distinction**.
It does **not** own control *sizes* — those live in [ergonomics](ergonomics.md) (finger-pad
minimums, grip diameters, the thumb-reach arc). Link there; never restate a number.

## Principle

A good part shows how to use it: a control is **discoverable** (you can see it is a control),
**reachable** (the operating hand gets to it without contortion), and gives **feedback** (a press
or turn is felt and seen). Norman's **affordances** are what a control *lets* you do; **signifiers**
are the visible cues — shape, relief, an indicator — that *advertise* it, because a hidden
affordance is no affordance at all. **Fitts's law** then says a target that is **bigger and closer**
is faster and lower-error to hit, so the most-used control should be the largest and the easiest to
reach — not tucked in a far corner.

## Data & defaults

Placement and layout defaults (sizes are deliberately absent — see ergonomics):

| Default | Rule | Why |
|---|---|---|
| Primary control placement | under the natural thumb/finger of the operating hand — lower-center of the held face, inside the thumb-reach arc (see [ergonomics](ergonomics.md#data--defaults)) | Fitts's law: shortest reach to the most-used target |
| Control prominence | primary control is the largest and most-relieved; secondary controls smaller/recessed | the eye and thumb both go to it first |
| Related controls | group by function into a cluster, consistent order, aligned | a group reads as one system; the user learns it once |
| Ports / connectors | keep on **one** face where possible, oriented to how the device rests or is held | cables exit one way; the user learns one face |
| Label / icon clearance | leave a clear flat margin around any label, icon, or molded-in legend (roughly the legend's own cap-height as breathing room) so a fillet, parting line, or neighbouring feature doesn't crowd or clip it | a crowded signifier stops signifying |
| Control target size | **link, don't restate** — pressable ≥ finger-pad min, comfortable size, and adjacent spacing all live in [ergonomics](ergonomics.md#data--defaults) | one source of truth for human dimensions |

**Tactile distinction.** Adjacent controls that do different jobs must be told apart by *feel*, not
just by looking (the eyes are often on the task, not the part). **Shape-code** them (round vs. bar
vs. notched), **size-code** them (the critical or most-used one larger), and where it matters add a
**texture or relief** cue. This is the cockpit "shape-coded control" idea from human-factors design:
the hand should never have to look to know which control it is on. Keep an unmistakable feel-gap
between two controls a user must not confuse (spacing per [ergonomics](ergonomics.md#data--defaults)).

**Feedback.** A control should confirm itself: travel and a detent on a button, a detent or hard
stop on a setting dial, an indicator mark on anything that points or sets a value. A control with no
felt or seen response reads as broken even when it works.

## Decision rules

- **Primary action → largest, most-reachable control.** Put the most-used control where the operating
  hand naturally rests, and make it the most prominent (biggest, most relieved). Demote everything
  else.
- **Never place a control where the grip hand covers it.** Map the grip first (which fingers land
  where), then keep the active control faces clear of that footprint. A button under the holding palm
  is unreachable and gets pressed by accident.
- **Group related controls; keep one consistent order.** A cluster of related controls beats the same
  controls scattered across faces.
- **Ports / connectors grouped on one face,** oriented to how the device rests or is held, so every
  cable exits the same way and nothing is blocked by the surface it sits on.
- **Distinguish adjacent controls by feel** — shape-code and/or size-code any two the user must not
  confuse; don't rely on the label alone.
- **Make every control a signifier.** If a feature is meant to be pressed or turned, it must *look*
  pressable or turnable (relief, a cap, knurl, an arrow) — a flush, unmarked control is invisible.
- **One face, one job, where you can.** Don't split a single interaction across two faces the hand
  can't span at once.

## Questions that matter

- **Which control is primary?** The single most-used action drives placement and prominence — it gets
  the largest, most-reachable spot. (If everything is "important," nothing is.)
- **Which faces carry ports vs. controls?** Decide early; it sets the whole layout and the grip. Ports
  prefer one face oriented to how the device rests.
- **Operated while held, or while resting?** Held → lay controls out for the operating hand's reach
  inside the thumb-reach arc and keep them off the grip footprint. Resting → controls go on the
  top/front face presented to the seated user, ports to the back/side.

## Verify

- **Map the grip, then the controls.** Confirm by construction that no control sits inside the grip
  hand's footprint (known from where you placed the grip and the controls).
- **Prominence check:** the primary control is the largest and most-relieved of the control set
  (known-by-construction from the sizes you set; the human-dimension floors come from
  [ergonomics](ergonomics.md#verify)).
- **Visual:** `capture_views(...)` the **control face** (and the grip-on view). Confirm every control
  is reachable and unobstructed by the grip, every control *reads* as a control (visible signifier),
  ports sit together on one oriented face, and the primary control is unmistakably the most prominent.
  This is the affordance check the numbers can't make.

## Sources

- **Donald A. Norman, *The Design of Everyday Things*** (rev. & expanded ed., Basic Books, 2013) —
  affordances vs. signifiers, discoverability, feedback, and the principle that a control must
  advertise its own use. Source for the "a good part shows how to use it" framing and the
  signifier/feedback rules.
- **William Lidwell, Kritina Holden & Jill Butler, *Universal Principles of Design*** (rev. ed.,
  Rockport, 2010) — **Fitts's law** (target acquisition time falls with larger, closer targets) and
  the **affordance** principle, behind the "primary action → largest, most-reachable control" rule.
  Also the basis for shape/size-coding controls so they are distinguished by feel.
- **Dieter Rams' Ten Principles of Good Design** — "good design makes a product understandable" and
  "good design is as little design as possible": controls should be self-evident and unnecessary ones
  removed, behind the "make every control a signifier" and "one face, one job" rules.
