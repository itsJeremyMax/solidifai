"""MCP stdio bridge to the solidifai engine endpoint.

External coding agents spawn this bridge over stdio. Each tool call is forwarded
as a single newline-delimited JSON RPC request to the engine's local IPC
endpoint (located via the ``SOLIDIFAI_ENGINE_SOCK`` env var; a UNIX socket on
unix, token-guarded loopback TCP on Windows) and the JSON result is returned.

This module MUST NOT import build123d -- it is a thin transport only
(solidifai_engine.ipc is transport-only too; the package __init__ is empty).
"""

from __future__ import annotations

import itertools
import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from solidifai_engine import ipc
from solidifai_engine.protocol import CAPABILITIES, PROTOCOL_VERSION

ENV_SOCK = "SOLIDIFAI_ENGINE_SOCK"

# A hung engine must eventually fail a tool call instead of blocking it forever,
# but long runs are legitimate: sweep/optimize/converge get up to
# SOLIDIFAI_LONGRUN_TIMEOUT (1200s default) inside the engine worker, and a normal
# build up to 180s. Sit comfortably above that ceiling so only a truly wedged
# engine trips this timeout, never a real build.
_LONGRUN_CEILING = float(os.environ.get("SOLIDIFAI_LONGRUN_TIMEOUT", "1200"))
_SOCKET_TIMEOUT = _LONGRUN_CEILING + 600.0

_id_counter = itertools.count(1)


class EngineError(RuntimeError):
    """Raised when the engine returns an error response or is unreachable.

    ``payload`` carries the structured failure fields from an ok:false response
    (scriptLine, traceback, a per-part ``failed`` map, ...) so the tool layer can
    surface them instead of dropping everything but the message."""

    def __init__(self, message: str, *, payload: dict | None = None):
        super().__init__(message)
        self.payload = payload or {}


def _engine_sock_path() -> str:
    path = os.environ.get(ENV_SOCK)
    if not path:
        raise EngineError(f"{ENV_SOCK} is not set; cannot reach the engine")
    return path


def forward(method: str, params: dict | None = None) -> Any:
    """Send one RPC request to the engine and return its ``result``.

    Raises ``EngineError`` if the engine reports ``ok == false``, the socket
    cannot be reached, or the connection is interrupted or hangs. On an ok:false
    response the raised error carries the engine's structured failure fields on
    its ``payload`` (scriptLine, traceback, a per-part ``failed`` map, ...).
    """
    sock_path = _engine_sock_path()
    request = {
        "id": next(_id_counter),
        "method": method,
        "params": params or {},
        "client": {"protocol": PROTOCOL_VERSION, "capabilities": sorted(CAPABILITIES)},
    }

    try:
        conn = ipc.connect(sock_path)
    except OSError as exc:
        raise EngineError(f"cannot connect to engine at {sock_path}: {exc}") from exc

    # Bound the round-trip so a truly hung engine fails cleanly instead of blocking
    # the tool call forever (see _SOCKET_TIMEOUT: comfortably above the longest
    # legal build, so a real long run is never cut off).
    conn.settimeout(_SOCKET_TIMEOUT)
    try:
        conn.sendall((json.dumps(request) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
    except TimeoutError as exc:
        raise EngineError(
            f"engine did not respond within {int(_SOCKET_TIMEOUT)}s; it may be hung, retry"
        ) from exc
    except OSError as exc:
        raise EngineError("engine connection interrupted; retry") from exc
    finally:
        conn.close()

    if not buf:
        raise EngineError("engine closed the connection without responding")

    # A truncated line (the engine died mid-reply) is not valid JSON; surface it as
    # a clean, retryable error instead of letting JSONDecodeError escape raw.
    try:
        response = json.loads(buf.decode("utf-8").splitlines()[0])
    except (ValueError, UnicodeDecodeError, IndexError) as exc:
        raise EngineError("engine connection interrupted; retry") from exc

    if not response.get("ok"):
        error = response.get("error", "engine returned an error")
        # Keep every structured failure field the engine sent (scriptLine,
        # traceback, failed map, ...) so _call can surface them to the agent.
        extras = {k: v for k, v in response.items() if k not in ("id", "ok", "result", "error")}
        raise EngineError(error, payload=extras)
    return response.get("result")


def _call(method: str, params: dict | None = None) -> Any:
    """Forward and convert engine errors into a return value (MCP tools should not
    raise raw transport exceptions at the agent). On a failed build the returned
    dict includes the engine's structured fields (scriptLine, traceback, a per-part
    ``failed`` map, ...), and the error text names the script line when known."""
    try:
        return forward(method, params)
    except EngineError as exc:
        message = str(exc)
        payload = exc.payload
        line = payload.get("scriptLine")
        if isinstance(line, int):
            message = f"{message} (line {line})"
        return {"error": message, **payload}


mcp = FastMCP("solidifai")


@mcp.tool()
def execute_script(code: str) -> Any:
    """Execute a build123d script and rebuild the current model."""
    return _call("execute_script", {"code": code})


@mcp.tool()
def run_file(path: str) -> Any:
    """Execute a build123d script from a file path."""
    return _call("run_file", {"path": path})


@mcp.tool()
def set_params(values: dict) -> Any:
    """Override parameter values and rebuild the current model."""
    return _call("set_params", {"values": values})


@mcp.tool()
def get_params() -> Any:
    """Return the current parameter schema and values."""
    return _call("get_params")


@mcp.tool()
def get_model_info() -> Any:
    """Return the current model.json (objects, bbox, volume, mass, ...)."""
    return _call("get_model_info")


@mcp.tool()
def list_materials() -> Any:
    """List the materials available in this workspace, with the default flagged.

    Each entry has: id (the name to use in model.py), label, base substance,
    colorHex, finish, process (fdm, sla, cnc, or injection), density, and
    isDefault. Use the default's process to pick the right design rules, and set
    an object's material by its id when you build the model. If the user has not
    asked for a specific material, use the default."""
    return _call("list_materials")


@mcp.tool()
def get_manufacturing_profile() -> Any:
    """Read this workspace's manufacturing profile: the configurable defaults Sol
    builds to. Returns the resolved fit class + clearance map, default wall,
    fillet/edge-break, min feature, the process (kind, nozzle, layer, overhang,
    infill), advisory fabrication settings (nozzle/bed temp, filament cost), and
    the default `material` (echoed read-only from the materials library). Use
    these as your defaults unless the user asks otherwise."""
    return _call("get_manufacturing_profile")


@mcp.tool()
def set_manufacturing_profile(
    values: dict | None = None, unset: list[str] | None = None, scope: str = "workspace"
) -> Any:
    """Change one or more manufacturing-profile defaults. `values` is a sparse
    object with any of: design (fit: loose|normal|tight, wallMm, filletMm,
    minFeatureMm), fits (looseMm/normalMm/tightMm), process (kind, nozzleMm,
    layerMm, overhangDeg, infillPct), fabrication (nozzleTempC, bedTempC,
    filamentCostPerKg). `unset` is a list of dotted keys to reset to the inherited
    value (e.g. ["design.wallMm"]). `scope` is "workspace" (default) or "global".
    Does not accept `material` (that lives in the materials library). Returns the
    updated resolved profile."""
    return _call(
        "set_manufacturing_profile",
        {"values": values or {}, "unset": unset or [], "scope": scope},
    )


@mcp.tool()
def lookup_standard(query: str) -> Any:
    """Look up standard hardware dimensions before modeling them: metric screw
    head dims (ISO 4762 cap / ISO 7380-1 button / ISO 10642 countersunk, M2-M8),
    clearance and pilot hole diameters (ISO 273, resolved through this
    workspace's manufacturing-profile fit), heat-set insert install holes
    (M2-M5), hex nuts (ISO 4032), washers (ISO 7089), and bearings 608/625/6201.
    Query by size and kind: "M3 clearance", "M4 heat-set insert", "608 bearing";
    a bare size returns everything for it. All values are published data with
    sources; prefer this over recalling numbers. Read-only (scout-safe)."""
    return _call("lookup_standard", {"query": query})


@mcp.tool()
def lookup_reference(object: str) -> Any:
    """Look up verified real-world dims for a named object from the reference
    library: a builtin seed of universal items (18650/21700/AA/AAA cells,
    USB-A/USB-C/HDMI/micro-HDMI port cutouts) plus every object saved with
    save_reference in past sessions. Returns the envelope, mounting holes or
    cutouts where applicable, design notes, provenance, and the source for each
    entry. Check here FIRST when a brief names a real object (the grounding
    skill's verified-dims rule); a miss returns what is available, then
    web-verify and save_reference the result. Read-only (scout-safe)."""
    return _call("lookup_reference", {"object": object})


@mcp.tool()
def save_reference(
    id: str,
    category: str,
    dims_mm: dict,
    source: str,
    aliases: list[str] | None = None,
    mounting_holes: dict | None = None,
    notes: str | None = None,
) -> Any:
    """Save a web-verified object's dims to the user's reference library so
    lookup_reference finds it in every future session. Call right after the
    grounding hard rule verifies a named object against a datasheet or official
    drawing, then tell the user in one line that you saved it. id is kebab-case
    ("raspberry-pi-5"); category is a short kind ("sbc", "cell", "port-cutout",
    "display-module", ...); dims_mm holds the governing dims, numbers or
    number lists (e.g. {"pcb": [85.0, 56.0, 1.4], "height_max": 18.0}); source
    is the URL you verified against. aliases are the names a user might say.
    Needs the app running; when it is not, the save fails soft and the dims
    stay in the build brief. Not for scouts: workers report dims back instead
    of saving."""
    entry = {
        "id": id,
        "category": category,
        "dims_mm": dims_mm,
        "source": source,
        "aliases": aliases,
        "mounting_holes": mounting_holes,
        "notes": notes,
    }
    return _call("save_reference", {"entry": {k: v for k, v in entry.items() if v is not None}})


@mcp.tool()
def report_issue(
    title: str,
    what_happened: str,
    steps: str | None = None,
    context: str | None = None,
    agent: str | None = None,
) -> Any:
    """Build a prefilled GitHub bug-report link for the user to review and submit.
    Use only through the solidifai-bug-report skill, after real debugging points to
    a genuine product defect, or when the user asks to file a bug. Supply `title`,
    `what_happened`, and optionally `steps` and `context` -- curated, safely
    shareable error or log excerpts. Never put file contents, secrets, absolute
    paths, or proprietary design details in any field; the engine also redacts home
    paths and secrets as a backstop. It auto-fills the app version, OS, and a safe
    diagnostics block, then returns {url, preview}. Show `preview` to the user (it is
    what becomes public) and give them `url` to click; they can still edit on GitHub
    before submitting. This never submits anything -- the click is the consent.
    `agent` is one of: Claude Code, Codex, opencode, Not agent-related."""
    return _call(
        "report_issue",
        {
            "title": title,
            "what_happened": what_happened,
            "steps": steps,
            "context": context,
            "agent": agent,
        },
    )


@mcp.tool()
def inspect_features() -> Any:
    """List the model's targetable features. Each entry gives the feature's
    name, kind, the parameter(s) that drive it (``driven_by``), its source
    line, and whether it was auto-detected. Use it to find which geometry a
    change should target, then edit a driven feature with ``set_feature``.

    An untagged model returns best-effort inferred features (``inferred: true``
    with a ``confidence``) for detected round features; these have no driving
    parameter and cannot be changed by ``set_feature`` until you name them in
    the script with a ``feature(...)`` block. Declared features take precedence.

    In assembly mode features are listed too, namespaced ``<part>/<name>`` (e.g.
    ``pin/center_bore``) and carrying a ``part`` field. A feature whose
    ``driven_by`` names a skeleton parameter is settable via ``set_feature``;
    a mis-wired ``driven_by`` shows a ``warning`` naming the available params."""
    return _call("inspect_features")


@mcp.tool()
def check_interferences() -> Any:
    """Check the shown parts for interference and connectivity problems.

    Returns, for each shown part, whether its solids are a single body,
    touching, internally overlapping, or disconnected/floating; and for each
    pair of parts whether they ``overlap`` (interpenetrate, with overlap
    volume), are ``adjacent`` (touching, the normal mating case), or ``clear``.
    Advisory: it never changes the model. Use it in self-verify, then decide
    whether each flag is intended (a fused boss, a designed press-fit) or a
    defect (a mating pair that interpenetrates, a floating lump)."""
    return _call("check_interferences")


@mcp.tool()
def analyze_dfm(process: str | None = None) -> Any:
    """Check the current model for manufacturability (DFM) problems and return a
    structured report. Measures real geometry: thin walls (sampled ray-cast),
    overhangs steeper than the support-free angle, long unsupported bridges, and
    holes below a reliable-print minimum. ``process`` overrides the per-part
    material inference; currently evaluates ``fdm`` only (other processes are reported
    as not-yet-supported, never with a wrong number). Each violation carries its
    severity, the measured value vs the threshold, a representative location, and
    the source. Advisory: it never changes the model. Use it in self-verify,
    then fix the flags that matter (a thin structural wall, a steep functional
    overhang) and re-check; a flag on an intentionally thin cosmetic rib may be
    fine to leave."""
    return _call("analyze_dfm", {"process": process})


@mcp.tool()
def measure() -> Any:
    """Mass properties of the current model: per-part and assembly-total volume,
    surface area, mass, center of mass, and the inertia tensor with principal
    moments and axes. Exact (straight from the B-rep), not sampled. Use it to
    verify a weight budget, find where a part balances, or get inertia for a
    motion calc. Advisory: it never changes the model."""
    return _call("measure")


@mcp.tool()
def measure_between(a: Any, b: Any, mode: str = "min") -> Any:
    """Distance between two things in the current model: the "how far apart" tool.

    Each of ``a`` and ``b`` is a TARGET, one of:
      - a feature name: single-model ``"bore"`` or assembly/occurrence
        ``"wheel@2/bore"`` (as listed by inspect_features),
      - a part / object / occurrence name: ``"base"`` or ``"wheel@2"``,
      - a face id from query_faces: ``"wheel@2:f13"``,
      - a literal point: ``[x, y, z]`` in millimetres (build123d Z-up).

    Returns ``min_distance`` (closest approach, exact B-rep, with the
    ``closest_points`` pair), ``center_distance`` (between the targets' centers),
    and ``distance`` (the value for the chosen ``mode``). When BOTH targets are
    cylindrical (a hole, boss, pin, or a cylindrical face) it also returns
    ``axis_distance`` (perpendicular distance between the two axis lines, for
    bolt-pattern / bore-spacing reasoning) and ``axis_angle_deg`` (0 = parallel).

    ``mode`` selects which value ``distance`` reports: ``"min"`` (default),
    ``"center"``, or ``"axis"`` (requires two cylindrical targets). Read-only.

    Example: ``measure_between("base/mount_hole", "wheel@2:f13")`` gives the gap
    from a hole to a specific face; ``measure_between("hole_a", "hole_b",
    mode="axis")`` gives the exact center-to-center spacing of two parallel bores.
    Face ids are only valid until the next rebuild -- re-run query_faces after any
    geometry change."""
    return _call("measure_between", {"a": a, "b": b, "mode": mode})


@mcp.tool()
def query_faces(filter: dict | None = None) -> Any:
    """Enumerate the current model's faces matching a filter: face-level
    addressing without a GUI picker. ``filter`` is a dict, all keys optional:
      - ``object``: restrict to one part/occurrence (``"wheel@2"``),
      - ``type``: ``"planar"`` | ``"cylindrical"`` | ``"conical"`` |
        ``"spherical"`` | ``"toroidal"`` | ``"other"``,
      - ``axis``: ``[x, y, z]`` -- keep faces whose normal (planar) or rotation
        axis (round) aligns with this direction, within ``axis_tol_deg``
        (default 5),
      - ``area_min`` / ``area_max``: face area bounds in mm^2,
      - ``sort``: ``"area_desc"`` (default) or ``"area_asc"``,
      - ``limit``: max hits (default 20).

    Each hit is ``{id, object, type, center, normal_or_axis, area, bbox}`` plus
    ``radius`` for round faces. The ``id`` (e.g. ``"wheel@2:f13"``) is a stable
    index into a deterministic enumeration and is ONLY valid until the next
    rebuild -- feed it straight into measure_between, then re-query after any
    geometry change. ``total_matched`` reports how many matched before ``limit``.

    Example: ``query_faces({"type": "planar", "axis": [0, 0, 1], "sort":
    "area_desc"})`` finds the large up-facing flats (candidate top surfaces)."""
    return _call("query_faces", {"filter": filter})


@mcp.tool()
def thickness_at(point: list[float], direction: list[float] | None = None) -> Any:
    """Local material (wall) thickness at a point: the "how thick is the wall
    here" tool. ``point`` is ``[x, y, z]`` in millimetres (build123d Z-up); it
    snaps to the nearest part surface, then casts a ray through the solid and
    measures to the far wall. Pass ``direction`` ``[x, y, z]`` to force the side
    the ray enters from (it casts along the OPPOSITE direction, into the
    material); by default it casts inward along the surface normal.

    Returns ``{ok, thickness, object, point, direction}`` where ``point`` is the
    surface point measured from. Read-only; works in single-model and assembly
    modes and on mirrored occurrences.

    Example: ``thickness_at([10, 0, 5])`` reports the wall thickness at that spot
    (e.g. ``thickness: 2.4``). Get a candidate point from a query_faces hit's
    ``center``."""
    args: dict[str, Any] = {"point": point}
    if direction is not None:
        args["direction"] = direction
    return _call("thickness_at", args)


@mcp.tool()
def stress_check() -> Any:
    """First-order stress check: flags sharp internal (re-entrant) corners where
    stress concentrates. Geometric heuristic, not a solved stress field, so it
    tells you WHERE load will concentrate and what fillet relieves it, not a
    stress number. Each hot-spot carries its severity, a location, and a fix
    hint. Advisory: it never changes the model. Use it in self-verify, then add
    a fillet where a flagged corner carries real load."""
    return _call("stress_check")


@mcp.tool()
def tolerance_stack(chain: list) -> Any:
    """Compute a 1-D tolerance stack over an ordered chain of links. Each link is
    {label, nominal, plus, minus, direction} or {label, nominal, fit, direction}
    where fit is an ISO 286 class (H7/H8/H9/H11 holes; g6/h6/h7/f7/k6/p6 shafts)
    and direction is +1 or -1. Returns the nominal sum, the worst-case and RSS
    (statistical) ranges, and -- for a mating pair (one +1, one -1) -- whether the
    fit is clearance, transition, or interference. Pure math; no model needed."""
    return _call("tolerance_stack", {"chain": chain})


@mcp.tool()
def get_workspace_meta() -> Any:
    """Read this workspace's record of itself: name, description, tags, and any
    staged name proposal. Call before set_workspace_meta so you write the full
    desired tag set and don't fight a name the user already dismissed."""
    return _call("get_workspace_meta")


@mcp.tool()
def set_workspace_meta(
    description: str | None = None,
    tags: list | None = None,
    proposed_name: str | None = None,
    force: bool = False,
) -> Any:
    """Keep this workspace described as you work. Set a short description and a
    few lowercase tags so it is easy to find later; pass `tags` as the FULL set
    (it replaces, it does not merge). You may propose a better `proposed_name`
    when the current name is weak, but you cannot rename the workspace yourself:
    the user accepts or dismisses your proposal. By default this respects fields
    the user edited by hand; only pass force=true when the user explicitly asks
    you to rewrite a field. Omitted arguments are left unchanged."""
    patch: dict = {}
    if description is not None:
        patch["description"] = description
    if tags is not None:
        patch["tags"] = tags
    if proposed_name is not None:
        patch["proposedName"] = proposed_name
    return _call("set_workspace_meta", {"patch": patch, "force": force})


@mcp.tool()
def set_requirements(requirements: list) -> Any:
    """Set the workspace's design requirements (the goals the part must meet).
    Each is {id, type, target, label?, enabled?} where type is one of: max_mass /
    min_mass (target grams), max_size (target [x,y,z] mm, fits inside that box),
    printable, no_interference, watertight (target null). Set these from the
    user's stated brief up front, then use check_requirements as the done-gate.
    Replaces the whole set; persists per workspace."""
    return _call("set_requirements", {"requirements": requirements})


@mcp.tool()
def check_requirements() -> Any:
    """Evaluate the stored requirements against the current model: pass/fail per
    goal plus a met/total summary. With no model yet, goals read as pass:null
    (not built), never failures. Use this as your done-gate -- only declare the
    part finished when the goals that matter are met."""
    return _call("check_requirements")


@mcp.tool()
def propose_build(brief: dict, expected_revision: int | None = None) -> Any:
    """State the build brief: the short plan you commit to before building (parts and why,
    key dims, interfaces, make-it-real, and the tier). Record it here so the checks and the
    app's brief panel can see it. `brief` is `{summary, parts, key_dims, interfaces, make_real,
    tier}`; `tier` is one of skip/stream/pause. The brief is structured, not an essay: `summary`
    is one or two sentences naming the object and the shape concept; every dimension goes in
    `key_dims` (with the PARAM it drives), every part's reason in its `why`, every meeting of
    parts in `interfaces`, and `make_real` is one line (process + material). A prose blob in
    `summary`/`make_real` is rejected."""
    return _call("propose_build", {"brief": brief, "expectedRevision": expected_revision})


@mcp.tool()
def get_build_brief() -> Any:
    """Read the build brief currently recorded for this workspace (or null if none)."""
    return _call("get_build_brief")


@mcp.tool()
def get_conformance() -> Any:
    """Evaluate recorded design obligations against current engine evidence."""
    return _call("get_conformance")


@mcp.tool()
def get_readiness() -> Any:
    """Return the compact export readiness level and unresolved finding IDs."""
    return _call("get_readiness")


@mcp.tool()
def update_build_brief(
    section: str,
    upserts: list[dict],
    remove_ids: list[str] | None = None,
    expected_revision: int | None = None,
) -> Any:
    """Patch one v2 build-brief section by stable id. Use the revision returned by
    get_build_brief/update_build_brief as expected_revision to avoid overwriting a
    concurrent editor; a mismatch returns a revision conflict without writing."""
    return _call(
        "update_build_brief",
        {
            "section": section,
            "upserts": upserts,
            "remove_ids": remove_ids or [],
            "expectedRevision": expected_revision,
        },
    )


@mcp.tool()
def converge_to_spec(objective: str = "min_mass", apply: bool = False) -> Any:
    """Search the model's parameters for values that satisfy every design
    requirement, without changing the model. Returns the proposed parameters and
    a before/after of each goal, or the closest miss when no setting satisfies
    them. Set apply=True to apply the found parameters. Requirements that no
    parameter can affect are listed under notAddressable; fix those by editing
    the model."""
    return _call("converge_to_spec", {"objective": objective, "apply": apply})


@mcp.tool()
def sweep(param: str, values: list, checks: bool = False) -> Any:
    """Explore a parametric model: build it at each value of one parameter (others
    held current) and return a table of value -> mass, volume, bounding box. Use
    this for "give me a few options" or to see how a dimension trades off against
    weight and size. Non-destructive: the live model and viewport are untouched.
    Set checks=true to also count critical DFM issues per variant (slower). Then
    apply the value you want with set_params."""
    return _call("sweep", {"param": param, "values": values, "checks": checks})


@mcp.tool()
def optimize(
    param: str,
    objective: str = "min_mass",
    steps: int = 9,
    constraints: dict | None = None,
    values: list | None = None,
) -> Any:
    """Find the best value of one parameter for an objective. objective is
    "min_mass" or "max_mass"; constraints may include max_size [x,y,z] (fits in
    that box) and printable: true (no critical DFM). Samples the parameter's range
    in `steps` points, or pass explicit `values` to evaluate exactly those points
    instead. Returns the feasible winner plus every point evaluated.
    Non-destructive; apply the winner with set_params."""
    return _call(
        "optimize",
        {
            "param": param,
            "objective": objective,
            "steps": steps,
            "constraints": constraints,
            "values": values,
        },
    )


@mcp.tool()
def check_motion(
    part: str | None = None,
    kind: str = "revolute",
    axis_origin: list | None = None,
    axis_dir: list | None = None,
    start: float | None = None,
    stop: float | None = None,
    steps: int = 12,
    joint: str | None = None,
) -> Any:
    """Sweep a moving part, or a declared joint, through its range of motion and
    find where it collides with the other parts.

    Part mode (pass part): kind is "revolute" (rotate start..stop degrees about the
    axis through axis_origin along axis_dir) or "prismatic" (translate start..stop
    mm along axis_dir). Joint mode (pass joint, the name of a joint the skeleton
    declared with s.joint(...)): drives that joint through its declared limits (or
    start..stop if you pass them), rotating or sliding every occurrence of its first
    `between` child about/along the joint frame axis. Returns whether and where it
    first collides and how far it moves clear (clearThrough). Use it to check a
    hinge clears, a slider doesn't jam, or a lid opens fully. Read-only; nothing
    changes the model."""
    return _call(
        "check_motion",
        {
            "part": part,
            "kind": kind,
            "axis_origin": axis_origin,
            "axis_dir": axis_dir,
            "start": start,
            "stop": stop,
            "steps": steps,
            "joint": joint,
        },
    )


@mcp.tool()
def diff_against(index: int) -> Any:
    """Compare the current model to a past checkpoint (by its history index) and
    report what changed: the material added and removed (volume and where) plus
    overall volume and bounding-box deltas. Use it to see exactly what an edit
    did. Read-only and non-destructive; it never moves your place in history.
    Get indexes from the history/timeline."""
    return _call("diff_against", {"index": index})


@mcp.tool()
def build_report(views: list | None = None) -> Any:
    """Package the current model into a printable spec sheet (report.html in the
    workspace): a rendered view grid plus mass, dimensions, material, and the DFM
    summary. Hand it to a person, or open it and print to PDF. Read-only. Pass
    `views` to choose the angles (defaults to iso/front/top/right)."""
    return _call("build_report", {"views": views})


@mcp.tool()
def analyze_import(name: str | None = None) -> Any:
    """Measure an imported (or shown) part so you can rebuild it as a clean
    parametric model: overall bounding box, volume, the face mix, a coarse shape
    guess (box / plate / cylinder / compound), and the detected round features
    (holes/bosses) with diameter, axis, and location. Without a name it targets
    the first reference import, else the first part. Use it to reverse-engineer a
    scan or a STEP: analyze, then write a PARAMS/build model that matches, and
    overlay it with capture_views to confirm. Read-only."""
    return _call("analyze_import", {"name": name})


@mcp.tool()
def import_reference(path: str, name: str | None = None) -> Any:
    """Bring an existing CAD/mesh file into the workspace as a ghosted REFERENCE
    fixture -- a part you fit around (a PCB, a motor, a mating component), not one
    you modify. ``path`` is an absolute path to a .step/.stp/.brep/.stl file; it
    is copied into the workspace ``assets/`` dir and recorded in ``imports.json``.
    References render translucent, are measurable and collision-checkable against
    your design, but are never exported or DFM-checked. To instead MODIFY an
    imported solid (e.g. add tabs to a bracket), use ``stage_import`` then call
    ``import_cad(<path>)`` in model.py and build on it."""
    return _call("import_reference", {"path": path, "name": name})


@mcp.tool()
def stage_import(path: str) -> Any:
    """Copy an external CAD file into the workspace ``assets/`` dir and return its
    workspace-relative path, WITHOUT registering a reference. Use this for the
    modify workflow: stage a .step/.stp/.brep, then in model.py write
    ``part = import_cad("assets/<file>")`` and edit it with build123d ops
    (boolean/fillet/cut) -- it becomes a normal, exported part."""
    return _call("stage_import", {"path": path})


@mcp.tool()
def list_imports() -> Any:
    """List the workspace's reference imports (id, name, path, format) from
    ``imports.json``. Use the ids with ``remove_import``."""
    return _call("list_imports")


@mcp.tool()
def remove_import(id: str) -> Any:
    """Remove a reference import (by its id from ``list_imports``) and re-render.
    Use this when promoting a reference to a modifiable part: after writing the
    ``import_cad(...)`` part into model.py, drop the now-redundant reference."""
    return _call("remove_import", {"id": id})


@mcp.tool()
def create_drawing(path: str | None = None) -> Any:
    """Generate a 2D technical drawing of the current model: a dimensioned
    multi-view sheet (front / top / right + iso, hidden lines dashed) with overall
    W/D/H dimensions, a hole schedule, a title block, and a spec sheet (material,
    process, mass, volume, bbox, BOM, and a DFM summary). Writes both an SVG and a
    PDF into the workspace ``exports/`` (or ``path``). Reference imports are
    excluded -- it draws your manufacturable parts only. This is the manufacturing
    handoff document; produce it when the design is ready to send out."""
    return _call("create_drawing", {"path": path})


@mcp.tool()
def set_feature(name: str, values: dict) -> Any:
    """Change a named feature (from ``inspect_features``) by adjusting the
    parameter(s) that drive it: ``values`` is a ``{param: value}`` dict keyed by
    the feature's ``driven_by`` names. Rebuilds the model. A feature that isn't
    parameter-driven (including an inferred/auto-detected one) returns an
    error directing you to name it with ``feature(...)`` or edit its source
    instead. In assembly mode, target the namespaced name (``pin/center_bore``);
    a feature driven by a skeleton parameter rebuilds the assembly through it,
    while a part-local (non-parameter) feature returns a clear error."""
    return _call("set_feature", {"name": name, "values": values})


@mcp.tool()
def feature_at(point: list[float], tolerance_mm: float | None = None) -> Any:
    """Resolve a 3D point to the feature at that location: the "which feature
    is here" lookup. ``point`` is ``[x, y, z]`` in millimetres (build123d Z-up).
    Returns ``{"ok": true, "match": <feature dict>}`` for the nearest feature
    whose mesh is near the point, or ``match: null`` when none is close enough.
    The hit radius adapts to model size (floored at ~1 mm); pass ``tolerance_mm``
    to set an explicit hit radius when a click keeps missing a small or offset
    surface. Retarget the matched feature with ``set_feature`` (name it first if
    it is inferred). In assembly mode features are namespaced ``<part>/<name>``.

    When no named feature is within tolerance (``match: null``), the reply also
    carries ``nearest_face``: the descriptor of the closest bare face (same shape
    as a ``query_faces`` hit, plus its ``distance``) so you still get something
    addressable to measure from. Example: ``feature_at([0, 0, 12])`` on a smooth
    wall returns ``match: null`` with ``nearest_face.id`` = ``"base:f4"``."""
    args: dict[str, Any] = {"point": point}
    if tolerance_mm is not None:
        args["tolerance_mm"] = tolerance_mm
    return _call("feature_at", args)


@mcp.tool()
def render() -> Any:
    """Re-render the current model and write fresh artifacts."""
    return _call("render")


@mcp.tool()
def export(format: str, path: str | None = None, options: dict | None = None) -> Any:
    """Export the current model to a file. Returns the written path.

    format: one of step, stl, glb, gltf, brep, 3mf.
    path: optional. With no path, the export lands in the workspace scratch dir.
    options: optional per-format settings. Unknown keys return an error.

    Options by format:
      step: unit (micron, mm, cm, m, in, ft), precision_mode (average, greatest,
            least, session), write_pcurves (bool), timestamp ("current" or a
            fixed ISO string for reproducible output).
      stl:  ascii (bool, false is binary), quality (draft, standard, fine,
            custom), tolerance (mm), angular_tolerance (radians).
      glb / gltf: unit, quality, linear_deflection (mm), angular_deflection
            (radians). Use format glb for binary, gltf for text.
      brep: none. Exact geometry, nothing to tune.
      3mf:  unit, quality, linear_deflection, angular_deflection, mesh_type
            (model, support, solid_support, other), part_number, uuid.
    """
    return _call("export", {"format": format, "path": path, "options": options})


@mcp.tool()
def capture_views(
    views: list[str] | None = None,
    layout: str = "separate",
    color: bool = True,
    explode: float = 0.0,
    highlight: list[str] | None = None,
    resolution: int = 512,
    section: dict | None = None,
    focus: str | list[float] | None = None,
) -> Any:
    """Render the current model from one or more camera views and return the
    images. Each entry of ``views`` is a named view — faces ``top`` ``bottom``
    ``front`` ``back`` ``left`` ``right``; the 8 corners e.g. ``front-top-right``;
    ``iso`` — or a custom angle ``az<deg>_el<deg>`` (e.g. ``az30_el20``).
    Defaults to ``["iso"]``. With ``layout="grid"`` the views are tiled into a
    single labeled contact sheet (cheaper to view than many separate images);
    ``layout="separate"`` (default) returns one image per view. Use this to
    visually verify geometry. Parts render in their assigned material colors by
    default; pass ``color=False`` for a uniform clay-gray render (geometry only).
    Pass ``explode`` (0..100, a percent) to spread the shown parts radially for
    THIS render only, so a multi-part assembly is captured pulled apart — use it
    to review a fit (a lid seating, a plug clearing its bore) that's hidden when
    the parts nest assembled. It never changes the saved or exported model;
    ``0`` (default) renders assembled. ``highlight`` emphasizes the named features
    from ``inspect_features`` with an orange accent overlay.
    Pass ``resolution`` (256..2048 px, default 512) and use 1024+ whenever you
    need to actually read fine detail: a thread, an edge break, a port lip, a
    seam. Pass ``section={"axis": "x"|"y"|"z", "offset_mm": <mm>}`` to render
    the model plane-cut at that offset (material on the positive side of the
    axis removed, camera defaulting to the matching face view + iso); the
    exposed cross-section faces are filled magenta so internal walls, cavities,
    bosses and clearances are visible. The cut is render-only: the saved model
    is never modified. Pass ``focus`` to frame the camera close on one target
    with about 15% margin while the rest of the model stays in frame for
    context: a feature name from ``inspect_features`` or a
    ``[xmin, ymin, zmin, xmax, ymax, zmax]`` mm region."""
    payload: dict[str, Any] = {
        "views": views,
        "layout": layout,
        "color": color,
        "explode": explode,
        "highlight": highlight,
    }
    # The perception params ride along only when used: a default call keeps the
    # exact legacy wire payload (the engine handler's defaults fill the rest).
    if resolution != 512:
        payload["resolution"] = resolution
    if section is not None:
        payload["section"] = section
    if focus is not None:
        payload["focus"] = focus
    result = _call("capture_views", payload)
    if not isinstance(result, dict) or "views" not in result:
        return result  # error envelope -> surface as-is (text)

    rendered = result.get("views", [])
    names = ", ".join(v.get("name", "?") for v in rendered)
    kind = "contact sheet of" if result.get("layout") == "grid" else "view(s) of"
    blocks: list = [
        f"{len(rendered)} {kind} the current model (buildId {result.get('buildId')}): {names}"
    ]
    for v in rendered:
        path = v.get("path", "")
        # FastMCP's Image reads the file lazily at serialization (after this
        # tool returns), so a missing path would fail deep in the framework.
        # Check existence here and emit a text fallback instead.
        if path and os.path.isfile(path):
            blocks.append(Image(path=path))
        else:
            blocks.append(f"[view '{v.get('name')}' missing/unreadable: {path}]")
    return blocks


@mcp.tool()
def cad_history() -> Any:
    """Return the workspace edit history (entries + current index)."""
    return _call("history")


@mcp.tool()
def cad_undo() -> Any:
    """Undo the last edit, restoring the previous model state."""
    return _call("undo")


@mcp.tool()
def cad_redo() -> Any:
    """Redo the last undone edit."""
    return _call("redo")


@mcp.tool()
def cad_checkpoint(message: str) -> Any:
    """Label the current model state as a named checkpoint in history."""
    return _call("checkpoint", {"message": message})


@mcp.tool()
def cad_goto(index: int) -> Any:
    """Jump to a specific entry in the edit history (by its index), restoring that
    model state. Get the indexes from cad_history."""
    return _call("goto", {"index": index})


@mcp.tool()
def fab_detect() -> Any:
    """Detect whether a supported slicer is installed on this machine.

    Returns whether a slicer was found, its version, and the executable path.
    Use this before other fabrication tools to confirm a slicer is available."""
    return _call("fab_detect")


@mcp.tool()
def fab_profiles() -> Any:
    """Return the printer and filament profiles available in the installed slicer.

    Lists the configured printers and filament materials the slicer knows about.
    Use the profile names with fab_estimate or fab_open to target a specific setup."""
    return _call("fab_profiles")


@mcp.tool()
def fab_estimate(destination_id: str | None = None) -> Any:
    """Estimate print time, weight, and cost for the current model.

    Slices the model using the slicer and returns estimated print time, filament
    weight, and cost. When no slicer is installed, returns an approximate weight
    and cost based on model volume and material density. Pass destination_id to
    target a specific printer destination; omit to use the default."""
    return _call("fab_estimate", {"destination_id": destination_id})


@mcp.tool()
def fab_orient(overhang_deg: float | None = None) -> Any:
    """Suggest a print orientation that minimizes support material.

    Analyzes the model geometry and returns the rotation that minimizes support
    contact area given the slicer overhang angle threshold. With no angle, uses
    the workspace manufacturing profile's process.overhangDeg (its default is 45
    deg); pass overhang_deg only to override the profile for this call. Returns
    the suggested rotation, support area, contact area, and worst-case support
    area."""
    params = {} if overhang_deg is None else {"overhang_deg": overhang_deg}
    return _call("fab_orient", params)


@mcp.tool()
def fab_open(destination_id: str | None = None) -> Any:
    """Open the current model in the slicer for printing.

    Exports the model and launches the installed slicer with the file loaded,
    ready to slice and send to the printer. Pass destination_id to target a
    specific printer destination; omit to use the default. Returns the path of
    the exported file that was opened."""
    return _call("fab_open", {"destination_id": destination_id})


# -- assembly authoring -----------------------------------------------------


@mcp.tool()
def set_skeleton(code: str) -> Any:
    """Create or replace the assembly skeleton (skeleton.py): the master model that
    owns shared PARAMS (the workspace sliders) and publishes named scalars and
    frames for parts to build against. Calling this turns a workspace into an
    assembly. Parts attach to the frames you declare here."""
    return _call("set_skeleton", {"code": code})


@mcp.tool()
def set_part(
    id: str,
    code: str,
    attach: str | None = None,
    inputs: list[str] | None = None,
    shape_inputs: list[str] | None = None,
) -> Any:
    """Add or update a leaf part (parts/<id>.py). The part's build(inputs) reads
    only the skeleton outputs named in inputs (scalars) and shape_inputs (published
    profiles/solids), and shows solid(s) in its own local frame; attach names the
    skeleton frame it is placed at (omit for the origin). A new id is added to the
    assembly; an existing id is rewritten. Source-only edits keep the existing
    attach/inputs/shape_inputs wiring."""
    return _call(
        "set_part",
        {"id": id, "code": code, "attach": attach, "inputs": inputs, "shape_inputs": shape_inputs},
    )


@mcp.tool()
def get_assembly_tree() -> Any:
    """Return the nested assembly structure: the skeleton's params, scalars, frames
    and declared joints, and every child (parts and sub-assemblies) with its attach
    frame, declared inputs, and occurrences (every placement of that one part
    definition). Use this to see how the assembly is wired before editing."""
    return _call("get_assembly_tree")


@mcp.tool()
def get_part_info(id: str) -> Any:
    """Return one part's source code, its attach frame, the skeleton inputs it
    reads, its occurrences (all placements of this one definition), and a summary
    of its last build (solid count across every occurrence)."""
    return _call("get_part_info", {"id": id})


@mcp.tool()
def attach(id: str, frame: str | None = None) -> Any:
    """Place a child at a different skeleton frame. This is a recompose, not a
    rebuild: the part geometry is reused and only re-placed at the new frame.
    Pass frame=None to attach at the node origin. If the part has occurrences,
    this re-points the primary one; use set_occurrences to change them all."""
    return _call("attach", {"id": id, "frame": frame})


@mcp.tool()
def set_occurrences(id: str, occurrences: list) -> Any:
    """Place ONE part definition at several frames (instancing). N identical parts
    are ONE part plus N occurrences, never N copies of the file. occurrences is a
    list of {"frame": <skeleton frame name, or null for the origin>, "mirror":
    <null, "xy", "yz", or "zx">}; a mirrored occurrence is reflected about that
    local plane (use it for a left/right handed pair). The part is built once and
    placed at each occurrence, so this is a cheap recompose, not N rebuilds.
    Occurrence bodies are named id, id@2, id@3 ... and each is a distinct body for
    interference and motion checks. attach re-points to the first occurrence."""
    return _call("set_occurrences", {"id": id, "occurrences": occurrences})


@mcp.tool()
def set_inputs(id: str, inputs: list[str]) -> Any:
    """Change which skeleton outputs a part reads. The part is rebuilt against the
    new scalar set (inputs are part of the build, unlike the attach frame)."""
    return _call("set_inputs", {"id": id, "inputs": inputs})


@mcp.tool()
def remove_part(id: str) -> Any:
    """Remove a part or sub-assembly from the assembly. Drops it from the manifest
    and deletes its source (parts/<id>.py, or the <id>/ folder for a sub-assembly)."""
    return _call("remove_part", {"id": id})


@mcp.tool()
def add_subassembly(id: str, attach: str | None = None, inputs: list[str] | None = None) -> Any:
    """Add a nested sub-assembly node (its own skeleton + parts) attached to a
    skeleton frame. Scaffolds <id>/ with an empty manifest and wires it in; author
    its skeleton and parts as a nested assembly. inputs are the parent scalars the
    sub-node may read as its own parent values."""
    return _call("add_subassembly", {"id": id, "attach": attach, "inputs": inputs})


@mcp.tool()
def build_part(id: str) -> Any:
    """Build one part in isolation against the current skeleton and report whether
    it is valid, its solid count and bounding box. Useful to check a part before
    composing the whole assembly."""
    return _call("build_part", {"id": id})


@mcp.tool()
def begin_round() -> Any:
    """Start a parallel authoring round: freeze the skeleton and defer composition.
    Returns the skeleton contract (params, scalars, frames) to hand to each part.
    Use this before fanning out one set_part per part, then call end_round to compose
    the whole assembly at once. While a round is open, set_skeleton is refused."""
    return _call("begin_round")


@mcp.tool()
def end_round() -> Any:
    """Finish the authoring round: compose and render the whole assembly once, and
    report any parts that failed to build during the round."""
    return _call("end_round")


@mcp.tool()
def abort_round() -> Any:
    """Discard the current authoring round without composing."""
    return _call("abort_round")


@mcp.tool()
def export_flat_model(write: bool = False) -> Any:
    """Flatten the assembly into a single, self-contained model.py and return its
    code. The emitted file depends only on solidifai + build123d and, run on its
    own, reproduces the composed assembly (same parts, placement, and path-id
    names). Pass write=True to also save it as flat_model.py in the workspace.
    Use it to hand off or archive an assembly as one runnable script."""
    return _call("export_flat_model", {"write": write})


@mcp.tool()
def check_interfaces() -> Any:
    """Validate the assembly's declared wiring and summarize geometric fit. Reports
    any child whose attach or occurrence frame names a frame the skeleton does not
    publish (missing_attach_frame) or whose inputs name a scalar the skeleton does
    not publish (missing_input), plus any declared joint whose frame is not
    published (missing_joint_frame) or whose `between` does not name a child
    (unknown_joint_between), recursively through sub-assemblies. Folds in the
    composed-model interference summary under `interference`. Read-only."""
    return _call("check_interfaces")


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")
