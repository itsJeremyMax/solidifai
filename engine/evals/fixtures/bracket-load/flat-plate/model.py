from build123d import Box, Cylinder, Pos

from solidifai import show

plate = Box(6, 50, 52)
plate -= Pos(0, -20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
plate -= Pos(0, 20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
show(plate, name="bracket")
