from build123d import Box, Cylinder, Pos, Rot

from solidifai import show

show(Box(90, 50, 4), name="base")
show(Pos(-25, 0, 5) * Cylinder(20, 6), name="gear_20")
shape = Cylinder(30, 6)
for index in range(30):
    shape += Rot(0, 0, index * 12) * Pos(30, 0, 0) * Box(4, 3, 6)
show(Pos(25, 0, 5) * shape, name="gear_30")
