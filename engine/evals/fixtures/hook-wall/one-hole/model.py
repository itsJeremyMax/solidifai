from build123d import Box, Cylinder, Pos

from solidifai import show

hook = Box(6, 50, 70)
hook += Pos(18, 0, -31) * Box(30, 24, 8)
hook += Pos(31, 0, -13) * Box(8, 24, 32)
hook += Pos(12, 0, -19) * Box(14, 24, 24)
hook -= Pos(0, -16, 18) * Cylinder(2.5, 12, rotation=(0, 90, 0))
show(hook, name="hook")
