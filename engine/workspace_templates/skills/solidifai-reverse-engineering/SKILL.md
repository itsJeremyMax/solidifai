---
name: solidifai-reverse-engineering
description: Rebuild an existing part as a clean, editable parametric model. Use when the user wants to reverse-engineer or copy a part, turn a scan or an STL/STEP into an editable model, match an existing object's dimensions, or start a model from a photo or a sketch they share. Covers importing the reference, measuring it with analyze_import (dimensions + detected holes/cylinders), rebuilding it parametrically to match, and confirming the rebuild against the original.
license: MIT
---

# solidifai reverse engineering

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

The goal is not a frozen copy of a mesh but a clean, **parametric** model the user can then
change: measure the reference, rebuild it intentfully, and confirm it sits where the original
did. Units are millimetres.

## When to use

- The user wants to reverse-engineer or copy an existing part, or turn a scan or an STL/STEP
  into an editable model.
- They want to match an existing object's dimensions, or start a model from a photo or sketch.
- **Skip when:** the part is being designed fresh from a brief; that is **solidifai-modeling**
  (or **solidifai-product-design** for an open design).

## The procedure

### From a scan or a CAD file

1. **Bring it in.** `import_reference(path)` loads an STL / STEP / BREP as a ghosted reference
   in the workspace, so you can see and measure it without it being "your" part.
2. **Measure it.** `analyze_import()` returns the overall bounding box, volume, the face mix, a
   coarse shape guess (box / plate / cylinder / compound), and the detected round features
   (holes and bosses) with diameter, axis, and location. Start the rebuild from the shape guess
   and the bounding box, then place the holes at the reported positions. The hole-vs-boss label
   is a best-effort heuristic; when its confidence is low, look at `capture_views` of the
   reference.
3. **Rebuild parametrically.** Write a `PARAMS` + `build()` model whose dimensions are the
   measured ones, every one driven by a named parameter (width, height, hole_dia,
   hole_spacing) so the user can dial the part in. Match the datum: build on the
   origin/orientation the reference reports so the overlay lines up.
4. **Confirm.** With the reference still shown, `capture_views(layout="grid")` to overlay your
   rebuild against the ghost and check the silhouette, and `check_interferences` to confirm
   your part occupies the same space (heavy overlap with the reference is expected here).
   Adjust parameters until it lines up, then remove or keep the reference as the user prefers.

### From a photo or a sketch

1. **Ground it before measuring.** A photo is a 2D projection: it hides the back, the
   cross-section, and how the parts attach and move. Work out what the object actually is;
   with web search, look up an exploded view or cross-section so you rebuild the real
   structure, not just the outline in the frame. See **solidifai-grounding**.
2. **Read the image**: rough aspect ratio, where holes and bosses sit, symmetry, any called-out
   dimensions.
3. **Get one true scale.** Ask for one real dimension if none is given (an overall length, a
   hole size); assume a sensible default and say so if the user is in a hurry.
4. **Build, show, refine.** Write a first parametric model from that reading, `capture_views`
   it, and show the user; refine against their feedback rather than trying to be exact in one
   shot.

## Anti-patterns

- Freezing a mesh copy instead of a parametric rebuild; editability is the whole point.
- Treating one photo as the whole solid.
- Building on a different datum than the reference reports.

## Cross-references

- **solidifai-grounding** - understand what the object is and how it works before rebuilding.
- **solidifai-modeling** - the build mechanics for the parametric rebuild.
- **solidifai-self-verify** - confirm and fix the rebuilt part.
