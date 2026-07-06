# ergonomics lens

Anthropometric data for parts a human holds, presses, or operates. All values mm. Numbers are
widely-cited population ranges from the sources below, not invented precision — use the band, not
a false single value.

## Principle

A part a human holds or operates must fit the human hand, not the average hand. Design **reach**
(can the smallest user reach the control?) to the **5th-percentile** dimension, and design
**clearance and grip** (does the part fit around / admit the largest user's hand?) to the
**95th-percentile** dimension. Sizing everything to the 50th-percentile mean fails the small user
on reach and the large user on clearance, so split the two: small for reach, large for fit.

## Data & defaults

| Quantity | Value | Use |
|---|---|---|
| Power-grip cylinder Ø (comfort band) | 30–50 mm | handles, grips, levers you wrap a fist around; ~38 mm typical optimum |
| Precision-grip Ø (thumb + fingertips) | 8–16 mm | pens, styluses, small knobs turned by fingertips |
| Finger-pad contact width (index) | 10–16 mm | sets the *minimum* footprint a pressable control must present to the pad |
| Pressable control min size | ≥ 10 mm | buttons, keys — never smaller than a finger pad |
| Pressable control comfortable size | 12–15 mm | default button/key size unless space forces smaller |
| Adjacent control spacing (edge-to-edge) | ≥ 6 mm | multi-button layouts; prevents accidental double-press |
| One-handed device max comfortable width | ~75–90 mm | held-and-thumbed devices; beyond this the thumb can't span the face |
| Thumb-reach arc (one-handed) | arc swept from the thenar/base of thumb, ~½ the holding hand's length | primary control belongs inside this arc, not in the far top corner |
| Adult hand **length** (wrist crease → middle-fingertip) | 5th ≈ 165 mm · 50th ≈ 183 mm · 95th ≈ 205 mm (sexes combined; women lower, men higher) | length sets handle length, reach depth |
| Adult hand **breadth** (across knuckles, no thumb) | 5th ≈ 74 mm · 50th ≈ 84 mm · 95th ≈ 95 mm | breadth sets minimum grip length / slot width a hand passes through |

Notes:
- The 5th/50th/95th hand figures above are sexes-combined approximations spanning the female-5th to
  male-95th civilian-adult range; tighten to a single-sex table from the sources if the user names a
  population.
- Gloved hands add roughly 6–13 mm to breadth and to any opening a hand must pass through — size
  grips and access holes up, not down, when gloves are in play.
- One-handed "max width" is a comfort guideline for *thumb span across the front face*, not a hard
  limit on overall device size.

## Decision rules

- Pressable control (button/key) → target **≥ 10 mm**, **12–15 mm** comfortable; if several,
  space them **≥ ~6 mm** edge-to-edge.
- Graspable handle for a **power grip** (wrap a fist) → cylinder **Ø 30–50 mm** (default ~38 mm);
  grip **length ≥ hand breadth (~95 mm at the 95th pct)** so a full fist fits.
- Fingertip-turned control (small knob/dial, precision grip) → **Ø 8–16 mm** with surface texture
  (knurl/flutes) for purchase.
- One-handed, thumb-operated device → keep overall front-face width **≤ ~75–90 mm** and put the
  **primary control inside the thumb-reach arc** (lower-center of the held face), never the far
  top-far corner.
- Design **reach to the 5th percentile** (smallest user must still reach it) and **clearance/grip
  to the 95th percentile** (largest user's hand must still fit). Do not size both to the 50th.
- Gloved or cold-weather use → add **~6–13 mm** to grips, openings, and control spacing.
- A child user → drop into a child anthropometric table; the adult bands above do **not** apply.

## Questions that matter

- **Who uses it** — adult, child, or gloved hands? (Picks the percentile table; child ≠ adult.)
- **One- or two-handed** operation? (One-handed → thumb-reach arc + max-width limit drives layout.)
- **Handedness** — must it work for left and right hands equally? (Default: keep the primary
  control and grip handedness-agnostic — centered or mirror-symmetric — unless told otherwise.)

## Verify

- **Assert (computed / known-by-construction):** the modeled grip Ø is within its band
  (power 30–50 mm, or precision 8–16 mm) and every pressable control's smallest dimension is
  **≥ the 10 mm finger-pad minimum**. These are *known-by-construction* — you set the grip Ø and
  the control footprint, so you know them — not measured back from `get_model_info()`. Grip Ø can
  also be checked against the bounding box of a cylindrical grip.
- **Assert spacing:** adjacent controls are **≥ ~6 mm** apart (known from the placement math).
- **Visual:** `capture_views(...)` the control face and confirm a thumb can sweep from the natural
  grip to the **primary control** without leaving the reach arc, and that no control sits where the
  grip hand would cover it.

## Sources

- **Henry Dreyfuss Associates / Alvin R. Tilley, *The Measure of Man and Woman: Human Factors in
  Design*** (rev. ed., Wiley, 2002) — hand length/breadth percentiles, grip-diameter and
  finger-clearance figures, reach-vs-clearance percentile method (5th for reach, 95th for
  clearance). Source for the hand-length/breadth table and the power/precision grip bands.
- **Stephen Pheasant & Christine M. Haslegrave, *Bodyspace: Anthropometry, Ergonomics and the
  Design of Work*** (3rd ed., CRC Press, 2006) — civilian-adult anthropometric tables, the
  5th/50th/95th percentile design principle, hand breadth and grip-length guidance, finger-pad and
  control-size minimums.
- **Steven Hoober, thumb-zone research** ("How Do Users Really Hold Mobile Devices?", UXmatters,
  2013, and follow-on touch-target work) — one-handed thumb-reach arc, comfortable one-handed
  width, and the lower-center primary-control placement for held-and-thumbed devices. Touch-target
  minimums in the 10–15 mm range corroborate the pressable-control sizing above.
