---
title: Validation and DFM
group: Features
order: 3
description: Check manufacturability, mass, and dimensions before you commit.
---

Before a part is worth making, it helps to know it can be made and that it meets
what you need. solidifai puts those checks right in the inspector, so you catch
problems while you design rather than at the printer.

## DFM checks

The **DFM** tab reviews the model for manufacturability and flags the parts of
the geometry that are likely to cause trouble for the way you plan to make it.
Treat its findings as a checklist to work through with Sol.

> [!WARNING]
> A clean DFM pass is not a guarantee. It catches common, detectable problems. A
> final human review still matters for anything you depend on.

## Requirements

The **Requirements** tab is where you capture what the part has to satisfy. Stating
requirements up front gives you and Sol a shared target to design against, and a
way to tell whether a change moved you closer or further away.

## Measure

The **Measure** tab reads real dimensions off the geometry: distances, angles,
and overall bounding size. Use it to confirm a feature is where and how big you
intended.

> [!NOTE]
> Mass and material-dependent checks rely on the material on each part. Assign
> materials first. See [materials](/docs/materials).
