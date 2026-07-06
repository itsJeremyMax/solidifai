---
title: Getting started
group: Guide
order: 1
description: Open a workspace, describe a part, and watch it build.
---

solidifai turns a plain description of a part into a real, manufacturable model.
You open a workspace, tell Sol what you want in everyday language, and the model
takes shape in the viewport. This page gets you from a blank library to your
first part.

## Your first workspace

Everything starts on the home library. It lists your workspaces with a captured
render of each, and you can search, filter, and reopen them from there.

To begin a new project, select **New workspace**, give it a name, and you land in
the editor. A workspace is one project: its model, its history, its materials,
and your conversation with Sol.

> [!NOTE]
> A workspace is a real folder on disk with its own git history. Every change Sol
> makes is committed, so your work is versioned and you can always step back.

## Describe a part

The editor opens with a terminal on one side. That is where you talk to Sol.
Describe the part you want, with real dimensions, and Sol builds it.

```text
> a 60mm aluminium knob with a knurled grip and an M6 threaded bore
```

The viewport redraws as soon as the build finishes, so what you asked for shows
up in place. Keep going in plain language to refine it.

## Find your way around

The editor has three working areas: the viewport, the inspector, and the
terminal. The [workspace editor](/docs/the-workspace-editor) page walks through
each one. When you are ready to ask for changes well, read
[designing with Sol](/docs/designing-with-sol).
