# dfm: formative lens

Design-for-formative judgment, keyed to the **formative process** — **injection molding** (a melt
forced into a hard tool), **casting** (urethane / silicone, a liquid resin poured into a soft mold),
and **thermoforming / vacuum forming** (a heated sheet pulled over one mold face). All values mm.
Numbers are widely-cited process rules and ranges from the sources below — use the rule, not false
precision, and **tune to the actual material / tool when the user names one** (a specific resin, a
glass-filled grade, a steel-vs-aluminum tool all shift draft, shrink, and the wall band). The
process comes from the material and the run: a molded or cast part fills a closed cavity and must
*release* from it; a thermoformed part is a shell drawn from flat sheet. This lens owns *what
formative demands* — the [manufacturability hub](manufacturability.md) keys the part to its process
and points here when that process is formative.

## Principle

Formative makes a part by **forcing or pulling material into a mold and then taking it back out**,
so every constraint follows from **fill, cool/cure, and release**. The melt or resin must fill every
feature evenly, then cool or cure — and wherever mass piles up (a thick boss, a lump behind a rib)
it cools last and pulls the surface in as a **sink mark** or warps the part as uneven shrink fights
itself, which is why a formative part wants a **uniform wall** above all else. Then it has to leave
the tool: a vertical wall with no **draft** drags and scuffs, a sharp internal corner traps the
part, and a true **undercut** can't pull straight at all — it forces a side-action / lifter (tooling
cost) or a redesign. Pick the **parting line and pull direction first** — they decide which faces
draft which way, where the witness line and gate land, and what reads as an undercut — then design
to fill evenly and release clean. Thermoforming is the one-sided case: detail forms on the mold face
only, the opposite face is loose, and the sheet **thins as it draws**.

## Data & defaults

| Rule | Injection molding | Casting (urethane / silicone) | Thermoforming / vacuum forming |
|---|---|---|---|
| Draft (per face) | **≥ ~1–2°** on every vertical wall; **more on textured / deep walls** (~1°/25 mm of depth) so the part releases | soft silicone tolerates light undercuts; **~3–5°** still eases release and tool life | **female ~1.5–3°**, **male ~3–7°** per side — generous; a draw drags badly without it |
| Uniform wall | **~1–3 mm**, held even; abrupt **thick↔thin → sink / warp** | **~1–3 mm** (down to ~0.5 mm small parts); even wall so it cures at one rate | single **sheet gauge** (~0.5–6 mm); wall **thins on the draw**, deep corners thinnest |
| Radii / corners | **generous fillets, no sharp internal corners** — sharp corners choke flow and crack | same — soft molds still want radii for fill and demold | **fillet ≥ sheet wall** (~2–3× gauge on deep draws); sharp corners web and thin |
| Parting line | place on an edge / least-cosmetic face; it leaves a **witness line + flash** | seam from the cut silicone mold; hide on a non-show face | trim line, not a true parting line; plan the **trim + web** |
| Undercuts | need **side-action / lifter / cam** (tooling cost) — or redesign to pull straight | flexible mold **peels** off mild undercuts; deep ones still split the mold | only via plug / pressure box; mostly **avoid** — draw straight |
| Shrinkage | **~0.5–2%** mold shrink, **material-dependent** (fill, fiber, wall all shift it) | **low (~0.1–0.3%)** — resin cures near net | sheet **thins**, not bulk-shrinks; budget the gauge for the draw |
| Draw ratio (depth : width) | n/a (closed cavity) | n/a (poured cavity) | **~1:1 typical**; beyond → **plug assist** to keep wall even; deep narrow pockets thin out |

Numbers are starting points — read the column for the active process and design to it. The wall band
and draft are *general-purpose-material* defaults; a stiff filled grade, a thin cosmetic shell, or a
deep textured wall moves them, and **a named resin sets the real shrink** (it can swing well outside
the band, and fiber fill makes shrink directional).

**DFM (design-for-formative) moves:**

- **Parting & pull first.** Before geometry, fix the **parting line** and **pull direction**: which
  way each half of the tool opens, which faces draft toward it, where the witness line and gate
  land, and what that makes an **undercut**. A feature that pulls straight is cheap; one that needs
  a side-action is a moving tool component and real cost. Decide it up front, not after modeling.
- **Uniform wall above all.** Hold the wall even — even wall fills, cools / cures evenly, and
  doesn't sink or warp. Where you need a thicker zone, **blend** in with a taper or fillet rather
  than stepping, and **core out** a heavy solid (box / shell it) rather than leaving a mass that
  sinks. Stiffen with ribs, not bulk (see the next move).
- **Draft every vertical wall.** A draft-free wall drags, scuffs, and can stick in the tool. Add
  **≥ ~1–2°** to each vertical face (more on textured or deep walls), drafting *toward* the parting
  line so the part lifts clean. Nearly free in CAD and expensive to add to a cut tool later.
- **Fillet, don't sharpen.** Generous internal radii let the melt / resin flow around the corner and
  cut the stress riser; sharp internal corners choke fill, crack in service, and grip the tool.
  Outside corners can be smaller (cosmetic / handling); no internal corner should be truly sharp.
- **Stiffen with ribs, not thickness — by the ratios next door.** A thick solid sinks and warps;
  win stiffness with **modest ribs / gussets** kept in proportion to the wall instead. The rib /
  boss / gusset ratios (rib-vs-wall, rib height, boss OD, root fillets) are **owned by
  [structure](structure.md#data--defaults)** — design ribs to *that* lens, don't fatten the wall.

## Decision rules

- **Vertical mold wall → add ≥ ~1–2° draft** toward the parting line (more on a **textured** or
  **deep** wall, ~1°/25 mm). A draft-free wall drags and scuffs on ejection — drafting it is nearly
  free in CAD.
- **Thick↔thin wall step → blend it, keep within the molding wall band (~1–3 mm), and for stiffness
  add modest ribs per [structure](structure.md#decision-rules), not bulk.** A piled-up mass cools /
  cures last and sinks or warps; a tapered blend plus ribs gets the stiffness without the lump.
- **Heavy solid section → core it out (shell / box it).** A solid chunk sinks on the show face and
  warps as it cools unevenly; hollow it to a uniform wall and rib the inside.
- **Sharp internal corner → fillet it.** Sharp corners choke fill, concentrate stress, and grip the
  tool; a generous radius flows, releases, and survives load (load-side fillet ratios live in
  [structure](structure.md#data--defaults)).
- **Undercut / re-entrant feature → side-action / lifter, or redesign to pull straight.** Name the
  cost: a side-action is a moving tool component. Open the feature to the pull direction, move it to
  the parting line, or split the part where you can. Soft silicone molds peel off mild undercuts;
  injection tools don't.
- **Cosmetic face → keep the parting line, gate, and ejector marks off it.** The witness line, gate
  vestige, and ejector pins all leave marks; put them on a hidden or non-show face, set by the
  parting choice above.
- **Thermoform pocket deeper than ~1:1 (depth : width) → plug-assist it or open the width.** A deep
  straight draw thins the corners badly; a plug assist pre-stretches the sheet for a more even wall,
  and generous draft + radii keep it from webbing.
- **Mating parts → leave a real clearance gap.** The per-process clearance is owned by
  [mating clearance](../../solidifai-modeling/SKILL.md#multi-part-models); molded /
  cast fits also have to account for shrink — don't model parts coincident.

## Questions that matter

- **Injection, cast, or thermoformed?** It picks the column above and rules whole feature classes in
  or out: injection needs draft + side-actions and pays for a hard tool (high volume); urethane
  casting peels mild undercuts from a soft silicone mold (low volume, near-net shrink);
  thermoforming makes a **one-sided shell** from sheet with detail on the mold face only and no real
  Z features on the back. Read it from the default material (`list_materials`, the `isDefault`
  entry's process) or a part's named material — don't apply injection undercut rules to a thermoform.
- **Parting direction and the cosmetic face?** Which way the tool opens sets where every wall drafts,
  where the witness line / gate / ejector marks land, and what becomes an undercut. Name the show
  face so those marks stay off it. This is the single choice the rest of the geometry hangs on.
- **How many parts, and what volume?** Each cavity, side-action, and split is tooling cost — a
  feature that forces a side-action or a second cavity quietly drives the bill. High volume earns a
  hard injection tool; a handful of parts wants casting or thermoforming. Splitting a part to pull
  straight can be cheaper than one tool full of lifters; fastening the split (molded-in boss /
  insert) detail is owned by the [manufacturability hub](manufacturability.md).

## Verify

- **Assert (known-by-construction):** every vertical mold wall carries **≥ ~1–2° draft** toward the
  parting line, the wall is **uniform within the molding band**, and internal corners are filleted.
  You *set* the draft, wall, and radii, so you **know** them — known-by-construction, not measured
  back from `get_model_info()` (which reports bounding box / volume / mass / `valid` / `manifold`,
  not draft, true min wall, or shrink on freeform geometry — say so rather than claiming a
  measurement).
- **Visual:** `capture_views(...)` and **look** — flag any **undercut** that can't pull straight,
  any draft-free vertical wall, the thickest piled-up **mass** (sink / warp risk), and on a
  thermoform the deepest **draw** (thinning). Confirm the parting line / gate / ejector marks fall
  off the named cosmetic face. These are the moldability killers the numbers alone won't surface.
- **Honesty:** report these as formative process-rules-of-thumb satisfied for the named process,
  **not** a verified molding. **Real shrink, sink, and warp need the actual material and tool** — a
  filled grade, a hot spot, or an unbalanced gate can move every number, so restate the
  tune-to-the-material caveat and don't claim a shrink figure the model can't show.

## Sources

- **Material-supplier part-design manuals** (DuPont / Bayer-Covestro / BASF *General Design
  Principles* booklets) — the molding fundamentals behind the table: **uniform wall** to avoid sink /
  warp, **draft on every vertical wall** for release, generous internal **radii** for flow and
  stress, and **material-dependent shrinkage** (the rib / boss proportions in those same booklets are
  owned by [structure](structure.md), not restated here). The primary source for the injection column.
- **Injection-molding manufacturer design guides** — **Protolabs** ("injection molding basics",
  "uniform wall thickness", "improving part moldability with draft") and **Xometry / Protolabs
  Network** injection-molding guides for the working ranges: draft **≥ ~1–2°** (~1°/25 mm on deep /
  textured walls), wall **~1–3 mm** held even, **parting-line / gate / ejector** placement, undercuts
  needing **side-action / lifters**, and shrink **~0.5–2%**, material-dependent. Corroborate and tune
  the table.
- **Urethane / silicone casting guides** (Protolabs / Xometry / SyBridge urethane-casting design
  tips) — soft-mold release peeling **mild undercuts**, light draft (~3–5°) for tool life, **uniform
  wall** for even cure, and **low near-net shrink** (~0.1–0.3%). Used for the casting column, not as
  exact spec — tune to the named resin.
- **Thermoforming design guides** (Ray Products / Profile Plastics / Protolabs thermoforming guides)
  — **one-sided** detail on the mold face, sheet **thinning on the draw**, **draw ratio ~1:1
  typical** with **plug assist** beyond it, generous **draft** (female ~1.5–3°, male ~3–7°) and
  **fillet ≥ sheet wall**, and the **trim / web** rules. Used for the thermoform column — tune to the
  gauge and tool.
- **Cross-links (single source of truth — linked, not restated):** the part-to-process keying and the
  fastener / molded-in-boss / insert detail live in the
  [manufacturability hub](manufacturability.md); the **rib / boss / gusset ratios** (rib-vs-wall, rib
  height, boss OD, root fillets) that turn "ribs not bulk" into real dimensions are owned by
  [structure](structure.md#data--defaults); the **per-process mating clearance** is owned by
  [solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models) — this
  lens links each rather than quoting a number.
