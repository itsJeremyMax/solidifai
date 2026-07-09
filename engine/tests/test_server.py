import json
import os
import socket
import stat
import threading
import time

from sockpath import short_socket_path

from solidifai_engine.server import Server

GOOD_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

with BuildPart() as p:
    Box(20, 20, 20)

show(p.part, name="C")
"""

PARAM_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {"size": {"value": 10, "min": 2, "max": 40, "step": 1, "unit": "mm"}}

def build(size):
    with BuildPart() as p:
        Box(size, size, size)
    show(p.part, name="Cube")
"""

FEATURE_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

with BuildPart() as p:
    Box(40, 40, 12)
    with feature("center_hole", driven_by="bore"):
        with Locations((0, 0)):
            Hole(radius=6)

show(p.part, name="Plate")
"""

OVERLAP_SCRIPT = """
from build123d import Box, Pos
from solidifai import show

show(Box(10, 10, 10), name="A")
show(Pos(5, 0, 0) * Box(10, 10, 10), name="B")
"""

# Raises at line 5 of the script (the leading newline makes the raise line 5).
BAD_SCRIPT = """
from build123d import Box
from solidifai import show

raise ValueError("boom in the script")
"""


def _send(sock_path, request):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(sock_path)
    c.sendall((json.dumps(request) + "\n").encode("utf-8"))
    buf = b""
    while b"\n" not in buf:
        chunk = c.recv(4096)
        if not chunk:
            break
        buf += chunk
    c.close()
    return json.loads(buf.decode("utf-8").splitlines()[0])


def _start(tmp_path):
    sock_path = short_socket_path(tmp_path)
    artifacts = str(tmp_path / "artifacts")
    os.makedirs(artifacts, exist_ok=True)
    server = Server(sock_path, artifacts)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Wait until the server is actually ACCEPTING connections — not merely until the
    # socket file exists. bind() creates the file before the accept loop is ready, so
    # a file-exists check races (intermittent ConnectionRefused) once the suite is
    # heavy enough to slow the server thread's startup.
    deadline = time.time() + 5.0
    while time.time() < deadline:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(sock_path)
            probe.close()
            break
        except OSError:
            probe.close()
            time.sleep(0.02)
    return server, sock_path, artifacts


def test_ping(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        resp = _send(sock_path, {"id": 1, "method": "ping"})
        assert resp == {"id": 1, "ok": True, "result": "pong"}
    finally:
        server.shutdown()


def test_socket_is_owner_only(tmp_path):
    """The engine socket is owner-only (0o600): the app and engine run as the
    same user, so no other local account should be able to drive execute_script."""
    server, sock_path, _ = _start(tmp_path)
    try:
        mode = stat.S_IMODE(os.stat(sock_path).st_mode)
        assert mode == 0o600, f"socket mode {oct(mode)} is not 0o600"
    finally:
        server.shutdown()


def test_execute_script_writes_artifacts(tmp_path):
    server, sock_path, artifacts = _start(tmp_path)
    try:
        resp = _send(
            sock_path,
            {"id": 2, "method": "execute_script", "params": {"code": GOOD_SCRIPT}},
        )
        assert resp["id"] == 2
        assert resp["ok"] is True
        assert resp["result"]["buildId"] == 1
        assert os.path.exists(os.path.join(artifacts, "model.glb"))
        assert os.path.exists(os.path.join(artifacts, "model.json"))
    finally:
        server.shutdown()


def test_multiple_sequential_connections(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        r1 = _send(sock_path, {"id": 1, "method": "ping"})
        r2 = _send(sock_path, {"id": 2, "method": "ping"})
        assert r1["result"] == "pong"
        assert r2["result"] == "pong"
    finally:
        server.shutdown()


def test_unknown_method_returns_error(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        resp = _send(sock_path, {"id": 9, "method": "nope"})
        assert resp["id"] == 9
        assert resp["ok"] is False
        assert "error" in resp
    finally:
        server.shutdown()


def test_check_interferences_over_socket(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        r1 = _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": OVERLAP_SCRIPT}},
        )
        assert r1["ok"] is True
        r2 = _send(sock_path, {"id": 2, "method": "check_interferences"})
        assert r2["id"] == 2
        assert r2["ok"] is True
        assert r2["result"]["summary"]["overlaps"] == 1
    finally:
        server.shutdown()


def test_set_params_over_socket_bumps_build(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        r1 = _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": PARAM_SCRIPT}},
        )
        assert r1["ok"] is True
        assert r1["result"]["buildId"] == 1

        r2 = _send(
            sock_path,
            {"id": 2, "method": "set_params", "params": {"values": {"size": 20}}},
        )
        assert r2["ok"] is True
        assert r2["result"]["buildId"] == 2

        info = _send(sock_path, {"id": 3, "method": "get_model_info"})
        assert info["ok"] is True
        assert abs(info["result"]["bbox"]["size"][0] - 20) < 1e-4
    finally:
        server.shutdown()


def test_set_params_missing_values_returns_clean_error(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": PARAM_SCRIPT}},
        )
        resp = _send(sock_path, {"id": 2, "method": "set_params", "params": {}})
        assert resp["id"] == 2
        assert resp["ok"] is False
        assert "missing param 'values'" in resp["error"]
    finally:
        server.shutdown()


def test_export_over_socket_writes_file(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": GOOD_SCRIPT}},
        )
        out = str(tmp_path / "out.step")
        resp = _send(
            sock_path,
            {"id": 2, "method": "export", "params": {"format": "step", "path": out}},
        )
        assert resp["ok"] is True
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0
    finally:
        server.shutdown()


def test_export_without_path_defaults_into_scratch(tmp_path):
    # No model_path here, so the scratch dir is <artifacts parent>/tmp and the
    # slug falls back to "model".
    server, sock_path, artifacts = _start(tmp_path)
    try:
        _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": GOOD_SCRIPT}},
        )
        resp = _send(
            sock_path,
            {"id": 2, "method": "export", "params": {"format": "step"}},
        )
        assert resp["id"] == 2
        assert resp["ok"] is True
        assert resp["result"]["path"].endswith(os.path.join("tmp", "exports", "model.step"))
        assert os.path.exists(resp["result"]["path"])
    finally:
        server.shutdown()


def test_capture_views_over_socket_returns_paths(tmp_path):
    import sys

    import pytest

    # This test drives the engine through its socket, so the render runs in the
    # server's background thread. On macOS, Cocoa/OpenGL must initialize on the
    # main thread, so an off-main-thread offscreen render hard-crashes the
    # process. In production the engine's serve_forever runs on the subprocess
    # MAIN thread (see __main__.py), so this is purely a test-harness limitation;
    # the render path itself is covered on the main thread by test_views.py.
    if sys.platform == "darwin":
        pytest.skip("offscreen GL can't init off-main-thread on macOS (test harness only)")
    # Probe offscreen GL up front and skip cleanly if unavailable (headless CI).
    try:
        import vtkmodules.all as vtk

        w = vtk.vtkRenderWindow()
        w.SetOffScreenRendering(1)
        w.AddRenderer(vtk.vtkRenderer())
        w.SetSize(64, 64)
        w.Render()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"offscreen GL unavailable: {exc}")

    server, sock_path, artifacts = _start(tmp_path)
    try:
        _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": GOOD_SCRIPT}},
        )
        resp = _send(
            sock_path,
            {"id": 2, "method": "capture_views", "params": {"views": ["iso", "top"]}},
        )
        assert resp["ok"] is True
        assert resp["result"]["buildId"] == 1
        got = resp["result"]["views"]
        assert [v["name"] for v in got] == ["iso", "top"]
        for v in got:
            assert os.path.exists(v["path"])
            assert os.path.join("tmp", "views", "1") in v["path"]
    finally:
        server.shutdown()


def test_capture_views_no_model_returns_error(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        resp = _send(sock_path, {"id": 1, "method": "capture_views", "params": {}})
        assert resp["ok"] is False
        assert "no model" in resp["error"]
    finally:
        server.shutdown()


def test_capture_views_unknown_view_returns_valid_list(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": GOOD_SCRIPT}},
        )
        resp = _send(
            sock_path,
            {"id": 2, "method": "capture_views", "params": {"views": ["nope"]}},
        )
        assert resp["ok"] is False
        assert "nope" in resp["error"]
        assert "iso" in resp["error"]  # the valid vocabulary is offered
    finally:
        server.shutdown()


def test_startup_loads_existing_model(tmp_path):
    # A workspace model file already on disk is loaded on startup, so export
    # and get_model_info work immediately (no prior execute_script needed).
    model_path = tmp_path / "model.py"
    model_path.write_text(GOOD_SCRIPT)
    sock_path = short_socket_path(tmp_path)
    artifacts = str(tmp_path / "artifacts")
    os.makedirs(artifacts, exist_ok=True)

    server = Server(sock_path, artifacts, model_path=str(model_path))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        for _ in range(200):
            if os.path.exists(sock_path):
                break
            time.sleep(0.01)

        info = _send(sock_path, {"id": 1, "method": "get_model_info"})
        assert info["ok"] is True
        assert info["result"]["buildId"] == 1
        assert abs(info["result"]["bbox"]["size"][0] - 20) < 1e-4

        out = str(tmp_path / "out.step")
        resp = _send(
            sock_path,
            {"id": 2, "method": "export", "params": {"format": "step", "path": out}},
        )
        assert resp["ok"] is True
        assert os.path.exists(out)
    finally:
        server.shutdown()


def test_inspect_features_over_socket(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        r1 = _send(
            sock_path,
            {"id": 1, "method": "execute_script", "params": {"code": FEATURE_SCRIPT}},
        )
        assert r1["ok"] is True
        resp = _send(sock_path, {"id": 2, "method": "inspect_features"})
        assert resp["ok"] is True
        feats = resp["result"]["features"]
        assert [f["name"] for f in feats] == ["center_hole"]
        assert feats[0]["driven_by"] == ["bore"]
        assert isinstance(feats[0]["source"]["line"], int)
        assert feats[0]["source"]["line"] > 0
    finally:
        server.shutdown()


def test_feature_at_over_socket(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        r1 = _send(
            sock_path, {"id": 1, "method": "execute_script", "params": {"code": FEATURE_SCRIPT}}
        )
        assert r1["ok"] is True
        miss = _send(
            sock_path, {"id": 2, "method": "feature_at", "params": {"point": [1e4, 1e4, 1e4]}}
        )
        assert miss["ok"] is True
        assert miss["result"]["match"] is None
    finally:
        server.shutdown()


def test_startup_with_missing_model_does_not_crash(tmp_path):
    # No model file on disk -> server starts fine and responds to ping.
    sock_path = short_socket_path(tmp_path)
    artifacts = str(tmp_path / "artifacts")
    os.makedirs(artifacts, exist_ok=True)

    server = Server(sock_path, artifacts, model_path=str(tmp_path / "absent.py"))
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        for _ in range(200):
            if os.path.exists(sock_path):
                break
            time.sleep(0.01)
        resp = _send(sock_path, {"id": 1, "method": "ping"})
        assert resp == {"id": 1, "ok": True, "result": "pong"}
    finally:
        server.shutdown()


def test_set_feature_over_socket(tmp_path):
    server, sock_path, _ = _start(tmp_path)
    try:
        r1 = _send(
            sock_path, {"id": 1, "method": "execute_script", "params": {"code": PARAM_SCRIPT}}
        )
        assert r1["ok"] is True
        res = _send(
            sock_path,
            {"id": 2, "method": "set_feature", "params": {"name": "x", "values": {"size": 20}}},
        )
        assert res["ok"] is False
        assert "x" in res["error"]
    finally:
        server.shutdown()


def test_failed_script_returns_line_and_trimmed_traceback(tmp_path):
    """A failing execute_script surfaces the user-script line and a traceback
    trimmed to the user's frames, not just a one-line error."""
    server, sock_path, _ = _start(tmp_path)
    try:
        resp = _send(
            sock_path,
            {"id": 3, "method": "execute_script", "params": {"code": BAD_SCRIPT}},
        )
        assert resp["ok"] is False
        assert "ValueError" in resp["error"]
        # The deepest user-script frame is the raise on line 5.
        assert resp["scriptLine"] == 5
        tb = resp["traceback"]
        assert "<solidifai-script>" in tb
        assert "ValueError: boom in the script" in tb
        # Engine internals are trimmed away.
        assert "session.py" not in tb
    finally:
        server.shutdown()


def test_script_line_extracts_deepest_user_frame():
    from solidifai_engine.server import _script_line

    tb = (
        "Traceback (most recent call last):\n"
        '  File "/x/solidifai_engine/session.py", line 247, in execute_script\n'
        "    exec(compiled, ns)\n"
        '  File "<solidifai-script>", line 12, in <module>\n'
        "    build()\n"
        '  File "<solidifai-script>", line 30, in build\n'
        "    raise ValueError('x')\n"
        "ValueError: x\n"
    )
    assert _script_line(tb) == 30
    assert _script_line("no frames here") is None
    assert _script_line(None) is None


def test_trim_traceback_drops_internal_frames_keeps_user():
    from solidifai_engine.server import _trim_traceback

    tb = (
        "Traceback (most recent call last):\n"
        '  File "/x/solidifai_engine/session.py", line 247, in execute_script\n'
        "    exec(compiled, ns)\n"
        '  File "<solidifai-script>", line 12, in <module>\n'
        "    raise ValueError('x')\n"
        "ValueError: x"
    )
    trimmed = _trim_traceback(tb)
    assert "session.py" not in trimmed
    assert "exec(compiled" not in trimmed
    assert '  File "<solidifai-script>", line 12, in <module>' in trimmed
    assert "raise ValueError('x')" in trimmed
    assert "ValueError: x" in trimmed
    assert trimmed.startswith("Traceback (most recent call last):")


def test_trim_traceback_falls_back_when_all_internal():
    from solidifai_engine.server import _trim_traceback

    tb = (
        "Traceback (most recent call last):\n"
        '  File "/x/solidifai_engine/session.py", line 10, in f\n'
        "    boom()\n"
        "RuntimeError: internal"
    )
    # No user frame present: keep the full traceback so a location is not lost.
    assert _trim_traceback(tb) == tb


def test_failure_response_passes_structured_extras_through():
    """A handler's structured extras (end_round's failed map, composeEmpty) ride
    the failed envelope; error/traceback/scriptLine are additive."""
    from solidifai_engine.server import _failure_response

    result = {
        "ok": False,
        "error": "assembly has children but composed to no geometry",
        "composeEmpty": True,
        "failed": {"lid": "ValueError: bad radius"},
        "built": ["base"],
    }
    resp = _failure_response(7, result)
    assert resp["id"] == 7
    assert resp["ok"] is False
    assert resp["error"] == "assembly has children but composed to no geometry"
    assert resp["composeEmpty"] is True
    assert resp["failed"] == {"lid": "ValueError: bad radius"}
    assert resp["built"] == ["base"]
    # No traceback -> no scriptLine/traceback keys are invented.
    assert "scriptLine" not in resp
    assert "traceback" not in resp


def test_rpc_capture_views_forwards_new_params():
    # Direct dispatch-table test (no socket, no GL): the lambda must pass
    # resolution/section/focus through to the session.
    from solidifai_engine.server import _HANDLERS

    class FakeSession:
        def capture_views(self, *args, **kwargs):
            return {"args": args, "kwargs": kwargs}

    class FakeSrv:
        _session = FakeSession()

    params = {
        "views": ["iso"],
        "resolution": 1024,
        "section": {"axis": "z", "offset_mm": 2.5},
        "focus": "corner_hole",
    }
    res = _HANDLERS["capture_views"](FakeSrv(), params)
    assert res["kwargs"]["resolution"] == 1024
    assert res["kwargs"]["section"] == {"axis": "z", "offset_mm": 2.5}
    assert res["kwargs"]["focus"] == "corner_hole"
    # Omitted params keep their defaults (byte-stable existing callers).
    res = _HANDLERS["capture_views"](FakeSrv(), {"views": ["iso"]})
    assert res["kwargs"]["resolution"] == 512
    assert res["kwargs"]["section"] is None
    assert res["kwargs"]["focus"] is None
