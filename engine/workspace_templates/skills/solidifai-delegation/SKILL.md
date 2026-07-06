---
name: solidifai-delegation
description: Work as a team when your harness supports it. Use whenever a solidifai job has separable or parallel work (several independent parts, an unknown mechanism to research, a finished part to verify) and you can dispatch workers (subagents, teammates, parallel tasks). Defines how Sol hands solidifai work out and integrates the results, with one hard rule: a single engine writer at a time. With no workers, run every phase inline; the workflow and the end result are identical, you only lose the concurrency.
license: MIT
---

# solidifai delegation

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

This is the one contract for handing solidifai work out to **workers** and putting the results
back together, written to read the same in every harness. A worker is an independent agent
context you can hand a self-contained task and get a result back; your harness may call it a
subagent, a teammate, or a parallel task. Each sibling skill names its own unit of delegable
work; this skill owns the shared rules underneath them.

## When to use

Delegate only when there is separable or parallel work worth the cost of a handoff: decompose,
or run inline.

- Several independent parts: per-part build workers under a round (**solidifai-orchestration**).
- A genuinely unknown mechanism, or a reproduction from an image: one or more grounding scouts
  on different angles, then synthesize (**solidifai-grounding**).
- Open design judgment on a human-facing part: a design scout (**solidifai-product-design**).
- A finished part that needs a real done-gate: verify scouts running the read-only checks in
  parallel (**solidifai-self-verify**).
- **Skip when:** the part is specified, single, and simple (just build it), or standing up a
  worker would not save real wall-clock or real thinking. Do the work inline.

Judge from your own available tools whether you have workers. With none, run every phase
inline: same steps, same end-state, you only lose the concurrency. Graceful degradation is
the contract, not a fallback, and the end result is identical either way.

## The procedure

1. **Decide writer and shape first.** The live workspace (`model.py`, `assembly.json`, the
   single-threaded CAD kernel) has exactly **one writer at a time**: you, or the per-part round.
   Everything you delegate is one of the two safe shapes below. When in doubt, you are the
   writer and the workers are scouts.

   ### Scouts (read-only, or no engine at all)

   A scout returns information and never changes the model. Four kinds:

   - **Grounding scout**: researches how a thing works (web, reasoning, a reference image)
     and returns the working principle and the parts it needs; it touches no engine, so
     several run freely in parallel.
   - **Design scout**: applies design judgment to the brief (grip size, control placement,
     proportion, printability). No geometry, so no engine. Returns decisions you apply.
   - **Verify scout**: runs the read-only checks (`analyze_dfm`, `check_interferences`,
     `stress_check`, `measure`, `capture_views`) on a stable model and reports flags. Several
     can run at once; never while a writer is editing, and it never edits.
   - **Critique critic** runs only after solidifai-self-verify's gates pass on a stream- or
     pause-tier build: a fresh-context scout that reads the build brief, new hi-res captures
     (grid, sections, close-ups), and the check outputs, and returns ranked defects (severity,
     what, where, suggested fix). It is prompted to find problems, not to approve, and like every
     scout it never edits the engine and never reads mid-write. The prompts, tier depths, and
     disposition rule live in **solidifai-critique**.

   `lookup_standard` and `lookup_reference` are read-only and safe for any scout (a
   grounding scout resolves named-object dims with them before the build). `save_reference`
   is a write and stays with Sol: scouts report verified dims back, the orchestrator saves.

   ### Part workers (scoped writers, only under a round)

   The **solidifai-orchestration** pattern: inside `begin_round` / `end_round`, each worker
   writes a different part with `set_part`, reading only the frozen skeleton, never a sibling.
   This is the only way two agents safely write at once, and they write different parts, never
   the same live state. State the pause-tier **build brief** before you open the round
   (AGENTS.md "State the build brief"); it is the same brief whether the parts are authored by
   workers or inline.

2. **Hand off a self-contained brief.** Give every worker exactly four things:

   - **Goal**: the one thing to produce.
   - **Inputs it may use**: the brief, the skeleton scalars and frames, the reference. Only what
     it needs.
   - **Boundary**: what it must not touch. A scout never writes the engine; a part worker only
     its own part, reading only the skeleton.
   - **Result shape**: the structured form to return (a parts list, a set of decisions, a list
     of flags, a build result). Workers return data, not prose for the user.

3. **Integrate, then speak.** You own the thread end to end: collect the scouts' findings and
   the part workers' results, reconcile conflicts, make every engine write yourself, verify the
   composed result, and present it as one piece of work. The team is yours; the voice is Sol's.

## Anti-patterns

- Two writers on the same live model, ever.
- A scout that edits the engine, or a verify scout reading while something is being built.
- Telling the user you ran subagents or split the work; delegation is internal, and to the user
  you are one companion, Sol.
- Reflexive delegation: spinning up workers for a job you could finish inline faster.
- Delegating a write outside a round; a round is the only place a write is delegated, one part
  per worker.

## Cross-references

- **solidifai-grounding** - the grounding scout's research phase.
- **solidifai-product-design** - the design scout's judgment phase.
- **solidifai-orchestration** and **solidifai-assemblies** - per-part authoring under a round.
- **solidifai-self-verify** - the verify scout's checks and the done-gate.
- **solidifai-critique** - the critic prompts, the tier depths, and the fix-or-justify disposition.
- `references/acceptance-scenarios.md` - the parity and safety scenarios this contract must
  satisfy.
