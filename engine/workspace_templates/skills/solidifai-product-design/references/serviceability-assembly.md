# serviceability & assembly lens

Grounded design-for-assembly judgment for **how a part goes together and comes apart** — how many
pieces it really needs, whether a tool can reach the fasteners, and whether the thing that gets
serviced can actually be opened. All values mm. These are **DFA design rules of thumb, not a scored
assembly study**: they tell you which parts are candidates to combine, which joint a person can
reach, and which closure suits the service interval — when assembly time or field service genuinely
drives cost, say it wants a proper DFA analysis on the real part, not a number this lens implies.

This lens is **cross-cutting** — any enclosure, lid, or multi-part playbook can pull it. It owns the
**assembly/service reasoning**: part-count reduction, fastener access and tool clearance, a single
assembly direction, captive hardware, and keying. It does **not** own the modeling mechanics of
multi-part files — *show each part separately, don't fragment one solid into fake pieces, don't fuse
parts meant to come apart* is owned by
[solidifai-modeling — multi-part](../../solidifai-modeling/SKILL.md#multi-part-models), linked here,
not restated. Nor does it own **which fastening method** to use (heat-set insert vs. captive nut vs.
tapped vs. snap-fit) — that strategy chooser lives in the
[manufacturability fastener strategy](manufacturability.md#decision-rules); this lens decides whether
a joint must be *serviceable* and *reachable*, then defers the method to that hub.

## Principle

A good assembly has **as few parts as it can**, each going in **one direction with one motion**, and
every joint reachable by a hand and a tool. The core move is consolidation: every separate part is
its own part to make, stock, align, and fasten, so the cheapest assembly combines parts unless one of
them genuinely has to be separate. The Boothroyd test settles that — a part earns its separateness
only if it **moves** relative to its neighbors, must be a **different material**, or must **separate
for assembly or service**; if none of those holds, it's a candidate to merge into an adjacent part.
Then make what's left easy to put together: stack it **top-down about one axis** so the assembler
never flips a half-built part, **key** mating parts so a wrong orientation physically won't seat, and
where a part must not fall out during assembly or service, make the hardware **captive**. Last, judge
the closure from the **service angle** — how often does this open in the field, and can a person open
it without breaking it.

## Data & defaults

| Quantity | Value / rule | Notes |
|---|---|---|
| **Minimum part count (the three-question test)** | a part may stay **separate** only if **yes** to one of: it **moves** relative to parts already assembled; it must be a **different material**; it must **separate** for assembly/disassembly of other parts. **All no → combine it.** | Boothroyd, Dewhurst & Knight's minimum-part criteria. Run it on each part as it's added; the count of yes-parts is the theoretical-minimum target. A part that's only there to fasten or space two others is usually a *no* on all three — design it out. |
| **Fastener access + tool clearance** | leave room to **reach and turn** the fastener: clear the **driver swing/rotation** and enough **driver length** to seat on the head from outside the cavity | A fastener you can't get a tool onto is a fastener you can't assemble or service. Check the tool's approach path and swing room, not just that the screw fits — a recessed screw in a deep pocket with no driver clearance is a build defect. Hidden or blocked fasteners slow assembly and block field service. |
| **Single assembly direction** | stack **top-down about one axis** ("pyramid" assembly); avoid flipping the partially-built part | Each reorientation is wasted handling and a chance to misassemble. Design so parts drop in along one reference axis from above, gravity helping seat them, the heaviest/base part first. Beats a sequence that makes the assembler flip the stack to reach the next part. |
| **Captive hardware** | use **captive nuts / retained screws** where a loose part could fall out during assembly or service | A nut that drops into a sealed box or a screw that falls on the bench is a stall (and on service, a lost part). Capture the nut in a pocket with a retaining face; use retained/captive screws on a panel that comes off in the field so nothing escapes. *Which* metal-thread method (captive-nut pocket vs. heat-set insert) is the [manufacturability fastener strategy](manufacturability.md#decision-rules) call. |
| **Keying / poka-yoke** | give mating parts an **asymmetry** so they physically seat **only one way** | A notch, an offset boss, an asymmetric tab-and-slot, or a corner cut — if two orientations are possible and one is wrong, key it so the wrong one won't go together. Mistake-proofing by geometry beats a label or an instruction. |

**DFA heuristics (rules of thumb):**

- **Every part must earn its place.** Run the three-question test before adding a part; a spacer,
  bracket, or filler that's only there to connect two others usually fails all three — merge it.
- **One axis, one motion, from above.** A part that drops straight down onto the stack assembles
  faster and misassembles less than one that needs the half-built assembly flipped or rotated.
- **If a tool can't reach it, it isn't fastened.** Clear the driver swing and approach before
  trusting a fastener; a screw with no tool path is worse than no screw.
- **Make it fit only one way.** Symmetry that hides a wrong orientation is a defect waiting to ship;
  key the part so the assembler can't seat it backwards.
- **Don't let anything fall out.** Where a loose nut or screw would drop into the box or off the
  bench, capture it — especially on a panel that's opened for service.

## Decision rules

- **Two parts, same material, never move relative to each other and never separate → combine them
  into one part.** That's all three Boothroyd questions answered *no*. Make it one solid in the model
  — but **don't fragment a single solid into fake pieces and don't fuse parts that are meant to come
  apart**; that multi-part modeling rule is owned by
  [solidifai-modeling — multi-part](../../solidifai-modeling/SKILL.md#multi-part-models).
- **A joint that gets serviced → a reachable screw with captive hardware, not a glued or
  snapped-shut box.** If a person has to open it, give them a fastener they can get a tool onto and
  capture the nut/screw so nothing falls; a permanently bonded or one-way-snapped closure on a
  serviced joint is a field-service trap.
- **It can assemble two ways and one is wrong → key it so it only fits one way.** Add the asymmetry
  (notch, offset, asymmetric tab-and-slot) at the mating interface so the wrong orientation physically
  won't seat — poka-yoke by geometry, not by instruction.
- **Frequently opened → choose the closure for repeated service.** A cover opened often wants a
  tool-free or quick closure that survives many cycles; one rarely opened can be screwed shut. *Which*
  closure — snap-fit vs. screw vs. insert — is the
  [manufacturability fastener strategy](manufacturability.md#decision-rules) call; this lens supplies
  the **how often it opens** that drives it.
- **Assembly time / field service genuinely drives cost → flag it.** These rules cut obvious waste; a
  product where assembly labor or serviceability really matters wants a proper DFA study (part-count
  efficiency, handling and insertion scoring) on the real part. Say so rather than implying this lens
  scored it.

## Questions that matter

- **Is it serviced or opened — and how often?** Never opened, opened once for a battery, or opened
  routinely in the field? This sets whether the closure is bonded/snapped-shut, screwed, or a
  repeated-service closure, and whether the hardware needs to be captive. It decides the whole closure
  approach before any geometry.
- **How many parts, and which actually must be separate?** Run the three-question test — which parts
  move, need a different material, or must separate for assembly/service? Everything else is a
  candidate to combine, which is the cheapest assembly improvement there is.
- **Is there a hand and a tool access path?** Can a person physically reach each fastener and swing a
  driver onto it, along one assembly direction? A joint that's unreachable on paper is unassemblable
  and unserviceable in the part.

## Verify

- **Assert (known-by-construction):** there is **one assembly direction** and **every fastener has a
  driver approach and swing path**, **part count is justified by the three-question test** (each
  separate part moves, is a different material, or must separate — else it's combined), and **captive
  hardware is used wherever a loose part could fall out**. You *chose* the assembly order, *placed*
  the fasteners, and *decided* each part's separateness, so you **know** these — this is
  known-by-construction, not a value recovered from `get_model_info()` (which reports bounding box /
  volume / mass / `valid` / `manifold`, **not** an assembly direction or a tool path).
  `check_interferences()` confirms separable parts read **adjacent/clear** (not fused) and a single
  intended solid reads as **one body** — advisory, judge the flag against intent.
- **Visual:** `capture_views(...)` (an exploded `capture_views(..., explode=70)` pulls the stack
  apart for a render without changing the model) and **look** — do the parts stack along
  one axis from above, is there visible clearance for a driver to reach every screw head, is each
  mating interface keyed so it seats one way, and does a serviced cover have a reachable fastener
  rather than a snapped-shut seam? This catches a buried fastener or a wrong-way-symmetric part the
  numbers alone won't.
- **Honesty:** report this as **a part count justified by the three-question test and an assembly
  with a single direction, reachable fasteners, captive hardware, and keying — not a scored DFA
  study.** If assembly labor or field serviceability genuinely drives the product's cost, say it needs
  a proper DFA analysis (part-count efficiency, handling/insertion scoring) on the real part; don't
  imply this lens measured it.

## Sources

- **Boothroyd, Dewhurst & Knight, *Product Design for Manufacture and Assembly* (DFMA)** (3rd ed.,
  CRC Press) — the **minimum-part criteria (three-question test)**: a part may stay separate only if
  it **moves** relative to assembled parts, must be a **different material**, or must **separate** for
  assembly/disassembly; all *no* → consolidate. Also the design-for-ease-of-assembly framing —
  reachable fasteners, fewer reorientations, mistake-proofing — and the **theoretical-minimum
  part-count** target. The basis for the consolidation rule and the DFA heuristics here, used as the
  design rule of thumb (the scored DFA study is the analysis, not this lens).
- **Karl T. Ulrich & Steven D. Eppinger, *Product Design and Development*** (McGraw-Hill, multiple
  eds.) — design-for-assembly at the product-decision layer: minimize part count, integrate features
  into fewer parts, design for ease of handling and insertion, and weigh serviceability against
  assembly cost. The decision-altitude framing above the dimensional rules.
- **General DFA practice notes** (e.g. Boothroyd-Dewhurst DFMA application material and DFA design
  guides) — **single-axis "pyramid" / top-down assembly** so the part isn't flipped, **fastener tool
  access and driver swing clearance**, **poka-yoke / keying** by asymmetric tabs/slots/notches so a
  part seats only one way, and **captive hardware** so nothing falls out during assembly or service.
  Qualitative DFA-practice basis, not a substitute for a scored assembly study.
- **Cross-links (single source of truth — linked, not restated):** the **multi-part modeling rule**
  (show each part separately, don't fragment one solid, don't fuse parts meant to come apart) is owned
  by [solidifai-modeling — multi-part](../../solidifai-modeling/SKILL.md#multi-part-models); **which
  fastening method** (heat-set insert / captive nut / tapped / snap-fit) is owned by the
  [manufacturability fastener strategy](manufacturability.md#decision-rules). This lens owns only the
  assembly/service reasoning layered on top.
