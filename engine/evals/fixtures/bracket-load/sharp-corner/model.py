from build123d import Box, Cylinder, Pos

from solidifai import show

bracket = Box(6, 50, 52) + Pos(15, 0, -22) * Box(30, 50, 8)
bracket -= Pos(0, -20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
bracket -= Pos(0, 20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
show(bracket, name="bracket")
