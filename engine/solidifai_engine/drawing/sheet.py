"""Lay out the projected views on an A4 sheet with dimensions, a hole schedule,
a title block and a spec/BOM panel -> a ``Drawing``.

All coordinates are page mm, origin top-left, +y down. Views are placed
third-angle (top above front, right beside front, iso upper-right) at one shared
scale chosen to fit. Overall W/D/H are dimensioned in true mm (scale-independent).
"""

from __future__ import annotations

import math

from solidifai_engine.drawing import project
from solidifai_engine.drawing.model import Drawing, Line, Rect, Text

SHEET_W, SHEET_H = 297.0, 210.0  # A4 landscape
MARGIN = 8.0
PANEL_W = 74.0
GAP = 26.0  # between views, leaving room for dimensions
PAD = 16.0  # inset of the view cluster inside the drawing area

# Brand + data-block palette.
INK = "#1a1d23"
MUTED = "#7b818c"
HAIRLINE = "#d4d7dd"
ACCENT = "#2b6cff"  # solidifai cobalt

# Drawn:real ratios, largest first.
_NICE = [50, 20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01]


def _nice_scale(fit: float) -> float:
    for s in _NICE:
        if s <= fit:
            return s
    return fit  # oversized part: no nice ratio fits, so use the exact fitting scale


def _col_label(n: int) -> str:
    """Spreadsheet-style label for a 0-based index: A..Z, AA, AB, ... so a chart
    with 27+ holes never runs the alphabet off into punctuation."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def _seg(drawing: Drawing, pts, ox, oy, bx, by, scale, dashed):
    # Consecutive-pair walk: pts[1:] is intentionally one shorter, so not strict.
    for (u1, v1), (u2, v2) in zip(pts, pts[1:], strict=False):
        drawing.add(
            Line(
                ox + (u1 - bx) * scale,
                oy + (v1 - by) * scale,
                ox + (u2 - bx) * scale,
                oy + (v2 - by) * scale,
                dashed=dashed,
                width=0.12 if dashed else 0.2,
            )
        )


def _place(drawing: Drawing, view: dict, bbox, ox, oy, scale) -> None:
    if bbox is None:
        return
    for pl in view["hidden"]:
        _seg(drawing, pl, ox, oy, bbox[0], bbox[1], scale, dashed=True)
    for pl in view["visible"]:
        _seg(drawing, pl, ox, oy, bbox[0], bbox[1], scale, dashed=False)


def _arrow(drawing: Drawing, x, y, sx, sy) -> None:
    """A small arrowhead at (x,y) pointing along unit (sx,sy)."""
    a = 1.6
    drawing.add(Line(x, y, x + sx * a + sy * 0.6 * a, y + sy * a + sx * 0.6 * a, width=0.15))
    drawing.add(Line(x, y, x + sx * a - sy * 0.6 * a, y + sy * a - sx * 0.6 * a, width=0.15))


def _dim_h(drawing: Drawing, x1, x2, y, value) -> None:
    drawing.add(Line(x1, y, x2, y, width=0.15))
    _arrow(drawing, x1, y, 1, 0)
    _arrow(drawing, x2, y, -1, 0)
    drawing.add(Text((x1 + x2) / 2, y - 1.4, f"{value:.1f}", size=2.6, anchor="middle"))


def _dim_v(drawing: Drawing, y1, y2, x, value) -> None:
    drawing.add(Line(x, y1, x, y2, width=0.15))
    _arrow(drawing, x, y1, 0, 1)
    _arrow(drawing, x, y2, 0, -1)
    drawing.add(Text(x - 1.4, (y1 + y2) / 2 + 0.9, f"{value:.1f}", size=2.6, anchor="end"))


def _label(drawing: Drawing, x, y, s) -> None:
    drawing.add(Text(x, y, s, size=2.8, anchor="middle", bold=True))


def hole_note(holes: dict) -> str:
    if not holes:
        return ""
    parts = ", ".join(f"{n}x Ø{float(d):.1f}" for d, n in sorted(holes.items()))
    return f"HOLES: {parts}"


def _aggregate_holes(holes):
    """Accept either the {dia: count} tally (assembly) or a list of hole dicts and
    return a {dia: count} mapping for ``hole_note``."""
    if isinstance(holes, dict):
        return holes
    agg: dict = {}
    for h in holes or []:
        agg[h["dia"]] = agg.get(h["dia"], 0) + 1
    return agg


def _hole_marks(drawing, holes, view, bbox, ox, oy, scale, start_tag):
    """Center-mark + letter tag for each hole that reads as a circle in ``view``
    (axis ~|| zdir). Returns rows ``(tag, hole, dx, dy)`` where dx/dy are the hole
    center's offset (mm) from this view's part lower-left corner, and the next tag
    ordinal. Tags continue across views via ``start_tag`` so the chart is unique."""
    rows: list = []
    if bbox is None:
        return rows, start_tag
    _x, _up, z = project.view_axes(view)
    tag = start_tag
    for h in holes:
        ax = h["axis"]
        if abs(ax[0] * z[0] + ax[1] * z[1] + ax[2] * z[2]) < 0.9:
            continue  # not a circle in this view
        u, v = project.project_point(view, h["center"])
        px, py = ox + (u - bbox[0]) * scale, oy + (v - bbox[1]) * scale  # screen position
        m = 1.4
        drawing.add(Line(px - m, py, px + m, py, width=0.15))
        drawing.add(Line(px, py - m, px, py + m, width=0.15))
        drawing.add(Text(px + m + 0.6, py - 0.6, _col_label(tag), size=2.2, color=ACCENT))
        # Chart datum is the part's lower-left: X from the left edge, Y up from the
        # bottom edge. Screen v grows downward, so the bottom edge is bbox[3].
        rows.append((_col_label(tag), h, u - bbox[0], bbox[3] - v))
        tag += 1
    return rows, tag


def _hole_chart(drawing, x, right, y, rows):
    """A compact hole table: Tag  Ø  X  Y (X/Y in mm from each hole's view datum)."""
    if not rows:
        return y
    y = _eyebrow(drawing, x, right, y, "HOLE CHART")
    drawing.add(Text(x, y, "TAG  DIA    X      Y", size=2.0, mono=True, color=MUTED))
    y += 4.2
    for tag, h, dx, dy in rows:
        row = f"{tag:<4} Ø{h['dia']:<5.1f}{dx:<6.1f} {dy:<6.1f}"
        drawing.add(Text(x, y, row, size=2.0, mono=True, color=INK))
        y += 3.8
    return y


def _iso_cube(drawing: Drawing, cx, cy, r, color) -> None:
    """A small isometric-cube brand mark (hexagon silhouette + the 3 near edges)."""
    pts = []
    for deg in (90, 150, 210, 270, 330, 30):
        a = math.radians(deg)
        pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))  # y is down
    for i in range(6):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % 6]
        drawing.add(Line(x1, y1, x2, y2, width=0.3, color=color))
    for i in (0, 2, 4):  # near corner -> top, lower-left, lower-right vertices
        drawing.add(Line(cx, cy, pts[i][0], pts[i][1], width=0.3, color=color))


def _eyebrow(drawing: Drawing, x, right, y, label) -> float:
    """An accent section header with a hairline rule under it. Returns the new y."""
    drawing.add(Text(x, y, label, size=2.3, bold=True, color=ACCENT))
    drawing.add(Line(x, y + 1.5, right, y + 1.5, width=0.12, color=HAIRLINE))
    return y + 5.6


def _kv(drawing: Drawing, x, right, y, label, value, step=5.4, size=2.5) -> float:
    """A label/value row: sans muted label left, mono ink value right. Returns new y."""
    drawing.add(Text(x, y, label, size=size, color=MUTED))
    drawing.add(Text(right, y, str(value), size=size, anchor="end", mono=True, color=INK))
    return y + step


def _meta(drawing: Drawing, x, y, label, value) -> None:
    drawing.add(Text(x, y, label, size=1.85, color=MUTED))
    drawing.add(Text(x, y + 4.0, str(value), size=2.7, mono=True, color=INK))


def _panel(drawing: Drawing, x0, spec: dict, scale: float, *, kind="assembly", placed=None) -> None:
    """Branded data block: brand header, specification, BOM (assembly) or hole
    chart (part), title block. ``placed`` is the list of located-hole rows."""
    x = x0 + 4.0
    right = SHEET_W - MARGIN - 4.0
    ty = SHEET_H - MARGIN - 40.0  # top of the ruled title block; content stays above it

    # -- brand header --
    _iso_cube(drawing, x + 2.0, MARGIN + 8.5, 2.4, ACCENT)
    drawing.add(Text(x + 6.4, MARGIN + 10.4, "solidifai", size=5.0, bold=True, color=ACCENT))
    drawing.add(Line(x, MARGIN + 13.6, right, MARGIN + 13.6, width=0.3, color=ACCENT))
    subtitle = "DETAIL DRAWING" if kind == "part" else "TECHNICAL DRAWING"
    drawing.add(Text(x, MARGIN + 17.2, subtitle, size=2.0, color=MUTED))

    # -- specification --
    y = _eyebrow(drawing, x, right, MARGIN + 24.0, "SPECIFICATION")
    W, D, H = spec.get("bbox", (0, 0, 0))
    y = _kv(drawing, x, right, y, "Material", spec.get("material", "-"))
    y = _kv(drawing, x, right, y, "Process", spec.get("process", "-"))
    if kind == "part":
        y = _kv(drawing, x, right, y, "Qty", spec.get("qty", 1))
        y = _kv(drawing, x, right, y, "Mass ea", f"{spec.get('mass_g', 0):.1f} g")
        y = _kv(drawing, x, right, y, "Size", f"{W:.1f} x {D:.1f} x {H:.1f}")
        if spec.get("dfm_summary"):
            y = _kv(drawing, x, right, y, "DFM", spec.get("dfm_summary"))
    else:
        y = _kv(drawing, x, right, y, "Mass", f"{spec.get('mass_g', 0):.1f} g")
        y = _kv(drawing, x, right, y, "Volume", f"{spec.get('volume_cm3', 0):.2f} cm3")
        y = _kv(drawing, x, right, y, "Size", f"{W:.1f} x {D:.1f} x {H:.1f}")
        y = _kv(drawing, x, right, y, "Parts", spec.get("part_count", 1))
        y = _kv(drawing, x, right, y, "DFM", spec.get("dfm_summary", "-"))

    # -- bill of materials (assembly) or hole chart (part) --
    if kind == "assembly":
        bom = spec.get("bom") or []
        if len(bom) > 1:
            y = _eyebrow(drawing, x, right, y + 3.0, "BILL OF MATERIALS")
            max_rows = 18
            for i, item in enumerate(bom[:max_rows], 1):
                qty = item.get("qty", 1)
                name = f"{i:>2}  {item.get('name', 'part')[:13]}" + (f" x{qty}" if qty > 1 else "")
                total = item.get("mass_total_g", item.get("mass_g", 0) * qty)
                y = _kv(drawing, x, right, y, name, f"{total:.1f} g", step=4.4, size=2.2)
            if len(bom) > max_rows:
                note_y = min(y, ty - 2.0)  # keep the overflow note clear of the title rule
                drawing.add(Text(x, note_y, f"+{len(bom) - max_rows} more", size=2.0, color=MUTED))
    elif placed:
        y = _hole_chart(drawing, x, right, y + 3.0, placed)

    # -- title block (ruled, bottom of the panel) --
    drawing.add(Line(x0, ty, SHEET_W - MARGIN, ty, width=0.3))
    drawing.add(Text(x, ty + 7.0, spec.get("name", "part")[:20], size=4.8, bold=True, color=INK))
    drawing.add(Text(x, ty + 11.0, "PART", size=1.85, color=MUTED))
    midx = (x + right) / 2 + 2.0
    gy = ty + 18.5
    _meta(drawing, x, gy, "SCALE", _scale_label(scale))
    _meta(drawing, midx, gy, "UNITS", spec.get("units", "mm"))
    _meta(drawing, x, gy + 9.0, "PROJECTION", "Third angle")
    _meta(drawing, midx, gy + 9.0, "DATE", spec.get("generated_at", ""))
    drawing.add(
        Text(
            right,
            SHEET_H - MARGIN - 2.5,
            "Generated with solidifai",
            size=1.85,
            anchor="end",
            color=MUTED,
        )
    )


def _scale_label(scale: float) -> str:
    if scale >= 1:
        return f"{scale:g}:1"
    return f"1:{1 / scale:g}"


def _framed() -> Drawing:
    """A blank A4 sheet with the border + the panel divider drawn."""
    d = Drawing(SHEET_W, SHEET_H)
    d.add(Rect(MARGIN, MARGIN, SHEET_W - 2 * MARGIN, SHEET_H - 2 * MARGIN))
    panel_x = SHEET_W - MARGIN - PANEL_W
    d.add(Line(panel_x, MARGIN, panel_x, SHEET_H - MARGIN, width=0.2))
    return d


def _render_sheet(d: Drawing, compound, spec: dict, opts: dict, *, kind: str) -> dict:
    """Lay out the 4 views + per-view extent dims + located-hole marks (part) or
    the hole note (assembly) + the right-hand panel onto the framed Drawing ``d``.
    ``kind`` is 'assembly' or 'part'. Returns the scale meta."""
    panel_x = SHEET_W - MARGIN - PANEL_W

    names = ("front", "top", "right", "iso")
    views = {v: project.project_view(compound, v) for v in names}
    bboxes = {v: project.polylines_bbox(views[v]["visible"] + views[v]["hidden"]) for v in names}

    W, D, H = spec.get("bbox", (1.0, 1.0, 1.0))

    def _span(bb, axis):  # projected mm span of a view bbox (0 = u/width, 1 = v/height)
        return 0.0 if bb is None else (bb[2] - bb[0] if axis == 0 else bb[3] - bb[1])

    # Budget the right column / top row by the iso's ACTUAL projected span (an iso is
    # wider and taller than a single ortho view), so no view bleeds into the panel
    # for flat, wide parts where the iso would otherwise overrun the depth budget.
    right_col_w = max(D, _span(bboxes["iso"], 0))
    top_row_h = max(D, _span(bboxes["iso"], 1))
    avail_w = (panel_x - MARGIN) - 2 * PAD
    avail_h = (SHEET_H - 2 * MARGIN) - 2 * PAD
    fit = min(
        (avail_w - GAP) / max(W + right_col_w, 1e-6),
        (avail_h - GAP) / max(H + top_row_h, 1e-6),
    )
    scale = _nice_scale(fit)

    ox = MARGIN + PAD + 6.0
    oy = MARGIN + PAD
    top_h = D * scale  # the top view's own depth extent (drives the depth dimension)
    front_y = oy + top_row_h * scale + GAP  # drop the front row clear of the taller iso
    right_x = ox + W * scale + GAP

    _place(d, views["top"], bboxes["top"], ox, oy, scale)
    _place(d, views["front"], bboxes["front"], ox, front_y, scale)
    _place(d, views["right"], bboxes["right"], right_x, front_y, scale)
    _place(d, views["iso"], bboxes["iso"], right_x, oy, scale)

    _label(d, ox + W * scale / 2, front_y + H * scale + 16.0, "FRONT")
    _label(d, ox + W * scale / 2, oy - 4.0, "TOP")
    _label(d, right_x + D * scale / 2, front_y + H * scale + 16.0, "RIGHT")
    _label(d, right_x + D * scale / 2, oy - 4.0, "ISO")

    _dim_h(d, ox, ox + W * scale, front_y + H * scale + 8.0, W)
    _dim_v(d, front_y, front_y + H * scale, ox - 8.0, H)
    _dim_v(d, oy, oy + top_h, ox - 8.0, D)

    placed: list = []
    if kind == "part":
        # Located holes: each hole is marked in the one view where it reads as a
        # circle (top for Z-axis holes, front for Y, right for X). Tags continue
        # across views so the chart is globally unique.
        holes = spec.get("holes") or []
        next_tag = 0
        for view, vx, vy, bb in (
            ("top", ox, oy, bboxes["top"]),
            ("front", ox, front_y, bboxes["front"]),
            ("right", right_x, front_y, bboxes["right"]),
        ):
            rows, next_tag = _hole_marks(d, holes, view, bb, vx, vy, scale, next_tag)
            placed.extend(rows)
        # Oblique holes read as ellipses in every ortho view, so they carry no
        # unambiguous X/Y datum and stay off the chart. Note the count rather than
        # inventing coordinates; their bore edges are still drawn in the views.
        oblique = len(holes) - len(placed)
        if oblique:
            d.add(
                Text(
                    ox,
                    front_y + H * scale + 23.0,
                    f"{oblique} hole(s) not charted (oblique)",
                    size=2.4,
                    color=MUTED,
                )
            )
    else:
        note = hole_note(_aggregate_holes(spec.get("holes")))
        if note:
            d.add(Text(ox, front_y + H * scale + 23.0, note, size=2.6))

    _panel(d, panel_x, spec, scale, kind=kind, placed=placed)
    return {"scale": scale, "scaleLabel": _scale_label(scale)}


def compose(compound, spec: dict, opts: dict) -> tuple:
    """The assembly sheet: all parts projected together, overall dims + grouped BOM."""
    d = _framed()
    meta = _render_sheet(d, compound, spec, opts, kind="assembly")
    return d, meta


def compose_part(group: dict, part_spec: dict, opts: dict) -> tuple:
    """A single part's detail sheet: its own views, extent dims, located holes."""
    d = _framed()
    meta = _render_sheet(d, group["shape"], part_spec, opts, kind="part")
    return d, meta


def compose_document(groups: list, assembly_compound, spec: dict, opts: dict) -> tuple:
    """Build the page set: an assembly overview followed by one detail sheet per
    unique part. A single-instance model returns just its one sheet. Returns
    ``(pages, meta)`` where ``meta`` carries the lead page's scale label."""
    if spec.get("part_count", len(groups)) <= 1 and len(groups) == 1:
        d, meta = compose_part(groups[0], groups[0].get("spec", spec), opts)
        return [d], meta
    pages = []
    asm, meta = compose(assembly_compound, spec, opts)
    pages.append(asm)
    for g in groups:
        try:
            d, _m = compose_part(g, g.get("spec", spec), opts)
            pages.append(d)
        except Exception:  # noqa: BLE001 - one bad part never drops the document
            continue
    return pages, meta
