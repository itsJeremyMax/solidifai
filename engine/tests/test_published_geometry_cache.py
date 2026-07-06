from build123d import Box, Rectangle

from solidifai_engine.assembly.cache import part_key


def test_identical_profile_same_key():
    a = part_key("src", {"seat": Rectangle(40, 30)}, path="parts/lid.py")
    b = part_key("src", {"seat": Rectangle(40, 30)}, path="parts/lid.py")
    assert a == b  # deterministic BREP hash -> cache hit on rebuild


def test_changed_profile_new_key():
    a = part_key("src", {"seat": Rectangle(40, 30)}, path="parts/lid.py")
    b = part_key("src", {"seat": Rectangle(40, 31)}, path="parts/lid.py")
    assert a != b  # a different profile invalidates the consumer


def test_geometry_input_changes_key_vs_scalar_only():
    base = part_key("src", {"n": 1.0}, path="p")
    withgeom = part_key("src", {"n": 1.0, "g": Box(1, 1, 1)}, path="p")
    assert base != withgeom  # a published solid participates in the key


def test_scalars_and_shapes_mix_is_stable():
    a = part_key("src", {"fit": 0.2, "seat": Rectangle(40, 30)}, path="p")
    b = part_key("src", {"seat": Rectangle(40, 30), "fit": 0.2}, path="p")
    assert a == b  # order-independent


def test_empty_shape_raises_clean_value_error():
    import pytest
    from build123d import Compound

    with pytest.raises(ValueError, match="serialized|invalid|empty"):
        part_key("src", {"g": Compound(children=[])}, path="p")
