# aesthetics & form lens

The fuzziest lens — taste doesn't quantify. So this is **consistency rules, not a beauty formula**:
share one radius family, choose proportions on purpose, keep transitions clean, break edges a hand
touches, and don't fight the material. These moves are what separate a part that reads as *designed*
from one that reads as *defaulted*. All values mm. Where a number is about the **hand** (how big to
break a grip edge, how a held form should feel), that lives in the
[ergonomics lens](ergonomics.md) — this lens links there rather than restating it.

## Principle

A coherent form reads as **designed** rather than thrown together, and coherence comes from a few
disciplines, not from talent: **consistent radii** (one fillet/chamfer family across the part, so
edges look related instead of random), **deliberate proportion** (ratios chosen on purpose — not an
accidental almost-square or almost-cube that looks like a mistake), **clean transitions** (faces
meet, fillets blend, and parting lines fall on edges rather than smearing across a show face), and
**honest material** (let the part look like what it is and how it's made, rather than faking a
different process). When in doubt, **make it consistent and intentional** — that alone carries most
of the "designed" read; the rest is restraint.

## Data & defaults

These are **consistency conventions, not measured thresholds.** Use them to keep a part coherent;
none of them is a law, and function always overrides taste.

| Concern | Default / rule | Why |
|---|---|---|
| **Radius family** | Pick **one small set of radii** for the whole part (e.g. a 2 mm "edge break," a 6 mm "soft corner," a larger "primary" radius) and reuse them; don't let every edge get its own arbitrary value. | Edges that share a radius read as a system; a dozen near-but-different radii read as accidental. Vary radius only where **function** dictates (a stress fillet, a grip, a seal land), not at random. |
| **Concentric / nested radii** | When one rounded form sits inside/atop another, keep them **concentric or offset by a constant** (outer R = inner r + wall) so the curves stay parallel. | Parallel curves look resolved; drifting ones look warped. |
| **Proportion** | Choose face and overall ratios **deliberately** — avoid the *accidental* near-square / near-cube (e.g. 51 × 49, or 30 × 31 × 29). Round to a clean ratio (a true 1:1 square, or a deliberate 1:1.6-ish, 2:3, 3:4) on purpose. | An "almost-square" reads as an error the eye keeps trying to correct; a committed ratio reads as a decision. |
| **Parting line / seam** | Put any split line, seam, or parting line **on a natural edge or a deliberate feature line**, not across a flat show face; keep it straight or following one clean curve. | A seam wandering across a visible face is the loudest "unfinished" signal; tucked on an edge it disappears. |
| **Transitions** | Faces meet on a **shared fillet or chamfer**, not a half-blended near-miss; tangent-continuous where the surface should look smooth. Keep wall/face transitions resolved (the structure lens owns the *load* reason; here it's the *look*). | A transition that almost-but-doesn't blend looks like a defect; a committed fillet or a crisp chamfer both look intentional. |
| **Visual weight** | **Relieve a heavy base** — chamfer or undercut the bottom edge, or add a small recessed plinth/foot — so a blocky part doesn't look like it's sinking into the table. Lighten visually-bottom-heavy forms; ground visually top-heavy ones. | A chamfered or floated base reads lighter and more resolved; a full-bleed slab base reads like a doorstop. |
| **Edge treatment (touched surfaces)** | **No raw sharp edges on any surface a hand touches or grips.** Break every handled edge with a chamfer or fillet. The *size* of that break is the manufacturing profile's edge-break default (`get_manufacturing_profile()`, the `filletMm` / edge-break value); **which surfaces** count as grip/contact is the human-dimension context owned by the [ergonomics lens](ergonomics.md#decision-rules). Link to the profile for the number and to ergonomics for the context. | Sharp handled edges feel cheap and bite the hand; a broken edge feels finished. Cosmetic outer edges (not touched) can take a smaller "edge break" purely for the designed look. |

Restraint note (Rams): **as little design as possible.** Don't add a chamfer, flute, or step that
earns nothing — decoration that isn't doing a job (grip, signifier, edge-break, visual weight) is
noise. Every form move should justify itself functionally or compositionally.

## Decision rules

- **Multiple fillets/chamfers on one part → share a radius family.** Reuse the same small set of
  radii unless **function dictates otherwise** (a stress fillet per [structure](structure.md), a
  grip radius per [ergonomics](ergonomics.md), a seal/clearance land per
  [manufacturability](manufacturability.md)). Random per-edge radii are the #1 "undesigned" tell.
- **A touched / gripped edge → break it** (chamfer or fillet); never ship a raw sharp edge on a
  surface the hand contacts. Size and which-surfaces come from
  [ergonomics](ergonomics.md#decision-rules) — link, don't restate.
- **Blocky / slab form → relieve it with a consistent corner radius** (and/or a chamfered base) so
  it reads as a designed volume, not a raw extrusion. Use the part's radius family.
- **Accidental near-square / near-cube → commit the ratio.** Nudge it to a true square or a clearly
  intentional ratio; don't leave a 49:51 that looks like a slipped dimension.
- **Visible parting line / seam on a show face → move it to an edge** or a deliberate feature line.
  If it must cross a face, make it dead straight and own it as a design line.
- **Heavy-looking base → chamfer / undercut / plinth it** to lighten the visual weight; conversely
  ground a top-heavy form on a wider or visually-anchored base.
- **Tempted to add an ornamental flourish → cut it** unless it does a real job (grip, signifier,
  edge-break, weight). Coherence and restraint beat decoration.

## Questions that matter

- **Is there a style to match?** Does this join an **existing product family** (matches a sibling's
  radii, proportions, surface language, color/material)? If so, **inherit that vocabulary** — borrow
  its radius family and proportions rather than inventing a new one; consistency *with the family*
  outranks any standalone rule here.
- **Is it visible / display, or hidden / internal?** A **shown** surface earns the full treatment —
  consistent radii, resolved transitions, hidden seams, deliberate proportion. A **hidden/internal**
  part (inside an enclosure, a bracket no one sees) should **not** be fussed over: skip the cosmetic
  polish, keep only the functional and the touched-edge breaks, and spend the effort where it shows.

## Verify

- **Visual is the primary channel here** — aesthetics don't reduce to an assert. `capture_views(...)`
  an **iso** (overall proportion and stance) **plus at least one corner / edge close-up** (where the
  radii and transitions actually live), and **look**: do the edges share a radius family, or does one
  corner have a stray different round? Is any face an *accidental* near-square that should be
  committed? Is there a **sharp edge on a surface a hand would touch** (cross-check against
  [ergonomics — Verify](ergonomics.md#verify))? Does a parting line cross a show face? Does the base
  look heavy / unrelieved?
- **Assert (known-by-construction):** the set of fillet/chamfer radii you applied comes from your
  **chosen radius family** (you set them, so you know whether they're consistent — this is
  known-by-construction, not measured back from `get_model_info()`, which reports bounding
  box / volume / mass / `valid` / `manifold`, not radius consistency). The bounding box **can**
  confirm a proportion you intended (e.g. that a face is a true square, not a 49:51 accident).
- **Honesty:** report this as "coherent and consistent by these rules," **not** "verified beautiful."
  Taste is a judgement call; flag any proportion or treatment you're unsure of for the user rather
  than asserting it's resolved.

## Sources

- **William Lidwell, Kritina Holden & Jill Butler, *Universal Principles of Design*** (rev. ed.,
  Rockport, 2010) — consistency, alignment, and the principle that coherent, related elements read as
  intentional; the basis for the **one radius family / shared treatment** rule and the
  "consistent-and-intentional carries the designed read" framing.
- **Kimberly Elam, *Geometry of Design*** (rev. ed., Princeton Architectural Press, 2011) —
  proportion systems and the case for **deliberate ratios** over accidental ones; behind the
  "commit the ratio / avoid the accidental near-square" and concentric-radii guidance.
- **Dieter Rams' Ten Principles of Good Design** — "good design is as little design as possible,"
  "good design is honest," and "good design is thorough down to the last detail": the **restraint**
  (cut ornament that earns nothing), **honest-material**, and **resolve-the-details** (clean
  transitions, hidden seams, broken edges) rules. The shown-vs-hidden effort split follows the same
  thoroughness-where-it-counts logic.
- **Cross-link (single source of truth — linked, not restated):** the **size** of an edge-break is
  the manufacturing profile's edge-break default (read via `get_manufacturing_profile()`); which
  surfaces count as grip/contact is the human-dimension context owned by the
  [ergonomics lens](ergonomics.md#decision-rules); the **load** reason for a corner fillet is owned
  by [structure](structure.md); printability of any radius/clearance by
  [manufacturability](manufacturability.md). This lens owns only the *look* — consistency,
  proportion, and restraint.
