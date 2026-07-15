from build123d import Box, Pos

from solidifai import show

show(Box(62, 42, 25) - Pos(0, 0, 2) * Box(58, 38, 25), name="box")
show(Pos(0, 0, 15.2) * (Box(62.4, 42.4, 5) - Box(58.4, 38.4, 5)), name="lid")
