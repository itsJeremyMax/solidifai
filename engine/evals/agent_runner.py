"""Headless agent + engine process management for eval runs.

Every subprocess call goes through the ``runner`` seam (a callable with
``_default_runner``'s signature) so graders/scorecard/judge tests never need a
real ``claude`` binary or engine process.

Why ``--dangerously-skip-permissions``: the agent runs unattended against a
disposable temp workspace with nothing valuable in reach, and there is no
human to answer permission prompts. Dev-only; never used outside this harness.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
# macOS AF_UNIX sun_path limit is 104 bytes; fail early with a clear message.
MAX_SOCK_PATH = 100


@dataclass
class ClaudeResult:
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool


def _killpg(proc: subprocess.Popen) -> None:
    """SIGKILL the child's whole process group; tolerate it already being gone."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)


def _default_runner(cmd: list[str], cwd: str, timeout_s: float, env: dict) -> ClaudeResult:
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # own process group: a timeout kill reaps MCP children too
        env=env,
    )
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        _killpg(proc)
        out, err = proc.communicate()
    except BaseException:
        # Any other interruption (KeyboardInterrupt, pipe OSError) must not
        # orphan the claude process group either.
        _killpg(proc)
        proc.wait()
        raise
    return ClaudeResult(
        proc.returncode, out or "", err or "", round(time.monotonic() - start, 2), timed_out
    )


def ensure_claude() -> str:
    path = shutil.which("claude")
    if not path:
        raise RuntimeError(
            "`claude` CLI not found on PATH; install Claude Code to run agent evals. "
            "Grading without the agent still works: --grade-only <workspace> --no-vlm"
        )
    return path


def invoke_claude(
    prompt: str,
    *,
    cwd: str,
    timeout_s: float,
    extra_args: list[str] | None = None,
    runner=None,
) -> ClaudeResult:
    """One headless ``claude -p`` call. ``--output-format json`` so stdout is a
    machine-readable envelope (saved as the transcript; parsed by the judge)."""
    exe = "claude" if runner is not None else ensure_claude()
    cmd = [exe, "-p", prompt, "--output-format", "json", *(extra_args or [])]
    return (runner or _default_runner)(cmd, cwd, timeout_s, os.environ.copy())


def valid_agent_envelope(stdout: str) -> bool:
    """Validate the successful ``claude --output-format json`` result contract."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return False
    return (
        isinstance(envelope, dict)
        and envelope.get("type") == "result"
        and envelope.get("subtype") == "success"
        and envelope.get("is_error") is False
        and isinstance(envelope.get("result"), str)
        and bool(envelope["result"].strip())
        and isinstance(envelope.get("num_turns"), int)
        and not isinstance(envelope["num_turns"], bool)
        and envelope["num_turns"] > 0
    )


def run_agent(
    brief: str,
    workspace: str,
    *,
    timeout_s: float,
    transcript_path: str | Path,
    runner=None,
) -> dict:
    """Run Sol headlessly on ``brief`` with cwd=workspace. The workspace's own
    ``.mcp.json`` (server name ``solidifai-cad``, same as the app) is passed via
    --mcp-config so the engine tools resolve exactly as they do in the app.
    Saves the transcript for debugging and returns ONLY run metadata — grading
    reads the workspace artifacts, never the transcript."""
    res = invoke_claude(
        brief,
        cwd=workspace,
        timeout_s=timeout_s,
        extra_args=[
            "--dangerously-skip-permissions",
            "--mcp-config",
            os.path.join(workspace, ".mcp.json"),
        ],
        runner=runner,
    )
    p = Path(transcript_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(res.stdout, encoding="utf-8")
    if res.stderr:
        p.with_name(p.stem + ".stderr.log").write_text(res.stderr, encoding="utf-8")
    envelope_valid = valid_agent_envelope(res.stdout)
    return {
        "exit_code": res.exit_code,
        "duration_s": res.duration_s,
        "timed_out": res.timed_out,
        "envelope_valid": envelope_valid,
        "transcript": str(p),
    }


def engine_rpc(sock_path: str, method: str, params: dict | None = None, timeout_s: float = 30.0):
    """One newline-delimited JSON RPC round trip on the engine socket (the same
    wire contract solidifai_mcp uses)."""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout_s)
    try:
        conn.connect(sock_path)
        conn.sendall(
            (json.dumps({"id": 1, "method": method, "params": params or {}}) + "\n").encode()
        )
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        conn.close()
    if not buf:
        raise RuntimeError("engine closed the connection without responding")
    resp = json.loads(buf.decode("utf-8").splitlines()[0])
    if not resp.get("ok"):
        raise RuntimeError(str(resp.get("error", "engine returned an error")))
    return resp.get("result")


class EngineProcess:
    """One engine RPC server for a workspace, spawned with the app's contract:
    ``<python> -m solidifai_engine --socket <ws>/.solidifai/engine.sock
    --artifacts <ws>/.solidifai/artifacts --model <ws>/model.py``."""

    def __init__(self, workspace: str, python: str | None = None):
        self.workspace = os.path.abspath(workspace)
        self.python = python or sys.executable
        dot = os.path.join(self.workspace, ".solidifai")
        self.sock_path = os.path.join(dot, "engine.sock")
        self.artifacts = os.path.join(dot, "artifacts")
        self.log_path = os.path.join(dot, "engine.log")
        self.proc: subprocess.Popen | None = None

    def start(self, timeout_s: float = 90.0) -> None:
        if len(self.sock_path) > MAX_SOCK_PATH:
            raise RuntimeError(
                f"socket path too long for AF_UNIX ({len(self.sock_path)} chars): "
                f"{self.sock_path}. Use a short --workspaces-root (default /tmp/sf-evals)."
            )
        os.makedirs(self.artifacts, exist_ok=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ENGINE_ROOT)
        # Hermetic config dir: without this, lookup_reference would read the
        # dev machine's real user reference library and contaminate results.
        env["SOLIDIFAI_CONFIG_DIR"] = os.path.join(self.workspace, ".solidifai", "config")
        with open(self.log_path, "ab") as log:
            self.proc = subprocess.Popen(
                [
                    self.python,
                    "-m",
                    "solidifai_engine",
                    "--override-bootstrap-mode",
                    "eval-test",
                    "--socket",
                    self.sock_path,
                    "--artifacts",
                    self.artifacts,
                    "--model",
                    os.path.join(self.workspace, "model.py"),
                ],
                stdout=log,
                stderr=log,
                stdin=None,
                env=env,
                start_new_session=True,
            )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"engine exited early (code {self.proc.returncode}); see {self.log_path}"
                )
            if os.path.exists(self.sock_path):
                probe_timeout = min(0.25, max(0.05, deadline - time.monotonic()))
                try:
                    engine_rpc(self.sock_path, "get_model_info", timeout_s=probe_timeout)
                    return
                except OSError:
                    pass
                except RuntimeError as exc:
                    if "no committed model publication is available" in str(exc):
                        return
            time.sleep(0.25)
        self.stop()
        raise RuntimeError(f"engine not ready within {timeout_s}s; see {self.log_path}")

    def stop(self) -> None:
        # Claim the handle first so a re-entrant stop() (signal handler,
        # second thread) is a no-op instead of double-signalling.
        p, self.proc = self.proc, None
        if p is None or p.poll() is not None:
            return
        p.terminate()  # the engine maps SIGTERM to an immediate exit
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()  # SIGKILL cannot be ignored; no timeout needed
