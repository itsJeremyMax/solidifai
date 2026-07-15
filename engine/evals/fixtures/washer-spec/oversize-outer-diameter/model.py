from build123d import Cylinder

from solidifai import show

show(Cylinder(8.6, 1.6) - Cylinder(4.2, 4), name="washer")
