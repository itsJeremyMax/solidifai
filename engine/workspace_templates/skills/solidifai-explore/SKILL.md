---
name: solidifai-explore
description: Explore a parametric model's design space and pick the best version. Use when the user asks for options or variants ("show me a few", "give me 3 options"), to compare a dimension's effect ("how does wall thickness change the weight"), to sweep or tabulate a parameter, or to optimize ("make it as light as possible", "the smallest that still fits", "lightest version that prints"). Covers sweep (a measured table across values), optimize (best value for an objective under constraints), seeing the options with capture_views, and applying the winner.
license: MIT
---

# solidifai explore

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

A parametric model is a whole family of parts, not one. `sweep` and `optimize` search that
family with real measurements; both are **non-destructive** (they build and measure variants
without touching the live model or the viewport), so you explore freely and only `set_params`
when you've chosen. Units are millimetres.

## When to use

- The user asks for options or variants ("show me a few", "give me 3 options").
- They want a dimension's effect measured ("how does wall thickness change the weight"), a
  parameter swept or tabulated, or an optimum ("as light as possible", "the smallest that
  still fits").
- **Skip when:** the model has no `PARAMS`/`build` (add parameters with **solidifai-modeling**
  first, or vary it by editing the script), or the job is driving the model to a stated spec;
  that is **solidifai-converge**.

## The procedure

1. **Sweep for the numbers.** `sweep(param, values)` builds the model at each value (other
   parameters held) and returns a table of value to mass, volume, and bounding box. Pass
   `checks=true` to also run a DFM check per sample and include the issue count.
2. **See the options.** For the values worth comparing, `set_params` to each and
   `capture_views(layout="grid")` so you and the user compare shapes, not only numbers.
3. **Optimize for a goal.** `optimize(param, objective, constraints)` samples the parameter's
   range and returns the best feasible value plus every point it evaluated, so you can show
   the trade-off. `objective` is `min_mass` or `max_mass`; `constraints` can be
   `max_size: [x, y, z]` and `printable: true`. State the objective and constraints plainly
   before you run it, and report what was feasible ("3 of 7 sampled sizes fit the box; the
   lightest was 18 mm at 24 g"). `printable: true` checks DFM per sample and is slower.
   Optimize one parameter at a time: for two interacting dimensions, optimize the dominant
   one, apply it, then the second.
4. **Apply the winner.** `set_params({param: chosen})` commits the value to the live model.
   With requirements set (`set_requirements`), results are judged against real goals. Then
   verify with **solidifai-self-verify** before declaring done.

### "Give me N options"

1. Pick the parameter that most changes the part for what the user cares about (wall thickness
   for weight, a fillet for feel, a diameter for fit).
2. `sweep` it across N sensible values.
3. `set_params` to each and `capture_views(layout="grid")` so they can be seen side by side, or
   capture the two or three most different ones.
4. Present each option with its mass and size from the sweep table, say which you'd pick and
   why, and offer to apply it. Remember to `set_params` back to the chosen one at the end (the
   sweep itself left the model untouched).

## Anti-patterns

- Nothing feasible and you silently return the closest miss; say so and propose loosening the
  constraint or varying a different dimension.
- Guessing a trade-off you could have swept and measured.
- Optimizing two interacting parameters at once.
- Running `printable: true` by default when printability isn't a real constraint.

## Cross-references

- **solidifai-modeling** - the build mechanics, and where a non-parametric model gets its
  `PARAMS`.
- **solidifai-self-verify** - confirm and fix the chosen variant before declaring done.
- **solidifai-converge** - drive the model to a stated spec instead of exploring around it.
