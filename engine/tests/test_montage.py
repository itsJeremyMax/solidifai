import os

import pytest
from PIL import Image

from solidifai_engine import montage


def _tiles(tmp_path, n):
    """n dummy solid-color PNGs; returns [(label, path), ...]."""
    items = []
    for i in range(n):
        p = str(tmp_path / f"v{i}.png")
        Image.new("RGB", (512, 512), (i * 7 % 256, 80, 120)).save(p)
        items.append((f"view{i}", p))
    return items


def test_grid_dimensions_for_14(tmp_path):
    items = _tiles(tmp_path, 14)
    out = str(tmp_path / "sheet.png")
    path, w, h = montage.grid(items, out)
    assert path == out
    assert os.path.exists(out)
    # 14 -> cols = ceil(sqrt(14)) = 4, rows = ceil(14/4) = 4
    assert (w, h) == (4 * montage.TILE_PX, 4 * (montage.TILE_PX + montage.CAPTION_H))
    with Image.open(out) as im:
        assert im.format == "PNG"
        assert im.size == (w, h)


def test_grid_dimensions_for_6(tmp_path):
    items = _tiles(tmp_path, 6)
    out = str(tmp_path / "sheet6.png")
    _, w, h = montage.grid(items, out)
    # 6 -> cols = 3, rows = 2
    assert (w, h) == (3 * montage.TILE_PX, 2 * (montage.TILE_PX + montage.CAPTION_H))


def test_grid_single_tile(tmp_path):
    items = _tiles(tmp_path, 1)
    out = str(tmp_path / "sheet1.png")
    _, w, h = montage.grid(items, out)
    assert (w, h) == (montage.TILE_PX, montage.TILE_PX + montage.CAPTION_H)


def test_grid_missing_tile_raises(tmp_path):
    out = str(tmp_path / "sheet.png")
    with pytest.raises(FileNotFoundError):
        montage.grid([("gone", str(tmp_path / "nope.png"))], out)
