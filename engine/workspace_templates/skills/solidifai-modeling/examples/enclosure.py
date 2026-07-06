# Enclosure: a hollow box (shelled with the top open) plus a recessed lip on
# the rim so a lid can sit into it. This is the canonical "case / housing"
# pattern: build a solid, then hollow it with offset(openings=...).
#
# Shelling in build123d is offset() with a negative amount and the face(s) to
# leave open passed as `openings`.

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Locations,
    Mode,
    offset,
)

from solidifai import show

PARAMS = {
    "length":    {"value": 70.0, "min": 30.0, "max": 200.0, "step": 1.0, "unit": "mm"},
    "width":     {"value": 50.0, "min": 30.0, "max": 200.0, "step": 1.0, "unit": "mm"},
    "height":    {"value": 30.0, "min": 10.0, "max": 120.0, "step": 1.0, "unit": "mm"},
    "wall":      {"value": 2.4,  "min": 1.0,  "max": 6.0,   "step": 0.2, "unit": "mm"},
    "lip_depth": {"value": 4.0,  "min": 1.0,  "max": 10.0,  "step": 0.5, "unit": "mm"},
}


def build(length, width, height, wall, lip_depth):
    """A bottom-closed, top-open box hollowed to a uniform wall, with an inner
    lip ledge cut into the top rim for a drop-in lid."""
    with BuildPart() as p:
        # Sit the box on the XY plane (bottom at z = 0).
        Box(length, width, height, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Hollow it, leaving the top face open -> uniform `wall` everywhere else.
        top = p.faces().sort_by(Axis.Z)[-1]
        offset(amount=-wall, openings=top)

        # Cut a shallow rebate around the inside of the top rim: a thinner wall
        # for the last `lip_depth` so a lid can nest down into the opening.
        with Locations((0, 0, height - lip_depth / 2)):
            Box(
                length - wall,
                width - wall,
                lip_depth,
                align=(Align.CENTER, Align.CENTER, Align.CENTER),
                mode=Mode.SUBTRACT,
            )

    show(p.part, name="Enclosure")


if __name__ == "__main__":
    build(**{key: spec["value"] for key, spec in PARAMS.items()})
