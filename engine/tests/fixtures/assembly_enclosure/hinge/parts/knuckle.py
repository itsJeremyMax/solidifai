from build123d import BuildPart, Cylinder, Hole

from solidifai import show


def build(inputs):
    with BuildPart() as p:
        Cylinder(radius=inputs["pin_d"], height=8)
        Hole(radius=inputs["pin_d"] / 2)
    show(p.part, name="Knuckle", material="pla")
