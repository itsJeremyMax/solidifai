# Handheld case: the handheld-enclosure playbook, worked end to end. A two-part
# assembly — a filleted hollow SHELL (top-open) plus a drop-in LID — sized to an
# internal device. Every number traces to a lens the playbook pulls:
#
#   - cavity = device + clearance per side, shell = device + 2*(clearance + wall)
#     (manufacturability: FDM mating clearance ~0.1-0.3 mm; loose end for the cavity)
#   - one radius family of filleted outer edges, no sharp grip surface
#     (aesthetics-form + the touched-edge rule from ergonomics)
#   - a button cutout >= the 10 mm finger-pad minimum, 12-15 mm comfortable
#     (ergonomics: pressable-control size), placed on the operating-thumb face
#   - a port opening = connector + ~0.5 mm so the plug clears the wall
#     (affordance-usability: group ports on one oriented face)
#   - a lid that drops into the rim with a real lip clearance, never coincident
#     (manufacturability: tighter end of the mating gap, for a lip that locates)
#
# Two parts: model the shell and lid as separate show() objects. Exploded view
# is a built-in viewport control (no explode parameter) — and you can review the
# fit yourself with capture_views(["iso", "front"], explode=70), which spreads
# the parts for that render only without changing the model.

from build123d import (
    Align,
    Axis,
    Box,
    BuildPart,
    Locations,
    Mode,
    fillet,
    offset,
)

from solidifai import show

PARAMS = {
    "device_w":   {"value": 60.0, "min": 30.0, "max": 120.0, "step": 1.0,  "unit": "mm", "desc": "Device width  (X) — the thing going inside"},
    "device_h":   {"value": 90.0, "min": 40.0, "max": 160.0, "step": 1.0,  "unit": "mm", "desc": "Device height (Y)"},
    "device_t":   {"value": 16.0, "min": 8.0,  "max": 60.0,  "step": 1.0,  "unit": "mm", "desc": "Device thickness (Z) inside the shell"},
    "wall":       {"value": 2.4,  "min": 1.6,  "max": 4.0,   "step": 0.2,  "unit": "mm", "desc": "Shell wall (>= printable minimum)"},
    "clearance":  {"value": 0.3,  "min": 0.1,  "max": 0.6,   "step": 0.05, "unit": "mm", "desc": "Cavity gap per side (loose FDM fit)"},
    "lid_clear":  {"value": 0.15, "min": 0.1,  "max": 0.3,   "step": 0.05, "unit": "mm", "desc": "Lid lip gap (tight locating fit)"},
    "corner_r":   {"value": 6.0,  "min": 1.0,  "max": 12.0,  "step": 0.5,  "unit": "mm", "desc": "Outer corner radius — one family"},
    "button_dia": {"value": 13.0, "min": 10.0, "max": 18.0,  "step": 0.5,  "unit": "mm", "desc": "Button cutout (>= 10 mm finger pad)"},
    "port_w":     {"value": 12.0, "min": 6.0,  "max": 24.0,  "step": 0.5,  "unit": "mm", "desc": "Port opening width  (connector + ~0.5)"},
    "port_h":     {"value": 7.5,  "min": 4.0,  "max": 16.0,  "step": 0.5,  "unit": "mm", "desc": "Port opening height (connector + ~0.5)"},
}


def build(
    device_w,
    device_h,
    device_t,
    wall,
    clearance,
    lid_clear,
    corner_r,
    button_dia,
    port_w,
    port_h,
):
    """Filleted top-open shell (button + port cut through its walls) plus a
    drop-in lid with a clearance-fit lip. One manifold solid each."""
    # Cavity = device + clearance per side; shell adds a wall on top of that.
    # So the outer box is device + 2*(clearance + wall) in W and H, and the
    # cavity depth is device_t + clearance (the lid caps the open top).
    out_w = device_w + 2 * (clearance + wall)
    out_h = device_h + 2 * (clearance + wall)
    out_t = device_t + clearance + wall  # closed floor + cavity, top stays open

    # --- Shell: filleted hollow box, top-open for the lid ------------------
    with BuildPart() as shell_b:
        # Solid outer body on the bed (floor at z = 0).
        Box(out_w, out_h, out_t, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # One radius family: break all four vertical grip edges.
        fillet(shell_b.edges().filter_by(Axis.Z), radius=corner_r)

        # Hollow to a uniform wall, leaving the top face open for the lid.
        top = shell_b.faces().sort_by(Axis.Z)[-1]
        offset(amount=-wall, openings=top)

        # Button cutout through the +X face (the operating-thumb side). A box
        # centered ON the face straddles the wall, so SUBTRACT punches a clean
        # through-hole. button_dia >= the 10 mm finger-pad minimum.
        x_face = shell_b.faces().sort_by(Axis.X)[-1]
        with Locations(x_face):
            Box(button_dia, button_dia, 4 * wall, mode=Mode.SUBTRACT)

        # Port opening through the -Y end face (one oriented port face), sized
        # connector + ~0.5 mm. Dropped toward the floor like a real USB cutout.
        y_face = shell_b.faces().sort_by(Axis.Y)[0]
        with Locations(y_face):
            with Locations((0, -(out_t / 2 - wall - port_h / 2))):
                Box(port_w, port_h, 4 * wall, mode=Mode.SUBTRACT)
    shell = shell_b.part

    # --- Lid: a flat cap plus a lip that drops into the rim ----------------
    # The lip plugs the opening with `lid_clear` of gap on every side (a tight
    # locating fit) — never modeled coincident with the rim. It seats from the
    # rim down by `lip_depth`; the cap sits one wall-thickness proud on top.
    cavity_w = device_w + 2 * clearance
    cavity_h = device_h + 2 * clearance
    lip_w = cavity_w - 2 * lid_clear
    lip_h = cavity_h - 2 * lid_clear
    lip_depth = min(5.0, device_t - 1.0)

    with BuildPart() as lid_b:
        # Cap covering the rim, one wall thick, sitting on top of the shell.
        with Locations((0, 0, out_t)):
            Box(out_w, out_h, wall, align=(Align.CENTER, Align.CENTER, Align.MIN))
            # Soften the lid's top corners to match the shell's radius family.
            fillet(lid_b.edges().filter_by(Axis.Z), radius=corner_r)
        # Lip dropping down into the cavity (clearance fit, not coincident).
        with Locations((0, 0, out_t - lip_depth)):
            Box(lip_w, lip_h, lip_depth, align=(Align.CENTER, Align.CENTER, Align.MIN))
    lid = lid_b.part

    show(shell, name="Case", material="petg")
    show(lid, name="Lid", material="petg", color=(0.85, 0.5, 0.2))


if __name__ == "__main__":
    build(**{k: v["value"] for k, v in PARAMS.items()})
