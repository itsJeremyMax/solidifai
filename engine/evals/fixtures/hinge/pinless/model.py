from build123d import Box, Pos

from solidifai import show

show(Pos(-11.5, 0, 0) * Box(20, 60, 3), name="leaf_a")
show(Pos(11.5, 0, 0) * Box(20, 60, 3), name="leaf_b")
