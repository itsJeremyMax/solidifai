"""The build worker must contain native kernel crashes and runaway builds.

These are the guarantees behind "the engine can't segfault": a build that makes
OpenCascade crash the *process* (a fillet as large as a shelled wall) or that
runs forever must fail as a clean error, leave the engine alive, keep the last
good model, and let the very next build succeed.
"""

import json
import tempfile
from pathlib import Path

import pytest

from solidifai_engine.operations import OperationQueue
from solidifai_engine.worker import KernelCrash, RemoteSessionError, SessionProxy, WorkerTimeout

CHANNEL = """
from solidifai import show
from build123d import *
with BuildPart() as bp:
    Box(40, 40, 10)
    Hole(radius=3)
show(bp.part, name="p")
"""

# fillet radius == the 3 mm shelled wall thickness -> native SIGSEGV in OCC
SEGFAULT = """
from solidifai import show
from build123d import *
with BuildPart() as bp:
    Box(90, 81, 23, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = bp.faces().sort_by(Axis.Z)[-1]
    offset(amount=-3.0, openings=top)
    fillet(bp.faces().sort_by(Axis.Z)[-1].edges(), 3.0)
show(bp.part, name="p")
"""

HANG = """
from solidifai import show
from build123d import Box
import time
time.sleep(30)
show(Box(10, 10, 10), name="p")
"""


@pytest.fixture
def proxy(tmp_path):
    (tmp_path / ".solidifai").mkdir()
    p = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"), model_path=str(tmp_path / "model.py")
    )
    yield p
    p.close()


def test_normal_build_and_capture(proxy):
    assert proxy.execute_script(CHANNEL)["ok"] is True
    # capture renders offscreen inside the worker
    proxy.capture_views(["iso"])
    assert proxy.get_model_info()["valid"] is True


def test_native_crash_is_contained_and_recovers(proxy):
    # a good build first, so there is a last-good model to fall back to
    assert proxy.execute_script(CHANNEL)["ok"] is True
    good_bbox = proxy.get_model_info()["bbox"]

    # the segfaulting build must raise a clean KernelCrash, not kill the test
    with pytest.raises(KernelCrash):
        proxy.execute_script(SEGFAULT)

    # engine recovered: the last-good model is intact and a new build works
    assert proxy.get_model_info()["bbox"] == good_bbox
    assert proxy.execute_script(CHANNEL)["ok"] is True


def test_runaway_build_times_out_and_recovers(tmp_path):
    (tmp_path / ".solidifai").mkdir()
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"),
        timeout=1.5,
        hard_timeout=2.5,
    )
    try:
        with pytest.raises(WorkerTimeout):
            proxy.execute_script(HANG)
        # worker was killed + respawned; a fresh build succeeds
        # Startup and the first fresh build may legitimately take longer than the
        # short timeout used above to exercise the deadline path.
        proxy._timeout = 30
        proxy._hard_timeout = 30
        recovered = proxy.execute_script(CHANNEL)
        assert recovered["ok"] is True, recovered
    finally:
        proxy.close()


def test_worker_configures_resolver_before_startup(tmp_path):
    """A workspace default material must apply to the startup build. The worker
    has to point the resolver at the workspace BEFORE it reloads the model, or
    mass/material read as the PLA built-in instead of the workspace default."""
    (tmp_path / ".solidifai").mkdir()
    (tmp_path / "materials.json").write_text(
        json.dumps(
            {
                "default": "shopsteel",
                "materials": [{"id": "shopsteel", "label": "Shop Steel", "base": "steel"}],
            }
        )
    )
    (tmp_path / "model.py").write_text(
        "from solidifai import show\nfrom build123d import Box\nshow(Box(10, 10, 10), name='p')\n"
    )
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"), model_path=str(tmp_path / "model.py")
    )
    try:
        info = proxy.get_model_info()
        # steel density ~7.85, not PLA 1.24
        assert info["mass"]["density"] == pytest.approx(7.85, rel=2e-2)
        assert info["mass"]["material"].lower() != "pla"
    finally:
        proxy.close()


def test_worker_writes_engine_log(tmp_path):
    """The worker is a fresh spawn interpreter, so it must run setup_logging
    itself: otherwise Session's build/geometry logs (which now all execute in
    the worker) never reach the workspace engine.log the file exists to capture."""
    (tmp_path / ".solidifai").mkdir()
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"), model_path=str(tmp_path / "model.py")
    )
    try:
        assert proxy.execute_script(CHANNEL)["ok"] is True  # runs inside the worker
        log_file = tmp_path / ".solidifai" / "logs" / "engine.log"
        assert log_file.exists()  # the worker installed the file handler
    finally:
        proxy.close()


def test_worker_cannot_inspect_parent_override_transport(tmp_path):
    """The parent owns override verification; model code sees no credentials."""
    (tmp_path / ".solidifai").mkdir()
    visible = tmp_path / "worker-visible.json"
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"),
        model_path=str(tmp_path / "model.py"),
        override_verifier=lambda _nonce, **_claims: {"ok": False},
    )
    try:
        script = f"""\
import json, os, sys
from build123d import Box
from solidifai import show
open({str(visible)!r}, "w").write(json.dumps({{"argv": sys.argv, "env": dict(os.environ)}}))
show(Box(1, 1, 1), name="p")
"""
        assert proxy.execute_script(script)["ok"] is True
        visible_state = json.loads(visible.read_text())
        assert not any("--override-control" in value for value in visible_state["argv"])
        assert not any("OVERRIDE_CONTROL" in key for key in visible_state["env"])
    finally:
        proxy.close()


def test_worker_cannot_recover_or_call_private_override_from_known_roots(tmp_path, monkeypatch):
    """Model code sees neither parent transport state nor pointer metadata."""
    (tmp_path / ".solidifai").mkdir()
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text("{}")
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(config))
    visible = tmp_path / "worker-probe.json"
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"),
        model_path=str(tmp_path / "model.py"),
        override_verifier=lambda _nonce, **_claims: {"ok": False},
    )
    try:
        script = f"""\
import json, os, pathlib
from build123d import Box
from solidifai import show
roots = [os.environ.get("SOLIDIFAI_CONFIG_DIR", ""), {str(tmp_path / ".solidifai")!r}]
files = [str(path) for root in roots if root for path in pathlib.Path(root).rglob("*")]
open({str(visible)!r}, "w").write(json.dumps({{"env": dict(os.environ), "files": files}}))
show(Box(1, 1, 1), name="p")
"""
        assert proxy.execute_script(script)["ok"] is True
        state = json.loads(visible.read_text())
        assert not any("OVERRIDE" in key for key in state["env"])
        assert not any("override.sock" in path for path in state["files"])
        rejected = proxy.export("stl", "forged.stl", strict_export=True, override_nonce="forged")
        assert rejected == {
            "ok": False,
            "error": "export override rejected",
            "findingIds": ["brief"],
        }
    finally:
        proxy.close()


def test_long_running_op_uses_the_larger_budget():
    """Aggregate multi-build ops (sweep/optimize/converge_to_spec/check_motion)
    run many builds inside one RPC, so they must not be capped by the single
    per-build timeout. The proxy picks the long-run budget for them and the
    normal budget for everything else."""
    proxy = SessionProxy("/tmp/unused", timeout=1.5, longrun_timeout=99.0)
    seen = {}

    def fake_recv(conn, procc, timeout, progress, **kwargs):
        seen["timeout"] = timeout
        seen["hard_timeout"] = kwargs["hard_timeout"]
        return ("ok", None)

    proxy._ensure = lambda: None
    proxy._conn = _FakeConn()
    proxy._proc = object()
    proxy._recv_result = fake_recv

    proxy.execute_script("x")
    assert seen["timeout"] == 1.5  # normal per-build ceiling
    proxy.converge_to_spec()
    assert seen["timeout"] == 1200.0  # aggregate op keeps the minimum long-run ceiling
    proxy.sweep("w", [1, 2])
    assert seen["timeout"] == 1200.0


def test_recv_result_forwards_progress_frames_before_the_final_reply():
    proxy = SessionProxy("/tmp/unused")
    conn = _ProgressConn([("progress", 0.9, "publishing"), ("ok", {"publicationId": "A"})])
    seen = []

    reply = proxy._recv_result(
        conn, _AliveProcess(), 1.0, lambda progress, phase: seen.append((progress, phase))
    )

    assert seen == [(0.9, "publishing")]
    assert reply == ("ok", {"publicationId": "A"})


def test_progress_frames_extend_soft_deadline_without_exceeding_hard_ceiling():
    proxy = SessionProxy("/tmp/unused", timeout=0.01, hard_timeout=0.04)
    clock = _Clock()
    conn = _TimedProgressConn(clock, [(0.009, ("progress", 0.5, "building"))])
    with pytest.raises(WorkerTimeout, match="hard limit"):
        proxy._recv_result(conn, _AliveProcess(), 0.01, hard_timeout=0.04, clock=clock)
    assert clock.value >= 0.04


def test_proxy_timeout_has_a_distinct_outcome_from_a_kernel_crash():
    proxy = SessionProxy("/tmp/unused", timeout=0.2)
    clock = _Clock()
    conn = _TimedProgressConn(clock, [])

    with pytest.raises(WorkerTimeout, match="soft limit"):
        proxy._recv_result(conn, _AliveProcess(), 0.2, hard_timeout=0.4, clock=clock)


@pytest.mark.parametrize(
    ("method", "args", "files"),
    [
        (
            "set_part",
            ("base", "new part"),
            {"assembly.json": b"old assembly", "parts/base.py": b"old part"},
        ),
        (
            "set_skeleton",
            ("new skeleton",),
            {
                "assembly.json": b"old assembly",
                "skeleton.py": b"old skeleton",
                ".gitignore": b"old ignore",
            },
        ),
    ],
)
def test_journalled_worker_timeout_rolls_back_and_preserves_timeout_type(
    tmp_path, method, args, files
):
    artifacts = tmp_path / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    proxy = SessionProxy(str(artifacts), model_path=str(tmp_path / "model.py"))
    proxy._ensure = lambda: None
    proxy._conn = _FakeConn()
    proxy._proc = object()
    proxy._teardown = lambda: None

    def timeout_after_mutation(*_args, **_kwargs):
        for relative in files:
            (tmp_path / relative).write_bytes(b"timed out mutation")
        raise WorkerTimeout("the build exceeded its deadline")

    proxy._recv_result = timeout_after_mutation

    with pytest.raises(WorkerTimeout, match="rolled back"):
        proxy._call_locked(method, args, {})

    assert {relative: (tmp_path / relative).read_bytes() for relative in files} == files
    queue = OperationQueue(
        lambda _method, _params, _heartbeat: proxy._call_locked(method, args, {})
    )
    try:
        operation = queue.submit(method, {})
        assert queue.wait(operation["operationId"], timeout=1)["state"] == "timed_out"
    finally:
        queue.close()


def test_publishing_frame_marks_active_call_non_cancellable_before_callback():
    proxy = SessionProxy("/tmp/unused")
    active = proxy._begin_active_call("operation")
    observed = []
    conn = _ProgressConn([("progress", 0.9, "publishing"), ("ok", {})])

    proxy._recv_result(
        conn,
        _AliveProcess(),
        1.0,
        lambda _progress, _phase: observed.append(proxy.begin_cancel("operation")),
    )

    assert [outcome.status for outcome in observed] == ["too_late"]
    assert conn.sent == [("publishing_ack", None)]
    proxy._finish_active_call(active)


def test_begin_cancel_distinguishes_not_active_claimed_and_too_late():
    proxy = SessionProxy("/tmp/unused")
    assert proxy.begin_cancel("operation").status == "not_active"

    active = proxy._begin_active_call("operation")
    claimed = proxy.begin_cancel("operation")
    assert claimed.status == "claimed"
    proxy._finish_active_call(active)  # completion wins while the scheduler holds the claim
    proxy.release_cancel_claim(claimed.claim)
    assert active.cancellation_claim is None
    assert proxy._active_call is None

    active = proxy._begin_active_call("operation")
    active.cancellable = False
    assert proxy.begin_cancel("operation").status == "too_late"
    proxy._finish_active_call(active)


class _FakeConn:
    def send(self, _payload):
        return None


class _ProgressConn:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def poll(self, _timeout):
        return bool(self.replies)

    def recv(self):
        return self.replies.pop(0)

    def send(self, _payload):
        self.sent.append(_payload)


class _AliveProcess:
    def is_alive(self):
        return True


class _Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class _TimedProgressConn:
    def __init__(self, clock, replies):
        self.clock = clock
        self.replies = list(replies)

    def poll(self, timeout):
        self.clock.value += timeout
        return bool(self.replies and self.clock.value >= self.replies[0][0])

    def recv(self):
        _at, reply = self.replies.pop(0)
        return reply

    def send(self, _payload):
        return None


def test_session_error_keeps_original_type_prefix(proxy):
    """A Session method that raises must surface with its own exception type,
    not the proxy's. The proxy re-raises as RemoteSessionError carrying the
    worker's already-formatted "<Type>: message" string verbatim, so the
    server can emit it without prepending a second (RuntimeError) prefix."""
    # 'notadict' makes set_requirements iterate a string and hit AttributeError
    # inside the worker (a normal caught error, not a native crash).
    with pytest.raises(RemoteSessionError) as excinfo:
        proxy.set_requirements("notadict")
    msg = str(excinfo.value)
    assert msg.startswith("AttributeError:")
    assert "RuntimeError:" not in msg


def test_server_does_not_double_prefix_session_error(tmp_path):
    """End to end: the client-facing error string keeps the original exception
    type and is not buried under a second RuntimeError prefix (the pre-worker
    behavior)."""
    from solidifai_engine.server import Server

    (tmp_path / ".solidifai").mkdir()
    srv = Server(
        socket_path=str(tmp_path / "sock"),
        artifacts_dir=str(tmp_path / ".solidifai" / "artifacts"),
        model_path=str(tmp_path / "model.py"),
    )
    try:
        line = json.dumps(
            {"id": 1, "method": "set_requirements", "params": {"requirements": "notadict"}}
        ).encode("utf-8")
        resp = srv._handle_line(line)
        assert resp["ok"] is False
        assert resp["error"].startswith("AttributeError:")
        assert not resp["error"].startswith("RuntimeError:")
    finally:
        srv._session.close()
