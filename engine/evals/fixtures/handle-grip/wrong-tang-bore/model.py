from build123d import Cylinder

from solidifai import show

show(Cylinder(18, 110) - Cylinder(5, 112), name="handle")
