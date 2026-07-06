# dfm: sheet-metal lens

Design-for-sheet-metal judgment, keyed to the **sheet-fabrication process** — a **flat pattern cut**
from one stock sheet (laser, plasma, waterjet, or punch / turret) then **bent on a press brake**.
All values mm, written as multiples of the **material thickness `t`** because `t` is the controlling
variable. Numbers are widely-cited fabrication rules and ranges from the sources below — use the rule,
not false precision, and **tune to the actual shop / material when the user names one** (a named gauge,
an alloy, a specific brake and tooling all shift the minimums; stainless work-hardens and wants the
looser end, soft aluminum the tighter). A sheet part is **one uniform stock thickness throughout** —
there is no varying wall, no Z bosses, only a 2D profile and the bends folded into it. This lens owns
*what sheet fabrication demands* — the [manufacturability hub](manufacturability.md) keys the part to
its process and points here when that process is sheet metal.

## Principle

A sheet part is born as a **flat blank** and made by **folding that blank**, so every constraint
follows from **cut-flat-then-bend**. The cut is a 2D profile through one thickness — nothing thicker,
thinner, or three-dimensional than the sheet exists yet. The bend is the whole craft: the brake presses
the flat over a die to an **inside radius that can't be smaller than ~`t`** (push tighter and the
outer fibre stretches past its limit and **cracks**), and because the metal stretches around that
radius the **flat blank is not the sum of the leg lengths** — it's shorter by a bend allowance set by
the **K-factor** (where the neutral axis sits, ~0.3–0.45 of `t`). The flat pattern only exists if the
part **unfolds**: design a feature that two bends fight over, or a bend that needs material that isn't
there, and there is no blank to cut. Pick the **bend order and direction first** — they decide which
faces the brake can reach, how the part nests, and what collides — then keep every hole, edge, and
flange clear of the bends so the fold doesn't tear or deform them.

## Data & defaults

| Rule | Default (as a multiple of `t`) | Why |
|---|---|---|
| Min inside bend radius | **≥ ~`t`** (mild steel ~1`t`; aluminum ~1–2`t`; stainless ~2–3`t`, it work-hardens) | tighter than ~`t` stretches the outer fibre past its limit and **cracks** the bend |
| Bend relief | slot at each bend end **≥ ~`t` wide, ≥ ~`t` deep** (commonly relief ≈ radius + `t`) | a bend that runs to an unrelieved edge **tears / bulges** at the corner — the relief lets it fold clean |
| K-factor / bend allowance | **~0.3–0.45** (default ~0.33 air bend) | the neutral axis sits inside the sheet, so **flat length ≠ sum of legs** — the flat is shorter by the allowance |
| Min flange length | **≥ ~4`t` + bend radius** | a shorter flange has no flat for the brake to grip — the punch can't engage it to make the bend |
| Hole-to-bend distance | **≥ ~2.5`t` + bend radius** (edge of hole to bend line) | a hole inside the bend deformation zone **stretches into an oval** as the fibre flows |
| Tabs & slots | tab into a matching slot for **self-fixturing** (~`t` clearance) | locates and squares mating sheet parts for weld / rivet without a jig — cut into the flat, costs nothing |
| Hems | folded-back edge, flat or teardrop; flat-hem inside ≈ ~`t` | stiffens a free edge and **removes the raw cut burr** from a handled / cosmetic edge |
| PEM / self-clinch fasteners | threaded nut / stud **pressed into a cut hole**, no back access | the **sheet-native threaded fastening** — see the note below; not a plastic insert |
| Uniform thickness | **one stock `t` throughout** — no varying wall, no Z bosses | the part is cut from one sheet; thickness is the gauge, not a modeled dimension |

Numbers are starting points — every row scales with `t`, and the **alloy moves the bend rows most**:
soft aluminum bends to ~`t`, stainless wants ~2–3`t` because it work-hardens and cracks at a tight
radius. The relief, flange, and hole figures are *standard-tooling* defaults; a named brake, die width,
or gauge shifts them.

**DFM (design-for-sheet) moves:**

- **Unfold first.** Before geometry, confirm the part is a **single flat blank with bends folded in** —
  one thickness, no feature that two bends fight over, no fold that needs material that isn't on the
  blank. If it won't unfold, it isn't a sheet part: split it, re-route the bends, or move it to another
  process. Then fix the **bend order and direction** so the brake reaches every fold and nothing
  collides on the closing bend.
- **Inside radius ≥ ~`t`, and one radius if you can.** Model every bend at an inside radius of at least
  ~`t` (looser for stainless) so the outer fibre doesn't crack, and reuse **one radius across the part**
  so the shop bends it all on **one tool** — mixed radii mean tool changes and cost.
- **Relieve every bend that meets an edge.** A bend running into an unrelieved edge tears or bulges at
  the corner. Cut a **relief slot ≥ ~`t`** at each such bend end in the flat — free in the cut, and it
  lets the fold finish clean.
- **Keep holes and forms clear of the bend zone.** Hold every hole, slot, and countersink **≥ ~2.5`t` +
  radius** from a bend line so the fold doesn't stretch it oval; if a hole must sit close, put it on the
  flat *after* an imagined unfold and check the distance there, not on the formed part.
- **Fasten with self-clinch, fixture with tabs.** Need a threaded hole in thin sheet → press in a
  **PEM / self-clinch nut or stud** (below), don't try to tap a single `t` of metal. Need two sheet
  parts located for weld or rivet → cut **tabs and matching slots** into the flats so they self-jig.

**Threaded fastening in sheet is self-clinch (PEM), not an insert.** A single thickness of sheet has too
few threads to tap, so the native sheet fastening is a **self-clinching nut, stud, or standoff pressed
permanently into a punched hole** — its knurled, displacing body cold-flows the parent metal around it
and locks in from one side, no welding and no back access. This is its own family; the heat-set / molded
insert tables are for plastic and **do not apply to sheet** — size a PEM to the gauge (every part has a
minimum sheet thickness) and the parent must be softer than the fastener.

## Decision rules

- **Inside bend radius < ~`t` (or a tight radius on stainless) → open it to ≥ ~`t`** (≥ ~2–3`t` for
  stainless). A radius tighter than the metal allows cracks the outer fibre on the brake — there's no
  fixing a cracked bend after the fact.
- **Bend runs up to an edge or another bend → add bend relief.** Cut a relief slot **≥ ~`t` wide and
  deep** at each bend end so the corner doesn't tear or bulge as it folds. Nearly free in the flat cut.
- **Hole / slot within ~2.5`t` + radius of a bend → move it or it deforms.** The bend zone stretches the
  metal; a hole inside it ovals. Slide the hole out along the flat, or relocate the bend.
- **Flange shorter than ~4`t` + radius → lengthen it or the brake can't bend it.** Too little flat means
  the punch has nothing to grip; add length, or form the short leg a different way.
- **Need a threaded fastening in sheet → self-clinch / PEM, not a plastic insert.** Press a PEM nut /
  stud into a cut hole sized to the gauge; don't tap a single `t`, and don't reach for the plastic
  heat-set tables — they don't apply to sheet.
- **Two sheet parts must locate for weld / rivet → tab-and-slot them.** Cut a tab into one flat and a
  matching slot (~`t` clearance) into the other so they self-fixture and square up without a jig.
- **Raw edge is handled or cosmetic → hem it.** Fold the edge back (flat or teardrop) to kill the cut burr
  and stiffen the edge; budget ~`t` for the hem's return in the flat pattern.
- **Part won't unfold (a true 3D form, varying thickness, a feature two bends share) → it isn't one
  sheet part.** Split it into bend-and-fasten pieces, or move the 3D feature to another process — a
  sheet part is one uniform `t` cut flat and folded, nothing more.
- **Bracket-style bent part needs a stiffening gusset → size it to the ratio next door.** A bend-up
  gusset or formed rib is fine; the **gusset / rib proportions** are owned by
  [structure](structure.md#data--defaults) — design to that lens, don't restate a ratio here.

## Questions that matter

- **What gauge and material?** The **thickness `t` and the alloy set every number above** — `t` scales
  the radius, relief, flange, and hole distances, and the alloy moves the bend rows (soft aluminum ~`t`,
  stainless ~2–3`t` because it work-hardens). Read the gauge from the stock / default material
  (`list_materials`, the `isDefault` entry) or a named material; one stated gauge fixes the whole table.
- **How many bends, and which direction does each fold?** Bend count and direction drive the **bend
  order** (does the brake reach every fold without the part colliding with itself or the tooling?) and
  the flat pattern. A part with one radius bent in a clean sequence is cheap; bends that fight the
  closing fold or need a tool change aren't.
- **Does it unfold into a single flat pattern?** The whole process assumes one **flat blank** of uniform
  `t`. Confirm there's no varying thickness, no Z boss, no feature two bends share — if it won't unfold,
  it's not a sheet part and the rest of the lens doesn't apply.

## Verify

- **Assert (known-by-construction):** every inside bend radius is **≥ ~`t`** (looser for the named
  alloy), every hole sits **≥ ~2.5`t` + radius** clear of its nearest bend, every bend that meets an
  edge has a **relief slot ≥ ~`t`**, and the part is **one uniform `t`** throughout. You *set* the radii,
  the hole positions, and the gauge, so you **know** them — known-by-construction, not measured back from
  `get_model_info()` (which reports bounding box / volume / mass / `valid` / `manifold`, not bend radius,
  hole-to-bend distance, or whether the part unfolds — say so rather than claiming a measurement).
- **Visual:** `capture_views(...)` and **look** — flag any bend running to an **unrelieved edge**, any
  **hole sitting in a bend zone**, any **flange too short** for the brake to grip, and confirm the part
  reads as one folded thickness with **no Z features**. These are the killers the numbers alone won't
  surface.
- **Flat-pattern honesty:** report these as sheet process-rules-of-thumb satisfied, **not** a verified
  flat pattern. The **true flat blank length and the real bend allowance depend on the actual brake,
  die width, and tooling** (the K-factor is a fit, not a constant) — state that the flat must be set
  from the shop's numbers, restate the tune-to-the-material caveat, and **flag any geometry that does
  not unfold** rather than implying a blank exists for it.

## Sources

- **Erik Oberg et al., *Machinery's Handbook*** (Industrial Press, current ed.) — the sheet-metal
  fundamentals behind the table: minimum inside **bend radius** as a function of thickness and material
  temper (it can't go below ~`t` without cracking, and work-hardening alloys want more), **bend
  allowance** and the neutral-axis / **K-factor** so the flat length isn't the sum of the legs, and
  bend-relief and edge-distance practice. The primary source for the bend rows.
- **Sheet-metal fabricator design guides** — **SendCutSend** (bending guidelines, bend-deformation and
  "design considerations" articles), **Protolabs** and **Xometry** sheet-metal design guides for the
  working ranges: inside radius **≥ ~`t`**, **bend relief ≥ ~`t`** wide/deep at bend ends, **K-factor
  ~0.3–0.45** (~0.33 air-bend default), **min flange ~4`t` + radius**, **hole-to-bend ~2.5`t` +
  radius**, plus **tabs / slots** for self-fixturing and **hems** for raw edges. Corroborate and tune
  the table to the named gauge.
- **Self-clinch fastener references** (PennEngineering / **PEM** self-clinching fastener handbook and
  Protocase / Onshape self-clinch design notes) — the **sheet-native threaded fastening**: a self-clinch
  nut / stud pressed into a punched hole, parent metal softer than the fastener, each part with a
  minimum sheet thickness, installed from one side with no back access. Used for the PEM row — note this
  is *not* the plastic heat-set / molded-insert family and those tables do not apply here.
- **Cross-links (single source of truth — linked, not restated):** the part-to-process keying lives in
  the [manufacturability hub](manufacturability.md); the **gusset / rib proportions** for a bent
  bracket's stiffening rib are owned by [structure](structure.md#data--defaults) — this lens links them
  rather than quoting a ratio, and states the PEM / self-clinch fastening in its own words.
