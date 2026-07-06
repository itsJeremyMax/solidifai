# support & stability lens

Grounded judgment for keeping a part **standing up under its own gravity** — a real base, a center
of mass that sits over its footprint, and nothing left floating unsupported. All values mm. These
are **rules of thumb, not a toppling simulation**: the statics are simple (a body tips when the
vertical through its center of gravity leaves its base of support) but the real margin depends on
the surface, knocks, and any payload — use the ratio, say what you assumed, and when balance is
safety-critical say it needs a real check rather than implying one.

This lens is about **will it stand up and stay put**. Whether a member is thick enough to *carry an
applied load* (ribs, gussets, the load path) lives in the [structure lens](structure.md) — that
owns *carrying the load*; this one owns *resisting gravity by default*. Whether a wall can *print*
at all is owned by [manufacturability](manufacturability.md).

## Principle

Gravity is always acting on the part, so design it to be **supported by default**: it rests on a
real base (or is properly mounted/hung), its weight runs down through that support to the ground,
and no piece floats unsupported in space. A body tips the moment the vertical line through its
**center of gravity** passes outside its **base of support** — the convex hull of the points it
actually touches the surface on. Three moves do most of the work: give every free-standing part a
**real footprint** wide enough that its center-of-mass projection lands inside with margin; keep the
**center of mass low** (mass at the bottom, lightness up high) so it takes a big tilt to walk that
projection off the edge; and **carry overhanging mass back to a support** rather than letting a
cantilever hold itself up by bending. Treat a part that only stands if you hold it, or geometry that
hovers off its parent, as a **defect to fix**, not a finished design — unless the user explicitly
wanted it floating, wall-mounted, or hung.

## Data & defaults

| Quantity | Value / rule | Notes |
|---|---|---|
| Base of support | **flat base or ≥3 non-collinear contact points** | A stable rest needs a real footprint — a flat face, a ring, or a tripod. Two points (or a line/edge contact) is a balancing act, not a stance. |
| CoM projection inside footprint | **vertical from the center of mass lands inside the base, ideally ≥ ~10–15% of the base dimension from any edge** | Right at the edge it is on the verge of tipping; the inset is the knock/nudge margin. `get_model_info()` reports `centerOfMass`; you built the footprint. |
| Tip angle | **θ_tip = atan(d / h)**, d = horizontal CoM-to-tip-edge distance, h = CoM height | The tilt it takes to topple. Want it comfortably above any expected lean/knock — **≈ ≥15–20°** for a desk object that gets bumped. **Wider base raises d, lower CoM lowers h** — both raise θ_tip. |
| Aspect rule of thumb | a free-standing part with **height > ~2–3× its base width** is knock-sensitive | Tall and narrow tips easily. Widen/lower the base, splay feet out, or **ballast the bottom** (thicker base, denser material low) to drop the CoM. |
| Leaning / loaded part | base must extend **behind the combined center of mass** | A leaned-back load (a stand holding a device) pushes the *combined* CoM back and up; the base has to reach behind that projection. The stand case is worked in [stand-cradle](../playbooks/stand-cradle.md). |
| Self-weight of an overhang | route it back to a support; don't let a thin cantilever hold itself | An unsupported horizontal arm sags or snaps under its own weight long before any applied load; the rib/gusset *how* is owned by [structure](structure.md#decision-rules). |
| Floating / disconnected geometry | **defect by default** | A shown body touching nothing, or a feature hovering off the wall it should sit on, isn't supported. `check_interferences()` flags it as `disjoint`; reconnect or re-seat it unless it's a deliberate separate part. |

**Stability heuristics (rules of thumb):**

- **Lower the center of mass before you widen the base.** Dropping h shrinks the tip angle's
  denominator directly; mass low and air up high is what makes a bottle harder to knock over than a
  same-footprint solid cylinder.
- **A wider footprint is cheap stability.** Increasing d — especially splaying feet or a base
  outward — walks the tip edge away from the CoM projection.
- **Three points beat four on an uneven surface.** A tripod never rocks; four feet on a warped print
  or desk rock between two diagonals. Use three contacts, or make one pair compliant.
- **Stand it the way it prints and rests.** Pick the resting orientation up front so it won't roll
  (round bottoms), slide (a slick foot on a slope), or sit on a point — and so the print lays the
  load-bearing direction along the layers ([manufacturability](manufacturability.md)).

## Decision rules

- **Free-standing part → give it a real base whose footprint contains the CoM projection** with
  ~10–15% margin. Read `centerOfMass` from `get_model_info()`; if its (x, y) lands near or outside
  the footprint, widen the base or move mass down/inward.
- **Tall / top-heavy (height > ~2–3× base width, or mass concentrated high) → widen and lower the
  base, splay feet, or ballast the bottom.** Don't ship a tippy tower; drop the CoM or grow the
  footprint until θ_tip clears ~15–20°.
- **Leaning or loaded part (a stand, a cradle, anything holding a weight off-center) → extend the
  base behind the combined CoM** so its projection stays inside. The combined CoM includes the
  payload, which `get_model_info()` doesn't know — say what payload weight you assumed.
- **Overhang / cantilever carrying its own weight → brace it back to a support** (link to
  [structure](structure.md#decision-rules) for the gusset/rib); don't rely on a thin arm not to sag.
- **A shown body disconnected from everything, or a feature floating off its parent → defect:
  reconnect or re-seat it.** Confirm with `check_interferences()` (a `disjoint` part or a stray
  solid). The only exceptions are a deliberate separate assembly part or an explicitly
  wall-mounted/hung design.
- **Won't-rest-flat geometry (a rounded or pointed bottom, a single-edge contact) → add a flat, a
  foot, or a stand**, or state that it's meant to be held/mounted. A part that can't sit still
  isn't done.
- **Mounted / hung / handheld instead of free-standing → design the support interface, not a base.**
  If gravity is taken by a bracket, a strap, or a hand, the rule moves to that interface (fastener
  pull-out, strap, grip) — don't bolt on a footprint it doesn't need.
- **Safety-critical balance (it must not tip onto a person, a child, hot contents) → flag it.**
  These are rules of thumb; if tipping is dangerous, say it needs a real stability check, don't
  imply the heuristic sized it.

## Questions that matter

- **Does it stand on its own, or is it mounted / hung / held?** The first fork: a free-standing part
  needs a stable footprint; a mounted/held one needs a good support *interface* and no base at all.
  Guessing wrong rebuilds the whole bottom of the part.
- **Which way is "up" in use, and what surface does it rest on?** A flat desk, a slick shelf, a
  wall — sets the base, the resting orientation, and whether it might slide or roll.
- **Roughly how tall vs. wide, and where's the mass?** An order-of-magnitude aspect and where the
  heavy bits sit is enough to spot a tip risk and choose "widen/lower/ballast" vs. "fine as is."
- **Is anything deliberately cantilevered or floating?** A reached-out arm or a separate part is a
  real design choice; an *accidentally* detached lump is a bug. Knowing which lets the interference
  check be read correctly.

## Verify

- **Assert (computed where possible, else known-by-construction):** read `centerOfMass` from
  `get_model_info()` and confirm its (x, y) **projects inside the base footprint you built**, with
  ~10–15% margin to the nearest edge. The footprint is known-by-construction (you placed a base of
  size W×D), the CoM is computed — so the projection check is a real, mostly-computed assert.
  **Honesty:** `get_model_info()` reports the *part's own* CoM, not an attached payload's mass or
  the combined CoM, so for a loaded/leaning part the margin is a geometric argument plus the weight
  you assumed, **not** a measured tip margin — say so.
- **Tool:** run **`check_interferences()`** and confirm **no part is `disjoint`** (nothing
  floating/disconnected) and there is **no unintended `overlap`** — i.e. every piece is actually
  attached to its support and nothing interpenetrates that shouldn't. An intended fusion or
  press-fit reads as `adjacent`/expected; judge each flag.
- **Visual:** `capture_views(["front", "right"])` — a side/front elevation reads the stance
  directly — and **look**: does it sit on a real base, is the base wide and grounded rather than
  tippy or top-heavy, is anything hovering unsupported, and would it stay put if the desk were
  nudged? This catches a too-narrow footprint or a floating feature the numbers won't.
- **Honesty:** report these as stability-rules-of-thumb satisfied, **not** a verified tip margin. If
  balance is meaningful or safety-critical, state that a proper check is still needed.

## Sources

- **Engineering statics — equilibrium and the base-of-support rule** (e.g. R. C. Hibbeler,
  *Engineering Mechanics: Statics*): a body is stable while the line of action of its weight (the
  vertical through its center of gravity) passes within its base of support, and tips once it
  leaves; the tip angle θ = atan(d/h) follows from the same geometry. Used here as the qualitative
  rule of thumb, not a substitute for a real stability calc.
- **Karl T. Ulrich & Steven D. Eppinger, *Product Design and Development*** — design-for-robustness
  / "works under real use" framing: a part has to stand, rest, and survive a knock in a real user's
  hands, not only look right in CAD.
- **General industrial- and product-design stability heuristics** — low center of mass, a footprint
  wide relative to height, the tripod (three-point) minimum, and ballasting the base to drop the
  CoM; widely repeated in design-for-stability guidance and adapted here for printed parts.
- **Cross-links (single source of truth — linked, not restated):** the **cantilever/overhang
  bracing** (gusset/rib) *how* lives in [structure](structure.md#decision-rules); the
  **leaned-back device-stand** worked example lives in
  [stand-cradle](../playbooks/stand-cradle.md); **print orientation along the load** is owned by
  [manufacturability](manufacturability.md); the floating/overlap **check** is the
  `check_interferences()` tool.
