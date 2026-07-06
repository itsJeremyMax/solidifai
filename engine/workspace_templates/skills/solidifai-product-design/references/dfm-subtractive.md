# dfm: subtractive lens

Design-for-subtractive judgment, keyed to the **subtractive process** — CNC **milling** (3-axis,
4-/5-axis), CNC **turning** (lathe), and flat-stock **cutting** (laser, waterjet, plasma). All
values mm. Numbers are widely-cited process rules and ranges from the sources below — use the rule,
not false precision, and **tune to the actual machine / tooling when the user names one** (a named
end-mill diameter, a stock alloy, a 5-axis cell all shift the limits). The process comes from the
material and the part: a milled or turned part is cut from solid bar/plate, a laser/waterjet part is
cut from flat sheet. This lens owns *what subtractive demands* — the
[manufacturability hub](manufacturability.md) keys the part to its process and points here when that
process is subtractive. This lens **owns the achievable CNC tolerance band** (the representative
number, below); which **fit class** — running / transition / press — to layer on top of that band is
owned by [fits-tolerances](fits-tolerances.md#decision-rules).

## Principle

Subtractive starts from a solid blank and **removes material with a rotating round tool** (mill,
drill) or a single point (lathe, laser, jet), so every constraint follows from **what the tool can
reach and how stiff it is there**. A round tool can never cut a perfectly sharp *internal* vertical
corner — it leaves its own radius — so internal corners must be filleted at least to the tool radius.
A tool reaching deep into a narrow pocket sticks far out of the holder and **deflects and chatters**,
so depth is limited relative to width. Anything the tool can't see in a straight line down — a true
**undercut**, a side feature behind a wall — needs another **setup** (re-fixture and re-cut), a
4-/5-axis machine, or a redesign. Pick the **process and the setups first**: milled vs. turned vs.
flat-cut decides which features are even reachable, then design the geometry to stay inside the
tool's reach and stiffness. Flat cutting (laser/waterjet) is the extreme case — it makes a 2D
profile through flat stock and **no Z features at all**.

## Data & defaults

| Rule | Milling | Turning | Laser / waterjet (flat) |
|---|---|---|---|
| Internal vertical radius | ≥ **tool radius** (no sharp internal corner); default fillet ~1–3 mm, ~1.3× tool R is comfortable; ≥ ~⅓ pocket depth keeps the tool stiff | n/a (turned profile); internal grooves limited by tool | corners take the **kerf** radius, not sharp |
| Pocket depth : width | ≤ ~**3:1** with a standard tool; ~4:1 reachable, beyond wants a long/special tool or EDM (deflection / chatter, cost) | bore depth limited by boring-bar stickout | n/a (no pockets — through-cut only) |
| Holes | drilled / bored **near-nominal**; ream / bore critical bores; standard drill sizes cheapest | bored on-axis near-nominal; cross-holes need a second op | pierced; hole Ø ≥ ~stock thickness, larger than the kerf |
| Achievable tolerance | **standard ~±0.125 mm (±0.005 in) / ISO 2768-m**; ~**±0.025 mm (±0.001 in)** on critical features with the right tooling + inspection; reamed / bored holes near-nominal — this lens **owns this band** | same band; on-axis turned diameters hold the tight end | as-cut ~±0.1 mm; don't put a tight band on a flame/jet edge |
| Threads | **tapped threads are native** — no inserts needed; depth ~1–3× Ø (first threads carry the load) | single-point or tapped on the lathe | n/a (no threads in flat cut) |
| Minimum wall | **tool-limited**; ~0.5–0.8 mm in metal is risky (chatter / deflect), thin **tall** ribs chatter under the tool — keep them within the rib aspect ratio ([structure](structure.md#data--defaults)) | thin turned walls chatter; support with a steady/tailstock | min web ≈ stock thickness; very thin stock warps |
| Undercuts / setups | a true undercut needs an **extra setup**, a **4-/5-axis** machine, or a redesign; every setup adds cost + re-fixture tolerance | back/face features need a second chucking | **no Z features at all** — flat profile only |
| Kerf / edge | n/a | n/a | **kerf** ~0.1–0.5 mm (laser) / ~0.5–1.2 mm (waterjet); a slight **edge taper** top→bottom; tol ~±0.1 mm |

Numbers are starting points — read the column for the active process and design to it. The thin-wall
and pocket figures are *metal-in-a-standard-tool* defaults; a stiffer setup, a stubbier tool, or a
softer material moves them, and **a named end-mill diameter sets the real internal radius** (it can
never be smaller than that tool's radius).

**DFM (design-for-subtractive) moves:**

- **Reach first.** Before geometry, decide milled vs. turned vs. flat-cut and **how many setups** the
  part needs: which faces the tool enters from, what it can see in a straight line, and what hides
  behind a wall. Every feature must be reachable by *some* tool from *some* setup, or it can't be
  cut — fewer setups is cheaper and holds tolerance better across faces.
- **Fillet internal corners to the tool.** A round tool leaves its radius in every internal vertical
  corner, so model those corners as fillets **≥ the tool radius** (~1.3× is comfortable). Sharp
  *outside* corners and *floor* edges are fine — only internal vertical corners are tool-limited.
- **Keep pockets shallow and wide.** Hold depth ≤ ~3× the pocket width (or the tool diameter) so the
  tool stays stiff; a deep narrow slot forces a long thin tool that deflects, chatters, and finishes
  poorly — widen it, step it, or accept a long-tool / EDM cost.
- **Tap, don't insert.** CNC cuts real **tapped threads** straight into the part — the native CNC
  fastening, no heat-set inserts (fastener/thread detail is owned by the
  [manufacturability hub](manufacturability.md)). Call out the thread and an engagement depth (the
  first few threads carry the load, so deeper rarely helps).
- **Design out undercuts.** A side hole, a re-entrant groove, or a feature behind a wall needs a
  second setup or a 4-/5-axis machine. Where you can, open the feature to a straight tool path or
  split the part so each face cuts from one direction.

## Decision rules

- **Internal sharp corner on a milled pocket → fillet it**, radius **≥ the tool radius** (default
  ~1–3 mm, ~1.3× tool R comfortable). A round tool physically can't leave a sharp internal corner —
  asking for one just gets you the tool radius anyway, or a slow corner-clearing pass.
- **Deep narrow pocket / slot (depth : width > ~3:1) → widen, step, or accept a long-tool / EDM
  cost.** A long thin tool deflects and chatters; pull the floor up, open the width, or budget for
  the special tooling rather than hoping a standard end-mill reaches.
- **Thin tall wall or rib (≤ ~0.5–0.8 mm metal, or beyond the rib aspect ratio) → thicken it,
  shorten it, or back it up.** Thin tall stock chatters under the cut and finishes rough or out of
  spec; add thickness, lower the rib, or fixture/support it (the rib aspect ratio and the rib *how*
  are owned by [structure](structure.md#data--defaults)).
- **True undercut / side feature behind a wall → add a setup, go 4-/5-axis, or redesign.** Name the
  cost: each extra setup is re-fixturing and looser cross-face tolerance. Prefer opening the feature
  to a straight tool path so one setup reaches it.
- **Critical bore / fit → bore or ream it near-nominal** and state the feature, don't assume a drill
  alone holds a tight fit. Default to the standard band (~±0.125 mm) and call out only the critical
  feature tighter (~±0.025 mm); for **which fit class** (running / transition / press) to choose on
  top of that band, see [fits-tolerances](fits-tolerances.md#decision-rules).
- **Flat part with Z features (bosses, pockets, varying thickness) → it isn't a laser/waterjet
  part.** Flat cutting makes a **2D profile through flat stock** only; move Z features to milling, or
  build them up as a separate cut-and-fasten assembly.
- **Laser/waterjet feature near the kerf → size for it.** Holes and slots want Ø ≥ ~stock thickness,
  expect a **kerf** (~0.1–0.5 mm laser, ~0.5–1.2 mm waterjet) and a slight **edge taper**; don't put
  a tight fit on a flame/jet-cut edge.

## Questions that matter

- **Milled, turned, or flat-cut?** A turned part is round-about-an-axis (shaft, hub, knob) and cheap
  on a lathe; a milled part is prismatic with pockets and faces; a laser/waterjet part is a **flat
  2D profile** with no Z features at all. The process picks the column above and rules whole feature
  classes in or out (no pockets in flat cut, no off-axis features in a single turning op).
- **Tool access and setups** — can a straight tool reach every feature, and from how many faces? Each
  re-fixture is cost and looser cross-face tolerance. Flag undercuts and deep pockets early; they're
  the features that quietly force a 5-axis machine, an EDM, or a redesign.
- **Which faces / bores are critical?** The faces that must be flat, the bores that must fit — those
  drive the setup plan (cut a critical face and its references in **one** setup) and the
  tolerance call — hold the standard band everywhere, tighten only those features, and pick the
  **fit class** on top ([fits-tolerances](fits-tolerances.md#decision-rules)); cosmetic faces can
  take the looser as-cut finish.

## Verify

- **Assert (known-by-construction):** every internal vertical corner is filleted at **≥ the intended
  tool radius**, and pockets are within the **depth ≤ ~3× width** rule. You *set* those radii and
  depths, so you **know** them — known-by-construction, not measured back from `get_model_info()`
  (which reports bounding box / volume / mass / `valid` / `manifold`, not min internal radius or true
  tolerance on freeform geometry — say so rather than claiming a measurement). State the **expected
  tolerance band** for the part (standard ~±0.125 mm, ~±0.025 mm on any feature you've flagged
  critical) so the fit can be reasoned about.
- **Visual:** `capture_views(...)` and **look** — flag any **undercut** or side feature that no
  straight tool can reach, the deepest narrow **pocket**, and any thin tall wall/rib; on a flat part
  confirm there are genuinely **no Z features**. These are the manufacturability killers the numbers
  alone won't surface.
- **Honesty:** report these as subtractive process-rules-of-thumb satisfied for the named process,
  **not** a verified machining plan or a held tolerance. The band above is the **representative**
  achievable tolerance; **real achievable tolerance needs the actual machine, tooling, and
  fixturing** — restate the tune-to-the-machine caveat rather than promising the number as held.

## Sources

- **Erik Oberg et al., *Machinery's Handbook*** (Industrial Press, current ed.) — the machining
  fundamentals behind the table: end-mill geometry and the round-tool internal-corner radius,
  tool-stickout / length-to-diameter deflection driving the pocket depth ratio, drilling and boring
  to near-nominal, and tapped-thread engagement length (the first threads carry the load). The
  primary source for the milling/turning rules above.
- **CNC manufacturer design guides** — **Protolabs** ("CNC machining design guidelines" / milling
  guide) and **Xometry** ("optimizing internal corner radii", CNC machining design guide) for the
  working ranges: internal radius ≥ tool radius (~1.3× R, ≥ ~⅓ pocket depth), pocket **depth : width
  ≤ ~3:1** (≤ ~4:1 with long tools), minimum wall ~0.5–0.8 mm in metal, tapped threads as native
  fastening, and undercuts needing extra setups / 5-axis. The same guides (with **ISO 2768-1**, the
  general-tolerance standard) give the **achievable-tolerance band this lens owns**: standard
  ~±0.125 mm (±0.005 in) / ISO 2768-m, ~±0.025 mm (±0.001 in) on critical features with the right
  tooling + inspection. Corroborate and tune the table.
- **Laser & sheet-cutting design guides** (Protolabs / Xometry sheet-cutting and laser/waterjet
  guides) — flat-stock-only (a 2D profile, no Z features), **kerf** ~0.1–0.5 mm (laser) / ~0.5–1.2 mm
  (waterjet), the slight **edge taper** top→bottom, holes ≥ ~stock thickness, and the ~±0.1 mm
  ballpark tolerance. Used for the flat-cut column, not as exact spec — tune to the named machine.
- **Cross-links (single source of truth — linked, not restated):** the part-to-process keying and the
  fastener / tapped-thread detail live in the
  [manufacturability hub](manufacturability.md); the **rib aspect ratio** and the rib / gusset *how*
  when a thin wall must be stiffened instead of thickened are owned by [structure](structure.md); the
  **achievable CNC tolerance band** is owned **here** (above), and the **fit-class framework** layered
  on top of it — which running / transition / press class to choose — is owned by
  [fits-tolerances](fits-tolerances.md#decision-rules).
