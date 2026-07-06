---
name: solidifai-grounding
description: Understand a thing before you model it, how its mechanism actually works and what parts the assembly really needs, so your first build has the right structure, not just the right silhouette. Use BEFORE the first build whenever the request involves a mechanism or moving parts (a click pen, hinge, latch, clamp, gear train), a multi-part product, an unfamiliar or named real-world object, or reproducing something from a photo, image, or reference. Grounding is fast and self-directed and never blocks the build waiting on the user; it is not a round of clarifying questions.
license: MIT
---

# solidifai grounding

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

The fast way to the wrong part is to model what a thing **looks like**; the right part comes
from modeling what it **is** and how it **works**. Grounding is the short research-and-reasoning
pass before the first build: seconds to a minute of reasoning plus a couple of web searches
when you have the tools. It waits on no one, so it is not stalling (AGENTS.md owns the
build-now rule). Units are millimetres.

## When to use

Ground first when the request is about how something works or what it's made of:

- a **mechanism or moving parts**: a click pen, hinge, latch, clasp, clamp, ratchet, spring,
  gear train, slider, cam, a threaded cap that actually turns;
- a **multi-part product**: several parts that fit, mate, or move together;
- a **containment object**: a device whose form is driven by what it holds (a cyberdeck,
  mini-PC, battery pack, camera rig); the real "parts" are the internal components, so ground
  them before wrapping a shell;
- a **named real-world object** whose dims govern the part: the hard rule below applies even
  when nothing moves;
- an **unfamiliar object** you can't fully picture in cross-section;
- a **reproduction from an image**: a photo, screenshot, sketch, or reference picture.
- **Skip when:** the part is pure geometry or fully specified (a bracket with given holes, a
  50 mm plate, a calibration cube). Don't research a thing you already know completely; hand
  straight to `solidifai-modeling`.

## The procedure

### Hard rule: verified dims for named objects

If the brief names a real-world object (a board, a cell, a phone, a connector, a
standard part: "Raspberry Pi 5", "18650", "GoPro mount", "M5 screw"), its governing
dimensions MUST be verified and recorded in the build brief BEFORE any geometry is
committed. Verified means confirmed this session against a spec sheet or another
authoritative source, not recalled from memory. Record each as
`name: L x W x H (source)` in the brief's key_dims or inventory.

- Check the engine's reference library FIRST: `lookup_reference("raspberry pi 5")` --
  check the library first; a hit is verified, a miss tells you what the library does know.
  Use `lookup_standard("M3 heat-set insert")` for screws, inserts, nuts, and bearings.
  A library hit IS verified; record it as `name: dims (engine reference library)` in the brief.
- Library miss, web tools available: search the object's datasheet or official drawing;
  prefer two sources when they disagree, and say which you used. Then call
  `save_reference` with the verified entry and its source so the library knows it
  next time, and tell the user in one line ("saved to your reference library").
- Library miss, no web tools: use the canonical dims you know, mark each one
  `(unverified, from memory)` in the brief, and tell the user plainly.
  Never silently guess a named object's dims. No source opened this
  session means the number is unverified no matter how sure you are;
  writing "verified" beside a recalled dim is the exact defect this
  rule exists to stop.
- Dims first, geometry second: an `execute_script` or `set_skeleton` for a
  named-object build with no recorded dims is a defect, not a shortcut.

### The grounding brief

Before any `execute_script`, get clear on six things (notes, not an essay):

1. **What & job**: what the object is and the job it does.
2. **Mechanism**: the working principle: what moves against what, how it's constrained, and
   what stores or transmits the force (a spring, a cam, a detent, a flexure).
3. **Parts**: the real part breakdown, named; which are separate bodies vs one solid, which
   move vs stay fixed. For a containment object, produce a **component inventory**: each
   internal component named with its real bounding dimensions and connector faces (recovered
   per the hard rule above).
4. **Interfaces**: how parts engage (pivot, slide, snap, thread, press-fit) and the clearance
   each needs.
5. **Key dims**: the few dimensions the *function* depends on (not the styling ones).
6. **Make-it-real**: how this gets built in *this* workspace's process/material, and where a
   faithful copy needs a print-appropriate substitute.

### How to ground

- **Reason first, always.** Write down the principle and the part list from first principles
  before reaching for anything else; this step needs no tools and is never skippable.
- **Search when you can.** With `WebSearch`/`WebFetch`, run a couple of targeted queries for
  the mechanism and the geometry you can't see: `"<thing>" how it works`, `"<thing>" exploded
  view`, `"<thing>" cross section`, `"<thing>" patent`, `"<thing>" dimensions / standard
  sizes`.
- **Read the references you find.** Open the exploded views, cross-sections, and diagrams and
  actually read them; that's where the hidden structure lives.
- **No web/image tools?** Lean on first-principles reasoning, flag the parts of the mechanism
  you're inferring rather than confirming, and mark named-object dims per the hard rule's
  degradation path. Still ground; never fall back to modeling the silhouette.

### Reproducing from an image

A photo is a 2D projection: it hides the back, the cross-section, and every internal
interface. Identify the object, then research it *as an object* (above) to recover the
unseen; only then measure it by eye for proportion and scale (see
**solidifai-reverse-engineering**) and build the structure you grounded, not the outline in
the frame.

### Make it real in this process

Ground the mechanism in this workspace's process and material (`get_manufacturing_profile()`).
A faithful copy of a sprung-steel or machined mechanism often won't function as a print;
design the print-appropriate equivalent that does the same job (a living hinge or flexure for
a folded-steel spring, a separate spring or elastic as the energy store, generous clearances
for printed moving parts) and tell the user plainly what you changed and why.

### Hand off and surface the brief

Your six-item brief IS the **build brief** the user sees (AGENTS.md "State the build brief").
For a mechanism, an assembly, an image reproduction, or a containment object it is a
**pause**-tier brief: record it with `propose_build` (tier set), state it in the thread, and
give the user a beat to steer before you commit geometry or call `begin_round`. Then hand it to the build skills: **solidifai-modeling** for geometry,
**solidifai-assemblies** for multi-part fit and motion (shared dims and meeting frames become
the skeleton, grounded interfaces the `attach` frames and `inputs`; parallel authoring via
**solidifai-orchestration**), **solidifai-product-design** for human-facing judgment, and the
packaging path (`internal-layout` lens + `integrated-device` playbook) for a containment
object. Confirm with **solidifai-self-verify**.

## Anti-patterns

| Excuse | Reality |
|--------|---------|
| "Build immediately means skip research" | Stalling is making the *user* wait. Grounding waits on no one. Build the *right* thing now. |
| "It's a familiar object, I know the shape" | Knowing the shape is not knowing the mechanism. The shape is the easy part, and the wrong one. |
| "I remember the Pi's size" | Recalled is not verified. Web-verify, or mark it unverified and say so. |
| "One photo is enough to copy it" | A photo is a projection; it hides the back, the section, and every interface. Ground the unseen. |
| "I verified it; saving is extra work" | A verified dim you don't save is re-verified every session. `save_reference` takes one call; do it while the source is open. |
| "I'll model the look and refine later" | Wrong structure doesn't refine into right structure; you rebuild from scratch. Ground once, build once. |
| "No web tools, so I can't research" | Reason from first principles; you know how most mechanisms work. Flag what you're inferring. |
| "It's a spring/metal part; I'll just copy it in plastic" | A faithful copy won't function in print. Design the print-appropriate mechanism for the same job. |

Red flags, all meaning stop, ground, then build:

- About to call `execute_script` on a mechanism / multi-part / photo request without having
  named the **parts** and the **working principle**.
- Modeling a stand-in for a mechanism: a pen tip frozen extended, a click button that's just
  a nub, a sprung body as a static prism.
- Treating a single photo as the whole solid.
- Reaching for `WebSearch` only to look at your *own* renders, never the reference.

## Cross-references

- **solidifai-modeling** - build the grounded geometry.
- **solidifai-assemblies** - multi-part fit and motion authoring.
- **solidifai-product-design** - human-facing design judgment (and the `integrated-device`
  playbook for containment objects).
- **solidifai-reverse-engineering** - rebuild from a photo or file.
- **solidifai-delegation** - grounding is the cleanest thing to hand out: fan
  **grounding scouts** over different angles (how it works, an exploded view, prior art) and
  synthesize their findings into one structure and parts list; a scout returns findings,
  never engine edits; with no workers, do the same passes in sequence.
