---
title: References
group: Features
order: 4
description: The library of verified real-world dimensions Sol designs against.
---

When a design has to fit a real object, an 18650 cell, a USB-C port, an off-the-shelf
board, guessed dimensions ruin parts. The reference library is where verified,
real-world dimensions live: the envelope, mounting holes, and cutouts for each object,
with the source they were verified against. Sol checks the library before reaching for
the web, so a dimension verified once is trusted in every workspace after.

## What is in the library

The library has two layers:

- **A builtin seed** of universal items (common battery cells like 18650, 21700, AA,
  and AAA, plus standard port cutouts such as USB and HDMI) that ships with the app.
- **Entries Sol learns.** When Sol verifies a named object's dimensions against a real
  source during research, it saves the entry so future sessions find it instantly. Sol
  mentions the save when it happens.

## Browsing and editing

Open **References** from the home header to manage the library. Search matches an
entry's name, aliases, and category. You can add entries yourself, and edit or delete
the ones you or Sol added. Editing a builtin entry keeps the seed intact: your version
takes precedence, and deleting it restores the original.

Every entry carries its source, so you can always tell where a dimension came from
before you trust a part to it.
