from build123d import Cylinder

from solidifai import show

show(Cylinder(8, 2.2) - Cylinder(4.2, 5), name="washer")
