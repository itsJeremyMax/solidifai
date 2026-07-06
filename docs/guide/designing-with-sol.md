---
title: Designing with Sol
group: Guide
order: 3
description: How to ask Sol for the part you want.
---

Sol is the companion built into every workspace. You describe what you want and
Sol does the modelling. The better your description, the closer the first result
lands, so a little care in how you ask goes a long way.

## Describe intent, not steps

You do not need to spell out modelling operations. Say what the part is and what
it is for, and let Sol choose how to build it.

```text
> a wall bracket that holds a 35mm round pipe and screws into a stud
```

## Be specific about dimensions

Numbers remove guesswork. Give sizes, thicknesses, hole diameters, and any
clearances that matter.

```text
> make the base 80 by 50mm, 4mm thick, with two M5 countersunk holes 60mm apart
```

> [!TIP]
> If a dimension has to match a real part, say so. "Sized for an M6 bolt" tells
> Sol the intent, not just a number.

## Iterate

Treat it as a conversation. Ask for one change at a time and check the viewport
after each. Small, clear steps are easier to review than one large request.

```text
> add a 4mm fillet to the top edge
> now bore a clearance hole through the boss for the M6
```

## When something goes wrong

If a change takes the model in the wrong direction, open the **History** tab and
roll back to the last good state. Because every build is committed, nothing is
lost and you can try a different approach.

> [!NOTE]
> Want to understand the panels Sol works alongside? See the
> [workspace editor](/docs/the-workspace-editor).
