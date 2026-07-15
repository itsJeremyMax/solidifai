from build123d import Box, Cylinder, Pos, Rot

from solidifai import show


def gear(radius, teeth, tooth_offset=0):
    shape = Cylinder(radius, 6)
    for index in range(teeth):
        shape += Rot(0, 0, index * 360 / teeth) * Pos(radius, tooth_offset, 0) * Box(4.5, 4, 6)
    return shape


show(Box(90, 50, 4), name="base")
show(Pos(-25, 0, 5) * gear(20, 20), name="gear_20")
show(Pos(25, 0, 5) * gear(30, 30, tooth_offset=2), name="gear_30")
