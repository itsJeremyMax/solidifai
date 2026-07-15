"""Fault-isolated build worker.

The modeling kernel (OpenCascade, via build123d) can crash the *process* on
degenerate geometry -- a fillet whose radius equals a wall thickness, a
self-intersecting boolean, a pathological tessellation -- with a native
SIGSEGV/SIGABRT that no ``try/except`` can catch. The engine runs arbitrary
agent-authored build123d code, so an in-process kernel crash would take the
whole engine down and drop the client's connection.

``SessionProxy`` moves the ``Session`` (all geometry work) into a spawned child
process and forwards each RPC to it over a pipe. A native crash now kills only
the child: the proxy detects the death, respawns a fresh worker (which reloads
the last good ``model.py`` on startup), and returns a clean build-failed error
for the offending call. The engine process itself never dies. The same boundary
bounds runaway builds: a call that exceeds ``timeout`` has its worker killed and
reported, instead of wedging the engine forever.

The proxy is a drop-in for ``Session`` from the ``Server``'s point of view: any
attribute it does not define is forwarded to the worker's ``Session`` method of
the same name, and results (plain JSON-able values -- the same ones that already
cross the RPC socket) come back over the pipe.
"""

from __future__ import annotations

import contextlib
import logging
import multiprocessing as mp
import os
import threading
import time
import traceback
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any, Literal, cast

from solidifai_engine.operations import OperationTimeout

log = logging.getLogger(__name__)

# Session methods that mutate script/material/import state: the worker must point
# the material resolver at the workspace before running them so a material
# created/edited mid-session resolves. Kept here (not in server.py) so both the
# proxy and the worker share one definition without a circular import.
REFRESH_METHODS = frozenset(
    {
        "execute_script",
        "run_file",
        "render",
        "set_params",
        "set_part_material",
        "import_reference",
        "remove_import",
        "set_skeleton",
        "set_part",
        "attach",
        "set_inputs",
        "remove_part",
        "add_subassembly",
        "build_part",
        "end_round",
    }
)

# Structural mutations whose source+manifest are written to disk BEFORE the build
# that validates them. If the build natively crashes the worker, its in-worker
# rollback never runs, so the poisoned files stay on disk and every respawned
# worker crashes rebuilding them on startup -- bricking the workspace forever. The
# parent journals the pre-mutation on-disk state before forwarding these and rolls
# back from the parent side when the call ends in a KernelCrash.
JOURNALED_METHODS = frozenset({"set_part", "set_skeleton"})

# A worker writes this marker in artifacts_dir just before its startup rebuild and
# removes it right after. A NATIVE crash during the rebuild is uncatchable, so the
# marker survives; the next spawned worker sees it and comes up model-less-but-
# serving (skipping the rebuild) so the agent can remove/fix the poisoned state
# instead of every respawn dying in startup. Healthy workspaces never see it, so
# the eager last-good reload is preserved for them.
_STARTUP_SENTINEL = "startup.lock"

# Aggregate operations that run MANY builds inside a single RPC: a parameter
# sweep, an optimize/converge loop, a motion range. One per-build ceiling would
# kill a legitimate long run partway (each of ~24 candidates rebuilds+measures),
# so these get a much larger budget while a truly wedged worker is still bounded.
# Names match the Session methods dispatched by the server.
LONG_RUNNING_METHODS = frozenset({"sweep", "optimize", "converge_to_spec", "check_motion"})

# Per-call ceiling (seconds). A build that runs longer is treated as wedged: the
# worker is killed and the call reported as failed, rather than hanging forever
# (the old in-process behavior). Generous so heavy-but-legitimate assembly builds
# and tessellations finish; override with SOLIDIFAI_BUILD_TIMEOUT for testing.
_DEFAULT_TIMEOUT = float(os.environ.get("SOLIDIFAI_BUILD_TIMEOUT", "180"))
_DEFAULT_HARD_TIMEOUT = float(os.environ.get("SOLIDIFAI_BUILD_HARD_TIMEOUT", "210"))
# Larger ceiling for LONG_RUNNING_METHODS, which run many builds per call.
_LONGRUN_TIMEOUT = float(os.environ.get("SOLIDIFAI_LONGRUN_TIMEOUT", "1200"))
_SPAWN_READY_TIMEOUT = float(os.environ.get("SOLIDIFAI_WORKER_START_TIMEOUT", "60"))
# Startup rebuilds the model synchronously BEFORE the worker replies "ready", so
# the spawn-ready budget must cover a legal build or a model that builds in
# (ready, build] seconds could never be reloaded -- reopen/crash would loop on
# "did not start in time" forever. The effective budget is at least the per-build
# timeout plus this margin, whatever the (possibly smaller) ready override is.
_START_MARGIN = 30.0
_HEARTBEAT_INTERVAL = float(os.environ.get("SOLIDIFAI_WORKER_HEARTBEAT_INTERVAL", "1"))


class KernelCrash(RuntimeError):
    """A build worker died on a native fault or was killed for exceeding the
    build timeout. Surfaced to the client as a failed build; the engine and the
    previous good model are unaffected."""


class WorkerTimeout(OperationTimeout):
    """The live worker exceeded its progress-sensitive execution budget."""


class RemoteSessionError(RuntimeError):
    """A ``Session`` method raised inside the worker (a normal, caught error).
    Carries the worker's already-formatted ``"<Type>: message"`` string verbatim
    so the server surfaces it without prepending a second type prefix, plus the
    worker's formatted ``traceback`` (when shipped) so the server can attach
    ``scriptLine`` + a trimmed traceback for raised errors too, not only for the
    ``{ok: false}`` returns that already carry one."""

    def __init__(self, message: str, traceback_str: str | None = None):
        super().__init__(message)
        self.traceback = traceback_str


@dataclass
class _ActiveCall:
    operation_id: str | None
    journal: list[tuple[str, bytes | None]] | None
    cancellable: bool = True
    cancellation_claim: object | None = None
    completed: bool = False


@dataclass(frozen=True)
class CancelOutcome:
    """Result of attempting to claim one operation's active worker call."""

    status: Literal["claimed", "too_late", "not_active"]
    claim: object | None = None


def _worker_main(
    conn: Connection,
    artifacts_dir: str,
    model_path: str | None,
) -> None:
    """Child entry point: hold a Session and serve one request at a time.

    Requests are ``(method, args, kwargs, refresh)``; replies are ``("ok",
    result)`` or ``("err", "Type: message")``. A native crash simply ends the
    process mid-reply -- the parent notices the closed pipe. Runs the build in
    this process so an OCC fault cannot reach the parent."""
    from solidifai_engine import materials
    from solidifai_engine.logconfig import setup_logging
    from solidifai_engine.session import Session

    # The worker is a fresh (spawn) interpreter, so the engine's main-process log
    # setup did not run here. Configure it now or Session's build/geometry logs --
    # which all execute in this worker -- never reach the workspace engine.log.
    setup_logging(artifacts_dir)

    # Workspace root for the material resolver, matching Server._workspace_root:
    # the model's dir, else the artifacts grandparent (artifacts live at
    # <root>/.solidifai/artifacts). Point the resolver at it BEFORE startup so the
    # reloaded model resolves the workspace's default + custom materials (not the
    # PLA built-in) for correct mass, and a part shown with a custom material
    # actually builds on open.
    if model_path:
        root: str | None = os.path.dirname(os.path.abspath(model_path))
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(artifacts_dir)))

    send_lock = threading.Lock()

    def send(frame: tuple) -> None:
        """Frames share one pipe; concurrent heartbeats cannot interleave sends."""
        with send_lock:
            conn.send(frame)

    def verifier(nonce, **claims):
        send(("verify_override", nonce, claims))
        response = conn.recv()
        return response[1] if response[0] == "verify_result" else {"ok": False}

    request_active = threading.Event()

    def publishing() -> None:
        if request_active.is_set():
            # Do not let render commit current.json until the parent has made this
            # active call non-cancellable. This closes the pipe-scheduling window
            # between a publication heartbeat and the durable pointer write. Keep
            # heartbeats out of this send/ack handshake as well: Connection does
            # not make a concurrent send and receive into one protocol transaction.
            with send_lock:
                conn.send(("progress", 0.9, "publishing"))
                acknowledgement = conn.recv()
            if acknowledgement[0] != "publishing_ack":
                raise RuntimeError(
                    f"worker received {acknowledgement[0]!r} instead of publication acknowledgement"
                )

    session = Session(
        artifacts_dir,
        model_path=model_path,
        override_verifier=verifier,
        on_publishing=publishing,
    )
    if root is not None:
        materials.configure_resolver(root)
    # Session.__init__ creates artifacts_dir, so the sentinel path is writable now.
    sentinel = os.path.join(artifacts_dir, _STARTUP_SENTINEL)
    if os.path.exists(sentinel):
        # A previous worker crashed INSIDE startup rebuilding this model (a native
        # fault leaves the marker behind). Come up model-less-but-serving so the
        # agent can remove/fix the poisoned state instead of respawns dying here
        # forever. Clear it so a later healthy reopen eagerly reloads again. The
        # last-good model.json on disk still serves get_model_info in the meantime.
        log.warning("skipping model reload: a previous startup crashed on this model")
        with contextlib.suppress(OSError):
            os.remove(sentinel)
    else:
        try:
            with open(sentinel, "w"):
                pass
            session.startup()  # reload last-good model + settings (never raises)
        except Exception:  # noqa: BLE001 - belt and suspenders; startup already guards
            log.exception("worker startup failed")
        finally:
            # Reached on a caught error or clean return; a NATIVE crash skips this
            # and deliberately leaves the marker for the next spawn to see.
            with contextlib.suppress(OSError):
                os.remove(sentinel)
    send(("ready", None))

    while True:
        try:
            request = conn.recv()
        except (EOFError, KeyboardInterrupt):
            return
        # A parent can have acknowledged a publication just as this worker was
        # torn down for a timeout. That acknowledgement has no meaning outside
        # its original call and is never a Session request.
        if request[0] == "publishing_ack":
            continue
        method, args, kwargs, refresh = request
        try:
            if refresh and root is not None:
                materials.configure_resolver(root)
            request_active.set()
            stop_heartbeat = threading.Event()

            def heartbeat_loop(stop: threading.Event) -> None:
                while not stop.wait(_HEARTBEAT_INTERVAL):
                    if request_active.is_set():
                        with contextlib.suppress(OSError, EOFError):
                            send(("progress", None, "building"))

            heartbeats = threading.Thread(
                target=heartbeat_loop,
                args=(stop_heartbeat,),
                name="solidifai-worker-heartbeat",
                daemon=True,
            )
            heartbeats.start()
            try:
                result = getattr(session, method)(*args, **kwargs)
            finally:
                request_active.clear()
                stop_heartbeat.set()
                heartbeats.join()
            send(("ok", result))
        except Exception as exc:  # noqa: BLE001 - forward as a clean error, don't die
            # Ship the traceback alongside the message so the server can attach
            # scriptLine + a trimmed traceback for a raised error too.
            send(("err", f"{type(exc).__name__}: {exc}", traceback.format_exc()))
        finally:
            request_active.clear()


class SessionProxy:
    """Runs a ``Session`` in a crash-isolated worker; forwards attribute calls."""

    def __init__(
        self,
        artifacts_dir: str,
        model_path: str | None = None,
        override_verifier=None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        longrun_timeout: float = _LONGRUN_TIMEOUT,
        hard_timeout: float | None = None,
        start_timeout: float = _SPAWN_READY_TIMEOUT,
    ):
        self._artifacts_dir = artifacts_dir
        self._model_path = model_path
        self._override_verifier = override_verifier
        self._timeout = timeout
        self._longrun_timeout = max(longrun_timeout, 1200.0)
        self._hard_timeout = max(hard_timeout or _DEFAULT_HARD_TIMEOUT, timeout)
        # Startup builds the model before replying "ready", so the ready budget
        # must cover a legal build; otherwise a model that builds in (start, build]
        # seconds bricks every reopen. Never below the per-build timeout + margin.
        self._start_timeout = max(start_timeout, timeout + _START_MARGIN)
        self._ctx = mp.get_context("spawn")  # fresh interpreter: safe cross-platform
        self._proc: mp.process.BaseProcess | None = None
        self._conn: Connection | None = None
        self._pipe_lock = threading.Lock()
        self._closed = False
        self._active_lock = threading.Lock()
        self._active_call: _ActiveCall | None = None
        self._operation_id: str | None = None
        self._operation_heartbeat = None

    # -- worker lifecycle ---------------------------------------------------

    def _spawn(self) -> None:
        """Start a fresh worker and block until it has loaded the model."""
        parent, child = self._ctx.Pipe()
        proc = self._ctx.Process(
            target=_worker_main,
            args=(
                child,
                self._artifacts_dir,
                self._model_path,
            ),
            daemon=True,
            name="solidifai-build-worker",
        )
        proc.start()
        child.close()  # only the worker keeps the child end
        if not parent.poll(self._start_timeout):
            _kill(proc)
            parent.close()
            raise KernelCrash("build worker did not start in time")
        try:
            tag, _ = parent.recv()
        except EOFError:
            _kill(proc)
            parent.close()
            raise KernelCrash("build worker died during startup") from None
        if tag != "ready":  # pragma: no cover - protocol invariant
            _kill(proc)
            parent.close()
            raise KernelCrash(f"build worker sent {tag!r} before ready")
        self._proc, self._conn = proc, parent

    def _ensure(self) -> None:
        if self._closed:
            raise KernelCrash("engine is shutting down")
        if self._proc is None or not self._proc.is_alive():
            self._teardown()
            self._spawn()

    def start(self) -> None:
        """Bring the worker up (loading the model via the worker's own startup)
        before serving, so the first client request isn't the one that spawns it.
        A fresh worker after a crash reloads the last good model the same way."""
        self._ensure()

    def _teardown(self) -> None:
        if self._proc is not None:
            _kill(self._proc)
        if self._conn is not None:
            with _suppress():
                self._conn.close()
        self._proc, self._conn = None, None

    def close(self) -> None:
        self._closed = True
        self._teardown()

    @contextlib.contextmanager
    def operation(self, operation_id: str):
        """Bind the writer thread's next live call to one scheduler operation."""
        prior = self._operation_id
        self._operation_id = operation_id
        try:
            yield
        finally:
            self._operation_id = prior

    def _begin_active_call(
        self, operation_id: str | None, journal: list[tuple[str, bytes | None]] | None = None
    ) -> _ActiveCall:
        active = _ActiveCall(operation_id, journal)
        with self._active_lock:
            self._active_call = active
        return active

    def _finish_active_call(self, active: _ActiveCall) -> None:
        with self._active_lock:
            if self._active_call is active:
                active.completed = True
                if active.cancellation_claim is None:
                    self._active_call = None

    def begin_cancel(self, expected_operation_id: str) -> CancelOutcome:
        """Claim a cancellable active call without yet touching its worker."""
        with self._active_lock:
            active = self._active_call
            if active is None or active.operation_id != expected_operation_id:
                return CancelOutcome("not_active")
            if not active.cancellable:
                return CancelOutcome("too_late")
            if active.cancellation_claim is not None:
                return CancelOutcome("not_active")
            claim = object()
            active.cancellation_claim = claim
            return CancelOutcome("claimed", (active, claim))

    def finish_cancel(self, claim: object) -> bool:
        """Tear down only the exact call claimed before scheduler intent was set."""
        active, token = cast(tuple[_ActiveCall, object], claim)
        with self._active_lock:
            if self._active_call is not active or active.cancellation_claim is not token:
                return False
            self._active_call = None
            proc, journal = self._proc, active.journal
        if proc is not None:
            _kill(proc)
        if journal is not None:
            self._rollback_journal(journal)
        return True

    def release_cancel_claim(self, claim: object) -> bool:
        """Release a claim whose completion won before teardown began."""
        active, token = cast(tuple[_ActiveCall, object], claim)
        with self._active_lock:
            if self._active_call is not active or active.cancellation_claim is not token:
                return False
            active.cancellation_claim = None
            if active.completed:
                self._active_call = None
            return True

    def cancel_current(self, expected_operation_id: str) -> bool:
        """Compatibility helper for callers that do not use queue claims."""
        outcome = self.begin_cancel(expected_operation_id)
        return outcome.status == "claimed" and self.finish_cancel(outcome.claim)

    # -- call forwarding ----------------------------------------------------

    def _recv_result(
        self,
        conn: Connection,
        proc: mp.process.BaseProcess,
        timeout: float,
        progress=None,
        *,
        hard_timeout: float | None = None,
        clock=time.monotonic,
    ) -> tuple:
        """Wait for the worker's reply, watching for death and the timeout.

        Returns the raw reply tuple -- ``("ok", result)`` or ``("err", message,
        traceback)`` -- on a reply, or raises ``KernelCrash`` if the worker died
        (native fault) or overran the build timeout."""
        started = clock()
        hard_deadline = started + (hard_timeout if hard_timeout is not None else timeout)
        deadline = min(started + timeout, hard_deadline)
        while True:
            if conn.poll(0.2):
                try:
                    reply = conn.recv()
                except EOFError:
                    raise KernelCrash("the modeling kernel crashed on that operation") from None
                if reply[0] == "verify_override":
                    verifier = self._override_verifier
                    result = (
                        verifier(reply[1], **reply[2]) if verifier is not None else {"ok": False}
                    )
                    conn.send(("verify_result", result))
                    continue
                if reply[0] == "progress":
                    if reply[2] == "publishing":
                        # current.json can commit immediately after this frame. Make
                        # publication the no-cancel boundary before exposing it.
                        with self._active_lock:
                            if self._active_call is not None:
                                self._active_call.cancellable = False
                        conn.send(("publishing_ack", None))
                    now = clock()
                    deadline = min(now + timeout, hard_deadline)
                    if progress is not None:
                        progress(reply[1], reply[2])
                    continue
                return reply
            if not proc.is_alive():
                # Died without sending: drain a possible in-flight reply, else crash.
                if conn.poll(0):
                    with _suppress():
                        return conn.recv()
                raise KernelCrash("the modeling kernel crashed on that operation")
            now = clock()
            if now >= hard_deadline:
                raise WorkerTimeout(
                    f"the build ran past the {int(hard_timeout or timeout)}s hard limit "
                    "and was stopped"
                )
            if now >= deadline:
                raise WorkerTimeout(
                    f"the build ran past the {int(timeout)}s soft limit and was stopped"
                )

    def _journal(self, method: str, args: tuple) -> list[tuple[str, bytes | None]] | None:
        """Snapshot the on-disk files a structural mutation will overwrite, as
        ``[(abspath, prior_bytes_or_None)]``, so the parent can roll them back if
        the worker dies mid-mutation (its own in-worker rollback never runs on a
        native crash). Returns None when there is nothing to journal."""
        if self._model_path is None:
            return None
        root = os.path.dirname(os.path.abspath(self._model_path))
        rels = ["assembly.json"]
        if method == "set_part":
            part_id = args[0] if args else None
            if not isinstance(part_id, str):
                return None
            rels.append(os.path.join("parts", f"{part_id}.py"))
        else:  # set_skeleton also (re)creates assembly.json + switches .gitignore
            rels.extend(["skeleton.py", ".gitignore"])
        snapshot: list[tuple[str, bytes | None]] = []
        for rel in rels:
            path = os.path.join(root, rel)
            try:
                with open(path, "rb") as f:
                    snapshot.append((path, f.read()))
            except OSError:
                snapshot.append((path, None))
        return snapshot

    @staticmethod
    def _rollback_journal(journal: list[tuple[str, bytes | None]]) -> None:
        """Restore each journaled file to its pre-mutation state: rewrite prior
        bytes (atomically), or delete a file that did not exist before."""
        for path, data in journal:
            try:
                if data is None:
                    if os.path.exists(path):
                        os.remove(path)
                else:
                    parent = os.path.dirname(path)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    tmp = path + ".tmp"
                    with open(tmp, "wb") as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, path)
            except OSError:  # best-effort; a rollback failure must not mask the crash
                pass

    def _call(self, method: str, args: tuple, kwargs: dict) -> Any:
        # Only the operation writer (and legacy callers routed through it) may
        # use the live OCC pipe; parent-owned snapshot reads never acquire this.
        with self._pipe_lock:
            return self._call_locked(method, args, kwargs)

    def _call_locked(self, method: str, args: tuple, kwargs: dict) -> Any:
        self._ensure()
        assert self._conn is not None and self._proc is not None
        refresh = method in REFRESH_METHODS
        timeout = self._longrun_timeout if method in LONG_RUNNING_METHODS else self._timeout
        hard_timeout = (
            self._longrun_timeout if method in LONG_RUNNING_METHODS else self._hard_timeout
        )
        journal = self._journal(method, args) if method in JOURNALED_METHODS else None
        active = self._begin_active_call(self._operation_id, journal)
        try:
            self._conn.send((method, args, kwargs, refresh))
        except (OSError, BrokenPipeError, ValueError):
            self._teardown()
            if journal is not None:
                self._rollback_journal(journal)
            raise KernelCrash("the modeling kernel crashed on that operation") from None
        try:
            reply = self._recv_result(
                self._conn,
                self._proc,
                timeout,
                self._heartbeat,
                hard_timeout=hard_timeout,
            )
        except (KernelCrash, WorkerTimeout) as exc:
            # The worker is dead or wedged: drop it so the next call respawns a
            # fresh one that reloads the last good model. For a journaled mutation,
            # roll the poisoned files back from the parent (the worker's own
            # rollback never ran) so the respawn's startup rebuilds a clean model.
            self._teardown()
            if journal is not None:
                self._rollback_journal(journal)
                if isinstance(exc, WorkerTimeout):
                    raise WorkerTimeout(f"{exc}; the {method} was rolled back") from None
                raise KernelCrash(f"{exc}; the {method} was rolled back") from None
            raise
        finally:
            self._finish_active_call(active)
        if reply[0] == "ok":
            return reply[1]
        # A Session method raised (a normal, caught error path): re-raise so the
        # server's handler maps it to an {ok: false} response, exactly as before.
        # The message is already "<Type>: message" (RemoteSessionError lets the
        # server emit it as-is, no second prefix); the traceback (when the worker
        # shipped one) lets the server attach scriptLine for raised errors too.
        message = reply[1] if len(reply) > 1 else "the modeling kernel reported an error"
        tb = reply[2] if len(reply) > 2 else None
        raise RemoteSessionError(str(message), tb)

    def _heartbeat(self, progress: float | None, phase: str | None) -> None:
        callback = getattr(self, "_operation_heartbeat", None)
        if callback is not None:
            callback(progress, phase)

    def __getattr__(self, name: str) -> Any:
        # Only reached for names not defined on the proxy: every Session method.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)

        def forward(*args: Any, **kwargs: Any) -> Any:
            return self._call(name, args, kwargs)

        return forward


def _kill(proc: mp.process.BaseProcess) -> None:
    with _suppress():
        if proc.is_alive():
            proc.kill()
            proc.join(5)


class _suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> bool:
        return True  # swallow everything: teardown must never raise
