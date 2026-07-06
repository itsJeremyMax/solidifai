import json
import os
import socket
import sys
import threading

from mcp.server.fastmcp import Image as _McpImage
from sockpath import short_socket_path

from solidifai_mcp.server import forward


def _fake_engine_returning(sock_path, response_result, ready):
    """A one-shot fake engine that replies with a fixed ``result`` payload.

    ``ready`` is set immediately after ``listen()`` so callers can wait for
    listening readiness (not just the bind-created socket file) — once
    listening, connects queue in the backlog, so there is no bind/listen race.
    """

    def run():
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(sock_path)
        srv.listen(1)
        srv.settimeout(5)
        ready.set()
        conn, _ = srv.accept()
        with conn:
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            req = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
            conn.sendall(
                (
                    json.dumps({"id": req["id"], "ok": True, "result": response_result}) + "\n"
                ).encode()
            )
        srv.close()

    return run


def _fake_engine(sock_path, captured, ready):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    srv.settimeout(5)
    ready.set()
    conn, _ = srv.accept()
    with conn:
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        line = buf.split(b"\n", 1)[0]
        request = json.loads(line.decode("utf-8"))
        captured.append(request)
        response = {
            "id": request["id"],
            "ok": True,
            "result": {"echo": request["method"], "params": request.get("params")},
        }
        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
    srv.close()


def _spawn_returning(sock_path, result):
    """Start a one-shot result-returning fake engine; block until it listens."""
    ready = threading.Event()
    t = threading.Thread(target=_fake_engine_returning(sock_path, result, ready), daemon=True)
    t.start()
    ready.wait(5)
    return t


def _spawn_capturing(sock_path, captured):
    """Start a one-shot request-capturing fake engine; block until it listens."""
    ready = threading.Event()
    t = threading.Thread(target=_fake_engine, args=(sock_path, captured, ready), daemon=True)
    t.start()
    ready.wait(5)
    return t


def test_forward_sends_rpc_and_returns_result(tmp_path, monkeypatch):
    sock_path = short_socket_path(tmp_path)
    captured = []
    t = _spawn_capturing(sock_path, captured)

    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    result = forward("execute_script", {"code": "show('x')"})
    t.join(timeout=5)

    assert captured, "engine received no request"
    req = captured[0]
    assert req["method"] == "execute_script"
    assert req["params"] == {"code": "show('x')"}
    assert result == {"echo": "execute_script", "params": {"code": "show('x')"}}


def test_bridge_does_not_import_build123d():
    # Importing the bridge must not pull in the heavy CAD kernel. Check in a
    # fresh interpreter so other test modules' imports don't pollute the result.
    import subprocess

    code = (
        "import importlib, sys; "
        "importlib.import_module('solidifai_mcp'); "
        "importlib.import_module('solidifai_mcp.server'); "
        "assert 'build123d' not in sys.modules, 'bridge imported build123d'; "
        "print('OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_history_tools_forward_expected_methods(monkeypatch):
    import solidifai_mcp.server as srv

    calls = []
    monkeypatch.setattr(
        srv, "forward", lambda method, params=None: calls.append((method, params)) or {"ok": True}
    )

    srv.cad_history()
    srv.cad_undo()
    srv.cad_redo()
    srv.cad_checkpoint("snapshot A")

    methods = [c[0] for c in calls]
    assert methods == ["history", "undo", "redo", "checkpoint"]
    assert calls[-1][1] == {"message": "snapshot A"}


def test_capture_views_wraps_paths_as_images(tmp_path, monkeypatch):
    # A real PNG on disk for the bridge to read and wrap.
    png = tmp_path / "iso.png"
    png.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64)  # PNG magic + filler
    sock_path = short_socket_path(tmp_path)
    result = {"ok": True, "buildId": 3, "views": [{"name": "iso", "path": str(png)}]}
    t = _spawn_returning(sock_path, result)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    from solidifai_mcp.server import capture_views

    out = capture_views(["iso"])
    t.join(timeout=5)

    # First item is a text summary; the rest are Image content blocks.
    assert isinstance(out, list)
    assert any(isinstance(x, _McpImage) for x in out)
    assert any(isinstance(x, str) and "iso" in x for x in out)


def test_capture_views_missing_file_returns_text(tmp_path, monkeypatch):
    sock_path = short_socket_path(tmp_path)
    result = {
        "ok": True,
        "buildId": 3,
        "views": [{"name": "iso", "path": str(tmp_path / "gone.png")}],
    }
    t = _spawn_returning(sock_path, result)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    from solidifai_mcp.server import capture_views

    out = capture_views(["iso"])
    t.join(timeout=5)
    # Missing file -> a text error, never an exception, no Image for it.
    joined = " ".join(x for x in out if isinstance(x, str))
    assert "iso" in joined and ("missing" in joined.lower() or "unreadable" in joined.lower())


def test_export_tool_forwards_optional_path(tmp_path, monkeypatch):
    # `export` with no path must forward path=None (the engine defaults it).
    sock_path = short_socket_path(tmp_path)
    captured = []
    t = _spawn_capturing(sock_path, captured)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    from solidifai_mcp.server import export

    export("stl")  # no path
    t.join(timeout=5)
    assert captured[0]["method"] == "export"
    assert captured[0]["params"] == {"format": "stl", "path": None, "options": None}


def test_capture_views_forwards_layout(tmp_path, monkeypatch):
    sock_path = short_socket_path(tmp_path)
    captured = []
    t = _spawn_capturing(sock_path, captured)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    from solidifai_mcp.server import capture_views

    capture_views(["iso", "top"], layout="grid")
    t.join(timeout=5)
    assert captured[0]["method"] == "capture_views"
    assert captured[0]["params"] == {
        "views": ["iso", "top"],
        "layout": "grid",
        "color": True,
        "explode": 0.0,
        "highlight": None,
    }


def test_capture_views_forwards_color_false(tmp_path, monkeypatch):
    sock_path = short_socket_path(tmp_path)
    captured = []
    t = _spawn_capturing(sock_path, captured)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    from solidifai_mcp.server import capture_views

    capture_views(["iso"], color=False)
    t.join(timeout=5)
    assert captured[0]["method"] == "capture_views"
    assert captured[0]["params"] == {
        "views": ["iso"],
        "layout": "separate",
        "color": False,
        "explode": 0.0,
        "highlight": None,
    }


def test_capture_views_grid_wraps_single_image(tmp_path, monkeypatch):
    png = tmp_path / "contact_sheet.png"
    png.write_bytes(bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 64)
    sock_path = short_socket_path(tmp_path)
    result = {
        "ok": True,
        "buildId": 5,
        "layout": "grid",
        "views": [{"name": "contact_sheet", "path": str(png)}],
    }
    t = _spawn_returning(sock_path, result)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    from solidifai_mcp.server import capture_views

    out = capture_views(["iso", "top"], layout="grid")
    t.join(timeout=5)
    assert sum(isinstance(x, _McpImage) for x in out) == 1
    assert any(isinstance(x, str) and "contact_sheet" in x for x in out)


def test_inspect_features_forwards_method(monkeypatch):
    import solidifai_mcp.server as srv

    calls = []
    monkeypatch.setattr(
        srv,
        "forward",
        lambda method, params=None: calls.append((method, params)) or {"features": []},
    )

    out = srv.inspect_features()
    assert calls == [("inspect_features", None)]
    assert out == {"features": []}


def test_check_interferences_forwards_method(monkeypatch):
    import solidifai_mcp.server as srv

    calls = []
    monkeypatch.setattr(
        srv,
        "forward",
        lambda method, params=None: calls.append((method, params)) or {"ok": True},
    )

    out = srv.check_interferences()
    assert calls == [("check_interferences", None)]
    assert out == {"ok": True}


def test_feature_at_forwards(monkeypatch):
    import solidifai_mcp.server as srv

    calls = []
    monkeypatch.setattr(
        srv,
        "forward",
        lambda method, params=None: calls.append((method, params)) or {"match": None},
    )
    srv.feature_at([1.0, 2.0, 3.0])
    assert calls == [("feature_at", {"point": [1.0, 2.0, 3.0]})]


def test_capture_views_forwards_highlight(tmp_path, monkeypatch):
    sock_path = short_socket_path(tmp_path)
    captured = []
    t = _spawn_capturing(sock_path, captured)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)
    from solidifai_mcp.server import capture_views

    capture_views(["iso"], highlight=["central_bore"])
    t.join(timeout=5)
    assert captured[0]["method"] == "capture_views"
    assert captured[0]["params"]["highlight"] == ["central_bore"]


def test_set_feature_forwards(monkeypatch):
    import solidifai_mcp.server as srv

    calls = []
    monkeypatch.setattr(
        srv, "forward", lambda method, params=None: calls.append((method, params)) or {"ok": True}
    )
    srv.set_feature("center_hole", {"bore": 16})
    assert calls == [("set_feature", {"name": "center_hole", "values": {"bore": 16}})]


def test_export_forwards_options(monkeypatch):
    import solidifai_mcp.server as srv

    calls = []
    monkeypatch.setattr(
        srv,
        "forward",
        lambda method, params=None: (
            calls.append((method, params)) or {"ok": True, "path": "/tmp/out.stl"}
        ),
    )
    srv.export("stl", "/tmp/out.stl", {"ascii": True})
    assert calls == [
        ("export", {"format": "stl", "path": "/tmp/out.stl", "options": {"ascii": True}})
    ]


def test_capture_views_forwards_new_params(tmp_path, monkeypatch):
    sock_path = short_socket_path(tmp_path)
    captured = []
    t = _spawn_capturing(sock_path, captured)
    monkeypatch.setenv("SOLIDIFAI_ENGINE_SOCK", sock_path)

    from solidifai_mcp.server import capture_views

    capture_views(
        ["iso"],
        resolution=1024,
        section={"axis": "z", "offset_mm": 0.0},
        focus="corner_hole",
    )
    t.join(timeout=5)
    p = captured[0]["params"]
    assert p["resolution"] == 1024
    assert p["section"] == {"axis": "z", "offset_mm": 0.0}
    assert p["focus"] == "corner_hole"
