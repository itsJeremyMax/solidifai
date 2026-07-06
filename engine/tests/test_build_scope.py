from build123d import Box

import solidifai
from solidifai import _registry, build_scope, reset_registry, show


def test_scopes_isolate_shown_objects():
    reset_registry()
    show(Box(1, 1, 1), name="root_obj")  # lands in the root scope
    with build_scope() as scope:
        show(Box(2, 2, 2), name="scoped_obj")  # lands ONLY in this scope
        assert [o.name for o in scope.objects] == ["scoped_obj"]
        assert [o.name for o in _registry()] == ["scoped_obj"]
    # After the scope exits, the root scope is untouched by the inner show()
    assert [o.name for o in _registry()] == ["root_obj"]


def test_reset_registry_clears_only_active_scope():
    reset_registry()
    show(Box(1, 1, 1), name="root_obj")
    with build_scope():
        show(Box(1, 1, 1), name="a")
        reset_registry()  # clears the active scope only
        assert _registry() == []
    assert [o.name for o in _registry()] == ["root_obj"]


def test_features_are_scoped_too():
    from solidifai import _feature_registry, feature

    reset_registry()
    with build_scope() as scope:
        with feature("hole", driven_by="d"):
            show(Box(1, 1, 1), name="x")
        assert [f.name for f in _feature_registry()] == ["hole"]
        assert [f.name for f in scope.features] == ["hole"]
    assert _feature_registry() == []


def test_nested_build_scope_restores_parent():
    reset_registry()
    with build_scope():
        show(Box(1, 1, 1), name="outer")
        with build_scope() as inner:
            show(Box(2, 2, 2), name="inner")
            assert [o.name for o in _registry()] == ["inner"]
        # inner exited -> back in outer
        assert [o.name for o in _registry()] == ["outer"]
        assert [o.name for o in inner.objects] == ["inner"]
    assert _registry() == []  # root scope untouched
