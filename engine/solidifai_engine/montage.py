"""Tile labeled view PNGs into a single captioned contact-sheet PNG.

Pure Pillow — no VTK, no build123d, no OpenGL — so it is testable without an
offscreen GL context. Consumes the per-view PNGs that ``views.render_views``
writes and composes them into one grid image for ``capture_views(layout="grid")``.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

TILE_PX = 256  # per-tile thumbnail edge
CAPTION_H = 18  # caption strip height under each tile
BG = (20, 20, 24)  # sheet background
FG = (230, 230, 235)  # caption text colour


def grid(items: list, out_path: str, tile_px: int = TILE_PX):
    """Tile ``items`` (``[(label, png_path), ...]`` in display order) into a
    captioned grid written to ``out_path``. Returns ``(out_path, width, height)``
    so callers need no Pillow of their own."""
    n = len(items)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = max(1, math.ceil(n / cols))
    cell_w = tile_px
    cell_h = tile_px + CAPTION_H
    width, height = cols * cell_w, rows * cell_h

    sheet = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(sheet)

    for i, (label, path) in enumerate(items):
        r, c = divmod(i, cols)
        x, y = c * cell_w, r * cell_h
        with Image.open(path) as tile:
            rgb = tile.convert("RGB").resize((tile_px, tile_px))
            sheet.paste(rgb, (x, y))
        text = str(label)
        tw = draw.textlength(text)
        draw.text((x + (tile_px - tw) / 2, y + tile_px + 3), text, fill=FG)

    sheet.save(out_path, "PNG")
    return out_path, width, height
