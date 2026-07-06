from build123d import BuildPart, Cylinder

from solidifai import show


def build(inputs):
    with BuildPart() as p:
        Cylinder(radius=inputs["pin_d"] / 2, height=24)
    show(p.part, name="Pin", material="steel")
