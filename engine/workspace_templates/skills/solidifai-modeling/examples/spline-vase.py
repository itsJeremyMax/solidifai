# Bud vase: revolve an organic spline silhouette about the Z axis, then hollow
# it into a thin-walled vessel with an open mouth. This is the canonical
# "curved silhouette" pattern -- draw a flowing half-profile with a Spline
# instead of straight Polyline segments, revolve it, then shell it with offset.
#
# The same recipe makes bottles, cups, pots, and lampshades: change the
# silhouette control points and the wall.

from build123d import (
    Axis,
    BuildLine,
    BuildPart,
    BuildSketch,
    Line,
    Plane,
    Spline,
    make_face,
    offset,
    revolve,
)

from solidifai import show

PARAMS = {
    "height":    {"value": 120.0, "min": 40.0, "max": 240.0, "step": 2.0, "unit": "mm"},
    "base_dia":  {"value": 56.0,  "min": 20.0, "max": 140.0, "step": 1.0, "unit": "mm", "desc": "Foot width"},
    "belly_dia": {"value": 86.0,  "min": 20.0, "max": 180.0, "step": 1.0, "unit": "mm", "desc": "Widest point"},
    "neck_dia":  {"value": 34.0,  "min": 12.0, "max": 120.0, "step": 1.0, "unit": "mm", "desc": "Narrowest point"},
    "mouth_dia": {"value": 48.0,  "min": 12.0, "max": 140.0, "step": 1.0, "unit": "mm", "desc": "Opening"},
    "wall":      {"value": 2.4,   "min": 1.2,  "max": 6.0,   "step": 0.2, "unit": "mm", "desc": "Wall thickness"},
}


def build(height, base_dia, belly_dia, neck_dia, mouth_dia, wall):
    """Spline silhouette revolved about Z, then hollowed to a thin-walled vessel
    open at the mouth."""
    with BuildPart() as p:
        # Half-profile on a vertical plane, entirely on +X. The Spline gives the
        # flowing belly -> neck -> flared lip; straight Lines close the foot,
        # the mouth, and the axis.
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Line((0, 0), (base_dia / 2, 0))                  # foot
                Spline(
                    (base_dia / 2, 0),
                    (belly_dia / 2, height * 0.32),              # belly
                    (neck_dia / 2, height * 0.72),               # neck
                    (mouth_dia / 2, height),                     # flared lip
                )
                Line((mouth_dia / 2, height), (0, height))       # across the mouth
                Line((0, height), (0, 0))                        # down the axis
            make_face()
        revolve(axis=Axis.Z)

        # Hollow it: the highest face is the mouth disk; leave it open.
        mouth = p.faces().sort_by(Axis.Z)[-1]
        offset(amount=-wall, openings=mouth)

    show(p.part, name="Vase")


if __name__ == "__main__":
    build(**{key: spec["value"] for key, spec in PARAMS.items()})
