---
name: solidifai-converge
description: Make a model satisfy its design requirements, by parameter search first and geometry edits second. Use when the user says "make it meet the spec", "converge", "hit all the requirements", "get it under <X> and printable and fitting", "nothing is passing", or "the wall is too thin and there's no param for it". Tries the free deterministic converge_to_spec tool first (searches declared parameters, leaves the model untouched), then escalates to targeted geometry edits via execute_script for anything that parameters alone can't fix. Loops check_requirements until every goal passes or the obstruction is clearly explained.
license: MIT
---

# solidifai converge

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

Getting a model to pass every design requirement takes two different moves: adjusting parameters
(fast, reversible, exact) and editing geometry (slower, for things no parameter controls). Try
the first move first; escalate to the second only for what it couldn't reach. This skill owns
the full requirements schema; **solidifai-self-verify** owns confirming and repairing what you
just built. Units are millimetres.

## When to use

- The user wants the model to SATISFY a stated spec: "make it meet the spec", "converge", "get
  it under <X> and printable and fitting", multiple goals to hit at once.
- A goal fails and no parameter reaches it ("the wall is too thin and there's no param for it").
- **Skip when:** you are confirming and repairing what you just built; hand back to
  **solidifai-self-verify**.

## The procedure

1. **Set the requirements.** Turn the brief into concrete, checkable goals before doing
   anything else. Call `set_requirements` with every goal you can read off the request, and
   only those; "done" should be defined, not guessed.

   ```
   set_requirements([
     {"id": "mass",     "quantity": "mass",         "op": "<=", "bound": 50},
     {"id": "size",     "quantity": "size",          "op": "<=", "bound": [80, 60, 30]},
     {"id": "wall",     "quantity": "min_wall",      "op": ">=", "bound": 1.2},
     {"id": "fit",      "quantity": "min_clearance", "op": ">=", "bound": 0.1},
     {"id": "printable","quantity": "dfm_critical",  "op": "<=", "bound": 0}
   ])
   ```

   Requirements persist in the workspace and re-check on every build; update them only when the
   user changes the brief.
2. **Try the deterministic tool.** Call `converge_to_spec()` (optionally
   `objective="min_mass"` or `"max_mass"`). It searches the declared `PARAMS` for a combination
   that satisfies every predicate requirement, non-destructively: it rebuilds variants
   internally and restores the live model, so it is safe at any point. Read the result:
   - `found: true`: review the proposed `params` and the `before`/`after` per-goal summary; if
     the numbers look right, `converge_to_spec(apply=True)` (or `set_params` manually), then
     `check_requirements` to confirm and `capture_views` to see it. Done.
   - `found: false`, or `notAddressable` non-empty: no parameter combination satisfies every
     goal, or some goals involve geometry no declared parameter controls. `closestMiss` shows
     the nearest candidate and what it still fails; `notAddressable` names the goals parameters
     cannot reach. Continue to step 3 for those. A model with no `PARAMS`/`build` skips
     straight to step 3.
3. **Fix what parameters couldn't reach.** For each failing goal, read its `detail` field (what
   failed and by how much), then make the smallest geometry change that closes the gap with
   `execute_script`:
   - `min_wall` too thin, no wall param: thicken that wall (shell thickness, rib width, a
     stepped profile); add a `wall_t` param while you are there.
   - `mass` over budget: hollow or shell, add lightening pockets, or trim a non-structural
     boss; confirm with `measure`, don't guess.
   - `size` over on one axis: the detail names the axis; compress it or reorient.
   - `dfm_critical` (overhang / bridge): chamfer or fillet the unsupported face, gusset the
     bridge, or reorient the build direction.
   - `min_clearance` too tight: adjust the mating dimension you own; use ISO 286 fits (H7/g6
     for clearance) when the mating part is fixed.
   - `watertight` failing: fuse touching bodies or close the open shell (usually an unfused
     shared face or a boolean sliver).

   After each edit, `capture_views(layout="grid")` and read the image, then
   `check_requirements`.
4. **Loop until green, or honestly stuck.** One goal, one change, one re-check. Stop when
   `check_requirements` reports all goals met, and report what you verified ("48 g, fits the
   80x60x30 box, min wall 1.4 mm, printable, watertight"). If a goal cannot be met (the size
   bound conflicts with the mass bound), say so plainly, show the trade-off, and ask which
   constraint to relax.
5. **Record the result.** Once everything passes, quietly set the workspace description and
   tags (AGENTS.md "Keeping the workspace described").

## Anti-patterns

- Several speculative changes at once; you lose the signal about which change helped.
- Touching geometry when a parameter adjustment is enough.
- Silently returning the closest miss, or loosening a requirement to make it "pass".

## Cross-references

- **solidifai-self-verify** - the capture-look-measure-repair loop after every geometry edit,
  and the confirm-and-repair done-gate.
- **solidifai-explore** - a parameter sweep to understand the trade-off before committing to a
  geometry edit.
- **solidifai-modeling** - the build mechanics (parametric scripts, PARAMS, show, feature
  tagging).
