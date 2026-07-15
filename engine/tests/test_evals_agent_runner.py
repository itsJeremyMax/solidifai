"""Subprocess-seam contract tests (no real `claude`) + one real engine round trip."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

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
        return ClaudeResult(0, json.dumps(_agent_envelope()), "warn", 1.0, False)

    return run


def _agent_envelope(*, result="done", **extra):
    return {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result,
        "num_turns": 1,
        **extra,
    }


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
    assert (
        json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))["result"] == "done"
    )
    assert (tmp_path / "transcript.stderr.log").read_text(encoding="utf-8") == "warn"
    # The transcript is saved for debugging but NEVER returned for grading.
    assert out["envelope_valid"] is True


@pytest.mark.parametrize(
    "envelope",
    [
        {},
        {"type": "result", "is_error": False, "result": "done", "num_turns": 1},
        _agent_envelope(result=""),
        _agent_envelope(num_turns=0),
        _agent_envelope(is_error=True),
    ],
)
def test_run_agent_rejects_structurally_invalid_success_envelopes(tmp_path, envelope):
    out = run_agent(
        "make a hook",
        str(tmp_path),
        timeout_s=10,
        transcript_path=tmp_path / "transcript.json",
        runner=lambda *args: ClaudeResult(0, json.dumps(envelope), "", 1.0, False),
    )
    assert out["envelope_valid"] is False


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
        try:
            eng.start()
        except RuntimeError:
            print(Path(eng.log_path).read_text(encoding="utf-8"))
            raise
        try:
            engine_rpc(
                eng.sock_path,
                "execute_script",
                {
                    "code": (
                        "from build123d import Box\n"
                        "from solidifai import show\n"
                        "show(Box(1,1,1), name='p')\n"
                    )
                },
            )
            info = engine_rpc(eng.sock_path, "get_model_info")
            assert isinstance(info, dict)
        finally:
            eng.stop()
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_engine_process_writes_eval_bootstrap_without_argv_or_env_leak(monkeypatch, tmp_path):
    seen = {}
    short = Path(tempfile.mkdtemp(dir="/tmp", prefix="sf-ev-"))

    class _Proc:
        def __init__(self):
            self.returncode = None

        def poll(self):
            return None

        def terminate(self):
            self.returncode = 0

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

    def fake_popen(cmd, stdout, stderr, env, start_new_session, stdin):
        seen["cmd"] = cmd
        seen["env"] = env
        seen["stdin"] = stdin
        return _Proc()

    monkeypatch.setattr("subprocess.Popen", fake_popen)
    monkeypatch.setattr("evals.agent_runner.engine_rpc", lambda *_args, **_kwargs: {})
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "evals.agent_runner.os.path.exists",
        lambda path: path == str(short / ".solidifai" / "engine.sock"),
    )

    try:
        eng = EngineProcess(str(short), python=sys.executable)
        eng.start(timeout_s=0.1)

        assert seen["cmd"][3:5] == ["--override-bootstrap-mode", "eval-test"]
        assert not any("OVERRIDE_CONTROL" in key for key in seen["env"])
        assert seen["stdin"] is None
    finally:
        shutil.rmtree(short, ignore_errors=True)


def test_engine_process_refuses_overlong_socket_path(tmp_path):
    deep = tmp_path / ("x" * 120)
    deep.mkdir()
    eng = EngineProcess(str(deep))
    try:
        eng.start(timeout_s=5)
        raise AssertionError("expected RuntimeError for overlong socket path")
    except RuntimeError as exc:
        assert "socket path too long" in str(exc)
