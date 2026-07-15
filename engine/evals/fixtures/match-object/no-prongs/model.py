from build123d import Box, Cylinder, Pos

from solidifai import show

show(Box(36, 20, 4) - Pos(0, 0, 7) * Cylinder(2.6, 30, rotation=(90, 0, 0)), name="gopro_mount")
