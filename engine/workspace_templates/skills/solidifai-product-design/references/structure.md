# structure lens

Grounded structural-design judgment for parts that **carry a load** — fillets, ribs, bosses,
gussets, and where the load actually flows. All values mm. These are **rules of thumb, not FEA**:
widely-cited ratios from the sources below that keep a part stiff and crack-resistant without
wasting material. Use the ratio, not false precision; when the user gives a real load or material,
that's a sizing problem beyond these heuristics — say so rather than implying a calculation.

This lens is about **will it carry the load**. Whether a wall is thick enough to *print* at all
(the FDM minimum-wall rule, overhangs, clearances) lives in the
[manufacturability lens](manufacturability.md) — that owns *can it print*. When manufacturability
says "thicken or add ribs" for a load path, the rib/fillet/gusset ratios here are the *how*.
Whether the part **stands up under its own gravity** — a stable base, tip-over, a center of mass
over its footprint, no floating unsupported mass — is a different concern owned by the
[support-stability lens](support-stability.md); this lens owns carrying the applied load, and the
two meet wherever a cantilever or overhang must be braced back to its support (the gusset/rib
*how* is here).

## Principle

A part should carry its loads without wasting material. Three moves do most of the work: **fillet
internal corners** so stress flows around them instead of piling up at a sharp notch that cracks
(brittle FDM beams especially); **add ribs instead of bulk** to win stiffness cheaply, because
bending stiffness scales with depth far faster than with solid thickness, and a thick solid both
wastes material and sinks/warps; and **keep walls, ribs, and bosses in sensible ratio** so nothing
is a thin one-bead afterthought or a heavy lump. Design the **load path** first — trace the force
from where it's applied to where it's reacted — then put material along that path and fillet/gusset
every place it turns a corner.

## Data & defaults

| Quantity | Value / rule | Notes |
|---|---|---|
| Internal-corner fillet (stress riser) | **radius ≥ ~0.5× the adjoining wall** | A sharp internal corner concentrates stress sharply (the riser grows fast as r/t → 0); r ≈ 0.5×t drops the stress-concentration factor into the ~1.5 range. Bigger is better up to where it eats the cavity. Outside corners can be smaller fillets/chamfers (cosmetic + handling, see [aesthetics-form](aesthetics-form.md) / [ergonomics](ergonomics.md)). |
| Rib thickness vs. wall | **rib ≈ 0.5–0.8× wall** (cap ~0.8×) | Classic injection-molding rule to avoid a **sink mark** on the opposite face where mass piles up; on FDM a too-thick rib also wastes time and can trap heat. Stiffen with **more/deeper ribs**, not thicker ones. |
| Rib height | **≤ ~3× wall** per rib | A rib much taller than ~3× its base wall gets slender and wants to buckle; for more depth use **several shorter ribs** or a deeper section, not one tall thin fin. |
| Rib draft / root | small root fillet at the rib base (~0.25–0.5× rib) | Kills the rib-root stress riser; on FDM also helps the rib fuse to the wall. Draft is a molding concern — not needed for FDM ([manufacturability](manufacturability.md)). |
| Boss outer wall | **OD ≈ 2–2.5× the hole/insert Ø**; boss wall ≈ same as nominal wall | A boss is a stub for a screw/insert/pin; too-thin a boss wall splits, too-thick sinks. Gusset or rib a **tall** boss to its base wall rather than fattening it. |
| Gusset (corner brace) | add when a wall/boss/mount is **cantilevered** or a corner is loaded | A triangular web tying a vertical feature back to its base; thickness ≈ rib (0.5–0.8× wall), filleted at both ends. Multiple modest gussets beat one massive one. |
| Wall-thickness uniformity | keep walls **within ~±25%** of each other | Abrupt thick→thin transitions concentrate stress and (on FDM) warp/separate; blend with a fillet or taper rather than a step. |

**Load-path heuristics (rules of thumb):**

- **Depth beats thickness for stiffness.** Bending stiffness goes with section *depth* cubed but
  only linearly with how much solid you add — so a ribbed or boxed section is dramatically stiffer
  per gram than a thicker plate. Reach for a rib/flange/box before a thicker solid.
- **Triangulate.** A triangle is rigid; a square rack. Gussets and diagonal ribs turn a floppy
  right-angle into a stiff braced one.
- **Pull, don't bend, where you can.** Material is far stronger in tension/compression than a thin
  section is in bending — route the load so it tensions/compresses a member rather than levering a
  thin cantilever.
- **Fillet every corner the load turns.** Each internal corner on the load path is a stress riser;
  a fillet there is the cheapest strength you can add.
- **Print along the load, not across it.** Layered processes like FDM are weakest between layers (interlayer adhesion), so
  a load-bearing member is strongest when the force runs *along* the layers, not pulling them
  apart — an orientation note shared with [manufacturability](manufacturability.md).

## Decision rules

- **Sharp internal corner under load → fillet it**, radius **≥ ~0.5× the adjoining wall**. A loaded
  square internal corner is a crack waiting to start, especially on brittle FDM.
- **Need stiffness without mass → ribs, not a thicker solid.** Add ribs at **0.5–0.8× wall**,
  height **≤ ~3× wall**, more/deeper rather than thicker; a thick solid wastes material and sinks.
- **Cantilevered mount / overhanging feature → gusset the root.** A triangular web from the feature
  back to its base, filleted at both ends, carries the bending moment the thin root can't.
- **Tall boss for a screw/insert/pin → rib or gusset it to the nearest wall**, keep its wall near
  nominal (OD ≈ 2–2.5× the hole). Don't just fatten the boss — that sinks and still snaps off.
- **Abrupt thick↔thin wall transition → blend it** (fillet/taper, keep walls within ~±25%) so
  stress and (on FDM) warp don't concentrate at the step.
- **Snap-fit / cantilever beam under flex → filleted root.** The cantilever-snap root fillet
  (≥ ~0.5× the beam thickness) and along-the-layers pull are owned by
  [manufacturability — Threads & fasteners](manufacturability.md#data--defaults); link to it, this
  lens just confirms the same riser principle.
- **Real load number / safety-critical part → flag it.** These are rules of thumb; if getting it
  wrong is dangerous or expensive, say the part needs a proper stress check (FEA / hand calc),
  don't imply the heuristics sized it.

## Questions that matter

- **Does it bear meaningful load** — or is it cosmetic / lightly handled? A decorative or
  zero-load part doesn't need ribs and gussets; don't over-build it (and don't impose structure
  opinions where there's no load to carry).
- **From what direction** — which way does the force push/pull, and where is it reacted? This sets
  where the load path runs, which corners to fillet, and which way to orient the print.
- **Roughly how much** — a hand-press, a hanging weight, a person's bodyweight, a motor's torque?
  An order-of-magnitude is enough to choose rib-and-fillet vs. "this needs a real calc"; precise
  load sizing is beyond this lens.

## Verify

- **Assert (known-by-construction):** every **internal load-bearing corner** on the path is
  filleted at **radius ≥ ~0.5× the adjoining wall**, and ribs are within ratio (**0.5–0.8× wall**,
  height **≤ ~3× wall**). You *set* these radii and rib dimensions, so you **know** them — this is
  known-by-construction, not a stress value measured back from `get_model_info()` (which reports
  bounding box / volume / mass / `valid` / `manifold`, not stress or true min-radius on freeform
  geometry).
- **Visual:** `capture_views(...)` along and across the load direction and **look**: is there a rib
  or gusset everywhere the path needs stiffening, is the cantilevered root braced, and are the
  loaded internal corners visibly radiused rather than sharp? This catches a missing gusset or an
  un-filleted root the numbers won't.
- **Honesty:** report these as load-rules-of-thumb satisfied, **not** a verified stress margin. If
  the load is meaningful or safety-critical, state that a proper structural check is still needed.

## Sources

- **Karl T. Ulrich & Steven D. Eppinger, *Product Design and Development*** (McGraw-Hill, multiple
  eds.) — design-for-robustness and the load-path / "put material where the force flows" framing;
  the design-decision layer above (trace the path, brace where it turns, don't over-build).
- **James G. Bralla (ed.), *Design for Manufacturability Handbook*** (2nd ed., McGraw-Hill) — and
  general DFM handbook guidance — internal-corner fillet to relieve stress concentration, rib
  proportion and rib-vs-bulk stiffening, boss reinforcement, uniform-wall guidance.
- **Classic injection-molding design guides** (e.g. material-supplier part-design manuals such as
  the DuPont / Bayer / BASF *General Design Principles* booklets) — the widely-cited **rib ≈
  0.5–0.8× wall** (sink-mark) ratio, **rib height ≤ ~3× wall**, **boss OD ≈ 2–2.5× hole**, and
  root-fillet ratios. Originated for molding; **adapted here for FDM**, where the same ratios avoid
  print/heat issues and the interlayer-adhesion (print-along-the-load) note is added.
- **Stress-concentration references** (e.g. Peterson's / Roark's charts) for the qualitative
  fillet rule that the stress riser falls steeply as the fillet radius grows toward ~0.5× the wall;
  used here for the **rule of thumb only**, not as a substitute for FEA.
- **Cross-link (single source of truth — linked, not restated):** the cantilever **snap-fit root
  fillet** and **print-along-the-layers** rule live in
  [manufacturability](manufacturability.md#data--defaults); the **minimum printable wall** (can it
  print at all) is owned there too — this lens covers load-carrying, not printability.
