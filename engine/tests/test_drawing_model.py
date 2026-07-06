"""Drawing-model primitives."""

from solidifai_engine.drawing.model import Drawing, Line, Rect, Text


def test_drawing_collects_items_by_type():
    d = Drawing(297, 210)
    d.add(Line(0, 0, 10, 0))
    d.add(Line(0, 0, 0, 10, dashed=True))
    d.add(Text(5, 5, "W=20"))
    d.add(Rect(0, 0, 50, 30))
    assert len(d.items) == 4
    assert len(d.lines()) == 2
    assert d.texts()[0].s == "W=20"
    assert d.lines()[1].dashed is True
