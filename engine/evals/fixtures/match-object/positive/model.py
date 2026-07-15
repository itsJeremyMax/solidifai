from build123d import Box, Cylinder, Pos

from solidifai import show

mount = Box(36, 20, 4)
mount += Pos(0, -6, 7) * Box(18, 4, 12) + Pos(0, 6, 7) * Box(18, 4, 12)
mount -= Pos(0, 0, 7) * Cylinder(2.6, 30, rotation=(90, 0, 0))
show(mount, name="gopro_mount")
