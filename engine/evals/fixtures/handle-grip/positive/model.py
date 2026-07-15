from build123d import Cylinder

from solidifai import show

show(Cylinder(18, 110) - Cylinder(6.1, 112), name="handle")
