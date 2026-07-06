# manufacturability hub

The **router** for design-for-manufacturing. A part is only good if it actually *makes* cleanly, and
what "cleanly" means depends on the **active process** — so this hub keys the part to its process and
points to the **family lens** that owns the real numbers. It holds the cross-process routing and the
fastening-strategy call; the per-process depth lives in each family lens.

Read the process from the material: call `list_materials`, take the `isDefault` entry's process; if
the user names a material for a part, use that part's process. All values mm. solidifai already owns
the **mating-clearance** and **fastener / thread** numbers — this hub **links to those canonical
homes**, it does not restate them.

## Principle

A part is only good if it actually makes cleanly, and you must **design to the active process** — the
same shape that prints fine can be unmoldable, unmachinable, or impossible to fold. Two ideas carry
across every process: keep the **wall uniform and thick enough for the process to form it** (no thin
single shell, no piled-up mass), and **minimize material and parts** (the cheapest, strongest, most
makeable part has the least wasted bulk and the fewest pieces). Everything past that — self-support
angle, draft, tool reach, bend radius — is process-specific and lives in the family lenses. Pick the
process, then design to its lens.

## Data & defaults

**Process → family-lens router.** Read the active process, open its lens for the real numbers:

| Process | Family lens |
|---|---|
| `fdm`, `sla` / resin, `sls` / `mjf`, metal AM (DMLS) | [dfm-additive](dfm-additive.md) |
| `cnc` milling / turning, laser, waterjet, plasma | [dfm-subtractive](dfm-subtractive.md) |
| injection molding, casting (urethane / silicone), thermoform | [dfm-formative](dfm-formative.md) |
| sheet metal (cut flat + press-brake bend) | [dfm-sheet](dfm-sheet.md) |

**Index, not authority — the family lens owns the real numbers; this row is the at-a-glance
pointer.** See roughly where a process lands, then open the lens to design to it:

| At a glance | FDM (additive) | CNC (subtractive) | Injection (formative) | Sheet metal |
|---|---|---|---|---|
| Min wall | ~0.8–1.2 mm (0.4 mm nozzle, 2–3 perimeters) | tool-limited (~0.5–0.8 mm metal) | ~1–3 mm, held uniform | one stock `t` throughout |
| Support need | overhang ≤ 45° or support / reorient | tool reach + setups, not overhang | draft so the part releases | bend order / brake reach |
| Mating clearance | ~0.1–0.3 mm | ± 0.1 mm or better | ~0.05–0.2 mm + shrink | ~`t` tab-and-slot clearance |
| Holes | undersize; teardrop a horizontal hole | drilled / bored near-nominal | near-nominal + draft | Ø ≥ ~`t`, clear of bends |
| Fastening | heat-set insert | tapped threads (native) | molded-in boss / insert | self-clinch / PEM |

The FDM row is kept at a glance so the playbook links to `#data--defaults` still land on real
figures, but the **baseline mating clearance** is owned by
[solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models) (the manufacturing profile
`fits` value) and the **achievable per-process tolerance** by each family lens (the matching column).
Design to those homes, not to this row.

## Decision rules

- **Read the active process first** (from the default material, a named material, or stated intent),
  then **open its family lens** for the numbers:
  [additive](dfm-additive.md#decision-rules) · [subtractive](dfm-subtractive.md#decision-rules) ·
  [formative](dfm-formative.md#decision-rules) · [sheet](dfm-sheet.md#decision-rules). Don't apply
  one process's rules (FDM's 45° overhang, a mold's draft) to a part made another way.
- **Mating parts must fit → give them the canonical clearance** for the active process
  ([solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models)); never
  model them coincident — tight end for a snug press / locating fit, loose end for an easy slip / lid.

**Fastener-strategy chooser.** *Which* fastening to use is a cross-process call and lives here; the
*dimensions* (clearance holes, counterbores, insert bosses, captive-nut pockets, tapped pilots,
cosmetic threads) are owned by
[cookbook §11 — Threads & fasteners](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners)
— link to it, don't restate the tables:

- **Heat-set insert** (cookbook §11 C) — default for a **reusable, load-bearing threaded joint** that
  gets assembled / disassembled (electronics, anything serviced); strongest pull-out, needs a boss.
  (On CNC / sheet, prefer the process-native thread instead.)
- **Captive nut pocket** (cookbook §11 D) — when you **can't heat-set** but still want metal threads;
  cheap and strong, but the pocket needs a capture face so the nut can't fall out or spin.
- **Tapped pilot** (cookbook §11 E) — light-duty, occasional-assembly threads cut into plastic;
  weaker than an insert. (CNC taps real threads natively.)
- **Snap-fit** (no fastener) — for **tool-free, repeated open / close** (lids, doors, clips). The
  cantilever snap needs a **root fillet** (≥ ~0.5× the beam thickness) to kill the stress riser that
  cracks the beam; keep deflection within the material's strain limit, and on layered processes pull
  the beam **along the layers** so it doesn't delaminate (root-fillet + along-layers detail shared
  with [structure](structure.md)).
- **Modeled helical thread** (cookbook §11 F) — cosmetic / large-pitch only; printed fine threads are
  weak and rarely clean. Prefer an insert / nut for real load.

## Questions that matter

- **What process?** Read it from the default material (`list_materials`, the `isDefault` entry's
  process), a part's named material, or the user's stated intent. It decides which **family lens**
  owns the part — each lens relaxes or tightens a different constraint, so route before you design.
- **Cosmetic face / orientation constraints** — a face that must show or stay smooth, a build plate /
  stock it must fit, a parting line or bend order it has to respect. These force the orientation or
  setup the family lens designs around; name them up front.

## Verify

- **Confirm the part was designed to its family lens's rules** for the active process, and say which
  process and lens. Defer the numeric asserts (min wall, overhang, draft, bend radius, tolerance) to
  that lens; this hub doesn't re-measure them.
- **Clearance / fastener check:** confirm any mating gap references the **canonical clearance value**
  ([solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models)) and any
  fastener feature follows the
  **[cookbook §11](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners)**
  tables — *not* a number invented here.

## Sources

- **Boothroyd, Dewhurst & Knight, *Product Design for Manufacture and Assembly* (DFMA)** (3rd ed.,
  CRC Press) — the cross-process framing: minimize parts and fasteners, choose the fastening strategy
  deliberately (insert vs. nut vs. snap-fit), design for ease of assembly.
- **James G. Bralla (ed.), *Design for Manufacturability Handbook*** (McGraw-Hill) — the broad
  process-spanning DFM reference: pick the process to the part and design to what each one can make.
- **Per-process figures live with the depth — see each family lens's Sources:**
  [dfm-additive](dfm-additive.md#sources) · [dfm-subtractive](dfm-subtractive.md#sources) ·
  [dfm-formative](dfm-formative.md#sources) · [dfm-sheet](dfm-sheet.md#sources).
- **Internal cross-links (single source of truth — linked, not restated):** **mating clearance** →
  [solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models);
  **threads & fasteners** →
  [cookbook §11](../../solidifai-modeling/references/build123d-cookbook.md#11-threads--fasteners).
