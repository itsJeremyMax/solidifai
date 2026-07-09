"""Pose-invariant part grouping + hole geometry extraction."""

from dataclasses import dataclass

from build123d import Align, Box, Cylinder, Plane, Pos, Rot, mirror

from solidifai_engine.drawing import features


@dataclass
class _Obj:  # mimics session objects: .shape/.name/.material/.color
    shape: object
    name: str
    material: str | None = None
    color: str | None = None


def _plate_with_two_holes():
    # 40x20x4 plate, two 5mm-dia through holes at x=-10 and x=+10. Achiral: two
    # mirror planes, so it is congruent to its own reflection.
    plate = Box(40, 20, 4)
    for dx in (-10, 10):
        plate -= Pos(dx, 0, 0) * Cylinder(radius=2.5, height=10)
    return plate


def _chiral_bracket():
    # Three arms of distinct length meeting at a corner (stepped in Z) plus an
    # off-axis hole -> no mirror plane, so it is genuinely handed. Its enantiomer
    # (mirror image) cannot be superimposed by any rotation/translation.
    b = (
        Box(30, 4, 6, align=(Align.MIN, Align.CENTER, Align.MIN))
        + Box(4, 22, 10, align=(Align.CENTER, Align.MIN, Align.MIN))
        + Box(4, 4, 16, align=(Align.CENTER, Align.CENTER, Align.MIN))
    )
    return b - Pos(20, 0, 3) * Rot(90, 0, 0) * Cylinder(radius=1.5, height=20)


def test_extract_holes_counts_and_diameters():
    holes = features.extract_holes(_plate_with_two_holes())
    assert len(holes) == 2
    for h in holes:
        assert abs(h["dia"] - 5.0) < 0.1
        # vertical through-holes -> axis parallel to Z
        ax = h["axis"]
        assert abs(abs(ax[2]) - 1.0) < 1e-3
    xs = sorted(round(h["center"][0], 1) for h in holes)
    assert xs == [-10.0, 10.0]


def test_extract_holes_none_when_solid():
    assert features.extract_holes(Box(10, 10, 10)) == []


def test_signature_groups_identical_parts_regardless_of_pose():
    base = Box(8, 4, 2)
    moved = Pos(50, 0, 0) * base
    turned = Rot(0, 0, 90) * base  # rotated 90 deg about Z
    distinct = Box(8, 4, 3)
    assert features.part_signature(base) == features.part_signature(moved)
    assert features.part_signature(base) == features.part_signature(turned)
    assert features.part_signature(base) != features.part_signature(distinct)


def test_chiral_part_and_mirror_get_distinct_signatures():
    # A handed part and its enantiomer share volume/area/face/edge counts AND the
    # (reflection-invariant) inertia tensor -- only chirality separates them.
    part = _chiral_bracket()
    flipped = mirror(part, Plane.YZ)
    assert features.part_signature(part) != features.part_signature(flipped)


def test_chiral_part_and_mirror_do_not_merge_into_one_group():
    part = _chiral_bracket()
    objs = [_Obj(part, "Bracket L"), _Obj(mirror(part, Plane.YZ), "Bracket R")]
    groups = features.group_parts(objs)
    assert len(groups) == 2
    assert all(g["qty"] == 1 for g in groups)


def test_chiral_part_groups_with_moved_or_rotated_copy():
    part = _chiral_bracket()
    objs = [
        _Obj(part, "Bracket 1"),
        _Obj(Pos(60, 5, -8) * part, "Bracket 2"),
        _Obj(Rot(41, -27, 63) * part, "Bracket 3"),
    ]
    groups = features.group_parts(objs)
    assert len(groups) == 1
    assert groups[0]["qty"] == 3


def test_achiral_part_and_mirror_still_group_together():
    # A part with a mirror plane == its own reflection, so it must stay one group.
    plate = _plate_with_two_holes()
    objs = [_Obj(plate, "Plate 1"), _Obj(mirror(plate, Plane.YZ), "Plate 2")]
    groups = features.group_parts(objs)
    assert len(groups) == 1
    assert groups[0]["qty"] == 2


def test_base_name_strips_only_separated_index():
    # An explicit separator before the number is an instance index -> strip it.
    assert features._base_name("Foot 1") == "Foot"
    assert features._base_name("Bay_03") == "Bay"
    # A number glued to letters is part of the spec token -> keep it.
    assert features._base_name("M3") == "M3"
    assert features._base_name("Panel v2") == "Panel v2"


def test_group_parts_qty_and_base_name():
    base = Box(8, 4, 2)
    objs = [_Obj(Pos(i * 20, 0, 0) * base, f"Foot {i + 1}") for i in range(4)] + [
        _Obj(Box(40, 20, 5), "Base")
    ]
    groups = features.group_parts(objs)
    by_name = {g["name"]: g for g in groups}
    assert by_name["Foot"]["qty"] == 4
    assert by_name["Base"]["qty"] == 1
    assert sum(g["qty"] for g in groups) == 5
