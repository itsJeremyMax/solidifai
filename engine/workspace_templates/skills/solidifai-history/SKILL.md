---
name: solidifai-history
description: Save versions of a model, see exactly what an edit changed, and package a finished part to share. Use when the user wants to checkpoint or save a version, asks what changed between two versions, wants a before/after or a diff of an edit, asks for a build report or spec sheet, or wants to hand the part off or share it. Covers checkpoints, the geometric diff (added and removed material), the build report (printable spec sheet), and exporting for sharing.
license: MIT
---

# solidifai history

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

The workspace keeps a versioned history of every build. This skill owns marking good states,
seeing precisely what a change did, and packaging a finished part for someone else;
**solidifai-modeling** owns making the changes themselves.

## When to use

- The user wants to checkpoint or save a version, or return to an earlier one.
- They ask what changed between two versions, or want a before/after of an edit.
- They want a build report or spec sheet, or to hand the part off or share it.
- **Skip when:** mid-build iteration; checkpoint at meaningful milestones, not every tweak.

## The procedure

1. **Checkpoint** with `cad_checkpoint("message")` at meaningful milestones ("base bracket",
   "added ribs", "ready for print") so there are clear points to compare and return to.
   `cad_history()` lists the timeline with each entry's index and message; `cad_undo` /
   `cad_redo` step one state, and `cad_goto(index)` jumps to any entry.
2. **Diff** with `diff_against(index)`: it compares the **current** model to the checkpoint at
   `index` and reports **added** and **removed** material, each with a volume and bounding box
   ("this edit added 1.2 cm3 of rib and removed the old 0.4 cm3 boss"), plus overall volume and
   bbox deltas even on geometry too gnarly for the boolean diff. It is read-only: it rebuilds
   the old state behind the scenes and leaves your model and your place in history untouched.
3. **Run diff and report after a successful build**; both read the last-good build.
4. **Package and share.** `build_report()` writes a printable spec sheet (`report.html` in the
   workspace): a rendered view grid plus mass, dimensions, material, and the DFM summary; tell
   the user where it is. For the geometry itself, `export("glb")` for a 3D viewer,
   `export("step")` for someone else's CAD, STL for printing.

### Assemblies

History works the same on an assembly, but on the **whole fileset** rather than one `model.py`:

- `cad_undo` / `cad_redo` / `cad_goto(index)` restore the entire assembly at that point (the
  skeleton, every `parts/<id>.py`, the manifest wiring), then rebuild and recompose. Undoing an
  "add part" removes that part's file again.
- `diff_against(index)` returns a **structural** diff instead of a material one:
  - **structural**: children `added` / `removed` / `rewired` (a part's attach frame or inputs
    changed),
  - **skeleton**: whether `skeleton.py` changed, with the PARAMS added/removed/changed,
  - **parts**: which `parts/<id>.py` sources changed.
  Use it to say precisely what an edit did ("added the lid, rewired the hinge, no skeleton
  change").
- `export_flat_model()` flattens the assembly into a single, self-contained `model.py` and
  returns its code (`write=true` also saves `flat_model.py`): a normal workspace script that
  reproduces the composed assembly on its own, for handing off or archiving.
- `check_interfaces()` validates the declared wiring (every attach names a published frame,
  every input a published scalar) and folds in the interference summary; run it before
  composing a complex assembly to catch a typo early.

## Anti-patterns

- Managing assembly files by hand across undo/redo; the history tools restore the whole
  fileset.
- Handing off without a checkpoint and a clean self-verify.

## Cross-references

- **solidifai-modeling** - the build mechanics behind every state you checkpoint.
- **solidifai-self-verify** - a good handoff is a checkpoint, a clean self-verify, a build
  report, and the right export.
