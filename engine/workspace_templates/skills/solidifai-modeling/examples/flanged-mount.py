# Flanged mount: a thin circular base flange with a raised central boss, bored
# through the middle, and a ring of bolt holes around the flange. This is the
# canonical "round part on a bolt circle" pattern -- PolarLocations places the
# holes evenly around a circle.

from build123d import (
    Align,
    Axis,
    BuildPart,
    Cylinder,
    Hole,
    Locations,
    PolarLocations,
)

from solidifai import show

PARAMS = {
    "flange_dia":  {"value": 60.0, "min": 30.0, "max": 140.0, "step": 1.0, "unit": "mm"},
    "flange_thk":  {"value": 6.0,  "min": 3.0,  "max": 20.0,  "step": 0.5, "unit": "mm"},
    "boss_dia":    {"value": 28.0, "min": 12.0, "max": 80.0,  "step": 1.0, "unit": "mm"},
    "boss_height": {"value": 18.0, "min": 4.0,  "max": 60.0,  "step": 1.0, "unit": "mm"},
    "bore_dia":    {"value": 14.0, "min": 4.0,  "max": 40.0,  "step": 0.5, "unit": "mm"},
    "bolt_dia":    {"value": 5.0,  "min": 2.0,  "max": 12.0,  "step": 0.5, "unit": "mm"},
    "bolt_count":  {"value": 4,    "min": 3,    "max": 12,    "step": 1,   "unit": ""},
}


def build(flange_dia, flange_thk, boss_dia, boss_height, bore_dia, bolt_dia, bolt_count):
    """Base flange + raised boss + through bore + bolt circle."""
    bolt_circle_r = (flange_dia / 2 + boss_dia / 2) / 2  # midway between boss and rim
    bottom = (Align.CENTER, Align.CENTER, Align.MIN)
    with BuildPart() as p:
        # Flange sits on the XY plane.
        Cylinder(radius=flange_dia / 2, height=flange_thk, align=bottom)
        # Boss rises from the top of the flange.
        with Locations((0, 0, flange_thk)):
            Cylinder(radius=boss_dia / 2, height=boss_height, align=bottom)
        # Bore straight through flange + boss.
        Hole(radius=bore_dia / 2)
        # Bolt circle on the underside of the flange.
        base = p.faces().sort_by(Axis.Z)[0]
        with Locations(base):
            with PolarLocations(radius=bolt_circle_r, count=int(bolt_count)):
                Hole(radius=bolt_dia / 2)

    show(p.part, name="FlangedMount")


if __name__ == "__main__":
    build(**{key: spec["value"] for key, spec in PARAMS.items()})
