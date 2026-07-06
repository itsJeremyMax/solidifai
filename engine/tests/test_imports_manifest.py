"""imports.json manifest store."""

from solidifai_engine import imports_manifest as im


def test_add_then_load(tmp_path):
    root = str(tmp_path)
    saved = im.add(root, {"name": "PCB", "path": "assets/pcb.stl", "format": "stl"})
    assert saved["id"] == "pcb"
    entries = im.load(root)
    assert len(entries) == 1
    assert entries[0]["path"] == "assets/pcb.stl"


def test_id_collision_de_collides(tmp_path):
    root = str(tmp_path)
    a = im.add(root, {"name": "PCB", "path": "assets/pcb.stl", "format": "stl"})
    b = im.add(root, {"name": "PCB", "path": "assets/pcb-1.stl", "format": "stl"})
    assert a["id"] == "pcb"
    assert b["id"] == "pcb-1"
    assert len(im.load(root)) == 2


def test_remove(tmp_path):
    root = str(tmp_path)
    im.add(root, {"name": "PCB", "path": "assets/pcb.stl", "format": "stl"})
    assert im.remove(root, "pcb") is True
    assert im.load(root) == []
    assert im.remove(root, "pcb") is False


def test_missing_and_corrupt_yield_empty(tmp_path):
    root = str(tmp_path)
    assert im.load(root) == []  # no file
    with open(tmp_path / "imports.json", "w", encoding="utf-8") as f:
        f.write("{ not json")
    assert im.load(root) == []  # corrupt
