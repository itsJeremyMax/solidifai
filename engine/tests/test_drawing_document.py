"""Multi-page document composition: assembly page + per-part detail sheets."""

from build123d import Box, Compound

from solidifai_engine.drawing import sheet


def _group(shape, name, qty):
    bb = shape.bounding_box().size
    return {
        "name": name,
        "qty": qty,
        "shape": shape,
        "spec": {
            "bbox": (round(bb.X, 1), round(bb.Y, 1), round(bb.Z, 1)),
            "name": name,
            "qty": qty,
            "mass_g": 1.0,
            "holes": [],
            "units": "mm",
            "generated_at": "2026-06-07",
            "material": "PLA",
            "process": "FDM",
        },
    }


_ASM_SPEC = {
    "bbox": (40.0, 20.0, 8.0),
    "name": "thing",
    "material": "PLA",
    "process": "FDM",
    "mass_g": 6.0,
    "volume_cm3": 6.0,
    "part_count": 3,
    "bom": [{"name": "Foot", "qty": 2, "mass_g": 1.0}, {"name": "Base", "qty": 1, "mass_g": 4.0}],
    "holes": {},
    "dfm_summary": "No issues",
    "units": "mm",
    "generated_at": "2026-06-07",
}


def test_document_is_assembly_plus_one_page_per_group():
    groups = [_group(Box(8, 4, 2), "Foot", 2), _group(Box(40, 20, 5), "Base", 1)]
    compound = Compound(children=[Box(8, 4, 2), Box(40, 20, 5)])
    pages, meta = sheet.compose_document(groups, compound, _ASM_SPEC, {})
    assert len(pages) == 1 + 2  # assembly + 2 unique parts
    assert meta["scaleLabel"]


def test_single_instance_is_one_page():
    groups = [_group(Box(8, 4, 2), "Solo", 1)]
    one = dict(_ASM_SPEC, part_count=1, bom=[{"name": "Solo", "qty": 1, "mass_g": 1.0}])
    pages, meta = sheet.compose_document(groups, Box(8, 4, 2), one, {})
    assert len(pages) == 1
