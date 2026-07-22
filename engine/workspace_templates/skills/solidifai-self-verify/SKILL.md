---
name: solidifai-self-verify
description: Verify a part is actually right before telling the user it's done, and fix what's wrong. Use whenever you've built or changed a model and want to confirm it, or when the user says "check it", "is it done", "make it printable", "get it under <weight>", "will it fit", "make sure it meets the requirements", or asks whether a part is good. Covers the capture-look-measure-repair-recheck loop: seeing your own geometry with capture_views, running the measured checks (analyze_dfm, check_interferences, stress_check, measure, check_requirements), and the concrete parametric fixes for each flag.
license: MIT
---

# solidifai self-verify

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

A model that renders is not a model that's right. Before you tell the user a part is done,
close the loop: **see it, measure it, fix what's wrong, check again.** Everything here is
advisory: nothing auto-changes the model; you decide the fix, apply it, and verify it landed.
Units are millimetres.

## When to use

- You built or changed a model and are about to say it's done.
- The user says "check it", "will it fit", "is it printable", "make sure it meets the
  requirements".
- **Skip when:** nothing has been built yet; and "make it satisfy a spec by parameter search"
  is **solidifai-converge** (this skill confirms and repairs).

## The procedure

1. **Set the goals first**, so "done" is defined, not guessed. Call `set_requirements` with
   the goals you can read off the request, and only those: a weight budget (`max_mass`), a
   space it must fit (`max_size`, the [x, y, z] box), `printable`, `no_interference`,
   `watertight`. Requirements persist and re-check on every build; update them when the brief
   changes. The full requirement schema (`min_wall` /
   `min_clearance` / `dfm_critical` via the `{id, quantity, op, bound}` predicate form) is
   owned by **solidifai-converge**.
2. **Build** with solidifai-modeling.
3. **Look.** Call `capture_views(layout="grid")` and actually read the image against the
   checklist below. The numbers can pass while the shape is wrong. Re-capture after every
   change; never trust a stale picture.
   For a stream- or pause-tier build, look deeper than the default grid: give any part
   with internal geometry (a cavity, channel, counterbore, contained components) at least
   one section view, e.g.
   `capture_views(section={"axis": "z", "offset_mm": <through the cavity>})`; the cut
   faces render magenta: solid reads as solid, hollow as hollow. Give every critical
   interface (a mating bore, a snap lip, a port cutout, a thread) a close-up with
   `focus=<feature name or bbox>` at `resolution=1024` or higher; 512 px cannot resolve a
   0.2 mm clearance. A skip-tier part keeps the plain grid; no section or focus passes
   there.
4. **Measure.** Run the checks that matter for this part:
    - `check_requirements`: your done-gate; pass / fail / not-built per goal.
   - `analyze_dfm` for printability; judge flags against the manufacturing profile's own
     thresholds (`get_manufacturing_profile()`: `design.wallMm`, `design.minFeatureMm`,
     `process.overhangDeg`), not a generic guess.
   - `stress_check` for sharp internal corners that concentrate stress.
   - `check_interferences` for parts that overlap or float.
   - `measure_between` for an exact clearance or bore spacing: compare the built gap to the
     profile clearance instead of eyeballing (`query_faces` gives face ids to measure to;
     `thickness_at` checks a local wall against the profile min-wall).
    - `check_motion(joint=...)` for any assembly with a declared non-rigid joint: sweep the DOF
      and confirm it moves clear (`clearThrough`), no early `firstCollision`.
    - `measure` for exact mass, center of mass, and bounding box.
    - If the request touches safety-critical structure, non-FDM manufacturing, imported-model
      modification, or anything you already triaged as conditional or unsupported, re-read
      `get_engine_capabilities()` before you make the claim so you report the actual support
      level and fallback.
5. **Repair.** Fix the flags that matter (playbook below). A flag on an intentionally thin
   cosmetic rib can be left; a thin structural wall cannot.
6. **Re-build and re-check.** Loop steps 3-5 until the visual read is right and the goals
   that matter pass. Run the brief conformance pass and, for a containment object, the
   containment gate (below). Unknown is not pass, and unsupported checks stay unsupported;
   report both plainly rather than translating either into a success claim.
7. **Then say it's done** and report what you verified ("42 g, fits the 60x40x20 box,
   printable, watertight"), not just "done".
8. **Critique before you present.** On a stream- or pause-tier build (the brief's tier), once
   the gates above pass, run **solidifai-critique**: fresh-context critics get the brief, new
   hi-res captures, and these check outputs, and return ranked defects the automated checks
   cannot see. Fix the criticals and majors or justify them in your reply, then present. A
   skip-tier part presents straight away, no critique.

### What to look for in the views

- **Silhouette vs intent**: does the outline match the part the user asked for?
- **Body count**: exactly the bodies you meant: no leftover construction solid, no missing
  leg, no doubled-up part from a stray `show()`.
- **Continuity**: walls meet cleanly, fillets actually blended, no paper-thin slivers or
  accidental gaps where two features should join.
- **Proportion and placement**: holes centered where intended, bosses on the right face,
  symmetry where symmetry was meant.
- **Orientation**: for a printed part, is the build-up direction (+Z) sensible, or is a
  critical face pointing down into overhang?
- **Section read**: on a cut view, the magenta cap is the material: a wall that should be
  solid shows a solid band, a cavity shows clear background, a rib or boss its true
  cross-section. A containment build whose section is one unbroken magenta slab is a
  hollow-shell failure.

### Repair playbook

Read the flag, then make the smallest parametric change that resolves it; prefer a driving
dimension or `set_params` over resending the script.

- **Thin wall**: thicken the driving wall dimension to at least the printable minimum (raise
  the shell thickness if it comes from a shell).
- **Steep overhang**: reorient so the face climbs at 45 degrees or steeper, or add a
  chamfer/gusset; reorientation is usually cheaper.
- **Long unsupported bridge**: add a rib or pillar under the span, or split it; keep flat
  unsupported runs under about 5 mm.
- **Small hole**: open it to the reliable-print minimum (about 2 mm), or note it's meant to
  be drilled/tapped after printing.
- **Sharp internal corner (stress)**: fillet the re-entrant edge at least the suggested
  radius; sharp inside corners are where parts crack.
- **Over the mass budget**: shell or hollow the solid, replace bulk with ribs, or trim a
  non-critical dimension; re-run `measure` to confirm.
- **Doesn't fit (max_size fails)**: the report names the axis and by how much; reduce that
  dimension or reorient.
- **Interference / overlap**: adjust the mating dimension to the intended clearance. For a
  real fit (pin in a hole, press vs slip), size with the Measure tab's Fit check or
  `tolerance_stack`, the hole and shaft as an ISO 286 pair (H7 over g6 is a clearance fit).
- **Not watertight**: two solids likely touch on a face without fusing, or a boolean left a
  sliver; fuse the bodies or clean the boolean.

### Brief conformance pass

If a brief was recorded (`get_build_brief` returns one), call `get_conformance()` after a
successful build. Its stable finding IDs are the repair queue: resolve or report each blocking
finding by its stable ID, persist any assumption disposition with `update_build_brief`, then
rerun `get_conformance()` after repairs. A required reference that is failed or unknown blocks
readiness; do not treat a capture or recalled value as replacement evidence.

Then run this **conformance** evidence pass:

- **Key dims**: read `get_params()` (each `key_dims[].drives` names a PARAM) and the
  `get_model_info()` bbox, and confirm the functional dimensions match the brief. Do not use
  `inspect_features()` for this; it returns feature names, not dimension values.
- **Interfaces**: run `check_interferences` (the part-overlap check, not the assembly-wiring
  `check_interfaces`) and reconcile each pair against the brief: a declared `press` may
  overlap; a declared `pivot`/`slide` must read `clear` or `adjacent`. Use `measure_between` to
  confirm an exact clearance rather than trusting the coarse flag.
- **Part count**: compare `get_model_info()` `objects` against the declared `parts`.
- **Published-profile consumers**: for an interface meant to be satisfied by a published
  profile, confirm the consuming part actually reads it (`shape_inputs` names the skeleton
  profile and the source builds from `inputs["<name>"]`) rather than re-deriving the outline,
  the classic silent-drift failure; `check_interfaces` reports `missing_shape_input` when the
  wiring is absent.

Run this only after a build succeeded; if `get_model_info()` returns only `{round_active}` or
`check_interferences` returns `ok:false`, skip it.

Captures are supporting evidence, not a substitute for conformance contract checks. Before a
delivery export, call `get_readiness()`: an unresolved blocking finding keeps strict export
blocked and names its `findingIds`. Repair and rerun `get_conformance()` and readiness; only a
host-authorized, audited override may bypass strict export, and agents cannot request or invent
one.

### Containment gate

For a containment object (anything whose form is driven by what it holds), run four checks
in the measurable-assert channel:

- **Inventory present.** Every internal component named in the grounding inventory is a body
  in the model (shown with `role="reference"`, so it is checked here but not exported or
  DFM-flagged). A hollow shell with no internals fails here.
- **Fits with clearance.** Each component bounding box plus its reserved clearance is fully
  inside the cavity; compute from `get_model_info()` bboxes and the skeleton params.
- **No collision / no breakout.** `check_interferences()` shows no component pair overlapping
  and no component protruding through a wall; these are defects, not press fits.
- **Provisioned.** Mounts or standoffs sit under each component; port cutouts match the real
  connector dimensions from the inventory. Known-by-construction from the `integrated-device`
  playbook; verify visually if unsure.

For the visual channel, run an explode-view review (`capture_views(explode=40)`) and confirm
each component is seated and each port cutout aligns with its connector face. Full criteria:
the `internal-layout` lens (`#verify`) and the `integrated-device` playbook checklist.

## Anti-patterns

- Declaring done from the numbers without ever looking at a render.
- Trusting a stale capture after a change.
- "Fixing" a failure by loosening the requirement instead of the part.
- Ignoring a structural thin-wall flag because a cosmetic one was ignorable.
- A verify scout editing the model; repairs are writes, and there is one engine writer.

## Cross-references

- **solidifai-modeling** - the build loop the repairs feed back into.
- **solidifai-product-design** - design judgment for human-facing parts (and its two-channel
  verify with the detail-density finishing pass).
- **solidifai-converge** - drive the model to a stated spec by parameter search; it owns the
  full requirements schema.
- **solidifai-delegation** - run independent read-only checks as **verify scouts** (DFM,
  interference, stress, measure, the conformance pass, a `capture_views` look), each returning
  flags. You integrate the flags and make every repair (one engine writer); a scout never runs
  while a build is in flight. With no workers, run the checks in sequence.
- **solidifai-critique** runs after these gates succeed on a stream- or pause-tier build; this skill proves the checks pass, critique asks whether the part is good.
