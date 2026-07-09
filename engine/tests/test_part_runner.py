from solidifai_engine.assembly import runner

PART = """
from solidifai import show
from build123d import BuildPart, Box

def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Base")
"""


def test_part_build_returns_shown_objects(tmp_path):
    (tmp_path / "base.py").write_text(PART, encoding="utf-8")
    objs, _assets, _features = runner.run_part(
        str(tmp_path / "base.py"), inputs={"body_w": 80.0, "wall": 2.4}
    )
    assert [o.name for o in objs] == ["Base"]
    assert objs[0].shape.bounding_box().size.X == 80.0


def test_part_build_does_not_leak_to_root_registry(tmp_path):
    import solidifai

    solidifai.reset_registry()
    (tmp_path / "base.py").write_text(PART, encoding="utf-8")
    runner.run_part(str(tmp_path / "base.py"), inputs={"body_w": 10.0, "wall": 1.0})
    assert solidifai._registry() == []  # the part's show() stayed in its own scope


def test_part_only_sees_declared_inputs(tmp_path):
    import pytest

    (tmp_path / "base.py").write_text(PART, encoding="utf-8")
    with pytest.raises(KeyError):
        runner.run_part(str(tmp_path / "base.py"), inputs={"body_w": 80.0})  # no "wall"
