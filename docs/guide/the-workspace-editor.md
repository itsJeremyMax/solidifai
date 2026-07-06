---
title: The workspace editor
group: Guide
order: 2
description: The viewport, the inspector, and the terminal, and how they fit together.
---

The editor is where a workspace comes to life. It has three parts: a live
viewport, an inspector for everything about the model, and a terminal where you
talk to Sol. Here is how they work together.

## The viewport

The center pane shows the current model with real materials and lighting. It
redraws as soon as a build finishes, so a change you ask for appears right where
you expect it. Scroll to zoom, drag to orbit, and right-click a face to open the
context menu.

> [!NOTE]
> The viewport draws only when it needs to. It wakes on interaction or when the
> model changes, so a still scene uses no power.

## The inspector

The inspector groups everything about the model into tabs:

- **Plan** shows Sol's build brief for the current request: the parts, key
  dimensions, and interfaces Sol intends to build, before and during the build.
- **Model** lists the parts, with per-part material assignment and visibility.
- **Requirements** captures what the part has to satisfy.
- **Measure** reads distances, angles, and bounding dimensions off the geometry.
- **DFM** surfaces manufacturability checks for the way you plan to make the part.
- **History** is the timeline of changes, and where you roll one back.
- **Make** sends the model to a connection for time and cost estimates.

## The terminal

The terminal is your conversation with Sol. Describe a change in plain language
and Sol edits the model directly. For how to phrase requests so you get what you
want, see [designing with Sol](/docs/designing-with-sol).

> [!TIP]
> Every build is a git commit. If a change goes the wrong way, the History tab
> rolls it back cleanly.

## Working across workspaces

You can open several workspaces at once. Each one becomes a tab with its own live
engine and its own agent. Some things belong to a single workspace, and some are
shared across the whole app:

| Scope         | Examples                                                  |
| ------------- | --------------------------------------------------------- |
| Per workspace | Model, history, chat, parts, manufacturing overrides       |
| App-wide      | Materials, Factory, References, the rest of your settings |
