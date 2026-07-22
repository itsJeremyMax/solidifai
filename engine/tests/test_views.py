import os

import pytest
from build123d import Box, Pos

from solidifai_engine import views
from solidifai_engine.session import Session, _srgb


def test_srgb_encode_lifts_linear_midtones():
    # base_color is linear; sRGB OETF brightens midtones for display so the
    # agent's render matches the color-managed viewport (not a darker version).
    assert _srgb(0.0) == 0.0
    assert abs(_srgb(1.0) - 1.0) < 1e-9
    assert 0.73 < _srgb(0.52) < 0.76  # PLA mid-gray (0.52 linear) -> ~0.748 display
    assert _srgb(0.5) > 0.5  # midtones always brighten under sRGB
    assert (
        abs(_srgb(0.001) - 12.92 * 0.001) < 1e-9
    )  # near-black uses the LINEAR segment, not the power curve


def test_fmt_mm_keeps_sub_mm_precision():
    # Regression: the view-grid dim label used :.0f, so a 1.6 mm washer was
    # captioned "2 mm" and misled both Sol and the eval VLM judge.
    assert views._fmt_mm(1.6) == "1.6"
    assert views._fmt_mm(16.0) == "16"
    assert views._fmt_mm(0.0) == "0"
    assert views._fmt_mm(123.45) == "123.5"  # 0.1 mm label resolution


def _mesh():
    """A known 40 x 24 x 16 mm box tessellated to (vertices, triangles)."""
    verts, tris = Box(40, 24, 16).tessellate(0.1)
    return [tuple(v) for v in verts], tris


def _offscreen_or_skip():
    """Skip the test if offscreen GL cannot initialize (headless CI)."""
    try:
        import vtkmodules.all as vtk

        win = vtk.vtkRenderWindow()
        win.SetOffScreenRendering(1)
        win.AddRenderer(vtk.vtkRenderer())
        win.SetSize(64, 64)
        win.Render()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"offscreen GL unavailable: {exc}")


def test_render_named_views_writes_pngs(tmp_path):
    _offscreen_or_skip()
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    result = views.render_views(verts, tris, out, ["iso", "front", "top"])

    assert [r["name"] for r in result] == ["iso", "front", "top"]
    for r in result:
        assert os.path.basename(r["path"]) == f"{r['name']}.png"
        assert os.path.getsize(r["path"]) > 2000  # non-trivial render
        assert r["width"] == views.VIEW_SIZE
        assert r["height"] == views.VIEW_SIZE


def test_unknown_view_raises_with_valid_list(tmp_path):
    # Validation happens before any GL work, so this needs no offscreen guard.
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    with pytest.raises(ValueError) as exc:
        views.render_views(verts, tris, out, ["front", "sideways"])
    msg = str(exc.value)
    assert "sideways" in msg
    assert "front" in msg  # the valid vocabulary is listed
    # "render nothing on any bad spec": no PNG for the valid one either
    assert not os.path.exists(os.path.join(out, "front.png"))


def test_custom_angle_view_renders(tmp_path):
    _offscreen_or_skip()
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    result = views.render_views(verts, tris, out, ["az30_el20", "az-90_el0"])
    names = [r["name"] for r in result]
    assert names == ["az30_el20", "az-90_el0"]
    for r in result:
        assert os.path.exists(r["path"])
        assert os.path.getsize(r["path"]) > 2000


def test_malformed_custom_angle_is_rejected(tmp_path):
    # Validation precedes GL work, so no offscreen guard needed.
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    with pytest.raises(ValueError):
        views.render_views(verts, tris, out, ["az_el"])  # no numbers


def _session_with_box(tmp_path):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    sess = Session(artifacts)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(40, 24, 16), name='B')\n"
    )
    return sess


def test_capture_views_grid_writes_single_sheet(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_box(tmp_path)
    res = sess.capture_views(["iso", "front", "top"], layout="grid")
    assert res["ok"] is True
    assert res["layout"] == "grid"
    assert len(res["views"]) == 1
    sheet = res["views"][0]
    assert sheet["name"] == "contact_sheet"
    assert os.path.basename(sheet["path"]) == "contact_sheet.png"
    from PIL import Image

    with Image.open(sheet["path"]) as im:
        # 3 views -> cols = 2, rows = 2 -> bigger than a single tile each way
        assert im.width >= 2 * 256 and im.height >= 2 * 256


def test_capture_views_invalid_layout_errors(tmp_path):
    # No GL needed: layout is validated before any render.
    sess = _session_with_box(tmp_path)
    res = sess.capture_views(["iso"], layout="sideways")
    assert res["ok"] is False
    assert "layout" in res["error"]


def test_capture_views_separate_still_default(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_box(tmp_path)
    res = sess.capture_views(["iso", "front"])
    assert res["ok"] is True
    assert res["layout"] == "separate"
    assert [v["name"] for v in res["views"]] == ["iso", "front"]


def _count_colors(path):
    """(reddish, bluish) saturated-pixel counts in a render. The dark gray
    background and black edges are neither, so nonzero counts mean a part of
    that hue actually rendered. The axes-triad inset (bottom-right 22 % of
    the viewport) is excluded so its red X-axis does not contaminate the
    count."""
    from PIL import Image

    red = blue = 0
    with Image.open(path) as im:
        px = im.convert("RGB").load()
        w, h = im.size
        inset_x = int(w * 0.78)
        # Inset viewport is VTK (0.78,0.0,1.0,0.22) = bottom-right, y-up; PIL y is
        # top-down, so the inset's bottom band maps to PIL y >= h*0.78.
        inset_y = int(h * 0.78)
        for y in range(0, h, 3):
            for x in range(0, w, 3):
                if x >= inset_x and y >= inset_y:
                    continue  # skip the axes-triad inset corner
                r, g, b = px[x, y]
                if r > 110 and r - g > 45 and r - b > 45:
                    red += 1
                elif b > 110 and b - g > 45 and b - r > 45:
                    blue += 1
    return red, blue


def test_render_views_groups_paint_color(tmp_path):
    _offscreen_or_skip()
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    # One group covering the whole mesh, painted red. The union (verts/tris) is
    # still passed for edges + bounds.
    result = views.render_views(verts, tris, out, ["iso"], groups=[(verts, tris, (0.9, 0.1, 0.1))])
    red, _ = _count_colors(result[0]["path"])
    assert red > 50, f"red group color did not reach the render (got {red})"


def test_render_views_without_groups_is_gray(tmp_path):
    _offscreen_or_skip()
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    result = views.render_views(verts, tris, out, ["iso"])  # groups=None -> clay
    red, blue = _count_colors(result[0]["path"])
    assert red == 0 and blue == 0, "clay render should have no saturated color"


def _session_with_two_colors(tmp_path):
    """A session whose model is a red box and a blue box, 40 mm apart."""
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    sess = Session(artifacts)
    sess.execute_script(
        "from build123d import Box, Pos\n"
        "from solidifai import show\n"
        "show(Box(20, 20, 20), name='R', color=(0.9, 0.05, 0.05))\n"
        "show(Pos(40, 0, 0) * Box(20, 20, 20), name='B', color=(0.05, 0.05, 0.9))\n"
    )
    return sess


def _session_with_highlightable_feature(tmp_path):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    sess = Session(artifacts)
    sess.execute_script(
        "from build123d import Align, BuildPart, Box, Pos\n"
        "from solidifai import feature, show\n"
        "with BuildPart() as p:\n"
        "    Box(40, 40, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "    with feature('boss'):\n"
        "        Pos(0, 0, 8) * Box(12, 12, 6, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
        "show(p.part, name='Plate')\n"
    )
    return sess


def test_capture_views_defaults_to_color(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_two_colors(tmp_path)
    res = sess.capture_views(["iso"])  # no color arg -> colored by default
    assert res["ok"] is True
    red, blue = _count_colors(res["views"][0]["path"])
    assert red > 20 and blue > 20, "both part colors should be visible by default"


def test_capture_views_color_false_is_clay(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_two_colors(tmp_path)
    res = sess.capture_views(["iso"], color=False)
    assert res["ok"] is True
    red, blue = _count_colors(res["views"][0]["path"])
    assert red == 0 and blue == 0, "color=False should render uniform clay gray"


def test_capture_views_feature_highlight_request_renders_successfully(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_highlightable_feature(tmp_path)

    highlighted = sess.capture_views(["top"], color=False, resolution=1024, highlight=["boss"])

    assert highlighted["ok"] is True
    assert os.path.exists(highlighted["views"][0]["path"])


def test_capture_views_color_survives_registry_reset(tmp_path):
    # Colors must come from the per-object snapshot, not the live registry that a
    # later (or failed) build may have reset.
    _offscreen_or_skip()
    import solidifai

    sess = _session_with_two_colors(tmp_path)
    solidifai.reset_registry()  # simulate a subsequent build clearing the registry
    res = sess.capture_views(["iso"], color=True)
    assert res["ok"] is True
    red, blue = _count_colors(res["views"][0]["path"])
    assert red > 20 and blue > 20, "snapshot, not live registry, must drive color"


def test_render_views_highlight_mesh_writes_png(tmp_path):
    """highlight_mesh adds an orange accent actor that actually reaches the
    framebuffer. Asserts a PNG is produced AND that the accent color shows up:
    HIGHLIGHT_COLOR (1.0, 0.55, 0.0) is predominantly red, so it registers as
    "reddish" in _count_colors. A differential check (same base mesh with vs.
    without the highlight) makes the assertion unambiguous — the clay base mesh
    on its own has no saturated color."""
    _offscreen_or_skip()
    verts, tris = _mesh()
    # A highlight sub-mesh that protrudes above the base mesh's top face (z=8)
    # so the accent actor is plainly visible (not occluded) from the iso camera.
    hverts, htris = (Pos(0, 0, 12) * Box(12, 12, 16)).tessellate(0.1)
    highlight_mesh = ([tuple(v) for v in hverts], htris)

    with_dir = str(tmp_path / "with")
    without_dir = str(tmp_path / "without")
    os.makedirs(with_dir, exist_ok=True)
    os.makedirs(without_dir, exist_ok=True)

    res_with = views.render_views(verts, tris, with_dir, ["iso"], highlight_mesh=highlight_mesh)
    res_without = views.render_views(verts, tris, without_dir, ["iso"])

    assert len(res_with) == 1
    assert os.path.exists(res_with[0]["path"])
    assert os.path.getsize(res_with[0]["path"]) > 2000

    red_with, _ = _count_colors(res_with[0]["path"])
    red_without, _ = _count_colors(res_without[0]["path"])
    # The clay base mesh has no saturated color; the orange accent adds reddish
    # pixels in non-trivial quantity.
    assert red_without == 0, "clay base mesh should have no saturated color"
    assert red_with > 50, f"orange highlight accent did not reach the render (got {red_with})"
    assert red_with > red_without, "highlight must add reddish/orange pixels"


def test_render_views_size_param_sets_png_dimensions(tmp_path):
    _offscreen_or_skip()
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    result = views.render_views(verts, tris, out, ["iso"], size=1024)
    assert result[0]["width"] == 1024 and result[0]["height"] == 1024
    from PIL import Image

    with Image.open(result[0]["path"]) as im:
        assert im.size == (1024, 1024)


def test_render_views_default_size_unchanged(tmp_path):
    # Byte-stability anchor: no size arg -> exactly VIEW_SIZE (512) pixels.
    _offscreen_or_skip()
    out = str(tmp_path / "out")
    os.makedirs(out, exist_ok=True)
    verts, tris = _mesh()
    result = views.render_views(verts, tris, out, ["iso"])
    from PIL import Image

    with Image.open(result[0]["path"]) as im:
        assert im.size == (views.VIEW_SIZE, views.VIEW_SIZE)


def test_capture_views_resolution_renders_bigger_png(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_box(tmp_path)
    res = sess.capture_views(["iso"], resolution=1024)
    assert res["ok"] is True
    from PIL import Image

    with Image.open(res["views"][0]["path"]) as im:
        assert im.size == (1024, 1024)


def test_capture_views_resolution_bounds_validated(tmp_path):
    # No GL needed: validation precedes any render.
    sess = _session_with_box(tmp_path)
    for bad in (100, 4096, "big"):
        res = sess.capture_views(["iso"], resolution=bad)
        assert res["ok"] is False
        assert "resolution" in res["error"] and "256" in res["error"] and "2048" in res["error"]


def test_capture_views_grid_tiles_scale_with_resolution(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_box(tmp_path)
    res = sess.capture_views(["iso", "front", "top"], layout="grid", resolution=1024)
    assert res["ok"] is True
    from PIL import Image

    with Image.open(res["views"][0]["path"]) as im:
        # 3 views -> 2x2 grid of 512-px tiles (resolution // 2), not 256-px tiles.
        assert im.width >= 2 * 512 and im.height >= 2 * 512


def _count_cap(path):
    """Magenta (CAP_COLOR) pixel count: red AND blue both high, green low.
    Disjoint from _count_colors' red/blue buckets, so caps never alias with
    material colors or the orange highlight in any test."""
    from PIL import Image

    n = 0
    with Image.open(path) as im:
        px = im.convert("RGB").load()
        w, h = im.size
        inset_x, inset_y = int(w * 0.78), int(h * 0.78)
        for y in range(0, h, 3):
            for x in range(0, w, 3):
                if x >= inset_x and y >= inset_y:
                    continue  # skip the axes-triad inset
                r, g, b = px[x, y]
                if r > 110 and b > 110 and r - g > 45 and b - g > 45:
                    n += 1
    return n


def test_render_views_cap_mesh_paints_cap_color(tmp_path):
    _offscreen_or_skip()
    verts, tris = _mesh()
    # A cap slab floating above the box top face (z=8) so it is plainly visible.
    cverts, ctris = (Pos(0, 0, 12) * Box(20, 12, 1)).tessellate(0.1)
    cap_mesh = ([tuple(v) for v in cverts], ctris)

    with_dir, without_dir = str(tmp_path / "with"), str(tmp_path / "without")
    os.makedirs(with_dir, exist_ok=True)
    os.makedirs(without_dir, exist_ok=True)
    res_with = views.render_views(verts, tris, with_dir, ["iso"], cap_mesh=cap_mesh)
    res_without = views.render_views(verts, tris, without_dir, ["iso"])

    assert _count_cap(res_without[0]["path"]) == 0, "clay render must have no cap color"
    assert _count_cap(res_with[0]["path"]) > 50, "cap mesh did not reach the render"


def test_cap_color_is_distinct_from_highlight():
    # The cap must never be confusable with the orange feature highlight.
    assert views.CAP_COLOR != views.HIGHLIGHT_COLOR
    r, g, b = views.CAP_COLOR
    assert r > 0.7 and b > 0.5 and g < 0.4  # magenta family


SHELL_SCRIPT = (
    "from build123d import Box\n"
    "from solidifai import show\n"
    "show(Box(40, 40, 20) - Box(34, 34, 14), name='Shell')\n"
)


def _session_with_shell(tmp_path):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    sess = Session(artifacts)
    assert sess.execute_script(SHELL_SCRIPT)["ok"] is True
    return sess


def test_capture_views_section_shows_magenta_caps(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_shell(tmp_path)
    res = sess.capture_views(["top"], section={"axis": "z", "offset_mm": 0.0}, color=False)
    assert res["ok"] is True
    assert _count_cap(res["views"][0]["path"]) > 50, "cut cross-section must render magenta"
    # And the model itself is untouched (boolean ran on copies).
    assert sess._model.volume == pytest.approx(40 * 40 * 20 - 34 * 34 * 14, rel=1e-6)


def test_capture_views_section_default_views_face_plus_iso(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_shell(tmp_path)
    res = sess.capture_views(section={"axis": "z", "offset_mm": 0.0})
    assert res["ok"] is True
    assert [v["name"] for v in res["views"]] == ["top", "iso"]


def test_capture_views_section_validation_errors(tmp_path):
    # No GL: every one of these is rejected before any render.
    sess = _session_with_shell(tmp_path)
    res = sess.capture_views(["iso"], section={"axis": "w", "offset_mm": 0})
    assert res["ok"] is False and "axis" in res["error"]
    res = sess.capture_views(["iso"], section={"axis": "z"})
    assert res["ok"] is False and "offset_mm" in res["error"]
    res = sess.capture_views(["iso"], section="z=0")
    assert res["ok"] is False and "section" in res["error"]
    res = sess.capture_views(["iso"], section={"axis": "z", "offset_mm": 99.0})
    assert res["ok"] is False and "99" in res["error"]
    res = sess.capture_views(["iso"], section={"axis": "z", "offset_mm": 0}, explode=40)
    assert res["ok"] is False and "explode" in res["error"]


def test_capture_views_section_times_out_cleanly(tmp_path, monkeypatch):
    # The boolean runs on a worker with a hard timeout; a hung OCC op must
    # surface as an error envelope, never a hung engine.
    import time as _time

    import solidifai_engine.session as session_mod

    sess = _session_with_shell(tmp_path)
    monkeypatch.setattr(session_mod, "SECTION_TIMEOUT_S", 0.05)
    monkeypatch.setattr(session_mod.section_mod, "cut_with_caps", lambda *a: _time.sleep(1.0))
    res = sess.capture_views(["iso"], section={"axis": "z", "offset_mm": 0.0})
    assert res["ok"] is False
    assert "timed out" in res["error"]


def test_capture_views_section_colored_assembly(tmp_path):
    # Per-object color groups survive sectioning (cut per object, same colors).
    # View must be "iso", not a side view: the z-cut caps are horizontal, so a
    # front view sees them edge-on (zero cap pixels) while iso sees caps AND sides.
    _offscreen_or_skip()
    sess = _session_with_two_colors(tmp_path)
    res = sess.capture_views(["iso"], section={"axis": "z", "offset_mm": 0.0})
    assert res["ok"] is True
    red, blue = _count_colors(res["views"][0]["path"])
    assert red > 10 and blue > 10, "both part colors must survive the section render"
    assert _count_cap(res["views"][0]["path"]) > 20, "caps must render on a colored capture"


def test_focus_camera_margin_math():
    # Pure math, no GL: the focus bbox's bounding sphere must subtend the view
    # angle shrunk by the 15% margin, i.e. fill ~87% of the half-frame.
    import math

    bounds = (40.0, -5.0, -5.0, 50.0, 5.0, 5.0)  # 10 mm cube at x=45
    focal, pos = views._focus_camera(bounds, (1, -1, 1))
    assert focal == (45.0, 0.0, 0.0)
    r = math.dist(bounds[:3], bounds[3:]) / 2
    d = math.dist(focal, pos)
    subtended = math.degrees(math.asin(r / d))
    expected = (30.0 / 2) / (1 + views.FOCUS_MARGIN)  # 15 deg / 1.15 ~= 13.04 deg
    assert abs(subtended - expected) < 0.1


def test_focus_camera_degenerate_bounds_do_not_crash():
    focal, pos = views._focus_camera((1.0, 2.0, 3.0, 1.0, 2.0, 3.0), (0, 0, 1))
    assert focal == (1.0, 2.0, 3.0)
    assert pos[2] > 3.0  # nonzero standoff even for a point target


def test_render_views_focus_fills_frame(tmp_path):
    # Differential pixel test: a small red cube next to a big clay box covers
    # far more of the frame when focused than in the default full-model frame.
    _offscreen_or_skip()
    verts, tris = (Box(60, 60, 60)).tessellate(0.1)
    verts = [tuple(v) for v in verts]
    sverts, stris = (Pos(45, 0, 0) * Box(6, 6, 6)).tessellate(0.1)
    small = ([tuple(v) for v in sverts], stris)
    # Merge into one mesh; color the small cube red via groups.
    base = len(verts)
    allverts = verts + small[0]
    alltris = list(tris) + [(a + base, b + base, c + base) for (a, b, c) in small[1]]
    groups = [(verts, tris, (0.7, 0.7, 0.72)), (small[0], small[1], (0.9, 0.05, 0.05))]

    fdir, ndir = str(tmp_path / "f"), str(tmp_path / "n")
    os.makedirs(fdir, exist_ok=True)
    os.makedirs(ndir, exist_ok=True)
    focused = views.render_views(
        allverts,
        alltris,
        fdir,
        ["iso"],
        groups=groups,
        focus_bounds=(42, -3, -3, 48, 3, 3),
        focus_label="knob",
    )
    normal = views.render_views(allverts, alltris, ndir, ["iso"], groups=groups)

    red_f, _ = _count_colors(focused[0]["path"])
    red_n, _ = _count_colors(normal[0]["path"])
    assert red_f > 200, f"focused target should dominate the frame (got {red_f})"
    assert red_f > 3 * max(red_n, 1), "focus must enlarge the target substantially"


FOCUS_FEATURE_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

with BuildPart() as p:
    Box(60, 40, 8)
    with feature("corner_hole", driven_by="bore"):
        with Locations((22, 12)):
            Hole(radius=3)

show(p.part, name="Plate")
"""


def test_capture_views_focus_by_feature_name(tmp_path):
    _offscreen_or_skip()
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    sess = Session(artifacts)
    assert sess.execute_script(FOCUS_FEATURE_SCRIPT)["ok"] is True
    res = sess.capture_views(["top"], focus="corner_hole", resolution=1024)
    assert res["ok"] is True
    assert res["views"][0]["width"] == 1024  # close-ups pair with hi-res
    assert os.path.getsize(res["views"][0]["path"]) > 2000


def test_capture_views_focus_unknown_feature_lists_valid(tmp_path):
    # No GL: validation precedes any render.
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    sess = Session(artifacts)
    assert sess.execute_script(FOCUS_FEATURE_SCRIPT)["ok"] is True
    res = sess.capture_views(["top"], focus="nope")
    assert res["ok"] is False
    assert "nope" in res["error"] and "corner_hole" in res["error"]


def test_capture_views_focus_region_validated(tmp_path):
    sess = _session_with_box(tmp_path)
    res = sess.capture_views(["iso"], focus=[0, 0, 0])  # not 6 numbers
    assert res["ok"] is False and "xmin" in res["error"]
    res = sess.capture_views(["iso"], focus=[10, 0, 0, 0, 5, 5])  # min > max
    assert res["ok"] is False and "xmin" in res["error"]


def test_capture_views_focus_region_renders(tmp_path):
    _offscreen_or_skip()
    sess = _session_with_two_colors(tmp_path)  # red box at origin, blue at x=40
    # View from front-top-LEFT so the blue box (at +x) cannot sit between the
    # camera and the focused red box and shave the count.
    res = sess.capture_views(["front-top-left"], focus=[-10, -10, -10, 10, 10, 10])
    assert res["ok"] is True
    red, blue = _count_colors(res["views"][0]["path"])
    assert red > 200, "the focused red box should dominate the frame"
