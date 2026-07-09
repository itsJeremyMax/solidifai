"""Newline-delimited JSON RPC server over a local IPC endpoint (see ipc.py:
a UNIX-domain socket on unix, token-guarded loopback TCP on Windows).

Two clients reach the engine over this endpoint: the app's UI (via Rust) and
the MCP stdio bridge. Every request is dispatched to a *single* shared
``Session`` under a lock, so builds are serialized and there is exactly one
current model.

Wire format (one JSON object per line):
  request:  {"id": int, "method": str, "params": obj}
  response: {"id": int, "ok": true, "result": any}
        or  {"id": int, "ok": false, "error": str, <structured failure fields...>}

A failed response always carries ``error`` (a string). It MAY also carry additive
structured fields that help a caller debug without bisecting: ``scriptLine`` (the
line in the user's script the failure traces to), ``traceback`` (trimmed to the
user's own frames), and any structured extras the handler returned (e.g.
end_round's per-part ``failed`` map, ``composeEmpty``/``empty`` markers). These are
additive: every field beyond ``error`` is optional, and clients that read only
``error`` keep working. The Rust shell parses with serde_json::Value reading only
ok/result/error, and the MCP bridge ignores unknown fields, so no protocol bump is
needed for a new failure field (bump PROTOCOL_VERSION only for method changes).
"""

from __future__ import annotations

import contextlib
import hmac
import itertools
import json
import logging
import os
import re
import socket
import sys
import threading
from typing import Any

from solidifai_engine import ipc, scratch
from solidifai_engine.worker import RemoteSessionError, SessionProxy

# -- parent-death detection ---------------------------------------------------
# On unix a dead parent reparents the engine, so polling getppid() works. On
# Windows os.getppid() keeps returning the original creator PID forever, so the
# poll never fires and orphaned engines outlive a force-quit shell; wait on the
# parent's process handle instead.

_SYNCHRONIZE = 0x0010_0000
_WAIT_OBJECT_0 = 0
_INFINITE = 0xFFFF_FFFF
# OpenProcess sets this when the PID does not exist (a dead parent); any other
# error (e.g. ACCESS_DENIED) means the parent may well be alive.
_ERROR_INVALID_PARAMETER = 87


def _watchdog_strategy() -> str:
    """Which parent-death signal works here: "handle-wait" (nt) or "ppid-poll"."""
    return "handle-wait" if os.name == "nt" else "ppid-poll"


def _open_parent_handle(ppid: int) -> tuple[int | None, int]:
    """OpenProcess(SYNCHRONIZE) on the parent: (handle, 0), or (None, last_error)
    on failure so the caller can tell "parent already dead" from "can't wait".
    (None, 0) off Windows."""
    if sys.platform != "win32":
        return None, 0
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_SYNCHRONIZE, False, ppid)
    if not handle:
        return None, ctypes.get_last_error()
    return int(handle), 0


def _wait_for_parent_exit(handle: int) -> bool:
    """Block until the parent process handle signals; True iff it exited.

    False means the wait itself failed (never treat that as parent death)."""
    if sys.platform != "win32":
        return False
    import ctypes

    return ctypes.windll.kernel32.WaitForSingleObject(handle, _INFINITE) == _WAIT_OBJECT_0


# -- structured failure envelope ----------------------------------------------
# A failed handler dict carries an error string and (for builds) a full traceback.
# The helpers below distil that into fields an agent can act on: the line in its
# own script, and a traceback trimmed to the user's frames. See the module
# docstring for the wire contract (all fields beyond ``error`` are additive).

# The filename session.execute_script passes to compile(); a traceback frame from
# this file is a line in the user's own script.
_USER_SCRIPT_FILE = "<solidifai-script>"

# A traceback frame whose file path contains one of these markers is engine
# internals (the package, the vendored kernel, the stdlib), not user source;
# trimming drops those so only the user's frames remain.
_INTERNAL_FRAME_MARKERS = (
    "solidifai_engine",
    "build123d",
    "site-packages",
    os.sep + "lib" + os.sep,
)

_TB_FILE_RE = re.compile(r'^  File "(?P<file>.*?)", line (?P<line>\d+)')


def _script_line(tb: str | None) -> int | None:
    """The line number of the last user-script frame in a formatted traceback, or
    None when the traceback has no user-script frame. "Last" = the deepest user
    frame, i.e. where the error actually surfaced in the user's code."""
    if not tb:
        return None
    last: int | None = None
    for raw in tb.splitlines():
        m = _TB_FILE_RE.match(raw)
        if m and m.group("file") == _USER_SCRIPT_FILE:
            last = int(m.group("line"))
    return last


def _trim_traceback(tb: str | None) -> str | None:
    """Trim a formatted traceback to the user's own frames.

    Drops the engine-internal frames (the dispatch/exec plumbing, the kernel, the
    stdlib) so the agent sees its script's frames and the final exception, not
    pages of engine internals. Keeps the header, chaining notes, and the exception
    line verbatim. Falls back to the full traceback when no user frame is present
    (a purely internal error), so a location is never lost."""
    if not tb:
        return None
    lines = tb.splitlines()
    out: list[str] = []
    kept_user_frame = False
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith('  File "'):
            m = _TB_FILE_RE.match(line)
            file = m.group("file") if m else ""
            # A frame is the `  File ...` header plus its more-indented source/caret
            # continuation lines (which are not themselves `  File` headers).
            block = [line]
            j = i + 1
            while j < n and lines[j].startswith("    ") and not lines[j].startswith('  File "'):
                block.append(lines[j])
                j += 1
            internal = file != _USER_SCRIPT_FILE and any(
                marker in file for marker in _INTERNAL_FRAME_MARKERS
            )
            if not internal:
                out.extend(block)
                kept_user_frame = True
            i = j
            continue
        out.append(line)
        i += 1
    if not kept_user_frame:
        return tb
    return "\n".join(out)


def _failure_response(req_id: Any, result: dict) -> dict:
    """Build a failed RPC envelope that carries the handler's structured failure
    fields through to the client.

    The wire contract only guarantees ``error`` (a string), but both real clients
    -- the Rust shell (rpc.rs parses with serde_json::Value, reading only
    ok/result/error) and the MCP bridge -- ignore unknown fields, so these extras
    are purely additive and need no protocol bump. ok:true payloads are untouched;
    a client that reads only ``error`` keeps working."""
    resp: dict[str, Any] = {
        "id": req_id,
        "ok": False,
        "error": result.get("error", "build failed"),
    }
    tb = result.get("traceback")
    line = _script_line(tb)
    if line is not None:
        resp["scriptLine"] = line
    trimmed = _trim_traceback(tb)
    if trimmed:
        resp["traceback"] = trimmed
    # Pass through any other structured fields the handler returned (end_round's
    # `failed`/`built`, composeEmpty/empty markers, buildId, skeletonChanged, ...).
    for key, value in result.items():
        if key not in ("ok", "error", "traceback"):
            resp.setdefault(key, value)
    return resp


class Server:
    def __init__(self, socket_path: str, artifacts_dir: str, model_path: str | None = None):
        self.socket_path = socket_path
        self.artifacts_dir = artifacts_dir
        self.model_path = model_path
        os.makedirs(artifacts_dir, exist_ok=True)

        # Reset the per-session scratch dir on startup (= "reset on workspace
        # open"; the engine is spawned per-workspace). Best-effort: a failure
        # here must never block the server from starting.
        with contextlib.suppress(OSError):
            scratch.clear_scratch(artifacts_dir)

        # The Session runs in a crash-isolated worker process (see worker.py): a
        # native kernel fault (a degenerate fillet, a bad boolean) kills only the
        # worker, which the proxy respawns, instead of taking the engine down.
        self._session = SessionProxy(artifacts_dir, model_path=model_path)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._token: str | None = None  # set by _bind on the TCP transport
        # Names each connection thread so interleaved per-connection logs stay
        # attributable. next() is atomic under the GIL, so no extra lock is needed.
        self._conn_counter = itertools.count(1)

        # Point the material resolver at this workspace so builds resolve the
        # workspace + global materials (not just the built-ins).
        from solidifai_engine import materials

        materials.configure_resolver(self._workspace_root())

    def _workspace_root(self) -> str:
        """The workspace root for this engine.

        Derived from the model path (the app spawns us with
        ``--model <root>/model.py``); falls back to the artifacts grandparent
        (artifacts live at ``<root>/.solidifai/artifacts``)."""
        if self.model_path:
            return os.path.dirname(os.path.abspath(self.model_path))
        return os.path.dirname(os.path.dirname(os.path.abspath(self.artifacts_dir)))

    def _refresh_resolver(self) -> None:
        """Re-read the global + workspace material libraries from disk so a
        material created/edited after engine start is always resolvable. Cheap
        (two small JSON reads) next to any build/render."""
        from solidifai_engine import materials

        materials.configure_resolver(self._workspace_root())

    # -- lifecycle ----------------------------------------------------------

    def _bind(self) -> socket.socket:
        # Owner-only either way: unix socket mode 0600, or a token handshake on
        # the Windows TCP substitute. No other local account may drive the
        # engine (execute_script et al.).
        sock, self._token = ipc.bind(self.socket_path)
        sock.listen(8)
        sock.settimeout(0.2)
        return sock

    def _load_startup_model(self) -> None:
        """Bring the workspace's model + saved settings live on startup. Never
        crash the server if the worker or model fail to load.

        Spawning the worker runs ``Session.startup()`` inside it exactly once
        (which itself never raises); the try/except here guards the spawn."""
        try:
            self._session.start()
        except Exception:  # noqa: BLE001 - never crash on a bad model / worker
            logging.getLogger(__name__).exception("startup failed")

    def _start_parent_watchdog(self) -> None:
        """Exit when the parent process dies.

        The app can't signal the engine on a force-quit/crash, so without this the
        engine lingers on a dead socket. A daemon thread detects parent death per
        the platform strategy (see _watchdog_strategy) and hard-exits. os._exit
        (not sys.exit) so a main thread wedged in a native OCC/VTK call can't
        block it."""
        original_ppid = os.getppid()

        def poll() -> None:
            # Unix: a dead parent reparents us, so getppid() changes.
            while not self._stop.wait(1.0):
                if os.getppid() != original_ppid:
                    os._exit(0)

        target = poll
        if _watchdog_strategy() == "handle-wait":
            handle, err = _open_parent_handle(original_ppid)
            if handle is not None:

                def wait() -> None:
                    if _wait_for_parent_exit(handle):
                        os._exit(0)
                    poll()  # wait failed mid-flight: degrade rather than exit spuriously

                target = wait
            elif err == _ERROR_INVALID_PARAMETER:
                # The shell died in the spawn->watchdog window: the PID no longer
                # exists, so we are already orphaned — and on Windows the ppid
                # fallback would never fire. Exit now instead of lingering forever.
                logging.getLogger(__name__).warning(
                    "parent watchdog: parent %d already gone at startup; exiting",
                    original_ppid,
                )
                os._exit(0)
            else:
                logging.getLogger(__name__).warning(
                    "parent watchdog: OpenProcess(%d) failed (error %d);"
                    " falling back to ppid polling",
                    original_ppid,
                    err,
                )

        threading.Thread(target=target, name="parent-watchdog", daemon=True).start()

    def serve_forever(self) -> None:
        self._start_parent_watchdog()
        self._sock = self._bind()
        self._load_startup_model()
        # Concurrency model: one daemon thread per connection. accept() hands each
        # connection straight to its own thread and loops, so a client that connects
        # then sits idle (or pauses between requests) no longer starves everyone
        # else -- the GUI shell, the MCP bridge, and the file watcher all share this
        # one endpoint, and any one of them could stall.
        #
        # Request DISPATCH stays serialized through self._lock (held in _dispatch),
        # so exactly one request ever runs against the Session at a time: the
        # single-engine-writer invariant holds, and two clients mid-request behave
        # exactly as before (the second blocks on the lock). Responses stay ordered
        # per connection because each connection's thread reads, dispatches, and
        # writes one request at a time. Threads are daemon and each reaps itself on
        # disconnect/error, so shutdown (self._stop + closing the listen socket)
        # still exits cleanly and connections never accumulate.
        try:
            while not self._stop.is_set():
                try:
                    conn, _ = self._sock.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                conn_id = next(self._conn_counter)
                threading.Thread(
                    target=self._handle_connection,
                    args=(conn, conn_id),
                    name=f"engine-conn-{conn_id}",
                    daemon=True,
                ).start()
        finally:
            self._close()

    def shutdown(self) -> None:
        self._stop.set()
        # Nudge accept() loop and clean up the socket file.
        self._close()
        # Tear down the build worker so it doesn't linger.
        with contextlib.suppress(Exception):
            self._session.close()

    def _close(self) -> None:
        if self._sock is not None:
            with contextlib.suppress(OSError):
                self._sock.close()
            self._sock = None
        if os.path.exists(self.socket_path):
            with contextlib.suppress(OSError):
                os.unlink(self.socket_path)

    # -- connection / dispatch ---------------------------------------------

    def _handle_connection(self, conn: socket.socket, conn_id: int = 0) -> None:
        logging.getLogger(__name__).debug("conn %d: open", conn_id)
        with conn:
            # Poll rather than block forever on recv so the thread notices shutdown
            # (and an idle connection is reaped): a timeout just re-checks _stop and
            # keeps the (possibly idle) connection open for its next request.
            conn.settimeout(1.0)
            buf = b""
            authed = self._token is None
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except TimeoutError:
                    continue  # idle between requests; loop back to re-check _stop
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                # TCP transport: the first line must be the shared token; drop
                # the connection on any mismatch (or an oversized first line).
                if not authed and len(buf) > 1024:
                    return
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not authed:
                        presented = line.decode("utf-8", "replace")
                        if not hmac.compare_digest(presented, self._token or ""):
                            return
                        authed = True
                        continue
                    if not line:
                        continue
                    response = self._handle_line(line)
                    try:
                        conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                    except OSError:
                        return

    def _handle_line(self, line: bytes) -> dict:
        try:
            request = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            return {"id": None, "ok": False, "error": f"invalid JSON: {exc}"}

        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        try:
            result = self._dispatch(method, params)
        except RemoteSessionError as exc:
            # The worker already formatted the Session error as "<Type>: message";
            # surface it verbatim so the original exception type isn't buried under
            # a second (RemoteSessionError) prefix. Route through _failure_response
            # so a raised error also gets scriptLine + a trimmed traceback when the
            # worker shipped one, matching the {ok: false} return path.
            result: dict[str, Any] = {"ok": False, "error": str(exc)}
            if exc.traceback:
                result["traceback"] = exc.traceback
            return _failure_response(req_id, result)
        except Exception as exc:  # noqa: BLE001
            return {"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

        # Methods that already return an {ok: false, error: ...} envelope
        # (e.g. a failed build) are surfaced as a failed RPC response, carrying
        # their structured failure fields through so the caller can debug.
        if isinstance(result, dict) and result.get("ok") is False:
            return _failure_response(req_id, result)

        return {"id": req_id, "ok": True, "result": result}

    @staticmethod
    def _require(params: dict, key: str) -> Any:
        """Fetch a required param, raising a clean error (surfaced to the client
        as ok:false) instead of a raw KeyError when it is missing."""
        if key not in params:
            raise ValueError(f"missing param {key!r}")
        return params[key]

    def _dispatch(self, method: str, params: dict) -> Any:
        with self._lock:
            handler = _HANDLERS.get(method)
            if handler is None:
                raise ValueError(f"unknown method: {method!r}")
            # The material resolver is refreshed inside the worker before the
            # methods that build/render (worker.REFRESH_METHODS), since that is
            # where geometry now runs; nothing to do here.
            return handler(self, params)


def _h_list_materials(srv: Server, p: dict) -> Any:
    # Lazy import keeps the materials module (and its OCC color deps) off the
    # server import path until a client actually asks for the library.
    from solidifai_engine import materials

    return materials.list_effective(srv._workspace_root())


def _h_get_manufacturing_profile(srv: Server, p: dict) -> Any:
    from solidifai_engine import manufacturing_profile

    return manufacturing_profile.effective(srv._workspace_root())


def _h_set_manufacturing_profile(srv: Server, p: dict) -> Any:
    from solidifai_engine import control, manufacturing_profile

    # Rust is the sole writer; delegate over the control channel, then return the
    # freshly resolved view (re-reads disk, echoes the default material).
    control.write(
        scope=p.get("scope", "workspace"),
        workspace_root=srv._workspace_root(),
        values=p.get("values") or {},
        unset=p.get("unset") or [],
    )
    srv._refresh_resolver()
    return manufacturing_profile.effective(srv._workspace_root())


def _h_lookup_standard(srv: Server, p: dict) -> Any:
    from solidifai_engine import standards

    return standards.lookup_standard(srv._require(p, "query"), workspace_root=srv._workspace_root())


def _h_lookup_reference(srv: Server, p: dict) -> Any:
    from solidifai_engine import standards

    return standards.lookup_reference(srv._require(p, "object"))


def _h_save_reference(srv: Server, p: dict) -> Any:
    from datetime import date

    from solidifai_engine import control, workspace_metadata

    # Strip None values so setdefault fills them in cleanly below.
    entry = {k: v for k, v in dict(srv._require(p, "entry")).items() if v is not None}
    for key in ("id", "category", "dims_mm", "source"):
        if not entry.get(key):
            raise ValueError(f"entry is missing {key!r}")
    entry.setdefault("origin", "learned")
    entry.setdefault("verified_at", date.today().isoformat())
    meta = workspace_metadata.load_metadata(srv._workspace_root())
    entry.setdefault("verified_in", meta.get("name") or "")
    try:
        library = control.write_reference(entry)
    except control.ControlError as exc:
        raise RuntimeError(
            f"reference library unavailable ({exc}); keep the verified dims in the build brief"
        ) from exc
    return {"saved": entry, "count": len(library.get("objects", []))}


def _orient_overhang(srv: Server, p: dict) -> float:
    """The overhang angle for fab_orient: explicit param, else the workspace
    manufacturing profile's process.overhangDeg, else 45."""
    given = p.get("overhang_deg")
    if given is not None:
        return float(given)
    from solidifai_engine import manufacturing_profile

    prof = manufacturing_profile.resolve(srv._workspace_root())
    return float((prof.get("process") or {}).get("overhangDeg", 45))


# RPC method registry: method name -> handler(server, params) -> raw result.
# The handle() wrapper adds the {ok, ...} envelope and maps exceptions. A table
# keeps the surface O(1) and introspectable (tests/test_surface_parity.py locks
# it against the MCP tool set) instead of an ever-growing if/elif.
# When this contract changes (add/remove/rename a method), bump PROTOCOL_VERSION
# in solidifai_engine/protocol.py so the Rust host rejects a stale engine loudly.
_HANDLERS: dict[str, Any] = {
    "ping": lambda srv, p: "pong",
    "execute_script": lambda srv, p: srv._session.execute_script(srv._require(p, "code")),
    "run_file": lambda srv, p: srv._session.run_file(srv._require(p, "path")),
    "render": lambda srv, p: srv._session.render(),
    "get_model_info": lambda srv, p: srv._session.get_model_info(),
    "list_materials": _h_list_materials,
    "get_manufacturing_profile": _h_get_manufacturing_profile,
    "set_manufacturing_profile": _h_set_manufacturing_profile,
    "lookup_standard": _h_lookup_standard,
    "lookup_reference": _h_lookup_reference,
    "save_reference": _h_save_reference,
    "get_params": lambda srv, p: srv._session.get_params(),
    "inspect_features": lambda srv, p: srv._session.inspect_features(),
    "check_interferences": lambda srv, p: srv._session.check_interferences(),
    "analyze_dfm": lambda srv, p: srv._session.analyze_dfm(p.get("process")),
    "measure": lambda srv, p: srv._session.measure(),
    "stress_check": lambda srv, p: srv._session.stress_check(),
    "tolerance_stack": lambda srv, p: srv._session.tolerance_stack(p.get("chain")),
    "get_workspace_meta": lambda srv, p: srv._session.get_workspace_meta(),
    "set_workspace_meta": lambda srv, p: srv._session.set_workspace_meta(
        srv._require(p, "patch"), force=bool(p.get("force", False)), user=bool(p.get("user", False))
    ),
    "set_workspace_name": lambda srv, p: srv._session.set_workspace_name(srv._require(p, "name")),
    "dismiss_proposed_name": lambda srv, p: srv._session.dismiss_proposed_name(),
    "set_requirements": lambda srv, p: srv._session.set_requirements(p.get("requirements")),
    "check_requirements": lambda srv, p: srv._session.check_requirements(),
    "propose_build": lambda srv, p: srv._session.propose_build(srv._require(p, "brief")),
    "get_build_brief": lambda srv, p: srv._session.get_build_brief(),
    "sweep": lambda srv, p: srv._session.sweep(
        srv._require(p, "param"), p.get("values") or [], bool(p.get("checks", False))
    ),
    "optimize": lambda srv, p: srv._session.optimize(
        srv._require(p, "param"),
        p.get("objective", "min_mass"),
        int(p.get("steps", 9)),
        p.get("constraints"),
        p.get("values"),
    ),
    "check_motion": lambda srv, p: srv._session.check_motion(
        srv._require(p, "part"),
        p.get("kind", "revolute"),
        p.get("axis_origin"),
        p.get("axis_dir"),
        float(p.get("start", 0.0)),
        float(p.get("stop", 90.0)),
        int(p.get("steps", 12)),
    ),
    "analyze_import": lambda srv, p: srv._session.analyze_import(p.get("name")),
    "diff_against": lambda srv, p: srv._session.diff_against(int(srv._require(p, "index"))),
    "build_report": lambda srv, p: srv._session.build_report(p.get("views")),
    "import_reference": lambda srv, p: srv._session.import_reference(
        srv._require(p, "path"), p.get("name")
    ),
    "stage_import": lambda srv, p: srv._session.stage_import(srv._require(p, "path")),
    "remove_import": lambda srv, p: srv._session.remove_import(srv._require(p, "id")),
    "list_imports": lambda srv, p: srv._session.list_imports(),
    "create_drawing": lambda srv, p: srv._session.create_drawing(p.get("path"), p.get("options")),
    "set_feature": lambda srv, p: srv._session.set_feature(
        srv._require(p, "name"), srv._require(p, "values")
    ),
    "feature_at": lambda srv, p: srv._session.feature_at(
        srv._require(p, "point"), tolerance_mm=p.get("tolerance_mm")
    ),
    "set_params": lambda srv, p: srv._session.set_params(srv._require(p, "values")),
    "set_part_material": lambda srv, p: srv._session.set_part_material(
        srv._require(p, "part_id"), p.get("material")
    ),
    "export": lambda srv, p: srv._session.export(
        srv._require(p, "format"), p.get("path"), p.get("options")
    ),
    "capture_views": lambda srv, p: srv._session.capture_views(
        p.get("views"),
        p.get("layout") or "separate",
        p.get("color", True),
        explode=p.get("explode") or 0.0,
        highlight=p.get("highlight"),
        resolution=p.get("resolution") or 512,
        section=p.get("section"),
        focus=p.get("focus"),
    ),
    "undo": lambda srv, p: srv._session.undo(),
    "redo": lambda srv, p: srv._session.redo(),
    "goto": lambda srv, p: srv._session.goto(srv._require(p, "index")),
    "history": lambda srv, p: srv._session.history_state(),
    "checkpoint": lambda srv, p: srv._session.checkpoint(srv._require(p, "message")),
    "fab_detect": lambda srv, p: srv._session.fab_detect(),
    "fab_profiles": lambda srv, p: srv._session.fab_profiles(),
    "fab_estimate": lambda srv, p: srv._session.fab_estimate(p.get("destination_id")),
    "fab_orient": lambda srv, p: srv._session.fab_orient(_orient_overhang(srv, p)),
    "fab_open": lambda srv, p: srv._session.fab_open(p.get("destination_id")),
    "list_destinations": lambda srv, p: srv._session.list_destinations(),
    "set_destinations": lambda srv, p: srv._session.set_destinations(
        srv._require(p, "destinations")
    ),
    "converge_to_spec": lambda srv, p: srv._session.converge_to_spec(
        p.get("objective", "min_mass"), p.get("apply", False)
    ),
    # Assembly authoring: write skeleton/parts and edit the tree.
    "set_skeleton": lambda srv, p: srv._session.set_skeleton(srv._require(p, "code")),
    "set_part": lambda srv, p: srv._session.set_part(
        srv._require(p, "id"),
        srv._require(p, "code"),
        attach=p.get("attach"),
        inputs=p.get("inputs"),
        shape_inputs=p.get("shape_inputs"),
        kind=p.get("kind", "part"),
    ),
    "get_part_info": lambda srv, p: srv._session.get_part_info(srv._require(p, "id")),
    "get_assembly_tree": lambda srv, p: srv._session.get_assembly_tree(),
    "export_flat_model": lambda srv, p: srv._session.export_flat_model(
        write=bool(p.get("write", False))
    ),
    "check_interfaces": lambda srv, p: srv._session.check_interfaces(),
    "attach": lambda srv, p: srv._session.attach(srv._require(p, "id"), p.get("frame")),
    "set_inputs": lambda srv, p: srv._session.set_inputs(
        srv._require(p, "id"), p.get("inputs") or []
    ),
    "remove_part": lambda srv, p: srv._session.remove_part(srv._require(p, "id")),
    "add_subassembly": lambda srv, p: srv._session.add_subassembly(
        srv._require(p, "id"),
        attach=p.get("attach"),
        inputs=p.get("inputs"),
    ),
    "build_part": lambda srv, p: srv._session.build_part(srv._require(p, "id")),
    # Authoring round: freeze the skeleton, defer compose, then compose once.
    "begin_round": lambda srv, p: srv._session.begin_round(),
    "end_round": lambda srv, p: srv._session.end_round(),
    "abort_round": lambda srv, p: srv._session.abort_round(),
}

# The set of methods that need the material resolver refreshed before they run
# now lives in worker.py (worker.REFRESH_METHODS): the resolver is configured in
# the worker process, where the build/render actually happens.
