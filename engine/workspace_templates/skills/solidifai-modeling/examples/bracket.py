# Rounded mounting bracket: a rounded rectangular plate with a chamfered top
# edge, a central bore, and four corner mounting holes. This is the canonical
# "flat plate + holes" pattern and the default starter model.
#
# Run it with the execute_script tool. Drag the sliders (or use set_params) to
# resize it; every value below is exposed as a slider.

from build123d import (
    Axis,
    BuildPart,
    BuildSketch,
    Hole,
    Locations,
    RectangleRounded,
    chamfer,
    extrude,
)

from solidifai import show

PARAMS = {
    "length":         {"value": 90.0, "min": 50.0, "max": 180.0, "step": 1.0, "unit": "mm"},
    "width":          {"value": 60.0, "min": 30.0, "max": 140.0, "step": 1.0, "unit": "mm"},
    "thickness":      {"value": 8.0,  "min": 3.0,  "max": 24.0,  "step": 0.5, "unit": "mm", "desc": "Plate depth"},
    "corner_radius":  {"value": 12.0, "min": 2.0,  "max": 30.0,  "step": 0.5, "unit": "mm", "desc": "Edge rounding"},
    "bore_dia":       {"value": 26.0, "min": 6.0,  "max": 60.0,  "step": 1.0, "unit": "mm", "desc": "Center hole"},
    "mount_hole_dia": {"value": 6.5,  "min": 2.0,  "max": 16.0,  "step": 0.5, "unit": "mm", "desc": "Mount holes"},
}


def build(length, width, thickness, corner_radius, bore_dia, mount_hole_dia):
    """Rounded plate, chamfered top edge, central bore, four corner holes."""
    inset = max(corner_radius, mount_hole_dia) + 6.0
    with BuildPart() as p:
        with BuildSketch():
            RectangleRounded(length, width, corner_radius)
        extrude(amount=thickness)

        # Soften the top outline with a small chamfer.
        top_face = p.faces().sort_by(Axis.Z)[-1]
        chamfer(top_face.edges(), length=min(thickness / 3.0, corner_radius / 2.0, 2.0))

        # Central bore.
        with Locations((0, 0)):
            Hole(radius=bore_dia / 2.0)

        # Four corner mounting holes.
        with Locations(
            (length / 2 - inset, width / 2 - inset),
            (-(length / 2 - inset), width / 2 - inset),
            (length / 2 - inset, -(width / 2 - inset)),
            (-(length / 2 - inset), -(width / 2 - inset)),
        ):
            Hole(radius=mount_hole_dia / 2.0)

    show(p.part, name="Bracket")


if __name__ == "__main__":
    build(**{key: spec["value"] for key, spec in PARAMS.items()})
