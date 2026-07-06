from build123d import Box

from solidifai import ShownObject
from solidifai_engine.assembly.compose import path_ids
from solidifai_engine.render import _node_ids


def _obj(name):
    return ShownObject(name=name, shape=Box(1, 1, 1), color=None, material=None)


def test_single_model_ids_unchanged():
    objs = [_obj("Base"), _obj("Lid")]
    assert _node_ids(objs) == ["base", "lid"]


def test_assembly_ids_are_path_style():
    objs = [_obj("base/Base"), _obj("hinge/pin/Pin")]
    assert _node_ids(objs) == ["base/base", "hinge/pin/pin"]


def test_dedupe_still_works():
    objs = [_obj("Part"), _obj("Part")]
    assert _node_ids(objs) == ["part", "part_1"]


def test_path_ids_agrees_with_node_ids():
    objs = [_obj("base/Base"), _obj("hinge/pin/Pin"), _obj("Lid")]
    assert path_ids(objs) == _node_ids(objs)
