from build123d import Box, Pos

from solidifai import show

show(Box(62, 42, 25) - Box(58, 38, 23), name="box")
show(Pos(0, 0, 40) * (Box(62.4, 42.4, 5) - Box(58.4, 38.4, 5)), name="lid")
