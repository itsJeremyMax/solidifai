# Parametric knob: a turned (revolved) profile with a softened top edge and a
# ring of finger flutes around the rim. This is the canonical "lathe part"
# pattern -- draw a 2D profile on a vertical plane, then revolve it about the
# Z axis.
#
# The profile is drawn on Plane.XZ entirely on the +X side of the Z axis; the
# axis of revolution must NOT pass through the profile interior.

from build123d import (
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Cylinder,
    Locations,
    Mode,
    Plane,
    Polyline,
    PolarLocations,
    make_face,
    revolve,
    fillet,
)

from solidifai import show

PARAMS = {
    "base_dia":  {"value": 36.0, "min": 16.0, "max": 80.0, "step": 1.0, "unit": "mm", "desc": "Grip width"},
    "top_dia":   {"value": 24.0, "min": 8.0,  "max": 70.0, "step": 1.0, "unit": "mm", "desc": "Top width"},
    "height":    {"value": 22.0, "min": 8.0,  "max": 60.0, "step": 1.0, "unit": "mm"},
    "shaft_dia": {"value": 6.0,  "min": 2.0,  "max": 20.0, "step": 0.5, "unit": "mm", "desc": "Center bore"},
    "flutes":    {"value": 12,   "min": 0,    "max": 36,   "step": 1,   "unit": "",   "desc": "Finger grips"},
    "flute_dia": {"value": 4.0,  "min": 1.0,  "max": 10.0, "step": 0.5, "unit": "mm", "desc": "Scallop size"},
}


def build(base_dia, top_dia, height, shaft_dia, flutes, flute_dia):
    """Revolved knob body, filleted top rim, optional finger flutes, center
    shaft bore."""
    br = base_dia / 2
    tr = top_dia / 2
    with BuildPart() as p:
        # Half-profile: base -> straight wall -> tapered shoulder -> top.
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(
                    (0, 0),
                    (br, 0),
                    (br, height * 0.55),
                    (tr, height),
                    (0, height),
                    close=True,
                )
            make_face()
        revolve(axis=Axis.Z)

        # Soften the top rim.
        top = p.faces().sort_by(Axis.Z)[-1]
        fillet(top.edges(), radius=min(tr / 3, 3.0))

        # Finger flutes: scallops cut around the widest part of the body.
        if int(flutes) > 0:
            with Locations((0, 0, height * 0.45)):
                with PolarLocations(radius=br, count=int(flutes)):
                    Cylinder(radius=flute_dia / 2, height=height, mode=Mode.SUBTRACT)

        # Center shaft bore from the bottom.
        Cylinder(radius=shaft_dia / 2, height=height, mode=Mode.SUBTRACT)

    show(p.part, name="Knob")


if __name__ == "__main__":
    build(**{key: spec["value"] for key, spec in PARAMS.items()})
