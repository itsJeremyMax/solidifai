---
title: Materials
group: Features
order: 1
description: Build a materials library and assign materials per part.
---

Materials give your model real properties and a real look. They drive how a part
appears in the viewport and feed the numbers behind mass and manufacturability.
The library is shared across the whole app, so you set a material up once and use
it in any workspace.

## The materials library

Open **Materials** from the home header to manage the library. Each material
carries the properties solidifai needs, and a preview so you can tell them apart
at a glance. Add the materials you work with most, and they are ready whenever you
need them.

## Assigning a material to a part

Inside a workspace, the **Model** tab lists the parts. Each part has a material
picker, so a model made of several parts can mix materials. Pick a material and
the viewport updates to match.

> [!NOTE]
> Material choice is per part, not per workspace. A printed bracket and its
> stainless fastener can each carry their own material in the same model.

## How materials shape the result

A material is more than a color. It informs the mass estimate and the
manufacturability checks in the [DFM tab](/docs/validation-and-dfm), so assigning
the right material early makes those numbers meaningful.
