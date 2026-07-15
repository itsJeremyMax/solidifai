from build123d import Box, Cylinder, Pos

from solidifai import show

plate = Box(6, 50, 70) - Pos(0, -16, 18) * Cylinder(2.5, 12, rotation=(0, 90, 0))
plate -= Pos(0, 16, 18) * Cylinder(2.5, 12, rotation=(0, 90, 0))
show(plate, name="hook")
