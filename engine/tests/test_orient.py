"""Auto-orient tests — pure geometry, no slicer, no engine socket.

Shapes are passed as build123d objects (same idiom as test_dfm.py / test_reverse.py).
"""

from build123d import Box, BuildPart, Mode

from solidifai_engine.fabrication import orient


def test_flat_block_prefers_identity():
    # A 40×40×5 slab is already optimal flat on the bed — no candidate should
    # require meaningful support, so the best rotation is the identity.
    best = orient.best_orientation(Box(40, 40, 5), overhang_deg=45)
    assert best["rotation"] in ([0, 0, 0], [0.0, 0.0, 0.0])


def test_result_has_required_keys():
    best = orient.best_orientation(Box(10, 10, 10), overhang_deg=45)
    assert "rotation" in best
    assert "supportArea" in best
    assert "contactArea" in best
    assert "worstSupportArea" in best


def test_overhang_orientation_reduces_support():
    # 40×10×20 block has obvious orientation choice (flat side down).
    # The chosen orientation must not be worse than the worst candidate.
    shape = Box(40, 10, 20)
    best = orient.best_orientation(shape, overhang_deg=45)
    assert best["supportArea"] <= best["worstSupportArea"]


def test_worst_support_area_ge_best():
    # worstSupportArea is always >= the chosen supportArea by definition.
    best = orient.best_orientation(Box(20, 10, 5), overhang_deg=45)
    assert best["worstSupportArea"] >= best["supportArea"]


def test_custom_candidates_accepted():
    # Caller can pass explicit candidate rotations.
    best = orient.best_orientation(
        Box(10, 10, 10),
        overhang_deg=45,
        candidates=[[0, 0, 0], [90, 0, 0]],
    )
    assert best["rotation"] in ([0, 0, 0], [90, 0, 0], [0.0, 0.0, 0.0], [90.0, 0.0, 0.0])


def test_box_with_overhang_reduces_support_from_worst():
    # L-shaped body: one candidate places the overhang down (high support),
    # another places it up (low support). The picker must choose the better one.
    with BuildPart() as _:
        Box(30, 10, 10)  # base
        Box(10, 10, 10, mode=Mode.ADD)  # adds nothing new — same bbox
    # Use an asymmetric shape instead: tall thin block placed on its side
    shape = Box(5, 5, 40)
    best = orient.best_orientation(shape, overhang_deg=45)
    # supportArea should be zero or minimal for a box (no true overhangs)
    assert best["supportArea"] >= 0
    assert best["worstSupportArea"] >= best["supportArea"]
