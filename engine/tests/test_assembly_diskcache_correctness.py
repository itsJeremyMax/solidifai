import json
import os
import shutil

from solidifai_engine.session import Session

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def _ws(tmp_path, name):
    root = tmp_path / name
    shutil.copytree(FIXTURE, root)
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    return root, artifacts


def _geom(artifacts):
    m = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    return (
        sorted(o["id"] for o in m["objects"]),
        [round(x, 6) for x in m["bbox"]["min"]],
        [round(x, 6) for x in m["bbox"]["max"]],
        round(m["mass"]["value"], 4),
    )


def test_disk_reopen_matches_fresh(tmp_path):
    root, art = _ws(tmp_path, "warm")
    Session(str(art), model_path=str(root / "assembly.json")).startup()
    s2 = Session(str(art), model_path=str(root / "assembly.json"))
    s2.startup()  # served from disk
    warm = _geom(art)
    croot, cart = _ws(tmp_path, "cold")
    Session(str(cart), model_path=str(croot / "assembly.json")).startup()  # no prior cache
    assert warm == _geom(cart)


def test_editing_a_part_source_invalidates(tmp_path):
    root, art = _ws(tmp_path, "edit")
    Session(str(art), model_path=str(root / "assembly.json")).startup()
    base = root / "parts" / "base.py"
    base.write_text(
        base.read_text(encoding="utf-8").replace(
            'Box(inputs["body_w"], inputs["body_w"], inputs["wall"])',
            'Box(inputs["body_w"] * 2, inputs["body_w"], inputs["wall"])',
        ),
        encoding="utf-8",
    )
    s2 = Session(str(art), model_path=str(root / "assembly.json"))
    s2.startup()
    assert s2.last_ok is True
    m = json.loads((art / "model.json").read_text(encoding="utf-8"))
    # the edited base doubled in X -> overall bbox X span grew beyond the unedited 60mm
    assert (m["bbox"]["max"][0] - m["bbox"]["min"][0]) > 60.0
