---
name: solidifai-orchestration
description: Build a multi-part assembly fast by decomposing it into a frozen skeleton and parts, then authoring the parts in parallel. Use when an assembly has several parts that share dimensions and can be written independently (a lid plus base plus latch, a bracket plus arm plus pivot, a multi-piece enclosure): write the skeleton, freeze it with begin_round, fan out one set_part per part (one subagent each when you can), then compose the whole assembly once with end_round and verify.
license: MIT
---

# solidifai orchestration

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

**solidifai-assemblies** owns the skeleton and part authoring mechanics; this skill owns the
**authoring round** on top of them: freeze the skeleton, write all the parts, compose once at the
end. The parallelism is in the authoring, not the kernel: the geometry kernel still builds parts
one after another under the engine's lock, but workers (contract: **solidifai-delegation**) can
write different parts at once because every part reads only the skeleton, never a sibling. A
round also defers the whole-assembly compose and render to `end_round`: one consistent result
instead of one per part.

## When to use

- An assembly has **several parts** that share dimensions and can each be written on its own,
  and the per-part work makes a fan-out worth it (a lid + base + latch, a multi-piece
  enclosure).
- **Skip when:** a single part, or a two-part assembly you can write in a few seconds; outside a
  round `set_part` composes immediately, exactly as in **solidifai-assemblies**.

## The procedure

1. **Ground and decompose.** For a mechanism, ground first (see **solidifai-grounding**). Then
   list: the **parts** (one simple id each), the **shared dimensions** (every number two or
   more parts must agree on; they become skeleton scalars), and each part's **interface**
   (where it sits and what it mates to; each placement a skeleton frame). If you cannot name
   the shared dimensions and frames yet, you are not ready to freeze. Identical repeated parts
   (four wheels, six bolts) are ONE part definition placed with `set_occurrences`, not N ids in
   the fan-out: publish a frame per placement and count them as one part here
   (**solidifai-assemblies**).
2. **Write the skeleton** with `set_skeleton(code)`: `PARAMS` for the sliders,
   `s.scalar(name, value)` per shared dimension, `s.frame(name, Location(...))` per attach point.

   ```python
   # doctest: +SKIP  (skeleton.py: runs in assembly mode via set_skeleton)
   from solidifai import skeleton
   from build123d import Location

   PARAMS = {
       "body_w": {"value": 60.0, "min": 30.0, "max": 120.0, "step": 1.0, "unit": "mm", "desc": "Body width"},
       "body_h": {"value": 30.0, "min": 15.0, "max": 90.0,  "step": 1.0, "unit": "mm", "desc": "Body height"},
       "wall":   {"value": 2.4,  "min": 1.2,  "max": 5.0,   "step": 0.2, "unit": "mm", "desc": "Wall"},
   }

   def build(body_w, body_h, wall):
       s = skeleton()
       s.scalar("body_w", body_w)
       s.scalar("wall", wall)
       s.frame("base_frame", Location((0, 0, 0)))         # the base
       s.frame("lid_frame", Location((0, 0, body_h)))     # the lid, body_h up
       s.frame("latch_frame", Location((body_w / 2, 0, body_h / 2)))  # the latch on the side
       return s
   ```

3. **State the pause-tier build brief** before you open a round (AGENTS.md "State the build
   brief"): parts map to the per-part workers, key_dims to skeleton scalars, interfaces to the
   attach frames and clearances; give the user a beat to steer before fanning out.
4. **Freeze with `begin_round()`.** It freezes the skeleton (a single writer while the round is
   open) and returns the **contract** for the fan-out: the params, scalars, frames, and any
   published shapes. Read it so you know which scalars each part may take as `inputs` and which
   frame each attaches to.

   ```python
   # doctest: +SKIP  (assembly-mode tool call)
   contract = begin_round()
   # contract["skeleton"] -> {"params": {...}, "scalars": ["body_w", "wall"],
   #                          "frames": ["base_frame", "lid_frame", "latch_frame"],
   #                          "shapes": ["seat"]}
   ```

   While the round is open, `set_skeleton` is refused. If a part needs a shared dimension or
   frame the skeleton lacks, finish the round, amend the skeleton, and start another round.
   `abort_round()` discards a round without composing.
5. **Fan out one part per worker.** The handoff per worker is small and complete: its **id**,
   what the part is, its **inputs** (the scalars it may read; a part building from a published
   shape also declares `shape_inputs=["seat"]`), and its **attach** frame. The worker writes the
   geometry and calls `set_part(id, code, attach=..., inputs=[...])`. With workers, each writes
   a different part at the same time; without, author the parts one after another; the round
   composes them at `end_round` either way. During a round each `set_part` builds and validates
   just that part and returns `{"ok": true, ..., "deferred": true}`. A part that fails comes
   back `{"ok": false, "error": ...}` and is **isolated**: rolled back (no source, no manifest
   entry), recorded in the round's failed map, and the round continues. Note it and move on;
   fix it after the compose.

   ```python
   # doctest: +SKIP  (parts/base.py: build(inputs) runs against skeleton inputs)
   from solidifai import show
   from build123d import BuildPart, Box

   def build(inputs):
       with BuildPart() as p:
           Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
       show(p.part, name="Base")
   ```

6. **Compose once with `end_round()`.** It leaves deferred mode and composes plus renders the
   whole assembly one time. Check the `failed` map: fix a failed part with another `set_part`
   (a fresh round for several, or one `set_part` outside a round, which composes immediately).

   ```python
   # doctest: +SKIP  (assembly-mode tool call)
   result = end_round()
   # result -> {"ok": true, "buildId": N, "failed": {}}   # all parts composed
   # if result["failed"] is e.g. {"latch": "...no geometry..."}, fix that part and re-set it.
   ```

7. **Verify the composed assembly** like any model: `check_interferences()` for static fit,
   `check_motion(joint=...)` (or `part, kind, ...`) for anything that moves, `capture_views([...])`
   to look.

### Worked example: a three-part enclosure

Base, lid, and a side latch, sharing `body_w` and `wall` from one skeleton. Author all three in a
single round, compose once, then check fit.

```python
# doctest: +SKIP  (the call sequence, in assembly mode)
set_skeleton(<skeleton code above>)        # publishes body_w, wall + base/lid/latch frames

begin_round()                              # freeze; returns the scalars + frames contract

# fan out (one subagent each, or in sequence) -- each part reads only the skeleton:
set_part("base",  <base code>,  attach="base_frame",  inputs=["body_w", "wall"])
set_part("lid",   <lid code>,   attach="lid_frame",   inputs=["body_w", "wall"])
set_part("latch", <latch code>, attach="latch_frame", inputs=["body_w", "wall"])

end_round()                                # compose + render the whole enclosure once

check_interferences()                      # confirm the lid seats and the latch clears
```

One compose for the whole enclosure, the three parts authored independently, instead of three
composes (one per `set_part`) outside a round.

## Anti-patterns

- Telling the user you ran parts on parallel kernels; you authored them in parallel and composed
  once.
- Authoring around a missing scalar or frame instead of finishing the round and amending the
  skeleton.
- Treating one failed part as fatal; it is isolated, the rest still composes.
- Opening a round for a single part; a lone `set_part` composes immediately on its own.
- Fanning out N workers for N identical parts; that is one part definition plus occurrences
  (`set_occurrences`), not N ids.

## Cross-references

- **solidifai-assemblies** - the skeleton and part mechanics (scalars, frames, `attach`,
  `inputs`, hardware, the checks) this round drives; for a sub-mechanism, scaffold with
  `add_subassembly` and give it its own skeleton and round.
- **solidifai-delegation** - the worker contract for the fan-out (one part per worker, single
  writer).
- **solidifai-grounding** - understand the mechanism before decomposing it.
- **solidifai-self-verify** - the full done-gate on the composed result; name parts clearly,
  since the checks and the failed map report by id.
