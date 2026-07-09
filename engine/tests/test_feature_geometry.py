from build123d import Box, BuildPart, Hole, Locations

import solidifai
from solidifai import feature
from solidifai_engine import features


def _build_hole():
    solidifai.reset_registry()
    with BuildPart():
        Box(40, 40, 20)
        with feature("bore", driven_by="d"), Locations((0, 0)):
            Hole(radius=5)
    return solidifai._feature_registry()[0]


def test_summarize_returns_center_bbox_metrics():
    rec = _build_hole()
    s = features.summarize(rec.faces)
    assert s["center"] is not None and len(s["center"]) == 3
    assert s["bbox"] is not None and len(s["bbox"]) == 3
    assert s["metrics"]["faces"] >= 1
    assert any("CYLINDER" in g for g in s["metrics"]["geom_types"])


def test_summarize_empty_faces():
    assert features.summarize([]) == {"center": None, "bbox": None, "metrics": None}


def test_tessellate_produces_mesh():
    rec = _build_hole()
    verts, tris = features.tessellate(rec.faces, tol=0.5)
    assert len(verts) > 0 and len(tris) > 0
    assert all(len(v) == 3 for v in verts[:3])


def test_nearest_picks_feature_near_point():
    rec = _build_hole()
    feats = [rec]
    # Pick a point that is genuinely ON the captured geometry. The bore is a
    # radius-5 cylinder about the Z axis in a box centered at the origin, so a
    # tessellated vertex near (5, 0, z) exists. To be robust, grab a real vertex:
    verts, _ = features.tessellate(rec.faces, tol=0.5)
    on_surface = verts[0]
    hit = features.nearest(feats, on_surface, tol=2.0)
    assert hit is rec
    miss = features.nearest(feats, (1000.0, 1000.0, 1000.0), tol=2.0)
    assert miss is None


def test_infer_detects_cylindrical_feature_in_untagged_model():
    with BuildPart() as p:
        Box(40, 40, 20)
        with Locations((0, 0)):
            Hole(radius=5)
    recs = features.infer(p.part)
    assert recs, "expected at least one inferred feature for the hole"
    assert all(r.inferred is True for r in recs)
    assert all(r.confidence is not None for r in recs)
    assert all(r.driven_by == [] and r.source_line is None for r in recs)
    assert any(r.faces for r in recs)


def test_infer_empty_for_plain_box():
    with BuildPart() as p:
        Box(10, 10, 10)
    assert features.infer(p.part) == []


def test_infer_never_raises_on_bad_input():
    assert features.infer(None) == []


def test_infer_types_a_hole():
    with BuildPart() as p:
        Box(40, 40, 20)
        with Locations((0, 0)):
            Hole(radius=5)
    recs = [r for r in features.infer(p.part) if "CYLINDER" in str(r.faces[0].geom_type)]
    assert recs
    assert any(r.kind == "hole" for r in recs), [r.kind for r in recs]
    assert all(0.0 < r.confidence <= 1.0 for r in recs)


def test_infer_types_a_boss():
    from build123d import Box as _Box
    from build123d import Cylinder as _Cyl
    from build123d import Pos as _Pos

    part = _Box(40, 40, 10) + _Pos(0, 0, 9) * _Cyl(radius=6, height=8)
    recs = [r for r in features.infer(part) if "CYLINDER" in str(r.faces[0].geom_type)]
    assert recs
    assert any(r.kind == "boss" for r in recs), [r.kind for r in recs]


def test_infer_confidence_present_and_kind_in_vocab():
    with BuildPart() as p:
        Box(40, 40, 20)
        with Locations((0, 0)):
            Hole(radius=5)
    for r in features.infer(p.part):
        assert r.kind in ("hole", "boss", "cylindrical")
        assert isinstance(r.confidence, float)


def test_hole_feature_bbox_is_the_hole_not_the_whole_part():
    solidifai.reset_registry()
    with BuildPart():
        Box(90, 60, 8)
        with feature("central_bore", driven_by="bore_dia"), Locations((0, 0)):
            Hole(radius=13)
    rec = solidifai._feature_registry()[0]
    s = features.summarize(rec.faces)
    # the bore is ~26x26x8, NOT the 90x60 plate
    assert s["bbox"][0] < 40 and s["bbox"][1] < 40, s["bbox"]


def test_feature_at_resolves_a_point_on_the_bore_wall():
    solidifai.reset_registry()
    with BuildPart():
        Box(90, 60, 8)
        with feature("central_bore", driven_by="bore_dia"), Locations((0, 0)):
            Hole(radius=13)
    rec = solidifai._feature_registry()[0]
    # a point dead-on the cylinder wall, mid-height (NOT on a rim vertex)
    hit = features.nearest([rec], (13.0, 0.0, 0.0), tol=1.0)
    assert hit is rec, "a click on the bore wall must resolve the feature"
    # a point far out on the flat plate body must NOT resolve to the bore
    miss = features.nearest([rec], (40.0, 25.0, 4.0), tol=1.0)
    assert miss is None


def test_infer_ignores_fillets_on_plain_box():
    from build123d import Box, BuildPart, fillet

    with BuildPart() as p:
        Box(40, 40, 20)
        fillet(p.edges(), radius=3)
    recs = features.infer(p.part)
    # A plain filleted box has no holes or bosses -- every cylindrical face is a
    # blend and must not be mistaken for one.
    assert all(r.kind not in ("hole", "boss") for r in recs), [r.kind for r in recs]


def test_infer_finds_holes_despite_fillets():
    from build123d import Axis, Box, BuildPart, Hole, Locations, fillet

    with BuildPart() as p:
        Box(40, 40, 20)
        with Locations((0, 0)):
            Hole(radius=5)
        # Fillet only the vertical corner edges so the through-hole stays a full
        # cylinder (a mixed part: real hole + real fillets).
        fillet(p.edges().filter_by(Axis.Z), radius=3)
    recs = features.infer(p.part)
    assert any(r.kind == "hole" for r in recs), "the real hole must still be inferred"
    assert not any(r.kind == "boss" for r in recs), "fillets must not become phantom bosses"


def test_nearest_caches_tessellation(monkeypatch):
    rec = _build_hole()  # existing helper in this file
    calls = {"n": 0}
    real = features.tessellate

    def counting(faces, tol=features.TESS_TOLERANCE):
        calls["n"] += 1
        return real(faces, tol)

    monkeypatch.setattr(features, "tessellate", counting)
    features.nearest([rec], (1000, 1000, 1000))
    features.nearest([rec], (1000, 1000, 1000))
    assert calls["n"] == 1, calls["n"]
