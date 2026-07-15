from build123d import Box, Pos

from solidifai import show

case = Box(95, 66, 28) - Pos(0, 0, 2) * Box(90, 60, 28)
for y in (-12, 12):
    case -= Pos(42.5, y, 0) * Box(20, 18, 10)
show(case, name="pi_case")
show(Box(85, 56, 18), name="pi5-board", role="reference")
