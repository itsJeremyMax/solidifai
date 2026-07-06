"""Subprocess-seam contract tests (no real `claude`) + one real engine round trip."""

import shutil
import sys
import tempfile
from pathlib import Path

from evals.agent_runner import (
    ClaudeResult,
    EngineProcess,
    engine_rpc,
    invoke_claude,
    run_agent,
)


def _fake_runner(record):
    def run(cmd, cwd, timeout_s, env):
        record.update({"cmd": cmd, "cwd": cwd, "timeout_s": timeout_s})
        return ClaudeResult(0, '{"result": "done"}', "warn", 1.0, False)

    return run


def test_invoke_claude_builds_headless_command(tmp_path):
    rec = {}
    res = invoke_claude(
        "hello", cwd=str(tmp_path), timeout_s=5, extra_args=["--x"], runner=_fake_runner(rec)
    )
    assert res.exit_code == 0 and not res.timed_out
    assert rec["cmd"][1:] == ["-p", "hello", "--output-format", "json", "--x"]
    assert rec["cwd"] == str(tmp_path)
    assert rec["timeout_s"] == 5


def test_run_agent_wires_workspace_and_saves_transcript(tmp_path):
    rec = {}
    out = run_agent(
        "make a hook",
        str(tmp_path),
        timeout_s=10,
        transcript_path=tmp_path / "transcript.json",
        runner=_fake_runner(rec),
    )
    assert "--dangerously-skip-permissions" in rec["cmd"]
    assert rec["cmd"][-2:] == ["--mcp-config", str(tmp_path / ".mcp.json")]
    assert (tmp_path / "transcript.json").read_text(encoding="utf-8") == '{"result": "done"}'
    assert (tmp_path / "transcript.stderr.log").read_text(encoding="utf-8") == "warn"
    # The transcript is saved for debugging but NEVER returned for grading.
    assert set(out) == {"exit_code", "duration_s", "timed_out", "transcript"}


class _FakeProc:
    """Stands in for a Popen whose wait() triggers a re-entrant stop()
    (a signal handler or second thread firing mid-shutdown)."""

    def __init__(self):
        self.terminations = 0
        self.reenter = None

    def poll(self):
        return None  # always "running" so stop() takes the terminate path

    def terminate(self):
        self.terminations += 1

    def wait(self, timeout=None):
        if self.reenter is not None:
            eng, self.reenter = self.reenter, None
            eng.stop()
        return 0


def test_engine_process_stop_is_reentrant_safe(tmp_path):
    eng = EngineProcess(str(tmp_path))
    proc = _FakeProc()
    proc.reenter = eng
    eng.proc = proc
    eng.stop()
    assert proc.terminations == 1  # the re-entrant stop() must be a no-op
    assert eng.proc is None


def test_engine_process_round_trip():
    # Real engine subprocess. A deterministically short workspace root keeps
    # the socket path under the AF_UNIX limit on any machine, regardless of
    # the ambient TMPDIR.
    assert Path("/tmp").exists()
    ws = tempfile.mkdtemp(dir="/tmp", prefix="sf-ev-")
    try:
        eng = EngineProcess(ws, python=sys.executable)
        eng.start(timeout_s=120)
        try:
            info = engine_rpc(eng.sock_path, "get_model_info")
            assert isinstance(info, dict)
        finally:
            eng.stop()
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_engine_process_refuses_overlong_socket_path(tmp_path):
    deep = tmp_path / ("x" * 120)
    deep.mkdir()
    eng = EngineProcess(str(deep))
    try:
        eng.start(timeout_s=5)
        raise AssertionError("expected RuntimeError for overlong socket path")
    except RuntimeError as exc:
        assert "socket path too long" in str(exc)
