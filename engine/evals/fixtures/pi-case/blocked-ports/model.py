from build123d import Box, Cylinder, Pos

from solidifai import show

case = Box(95, 66, 28) - Pos(0, 0, 2) * Box(90, 60, 28)
for x in (-30, -10, 10, 30):
    case -= Pos(x, 0, 0) * Cylinder(2, 32)
show(case, name="pi_case")
show(Box(85, 56, 18), name="pi5-board", role="reference")
