from build123d import Box, Pos

from solidifai import show

show(Box(90, 24, 64) - Box(82, 19.4, 61), name="battery_box")
show(Pos(0, 0, 35) * Box(90, 24, 4), name="lid")
