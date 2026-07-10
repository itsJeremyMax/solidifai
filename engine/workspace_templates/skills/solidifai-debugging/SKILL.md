---
name: solidifai-debugging
description: Diagnose and fix a failed solidifai CAD build. Use when execute_script returns an error, the model didn't render, the viewport is empty, a fillet/chamfer/offset/revolve failed, or the user says "debug my model" / "why isn't it showing" / "fix the error". Maps common solidifai modeling errors to their cause and fix.
license: MIT
---

# solidifai debugging

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

This skill owns the failed or wrong-looking build. A failed `execute_script` returns
`{"ok": false, "error": ..., "traceback": ...}` and the **previous good model stays in the
viewport**, so you can fix and re-run without losing work. **solidifai-self-verify** owns the
done-gate on a build that succeeded; this skill gets it building and looking right first.

## When to use

- `execute_script` returned an error, or the build succeeded but the geometry looks wrong.
- The viewport is empty, or the user says "debug my model", "why isn't it showing", "fix the
  error".
- A fillet, chamfer, offset, shell, or revolve failed.
- **Skip when:** nothing failed and you want the done-check against the brief; that is
  **solidifai-self-verify**.

## The procedure

1. **Read the error string and traceback.** The last line names the failing call. Most failures
   are one of the cases in `references/common-errors.md`.
2. **Did you `show()` anything?** "nothing to render: registry is empty" means no `show(...)`
   call ran. Every script must end up calling `show(part, name="...")`.
3. **Is the geometry valid?** If it built but looks wrong, call `get_model_info()` and check
   `valid` and `manifold`. `false` means a degenerate or self-intersecting solid, usually a
   fillet/chamfer/offset radius that's too large, or a profile that crosses the revolve axis.
4. **Look at it.** When the build succeeds but something doesn't add up, call
   `capture_views(["iso","front","right"], layout="grid")` and actually inspect the images
   before guessing; a model can be valid and manifold yet completely wrong (a boolean cut the
   wrong body, a fillet rolled the wrong edge, a mirrored part). Add views or `color=False` to
   disambiguate; how to read the images is self-verify's "What to look for in the views".
5. **Reproduce smaller.** Comment out the last operation (the fillet, the shell, the boolean)
   and re-run. Whichever step makes it pass is the culprit; adjust that step's parameters.

If you have made genuine fix attempts and the same operation keeps failing in a way that
looks like a product defect rather than a user or modeling mistake, switch to
**solidifai-bug-report** to offer the user a prefilled GitHub issue. Do not report a bug you
have not actually tried to fix.

### Fast checklist

- **Empty viewport, no error** → you didn't `show()`, or you edited `model.py` as a file
  without `run_file("model.py")`.
- **`cannot connect to engine`** → the app's engine is still starting; retry in a moment.
- **Fillet/chamfer failed** ("try a smaller value") → the size exceeds ~half the local wall, or
  the edge selection is wrong/empty. Don't retry random numbers: use `safe_fillet` /
  `safe_chamfer` (from `solidifai`), which clamp to the largest size that fits. (cookbook §6.)
- **Screw holes lose symmetry / "only some go in"** → `Hole()` is fragile on thin walls and
  narrow ledges. Subtract a cutter at an explicit position:
  `part - Pos(x, y, 0) * hardware.clearance_hole("M3", depth)`. (cookbook §7.)
- **Revolve failed / weird solid** → the profile crosses the rotation axis, or isn't a closed
  face. Keep it on one side of the axis and `make_face()` it.
- **`offset`/shell failed** → wall thickness too large for the part, or wrong `openings` face.
- **A tweak changed the wrong geometry, or you're unsure which parameter drives a feature** →
  `inspect_features()` lists the named features and the `driven_by` parameter each is bound to;
  confirm the mapping, then adjust with `set_params` (only `feature(...)`-wrapped operations
  show up).

### Assembly failure modes

The big one: **per-node isolation**. When one part's build fails, that node keeps its last-good
geometry and the rest still composes, so fix one part at a time. `get_assembly_tree()` shows
what the skeleton publishes and the wiring; `get_part_info(id)` reads one part's source.

- **"part produced no geometry"** → the part's `build(inputs)` never called `show()` (or showed
  `None`).
- **A skeleton input the part reads is not published** → `inputs` lists a scalar the skeleton
  never `s.scalar(...)`'d. Publish it, or fix `inputs` to match.
- **Missing attach frame** → `attach` names a frame the skeleton never `s.frame(...)`'d. Add it
  or correct the name.
- **One part fails but the rest renders** → per-node isolation; fix that part and `set_part`
  it again. The others stay served from cache.
- **Invalid part `id` rejected** → ids must match `^[A-Za-z0-9_-]+$`; no slashes, dots, or
  spaces.

## Anti-patterns

- Guessing at a fix before reading the traceback.
- Re-running the whole script when `set_params` reproduces the problem faster.
- Assuming `valid` + `manifold` means correct; look at the render.

## Cross-references

- `references/common-errors.md` - error signatures → cause → fix, with corrected snippets.
- **solidifai-modeling** - the modeling APIs themselves, and its
  `references/build123d-cookbook.md`.
- **solidifai-self-verify** - the done-gate once it builds, and how to read the captured views.
- **solidifai-bug-report** - once real fixes fail and the problem looks like a genuine
  product defect, offer the user a prefilled GitHub issue.
