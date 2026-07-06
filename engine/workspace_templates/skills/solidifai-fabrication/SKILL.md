---
name: solidifai-fabrication
description: Estimate print time, filament weight, and cost for the current model, or find the best print orientation to minimize supports, or open the model in OrcaSlicer to slice and send to a printer. Use when the user asks "how much will this cost to print", "how long to print", "how heavy", "how much filament", "orient it for printing", "best print orientation", "open in the slicer", "send it to print", or "is it cheap to make". Covers fab_detect, fab_estimate, fab_orient, and fab_open through the solidifai-cad MCP server.
license: MIT
---

# solidifai fabrication

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

This skill owns the print-side tools: real estimates, orientation, and the slicer handoff,
through the same `solidifai-cad` MCP server used for modeling. **solidifai-modeling** owns
building the part; **solidifai-self-verify** owns confirming it is printable.

## When to use

- The user asks what a print costs, how long it takes, how heavy it is, or how much filament it
  uses.
- They want the best print orientation, or to open the model in the slicer and send it to
  print.
- **Skip when:** there is no model yet (build it with **solidifai-modeling** first; an empty
  model returns an error), or the question is whether the part is printable at all
  (**solidifai-self-verify**).

## The procedure

1. **Read the defaults from the manufacturing profile** (`get_manufacturing_profile()`) instead
   of guessing; the user changes them with `set_manufacturing_profile({...})`:
   - `process.overhangDeg` is the support-free overhang angle (what `fab_orient` uses by
     default; pass an explicit angle only to override).
   - `process.nozzleMm` / `process.layerMm` / `process.infillPct` are the print setup you
     describe.
   - `fabrication.nozzleTempC` / `fabrication.bedTempC` are advisory print temps. The slicer
     (Orca) owns the real values; quote these as the workspace's starting point, not as
     authoritative machine settings.
   - `fabrication.filamentCostPerKg` is the rate for any cost estimate.

### Detect the slicer

`fab_detect()` reports whether OrcaSlicer is installed and its version. You do not need it
before every estimate; use it when the user asks whether a slicer is available (report
found/not-found and version) or to explain why time is absent from an estimate.

### Estimate

`fab_estimate(destination_id=None)` returns print time, filament weight, and material cost for
the current model ("How much will this cost to print?": call it and report all three).

- **With a slicer installed**, estimates are real: the model is silently sliced in the
  background and time, weight, and cost come from the slicer's own output.
- **With no slicer**, estimates are geometry-based approximations from volume and material
  density, and `time` is null. Be upfront that time is unavailable and the other numbers are
  approximate, briefly and without alarm.
- `destination_id` targets a named printer the user configured in the Make tab; omit it for
  the workspace default. Never invent or guess one.
- Report time (if present), weight in grams, and cost in the user's configured currency. If the
  model changes after an estimate, re-run `fab_estimate()`.

### Orient

`fab_orient()` suggests a rotation (x, y, z degrees) that minimizes the overhang area needing
support, with the support metrics for that orientation vs the current one. It is advisory: the
user applies the rotation before exporting, or ignores it (for example, to preserve a surface
finish direction). Lower the profile's `process.overhangDeg` threshold only for a material or
printer that handles steeper overhangs. After suggesting an orientation, offer to re-run
`fab_estimate()` to show how it changes the numbers.

### Hand off to OrcaSlicer

`fab_open(destination_id=None)` opens the current model in OrcaSlicer, non-blocking: solidifai
hands the file over and returns. Use it when the user wants to print, slice, or send to the
printer; confirm it opened. The user configures settings, supports, and bed placement inside
OrcaSlicer and sends the job from there; you do not control what happens inside it.

## Anti-patterns

- Inventing or guessing a `destination_id`.
- Creating, deleting, or editing printer destinations; the user manages those in the app's
  **Make tab**, so direct them there.
- Naming a third-party remote fulfillment service; for an external print shop, tell the user to
  export the file (STL or 3MF) from the Make tab and upload it themselves.
- Estimating an empty or missing model; build first.

## Cross-references

- **solidifai-modeling** - build the part before running fabrication tools.
- **solidifai-self-verify** - confirm printability (thin walls, overhangs) before committing to
  a print.
