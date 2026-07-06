# Ergonomic grip: loft a stack of oval cross-sections that swell at the palm and
# taper toward the ends, then round the end rims. This is the multi-section loft
# pattern -- stack 2D sketches on parallel planes and blend them into one smooth
# body. Swap the Ellipses for RectangleRounded sections for a flatter,
# paddle-like grip.
#
# Pairs with the grip-handle playbook in the solidifai-product-design skill.

from build123d import Axis, BuildPart, BuildSketch, Ellipse, Plane, fillet, loft

from solidifai import show

PARAMS = {
    "length": {"value": 110.0, "min": 60.0, "max": 200.0, "step": 2.0, "unit": "mm"},
    "width":  {"value": 38.0,  "min": 18.0, "max": 70.0,  "step": 1.0, "unit": "mm", "desc": "Palm width"},
    "thick":  {"value": 30.0,  "min": 14.0, "max": 60.0,  "step": 1.0, "unit": "mm", "desc": "Front-back depth"},
    "taper":  {"value": 62.0,  "min": 30.0, "max": 95.0,  "step": 1.0, "unit": "%",  "desc": "End size vs belly"},
}


def build(length, width, thick, taper):
    """Three oval sections (slim end, full belly, slim end) lofted into a waisted
    grip, with the end rims rounded off."""
    bw, bt = width / 2, thick / 2                   # belly half-axes
    ew, et = bw * taper / 100, bt * taper / 100     # end half-axes
    with BuildPart() as p:
        with BuildSketch(Plane.XY):
            Ellipse(ew, et)
        with BuildSketch(Plane.XY.offset(length / 2)):
            Ellipse(bw, bt)                          # full at the palm
        with BuildSketch(Plane.XY.offset(length)):
            Ellipse(ew, et)
        loft()

        # Round the two flat end caps so the grip has no hard rim.
        caps = p.faces().filter_by(Axis.Z).edges()
        fillet(caps, radius=min(ew, et) * 0.7)

    show(p.part, name="Grip")


if __name__ == "__main__":
    build(**{key: spec["value"] for key, spec in PARAMS.items()})
