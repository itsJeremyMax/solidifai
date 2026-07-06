# dfm: additive lens

Design-for-additive judgment, keyed to the **additive process and technology** — FDM, SLA / DLP,
SLS / MJF, and metal AM (DMLS). All values mm. Numbers are widely-cited process rules and ranges
from the sources below — use the rule, not false precision, and **tune to the actual machine /
material when the user names one** (a 0.4 mm nozzle, a specific resin, a powder bed all shift the
minimums). The process comes from the material: call `list_materials`, take the `isDefault` entry
and read its process; if the user names a material for a part, use that part's process. This lens
owns *what additive demands* — the [manufacturability hub](manufacturability.md) keys the part to
its process and points here when that process is additive.

## Principle

Additive builds a part **layer by layer from the bottom up**, and every additive constraint follows
from that: a wall must be a few deposited tracks wide or it won't form, an overhang has nothing to
rest on until the angle is shallow enough to self-support, an enclosed cavity traps the resin or
powder it was built in, and the part is weakest **across** the layers because that's where the bond
is. Pick the **build orientation first** — it decides which faces become overhangs, which face is
cosmetic, and which direction is weakest — then design the geometry to need as little support as
possible. Each technology relaxes a different one of these: SLA / DLP supports any angle but must
drain; SLS / MJF self-supports in its powder bed but must let that powder escape; metal AM needs
supports *and* heat anchoring. Design to the active technology's row, not a generic "3D-printable."

## Data & defaults

| Rule | FDM | SLA / DLP | SLS / MJF | Metal AM (DMLS) |
|---|---|---|---|---|
| Minimum wall | ~0.8–1.2 mm (0.4 mm nozzle, 2–3 perimeters) | ~0.5–1 mm | ~0.7–1 mm | ~0.4–1 mm (tech-dependent) |
| Supports / overhang | stay ≤ 45° from vertical, else support / reorient | supports any angle; needs drain + cleanup | self-supporting; no supports | needs supports + heat anchoring |
| Bridging | re-shape / support beyond ~5–10 mm | supported | n/a (powder bed) | limited; orientation-driven |
| Holes | print undersize; teardrop a horizontal hole | near-nominal | near-nominal | near-nominal; ream critical bores |
| Hollow parts | n/a | drain hole for trapped resin | powder-escape hole ≥ ~3.5–5 mm | trapped-powder escape |
| Anisotropy | weak between layers; print load along layers | mild | near-isotropic | near-isotropic after stress-relief |

Numbers are starting points — read the column for the active technology and design to it. The thin
wall figures are *supported* walls; an unsupported or tall thin wall wants the looser end (and on
FDM a load-bearing wall wants ≥ ~1.2 mm, two-plus perimeters).

**DFAM (design-for-additive) moves:**

- **Orientation first.** Before anything else, decide how the part lies on the build plate: which
  faces become overhangs (and so need support or a chamfer), which face is the cosmetic / smooth
  one (lay it up or on a flat, not against supports), and which direction carries load (run it
  *along* the layers — see [structure](structure.md#data--defaults), not across the weak interlayer
  bond). A good orientation removes more support and anisotropy problems than any later fix.
- **Design out supports.** A support is a surface, time, and cleanup cost. Before accepting one,
  **reorient**, **chamfer or fillet** the offending overhang to within the self-support angle, or
  **teardrop** a horizontal hole so its top self-supports. Prefer the geometry fix; accept support
  only where the part genuinely can't be reoriented out of it.
- **Bed adhesion & warping on large flats.** A big flat first layer warps and lifts as it cools
  (FDM / metal especially). Keep walls **even** (uneven mass cools unevenly and pulls), break a
  large flat with **ribbing** or a slight dome, and lean on a **brim or raft** for grip rather than
  fighting a curling corner. Rounded outside corners on the footprint lift less than sharp ones.
- **Elephant's foot.** The first layers squish out under the weight above and the bottom edge bulges
  wider than nominal, fouling fits and flatness. **Chamfer the bottom ~0.5–1 mm edge** (a couple of
  layers) so each first layer is slightly inset — the squish then lands inside nominal instead of
  past it. Cheaper in CAD than chasing it in the slicer.
- **Powder-escape holes for SLS / MJF hollows.** A sealed cavity traps unsintered powder that adds
  weight and can never be cleaned out. Add at least one (ideally two, on opposite faces) escape hole
  **≥ ~3.5–5 mm** per hollow volume; longer internal channels want the larger end.

## Decision rules

- **On FDM:** wall **< the FDM minimum** (~0.8 mm at a 0.4 mm nozzle) → **thicken to the table
  value** (≥ ~1.2 mm on a load path) or keep it thin and **add ribs / gussets** for stiffness
  (link [structure](structure.md)) — don't ship a one-bead wall on a load path.
- **On FDM:** overhang **> 45° from vertical** → **chamfer / fillet** the face within the
  self-support angle, **reorient** so it points up, or accept **support** (and its cleanup). Prefer
  the geometry fix.
- **On FDM:** horizontal **bridge > ~5–10 mm** → add a support, a center pillar, or **re-shape it**
  (arch, teardrop, 45° chamfered underside) so it self-supports.
- **On FDM:** small **horizontal hole or pin** → oversize ~0.1–0.3 mm and / or **teardrop** the top
  so it prints round (other processes print holes near-nominal).
- **On SLA / DLP:** thin feature → it can go finer (~0.5–1 mm), and supports take any angle — but a
  **fully enclosed cavity** needs a **drain hole** (≥ ~2.5–3.5 mm) so trapped resin doesn't cup,
  crack, or blow out, and every part still needs **support + post-cure cleanup** planned in.
- **On SLS / MJF:** no supports to design around (self-supporting in the powder bed), but any
  **hollow / enclosed volume** needs a **powder-escape hole ≥ ~3.5–5 mm** (two is better) or the
  powder is trapped for good.
- **On metal AM (DMLS):** treat min wall as **tech-dependent and heavier** (~0.4–1 mm; unsupported
  walls toward the top of that), design in **supports + thermal anchoring** for overhangs, and plan
  to **ream / machine critical bores** to tolerance after a **stress-relief** step. Orientation is
  critical — it drives residual stress and which faces need support.
- **Any process:** large flat first layer or uneven walls → expect **warp + elephant's foot**;
  even out the walls, break the flat with ribbing / a dome, chamfer the bottom edge, and plan a
  **brim / raft**.

## Questions that matter

- **Which process, and which technology?** Read it from the default material (`list_materials`, the
  `isDefault` entry's process) or a part's named material. It picks the column above — FDM, SLA /
  DLP, SLS / MJF, or metal AM — and each relaxes a *different* constraint (SLA drains, SLS escapes
  powder, metal needs anchoring). Don't apply the FDM 45° / bridging rules to a powder-bed part.
- **Which face is cosmetic, and which way does load run?** The cosmetic face wants to lie up or on a
  flat (not against supports); the load direction wants to run **along** the layers, not across the
  weak interlayer bond. Both feed the orientation choice.
- **Any orientation constraints?** A face that must be smooth, a bed it must fit, a bore that must
  be round — these can force the build orientation, which then sets where the overhangs and the weak
  direction land. Decide it up front, not after modeling.

## Verify

- **Assert (known-by-construction):** every wall is at or above the **minimum-wall figure for the
  active technology** (the table column); load paths get extra. You *set* the wall, so you **know**
  it — known-by-construction, not measured back from `get_model_info()`. (True minimum wall on
  freeform geometry is **not** recoverable from `get_model_info()`, which reports bounding box /
  volume / mass / `valid` / `manifold`, not min thickness — say so rather than claiming a
  measurement.)
- **Visual:** `capture_views(...)` and **look** — flag any face steeper than **45° from vertical**
  (FDM) and the longest unsupported **bridge**, and check the cosmetic face and the build-up
  direction read right. On SLA confirm any enclosed cavity has a drain hole; on SLS / MJF confirm a
  powder-escape hole on each hollow; on metal confirm overhangs are anchored. Overhang angle on a
  curved face is a visual / known-by-construction check, not a number from the model info.
- **Orientation stated:** say which way the part builds, and why (cosmetic face up, load along the
  layers, overhangs minimized). The constraints above only hold relative to a chosen orientation, so
  name it.
- **Honesty:** report these as additive process-rules-of-thumb satisfied for the named technology,
  **not** a verified print. The real machine / material can shift every minimum — restate the
  tune-to-the-machine caveat when the user names a specific one.

## Sources

- **Ben Redwood, Filemon Schöffer & Brian Garret, *The 3D Printing Handbook: Technologies, design
  and applications*** (3D Hubs / Protolabs, 2017) — the per-technology design rules: FDM minimum
  wall, the 45° overhang rule and bridging limits; SLA wall minimums, supports and drain holes;
  SLS / MJF self-support and powder-escape holes; metal-AM supports, anchoring and orientation. The
  primary source for the table above.
- **Manufacturer design guides** — Prusa and Bambu Lab ("modeling with 3D printing in mind",
  layers-and-perimeters, elephant-foot compensation) for FDM min wall (~0.8–1.2 mm at a 0.4 mm
  nozzle, 2–3 perimeters), the 45° self-support angle, bridging (~5–10 mm), teardrop holes and the
  elephant's-foot chamfer; **Formlabs** ("Designing for SLA", minimum-wall and hollowing guides) for
  SLA / DLP wall minimums and resin drain holes; **HP / Materialise** PA-12 (MJF / SLS) guidelines
  for self-support and powder-escape holes (≥ ~3.5–5 mm). Corroborate and tune the table.
- **Powder-bed & metal-AM vendor guides** (Protolabs / Xometry SLS-, MJF- and DMLS-design guides)
  — near-isotropy of powder-bed nylon, metal-AM heavier minimum wall (supported ~0.8 mm,
  unsupported ~1 mm, tech-dependent), supports + thermal anchoring, post-machined critical bores,
  and the stress-relief step. Used for the ranges, not as exact spec — tune to the named machine.
- **Cross-links (single source of truth — linked, not restated):** the part-to-process keying and
  fastener homes live in the [manufacturability hub](manufacturability.md), and the **baseline
  mating-clearance** home is
  [solidifai-modeling](../../solidifai-modeling/SKILL.md#multi-part-models) (the manufacturing
  profile `fits` value); this lens owns the **achievable FDM/SLA tolerance band** (how tight a
  printed fit can actually hold), not the baseline number; the **print-along-the-load** orientation
  rule is shared with [structure](structure.md#data--defaults), which owns the rib / gusset *how*
  when a thin wall must be stiffened instead of thickened.
