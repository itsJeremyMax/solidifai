from build123d import Location

from solidifai import skeleton

PARAMS = {}


def build(parent):
    s = skeleton()
    s.scalar("pin_d", parent["body_w"] / 12)
    s.frame("pin_frame", Location((0, 0, 0)))
    s.frame("knuckle_frame", Location((0, 0, 6)))
    return s
