from build123d import Box, Cylinder, Pos, Rot

from solidifai import show


def gear(radius, teeth):
    shape = Cylinder(radius, 6)
    for index in range(teeth):
        shape += Rot(0, 0, index * 360 / teeth) * Pos(radius, 0, 0) * Box(4, 3, 6)
    return shape


show(Box(90, 50, 4), name="base")
show(Pos(-25, 0, 5) * gear(19, 19), name="gear_20")
show(Pos(25, 0, 5) * gear(30, 30), name="gear_30")
