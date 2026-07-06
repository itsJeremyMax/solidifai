"""Render a ``Drawing`` to SVG (zero-dep XML) and PDF (fpdf2, optional).

Both backends consume the same page-mm ``Drawing`` model, so the layout logic
lives only in ``sheet``. PDF degrades gracefully: if ``fpdf2`` is not installed,
``to_pdf`` returns ``None`` and the caller reports SVG-only.
"""

from __future__ import annotations

from solidifai_engine.drawing.model import Drawing, Line, Rect, Text

_STROKE = "#1a1d23"
PAGE_GAP = 10.0  # mm between stacked sheets in a multi-page SVG


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _svg_body(drawing: Drawing, dy: float = 0.0) -> list[str]:
    """Render a single drawing's primitives as SVG element strings, translated
    down by ``dy`` mm (for stacking pages)."""
    out: list[str] = []
    for it in drawing.items:
        if isinstance(it, Line):
            dash = ' stroke-dasharray="1.4,1"' if it.dashed else ""
            stroke = f' stroke="{it.color}"' if it.color else ""
            out.append(
                f'<line x1="{it.x1:.3f}" y1="{it.y1 + dy:.3f}" x2="{it.x2:.3f}" '
                f'y2="{it.y2 + dy:.3f}" stroke-width="{it.width}"{stroke}{dash}/>'
            )
        elif isinstance(it, Rect):
            stroke = f' stroke="{it.color}"' if it.color else ""
            fill = f' fill="{it.fill}"' if it.fill else ""
            out.append(
                f'<rect x="{it.x:.3f}" y="{it.y + dy:.3f}" width="{it.w:.3f}" '
                f'height="{it.h:.3f}" stroke-width="{it.width}"{stroke}{fill}/>'
            )
        elif isinstance(it, Text):
            weight = ' font-weight="bold"' if it.bold else ""
            family = ' font-family="SFMono-Regular, Menlo, Consolas, monospace"' if it.mono else ""
            out.append(
                f'<text x="{it.x:.3f}" y="{it.y + dy:.3f}" font-size="{it.size}" '
                f'fill="{it.color or _STROKE}" stroke="none" '
                f'text-anchor="{it.anchor}"{weight}{family}>'
                f"{_esc(it.s)}</text>"
            )
    return out


def to_svg(drawing: Drawing) -> str:
    """Render a single drawing to an SVG string (mm units, viewBox = sheet size)."""
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{drawing.width}mm" '
        f'height="{drawing.height}mm" viewBox="0 0 {drawing.width} {drawing.height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<g stroke="{_STROKE}" fill="none" '
        'font-family="Helvetica, Arial, sans-serif" stroke-linecap="round">',
    ]
    out.extend(_svg_body(drawing))
    out.append("</g></svg>")
    return "\n".join(out)


def to_svg_document(drawings: list) -> str:
    """Stack pages vertically into one SVG (each its own sheet, PAGE_GAP between)."""
    if not drawings:
        return to_svg(Drawing(297, 210))
    w = max(d.width for d in drawings)
    total_h = sum(d.height for d in drawings) + PAGE_GAP * (len(drawings) - 1)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" '
        f'height="{total_h}mm" viewBox="0 0 {w} {total_h}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<g stroke="{_STROKE}" fill="none" '
        'font-family="Helvetica, Arial, sans-serif" stroke-linecap="round">',
    ]
    dy = 0.0
    for d in drawings:
        out.extend(_svg_body(d, dy))
        dy += d.height + PAGE_GAP
    out.append("</g></svg>")
    return "\n".join(out)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _latin1(s: str) -> str:
    """fpdf2 core fonts are latin-1; substitute anything outside it."""
    return s.encode("latin-1", "replace").decode("latin-1")


def _pdf_page(pdf, drawing: Drawing, ink) -> None:
    """Render one drawing's primitives onto the current (already-added) PDF page."""
    pdf.set_draw_color(*ink)
    pdf.set_text_color(*ink)
    for it in drawing.items:
        if isinstance(it, Line):
            pdf.set_draw_color(*(_rgb(it.color) if it.color else ink))
            pdf.set_line_width(it.width)
            pdf.set_dash_pattern(dash=1.4, gap=1.0) if it.dashed else pdf.set_dash_pattern()
            pdf.line(it.x1, it.y1, it.x2, it.y2)
        elif isinstance(it, Rect):
            pdf.set_dash_pattern()
            pdf.set_line_width(it.width)
            pdf.set_draw_color(*(_rgb(it.color) if it.color else ink))
            if it.fill:
                pdf.set_fill_color(*_rgb(it.fill))
                pdf.rect(it.x, it.y, it.w, it.h, style="DF")
            else:
                pdf.rect(it.x, it.y, it.w, it.h)
        elif isinstance(it, Text):
            font = "Courier" if it.mono else "Helvetica"
            pdf.set_font(font, "B" if it.bold else "", size=it.size * 2.83)
            pdf.set_text_color(*(_rgb(it.color) if it.color else ink))
            s = _latin1(it.s)
            x = it.x
            if it.anchor in ("middle", "end"):
                w = pdf.get_string_width(s)
                x -= w / 2 if it.anchor == "middle" else w
            pdf.text(x, it.y, s)
    pdf.set_dash_pattern()


def to_pdf_document(drawings: list, path: str) -> str | None:
    """Render pages to a multi-page PDF (one A4 landscape page each). Returns the
    path, or ``None`` when fpdf2 is unavailable (the caller falls back to SVG-only)."""
    try:
        from fpdf import FPDF
    except Exception:  # noqa: BLE001 - optional dependency
        return None

    ink = (26, 29, 35)
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    for drawing in drawings or [Drawing(297, 210)]:
        pdf.add_page()
        _pdf_page(pdf, drawing, ink)
    pdf.output(path)
    return path


def to_pdf(drawing: Drawing, path: str) -> str | None:
    """Render a single drawing to a one-page PDF (wrapper over ``to_pdf_document``)."""
    return to_pdf_document([drawing], path)
