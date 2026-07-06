from build123d import Location

from solidifai import skeleton

PARAMS = {
    "body_w": {
        "value": 60.0,
        "min": 30,
        "max": 120,
        "step": 1.0,
        "unit": "mm",
        "desc": "Body width",
    },
    "body_h": {
        "value": 30.0,
        "min": 15,
        "max": 90,
        "step": 1.0,
        "unit": "mm",
        "desc": "Body height",
    },
    "wall": {"value": 2.4, "min": 1.2, "max": 5.0, "step": 0.2, "unit": "mm", "desc": "Wall"},
}


def build(body_w, body_h, wall):
    s = skeleton()
    s.scalar("body_w", body_w)
    s.scalar("wall", wall)
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, body_h)))
    s.frame("hinge_frame", Location((body_w / 2, 0, body_h / 2)))
    return s
