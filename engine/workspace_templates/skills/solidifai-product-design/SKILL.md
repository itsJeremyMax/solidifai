---
name: solidifai-product-design
description: Apply real product-design judgment to a human-facing physical part in this solidifai CAD workspace; make it comfortable to hold, easy to use, and clean to print. Use whenever a request is about a product a person holds, wears, operates, or sees (a case, enclosure, grip, handle, knob, wearable, bracket, stand, lid) and the user has NOT fully specified every dimension, i.e. whenever how the part is held, where its controls go, whether it's printable, or how it looks actually matters. This is the design brain: what makes a part good.
license: MIT
---

# solidifai product design

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

`solidifai-modeling` is the engine driver (how to write the model and drive the tools); this
skill is the **design brain**: what makes the part good, ergonomic to hold, usable, printable,
and well-proportioned. Units are millimetres.

## When to use

- A request about a **product**, anything a person holds, wears, operates, or sees, where the
  request leaves design decisions open (the usual case).
- **Skip when:** the part is pure geometry/utility (a calibration cube, "a 50 mm plate with 4
  M3 holes at these exact coordinates"), or the user already gave full explicit specs and just
  wants it built. Hand straight back to `solidifai-modeling` and impose no design opinion.

## The procedure

1. **Classify.** Map the request to a part class with the router below. If the product has a
   working mechanism or is several parts, ground it first (**solidifai-grounding**) so you
   design around how it works, not how it looks.
2. **Load** that playbook and only the lenses (`references/`) it names.
3. **Infer & default.** Fill every unspecified dimension from the playbook's default recipe
   and the lenses' decision rules, then state the assumptions briefly to the user (e.g. "M3
   screws, 2 mm walls, 0.2 mm lid clearance"). The dims and the "why" you settle here fill the
   **build brief**'s `key_dims` and each part's `why` (AGENTS.md "State the build brief");
   record it with `propose_build` (tier set) and state it before you build.
4. **Surface the few that matter:** the 1-3 decision-changing unknowns the playbook flags, as
   stated assumptions the user can correct, not a gate you wait behind. If guessing wrong is
   cheap, just default. Never quiz, never block.
5. **Build** through `solidifai-modeling` (`execute_script`), parametric where it earns it.
6. **Run the finishing pass, then self-verify** (both below). Walk the finishing checklist
   item by item and say what each got (which face carries the seam, where the draft went,
   which edges were broken); a pass you didn't narrate didn't happen.
7. **Refine & report.** Fix what failed (`set_params`/rebuild), re-verify, run the tier's
   critique (self-verify's step 8) on a stream or pause part, then report the class assumed, the
   key defaults applied, the assumptions flagged, and any trade-off you could not resolve.

### Route the part

An idea branches on two axes, **what part is it** (the playbook) and **how is it made** (the
DFM family lens), plus any cross-cutting lens whose signal is present. Route both first.

| The request is about… | Playbook |
|---|---|
| a held device's case with buttons/ports, operated in the hand | `handheld-enclosure` |
| a **PCB / Raspberry Pi / SBC / project box / sensor housing** (a board inside, ports, heat) | `electronics-enclosure` |
| a box + lid that stores loose contents | `container-lid` |
| a stand / dock / cradle holding a device at an angle | `stand-cradle` |
| a bracket / mount fastening one thing to another | `bracket-mount` |
| a knob / dial / button / switch turned or pressed by the fingers | `knob-control` |
| a handle / grip / lever a fist wraps | `grip-handle` |
| a strap / clip / part worn on the body | `wearable` |
| a self-contained **device built around several internal components** (a cyberdeck, handheld console, mini-PC, drone body, battery pack) | `integrated-device` |

If the request spans two classes, pick the closest and pull both sets of lenses. A human-held
enclosure with several internal components routes to **integrated-device** when the form is
driven by packing the components, else **handheld-enclosure**; the playbook's Scope confirms
or redirects.

**Method:** the active method routes to a DFM family lens; the canonical process-to-family
table lives in the [manufacturability hub](references/manufacturability.md#data--defaults),
route there, don't restate it. The method is stated-or-inferred from the request, else the
default material's process from `list_materials`, else FDM. Honesty: auto-detection from the
material yields only `fdm` (plastics) or `cnc` (metals); the other families engage only when
the user names the method or you infer it.

**Cross-cutting lenses**, pull whenever the signal appears in the request:

- `thermal-ventilation` - runs warm / encloses electronics
- `sealing-ingress` - wet / dusty / outdoor / sealed
- `fits-tolerances` - mating or moving parts
- `serviceability-assembly` - multi-part / serviced / opened
- `structure` - carries a load
- `support-stability` - free-standing (must not tip)
- `ergonomics` / `affordance-usability` / `aesthetics-form` - a person holds, operates, or sees it

### Finishing pass: detail density

Run this on every product part before self-verify. Real products read as real
because their surfaces are deliberately finished; a correct-but-slab part fails
the brief.

- [ ] **Every visible edge is broken** with the profile's edge-break value
      (`get_manufacturing_profile()`); no raw 90-degree edge a hand or eye lands on.
- [ ] **No unbroken slab faces on human-facing surfaces.** A large flat face gets a
      crown, a chamfer frame, a recess, or a texture band so it reads as designed,
      not extruded.
- [ ] **Ribs, not solid slabs.** Stiffen with ribs and gussets sized off the profile
      wall (rib thickness about 0.6x wall), not with bulk volume.
- [ ] **Draft where parts grip.** Gripped, inserted, or nested surfaces get 1-2
      degrees of draft or a lead-in chamfer so they seat and release cleanly.
- [ ] **Parting line / print seam placed on purpose.** Decide which face carries the
      layer seam or parting line and keep it off the show surface (`fab_orient`
      helps pick the orientation).
- [ ] **Proportions are intentional.** Name the ratio you used (1:1.618, thirds,
      square) in the build brief; never ship an accidental aspect ratio.

Skip-tier parts (pure geometry, fully specified) skip this pass entirely; it is for
parts a person sees or holds.

### Self-verify: two channels, both required

- **(a) Measurable asserts.** Compute what you can from `get_model_info()` (bbox, volume,
  mass, `valid`, `manifold`) and the parameters you set, and check the playbook's numeric
  thresholds (wall >= printable min, cavity >= device + clearance, grip diameter in the
  comfort band, control >= finger-pad min, fastener spacing). **Honesty rule:** quantities not
  recoverable from `get_model_info()` (true minimum wall on freeform geometry, overhang on a
  curved face) are **known-by-construction**: you set a 2 mm wall so you know it is 2 mm.
  Never claim a measurement you did not make; say which checks are which. **Gravity, by
  default:** every part has a real base (or is properly mounted/hung), its center of mass
  projects inside its support, and `check_interferences()` shows nothing overlapping or
  floating that shouldn't be (rules:
  [`references/support-stability.md`](references/support-stability.md)).
- **(b) Visual review.** Call `capture_views(...)` at the angles the playbook names and look
  at the images against its named cues: every control reachable, unobstructed, visibly a
  pressable affordance; proportion balanced; no sharp or awkward transition. This catches
  what numbers can't.

**Pass = all asserts pass AND the visual review surfaces no blocking issue.** Otherwise loop
back to refine. Report residual trade-offs; never hide them.

## Anti-patterns

- Back-seat designing a part the user fully specified, or one no human operates.
- Quizzing the user instead of defaulting and flagging.
- Loading every lens for every part instead of the playbook's named few.
- Claiming a measurement that was actually known-by-construction.
- Shipping an unbroken slab face, a raw 90-degree edge, or an accidental aspect ratio on a
  product part (the finishing pass exists to catch these).

## Cross-references

- **solidifai-grounding** - understand a mechanism or assembly before designing it.
- **solidifai-modeling** - build the geometry; this skill decides, that one drives.
- **solidifai-self-verify** - the full verify loop and repair playbook.
- **solidifai-converge** - drive the part to a stated spec.
- **solidifai-delegation** - when the brief leaves real design directions open and your
  harness has workers, a **design scout** can return decisions (grip size, control placement,
  proportion, printability calls) for you to apply; generating CAD variants is a build
  activity and stays with you. With no workers, make the calls yourself.
- **`references/` (lenses)** - cross-cutting knowledge with sourced numbers: the
  cross-cutting list above, plus the DFM hub `manufacturability` routing to `dfm-additive` /
  `dfm-subtractive` / `dfm-formative` / `dfm-sheet`, and `internal-layout` (the inside-out
  packing method: INVENTORY -> LAYOUT -> RESERVE -> DERIVE -> WRAP).
- **`playbooks/` (part classes)** - the classes in the router above, `handheld-enclosure`
  through `integrated-device` (shell derived from the packed component inventory), each
  composing a few lenses. Start from the playbook; it links into the exact lens sections it
  needs. A number lives in exactly one lens; playbooks link, they don't restate.
- **`references/acceptance-scenarios.md`** - worked end-to-end design scenarios showing the
  full routing, lens composition, and verify pass.
