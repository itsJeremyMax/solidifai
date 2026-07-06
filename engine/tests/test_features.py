# engine/tests/test_features.py
import inspect

from solidifai import (
    FeatureRecord,
    _feature_registry,
    _registry,
    feature,
    reset_registry,
    show,
)


def setup_function():
    reset_registry()


def test_feature_records_metadata_on_clean_exit():
    with feature("central_bore", driven_by="bore_dia", kind="hole"):
        pass
    reg = _feature_registry()
    assert len(reg) == 1
    rec = reg[0]
    assert isinstance(rec, FeatureRecord)
    assert rec.name == "central_bore"
    assert rec.driven_by == ["bore_dia"]
    assert rec.kind == "hole"


def test_driven_by_normalizes_to_list():
    with feature("a", driven_by="x"):
        pass
    with feature("b", driven_by=["y", "z"]):
        pass
    with feature("c"):
        pass
    with feature("d", driven_by=("p", "q")):
        pass
    reg = _feature_registry()
    assert reg[0].driven_by == ["x"]
    assert reg[1].driven_by == ["y", "z"]
    assert reg[2].driven_by == []
    assert reg[3].driven_by == ["p", "q"]


def test_feature_captures_source_line():
    base = inspect.currentframe().f_lineno
    with feature("hole_a"):  # this is line base + 1
        pass
    assert _feature_registry()[0].source_line == base + 1


def test_exception_in_block_is_not_recorded_and_propagates():
    try:
        with feature("doomed"):
            raise RuntimeError("boom")
    except RuntimeError as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("exception did not propagate")
    assert _feature_registry() == []


def test_reset_registry_clears_both_registries():
    show("A")
    with feature("f"):
        pass
    assert len(_registry()) == 1
    assert len(_feature_registry()) == 1
    reset_registry()
    assert _registry() == []
    assert _feature_registry() == []


def test_feature_captures_new_faces_inside_buildpart():
    from build123d import Box, BuildPart, Hole, Locations

    reset_registry()
    with BuildPart():
        Box(40, 40, 20)
        with feature("bore", driven_by="d"), Locations((0, 0)):
            Hole(radius=5)
    rec = _feature_registry()[0]
    assert rec.faces, "expected captured faces for the hole"
    kinds = {str(f.geom_type) for f in rec.faces}
    assert any("CYLINDER" in k for k in kinds), kinds


def test_feature_without_active_builder_captures_nothing():
    # Used outside a BuildPart there is no active builder — must not raise.
    reset_registry()
    with feature("loose"):
        pass
    assert _feature_registry()[0].faces == []
