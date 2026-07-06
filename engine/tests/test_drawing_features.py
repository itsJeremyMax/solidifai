"""Pose-invariant part grouping + hole geometry extraction."""

from dataclasses import dataclass

from build123d import Box, Cylinder, Pos, Rot

from solidifai_engine.drawing import features


@dataclass
class _Obj:  # mimics session objects: .shape/.name/.material/.color
    shape: object
    name: str
    material: str | None = None
    color: str | None = None


def _plate_with_two_holes():
    # 40x20x4 plate, two 5mm-dia through holes at x=-10 and x=+10.
    plate = Box(40, 20, 4)
    for dx in (-10, 10):
        plate -= Pos(dx, 0, 0) * Cylinder(radius=2.5, height=10)
    return plate


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
