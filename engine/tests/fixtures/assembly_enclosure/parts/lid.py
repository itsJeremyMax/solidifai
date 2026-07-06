from build123d import Box, BuildPart

from solidifai import show


def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Lid", material="pla")
