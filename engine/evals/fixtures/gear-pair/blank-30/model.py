from build123d import Box, Cylinder, Pos, Rot

from solidifai import show

shape = Cylinder(20, 6)
for index in range(20):
    shape += Rot(0, 0, index * 18) * Pos(20, 0, 0) * Box(4, 3, 6)
show(Box(90, 50, 4), name="base")
show(Pos(-25, 0, 5) * shape, name="gear_20")
show(Pos(25, 0, 5) * Cylinder(30, 6), name="gear_30")
