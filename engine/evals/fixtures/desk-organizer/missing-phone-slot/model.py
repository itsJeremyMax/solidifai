from build123d import Box, Pos

from solidifai import show

organizer = Box(104, 44, 42)
organizer -= Pos(-32, 0, 6) * Box(20, 20, 30)
organizer -= Pos(30, 0, 14.5) * Box(28, 28, 13)
show(organizer, name="organizer")
