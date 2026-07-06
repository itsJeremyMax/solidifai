"""SVG + PDF backends."""

from solidifai_engine.drawing import backends
from solidifai_engine.drawing.model import Drawing, Line, Rect, Text


def _sample() -> Drawing:
    d = Drawing(297, 210)
    d.add(Rect(8, 8, 281, 194))
    d.add(Line(20, 20, 60, 20))
    d.add(Line(20, 30, 60, 30, dashed=True))
    d.add(Text(40, 18, "20.0", anchor="middle"))
    d.add(Text(12, 100, "widget", bold=True))
    return d


def test_svg_is_wellformed_and_has_content():
    svg = backends.to_svg(_sample())
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "20.0" in svg
    assert "widget" in svg
    assert "stroke-dasharray" in svg  # the dashed (hidden) line
    assert 'viewBox="0 0 297 210"' in svg


def test_svg_escapes_text():
    d = Drawing(10, 10)
    d.add(Text(0, 0, "a < b & c"))
    assert "&lt;" in backends.to_svg(d)
    assert "&amp;" in backends.to_svg(d)


def test_pdf_writes_a_real_pdf(tmp_path):
    path = str(tmp_path / "drawing.pdf")
    out = backends.to_pdf(_sample(), path)
    if out is None:
        import pytest

        pytest.skip("fpdf2 not installed; PDF backend unavailable")
    with open(out, "rb") as f:
        head = f.read(5)
    assert head.startswith(b"%PDF")


def test_mono_color_and_fill_render():
    d = Drawing(50, 50)
    d.add(Text(2, 2, "9.9", mono=True, color="#2b6cff"))
    d.add(Rect(0, 0, 5, 5, fill="#2b6cff"))
    svg = backends.to_svg(d)
    assert "monospace" in svg
    assert 'fill="#2b6cff"' in svg  # mono value color + filled rect
    assert "#2b6cff" in svg


def _two_pages():
    a = Drawing(297, 210)
    a.add(Rect(8, 8, 281, 194))
    a.add(Text(20, 20, "PAGE-A"))
    b = Drawing(297, 210)
    b.add(Rect(8, 8, 281, 194))
    b.add(Text(20, 20, "PAGE-B"))
    return [a, b]


def test_svg_document_stacks_pages():
    svg = backends.to_svg_document(_two_pages())
    assert svg.startswith("<svg")
    assert "PAGE-A" in svg and "PAGE-B" in svg
    # root height spans both sheets + the inter-page gap
    h = 2 * 210 + backends.PAGE_GAP
    assert f'height="{h}mm"' in svg


def test_pdf_document_has_two_pages(tmp_path):
    path = str(tmp_path / "doc.pdf")
    out = backends.to_pdf_document(_two_pages(), path)
    if out is None:
        import pytest

        pytest.skip("fpdf2 not installed")
    with open(out, "rb") as f:
        data = f.read()
    assert data.count(b"/Type /Page") >= 2 or data.count(b"/Type/Page") >= 2
