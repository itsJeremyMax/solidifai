from build123d import Location

from solidifai import skeleton


def test_collects_scalars_and_frames():
    s = skeleton()
    s.scalar("body_w", 80.0)
    s.scalar("wall", 2.4)
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, 40.0)))
    assert s.scalars == {"body_w": 80.0, "wall": 2.4}
    assert set(s.frames) == {"base_frame", "lid_frame"}


def test_resolve_inputs_picks_declared_only():
    s = skeleton()
    s.scalar("body_w", 80.0)
    s.scalar("secret", 9.9)
    assert s.resolve_inputs(["body_w"]) == {"body_w": 80.0}


def test_resolve_inputs_unknown_name_raises():
    import pytest

    s = skeleton()
    s.scalar("body_w", 80.0)
    with pytest.raises(KeyError, match="nope"):
        s.resolve_inputs(["nope"])


def test_frame_lookup_and_missing():
    import pytest

    s = skeleton()
    s.frame("f", Location((1, 2, 3)))
    assert s.frame_for("f").position == Location((1, 2, 3)).position
    assert s.frame_for(None).position == Location().position  # None -> node origin
    with pytest.raises(KeyError, match="ghost"):
        s.frame_for("ghost")
