from build123d import Box, Cylinder, Pos

from solidifai import show

leaf_a = Pos(-11.6, 0, 0) * Box(20, 3, 60)
leaf_b = Pos(11.6, 0, 0) * Box(20, 3, 60)
for z in (-25, 5):
    knuckle = Pos(0, 0, z) * Cylinder(4.5, 12)
    leaf_a += knuckle - Pos(0, 0, z) * Box(3.2, 3.2, 14)
for z in (-10, 20):
    knuckle = Pos(0, 0, z) * Cylinder(4.5, 12)
    leaf_b += knuckle - Pos(0, 0, z) * Box(3.2, 3.2, 14)
show(leaf_a, name="leaf_a")
show(leaf_b, name="leaf_b")
show(Pos(0, 0, -32) * Cylinder(1.5, 64), name="pin")
