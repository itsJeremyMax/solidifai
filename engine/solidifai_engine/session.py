"""The Session holds the engine's *current model*.

A session executes a user script (build123d + ``solidifai.show``) in a fresh
namespace, then renders the resulting registry to artifacts. The buildId is
monotonic and only advances on a successful build; a failed build leaves the
last-good artifacts untouched.
"""

from __future__ import annotations

import ast
import contextlib
import glob
import hashlib
import json
import logging
import os
import re
import time
import traceback
from typing import TYPE_CHECKING, Any, TypeGuard

import solidifai
from solidifai_engine import (
    build_brief,
    montage,
    part_materials,
    paths,
    scratch,
    settings,
    workspace_metadata,
)
from solidifai_engine import features as feature_geom
from solidifai_engine import materials as _materials
from solidifai_engine import requirements as requirements_mod
from solidifai_engine import section as section_mod  # noqa: F401 - test monkeypatch surface
from solidifai_engine import views as views_mod
from solidifai_engine.analysis import Analysis

# Re-exported (not called directly here) so code importing these from
# session.py — their pre-extraction home — keeps working unchanged.
from solidifai_engine.capture import (
    _SECTION_FACE_VIEW,
    SECTION_TIMEOUT_S,
    TESS_TOLERANCE,  # noqa: F401
    CaptureError,
    _run_with_timeout,  # noqa: F401
    _srgb,  # noqa: F401
    assemble_capture_mesh,
    resolve_focus,
    resolve_highlight,
    validate_capture_args,
)
from solidifai_engine.exploration import Exploration
from solidifai_engine.exports import export as exports_export
from solidifai_engine.fabrication.service import Fabrication
from solidifai_engine.import_manager import ImportManager
from solidifai_engine.render import _compound_from_registry, _node_ids, _slug, render_to
from solidifai_engine.reporting import Reporting

if TYPE_CHECKING:
    from build123d import Compound

# Consecutive param commits within this many seconds amend (coalesce) into one.
COALESCE_WINDOW = 0.7


def _module_build_overrides(code: str, valid_names: set) -> dict:
    """Statically read the literal keyword args of a top-level ``build(...)`` call
    in ``code``. When a script calls ``build(size=50)`` at module level (an
    off-convention build, not the ``__name__ == "__main__"`` guard), this lets the
    engine report the values the geometry was actually built with instead of the
    PARAMS defaults. Only literal-evaluable kwargs (and ``**{...}`` literals) are
    returned; anything dynamic (a comprehension, a variable) is ignored, and the
    conventional guarded ``build(**defaults)`` tail is never a top-level call so it
    never reaches here."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}
    overrides: dict = {}
    for node in tree.body:  # module-level statements only
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "build"
        ):
            continue
        for kw in node.value.keywords:
            try:
                if kw.arg is None:  # build(**{...})
                    value = ast.literal_eval(kw.value)
                    if isinstance(value, dict):
                        overrides.update({k: v for k, v in value.items() if k in valid_names})
                elif kw.arg in valid_names:
                    overrides[kw.arg] = ast.literal_eval(kw.value)
            except (ValueError, SyntaxError):
                continue  # non-literal arg: leave the default in place
    return overrides


class Session:
    def __init__(self, artifacts_dir: str, model_path: str | None = None):
        self.artifacts_dir = artifacts_dir
        os.makedirs(artifacts_dir, exist_ok=True)
        # When set, the durable model source file. On a successful
        # execute_script the executed code is written here (atomically), so the
        # workspace can be reopened/restored exactly and export always works.
        self.model_path: str | None = model_path
        # Workspace root (parent of model.py) — None for bare artifact-only
        # sessions (tests). Settings + git history are enabled only when set.
        self.root = os.path.dirname(model_path) if model_path else None
        # When True, successful builds skip auto-persisting settings.json (used
        # during the startup replay so reopening a workspace doesn't rewrite
        # settings.json on every load).
        self._suppress_persist = False
        # Git history (enabled only for real workspaces; bare sessions skip it).
        self.history = None
        self._last_param_commit_t = 0.0
        if self.root is not None:
            try:
                from solidifai_engine.history import History

                hist = History(self.root)
                hist.ensure()
                self.history = hist
            except Exception:  # noqa: BLE001 - missing dulwich / repo error degrades
                self.history = None
        self.code: str | None = None
        self.build_id: int = 0
        # last_ok = did the MOST RECENT build operation (execute_script /
        # set_params / render) succeed. Operation-level and transient: a failed
        # op flips it to False but leaves build_id and the last-good artifacts
        # intact, so the UI can show last-good geometry plus a transient error
        # flag independently. None until the first operation runs.
        self.last_ok: bool | None = None
        self._params_schema: dict = {}
        self._param_values: dict = {}
        # Per-part material overrides ({partId: materialId}), applied at render
        # time over what model.py set. Loaded from part_materials.json in
        # startup() and updated by set_part_material.
        self._material_overrides: dict = {}
        # Design requirements (list of goal dicts), loaded from requirements.json
        # in startup() and updated by set_requirements. Advisory; never gate a build.
        self._requirements: list = []
        self._build_fn = None
        # sha256 of the model.py source that produced the current build_fn (set on
        # every successful single-model load). set_params compares it against disk
        # to catch an out-of-band edit before committing a diverged snapshot.
        self._model_hash: str | None = None
        # The Compound of the last SUCCESSFUL build, snapshotted so capture_views
        # renders last-good geometry (not a failed script's partial registry).
        self._model: Compound | None = None
        # Per-object snapshot taken alongside self._model, so colored captures
        # use last-good objects (with their materials/colors) and never a later
        # script's partial or reset registry.
        self._objects: list | None = None
        # Last-good params block (parallels _objects/_model): a re-render of the
        # last-good model reports these PARAMS even after a failed build reset the
        # live param state to empty.
        self._last_params_block: dict | None = None
        # Last-good snapshot of declared features (parallels self._model).
        self._features: list = []
        # Collaborators: cohesive method groups that hold a back-reference to
        # this session (they read/write self._... state and call lifecycle
        # helpers that stay on Session). The public methods below delegate to
        # them so server.py's by-name dispatch is unchanged.
        self._analysis = Analysis(self)
        self._exploration = Exploration(self)
        self._fabrication = Fabrication(self)
        self._imports = ImportManager(self)
        self._reporting = Reporting(self)
        from solidifai_engine.assembly.cache import NodeCache

        self._node_cache = NodeCache()
        # Authoring round state (in-memory, assembly-scoped, transient). While
        # active, set_part/build_part validate each part in isolation but defer the
        # whole-assembly compose to end_round, and set_skeleton is refused (single
        # writer). Never touches the single-model.py path. See begin_round.
        self._round: dict = {"active": False}
        # L2 disk cache: only for real workspaces; bare/single-model sessions leave it None.
        from solidifai_engine.assembly.diskcache import DiskCache

        self._disk_cache = DiskCache(self.root) if self.root else None

    # -- public API ---------------------------------------------------------

    def run_file(self, path: str) -> dict:
        if self._is_assembly_mode():
            return self._assembly_script_refusal()
        with open(path, encoding="utf-8") as f:
            code = f.read()
        return self._run_script(code)

    @staticmethod
    def _assembly_script_refusal() -> dict:
        """Refuse execute_script/run_file on an assembly workspace. Running a single
        model.py would render over the composed assembly while assembly.json stays on
        disk, so set_params routes to the assembly branch and history commits the
        assembly fileset: a split-brain the agent cannot undo. Mirror of set_part's
        reverse-direction guard."""
        return {
            "ok": False,
            "error": "this workspace is an assembly; edit it with set_part or "
            "set_skeleton. execute_script builds a single model and would replace "
            "the assembly.",
        }

    def _render_and_snapshot(
        self, next_build: int, *, params: dict | None, duration_ms: int | None
    ) -> None:
        """Render the current registry to ``next_build`` and snapshot it into
        _model/_objects/_features. Raises on failure -- the caller converts the
        exception via ``_build_failed``. Does NOT apply references, bump
        buildId, persist, or call ``_after_build``; callers that need those do
        them around this call so each keeps its own original ordering.

        ``duration_ms`` is omitted from the render_to call entirely when None,
        matching render()'s existing behavior of not timing itself."""
        render_kwargs: dict[str, Any] = {
            "params": params,
            "overrides": self._material_overrides,
        }
        if duration_ms is not None:
            render_kwargs["duration_ms"] = duration_ms
        render_to(self.artifacts_dir, next_build, **render_kwargs)
        self._model = _compound_from_registry(solidifai._registry())
        self._objects = list(solidifai._registry())
        self._last_params_block = params
        self._snapshot_features()

    def _build_failed(self, exc: Exception) -> dict:
        """Shared build-failure handling: discard temps, mark last_ok False,
        and format the standard error dict."""
        self._cleanup_temps()
        self.last_ok = False
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }

    def execute_script(self, code: str) -> dict:
        """Execute ``code`` and render. Refused on an assembly workspace (would
        replace the composed assembly with a single model, split-braining state)."""
        if self._is_assembly_mode():
            return self._assembly_script_refusal()
        return self._run_script(code)

    def _run_script(self, code: str) -> dict:
        """Execute ``code`` and render. On any failure, return an error dict
        without bumping buildId or overwriting last-good artifacts.

        Unguarded internal build path: the public execute_script/run_file add the
        assembly refusal, but internal rebuilds (imports) run a single model.py here
        directly so they are not blocked by that guard."""
        next_build = self.build_id + 1
        started = time.perf_counter()

        solidifai.reset_registry()
        # Let model.py's import_cad("assets/x.step") resolve against the workspace.
        solidifai.set_workspace_root(self.root)
        ns: dict[str, Any] = {"__name__": "__solidifai_script__"}

        # Stash the live parametric state so a failed build can restore it: a
        # failure must leave get_params/set_params pointed at the last-good model,
        # not the wiped-empty block this build cleared before running (same
        # last-good discipline as self._last_params_block).
        prior_schema = self._params_schema
        prior_values = self._param_values
        prior_build_fn = self._build_fn
        try:
            self._params_schema = {}
            self._param_values = {}
            self._build_fn = None

            compiled = compile(code, "<solidifai-script>", "exec")
            exec(compiled, ns)

            params_schema = ns.get("PARAMS")
            build_fn = ns.get("build")
            params_block = None
            if isinstance(params_schema, dict) and callable(build_fn):
                self._build_fn = build_fn
                # _param_values keeps ALL declared params (any type) so every one
                # still reaches build(). _params_schema is the normalized,
                # numeric-only subset surfaced to the UI + model.json.
                self._param_values = self._default_values(params_schema)
                self._params_schema = self._normalize_schema(params_schema)
                # Build once: if the script already invoked build() at module level
                # (the conventional `build(**defaults)` tail, or a __main__ guard
                # that did not fire), reuse that registry, so we never run the kernel
                # twice. Only build ourselves when build() was defined but not called
                # (registry empty).
                if not list(solidifai._registry()):
                    build_fn(**self._param_values)
                else:
                    # A module-level build(...) already ran. If it used non-default
                    # literal args (e.g. `build(size=50)`), reflect them so
                    # get_params/model.json match the geometry instead of reporting
                    # the PARAMS defaults.
                    self._param_values.update(
                        _module_build_overrides(code, set(self._param_values))
                    )
                params_block = self._params_block()

            # Load reference fixtures into the registry before render, so they
            # appear in the GLB/model.json and the snapshot, but never in model.py.
            self._apply_references()
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._render_and_snapshot(next_build, params=params_block, duration_ms=duration_ms)
        except Exception as exc:  # noqa: BLE001 - report any script/render error
            self._params_schema = prior_schema
            self._param_values = prior_values
            self._build_fn = prior_build_fn
            return self._build_failed(exc)

        # Success: persist the durable model (only on success, never on
        # failure) and commit new state.
        if self.model_path is not None:
            try:
                self._persist_model(code)
            except OSError as exc:  # pragma: no cover - rare disk error
                self.last_ok = False
                return {
                    "ok": False,
                    "error": f"model rendered but could not be persisted to "
                    f"{self.model_path!r}: {exc}",
                    "traceback": traceback.format_exc(),
                }
        # Record the hash of the source that produced the live build_fn so
        # set_params can detect an out-of-band model.py edit before committing a
        # snapshot whose code and geometry never coexisted (see set_params).
        self._model_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
        self.code = code
        self.build_id = next_build
        self.last_ok = True
        if not self._suppress_persist:
            self._after_build(structural=True)
        return {"ok": True, "buildId": self.build_id}

    def get_params(self) -> dict:
        """Return the current parameter ``{schema, values}`` (the normalized,
        numeric-only slider view -- always frontend-valid).

        Empty schema/values when the current script does not define PARAMS."""
        block = self._params_block()
        if block is None:
            return {"schema": {}, "values": {}}
        return block

    def set_params(self, values: dict) -> dict:
        """Override parameter values, rebuild via ``build(**values)`` and
        render with the next buildId. No-op error if no PARAMS script is loaded.

        A failed rebuild does not bump buildId or clobber last-good artifacts;
        the previously committed values are also left unchanged.
        """
        if self._is_assembly_mode():
            if (guard := self._round_guard()) is not None:
                return guard
            # Validate against the skeleton's PARAMS schema before rebuilding so an
            # unknown/invalid key returns a clean error instead of a raw TypeError
            # from build(**merged) -- same discipline as the single-model branch.
            if (err := self._validate_param_values(values or {})) is not None:
                return err
            merged = dict(self._param_values)
            merged.update(values or {})
            res = self._build_assembly(params=merged)
            if res.get("ok"):
                self._param_values = merged
                if not self._suppress_persist:
                    self._after_build(structural=False)
            return res

        if not callable(self._build_fn):
            return {
                "ok": False,
                "error": "no parametric model loaded (script has no PARAMS/build)",
            }

        if (err := self._validate_param_values(values or {})) is not None:
            return err
        if (err := self._check_model_unchanged()) is not None:
            return err

        merged = dict(self._param_values)
        merged.update(values or {})

        next_build = self.build_id + 1
        started = time.perf_counter()
        solidifai.reset_registry()
        solidifai.set_workspace_root(self.root)
        try:
            self._build_fn(**merged)
            self._apply_references()
            duration_ms = int((time.perf_counter() - started) * 1000)
            self._render_and_snapshot(
                next_build, params=self._params_block(merged), duration_ms=duration_ms
            )
        except Exception as exc:  # noqa: BLE001
            return self._build_failed(exc)

        self._param_values = merged
        self.build_id = next_build
        self.last_ok = True
        if not self._suppress_persist:
            self._after_build(structural=False)
        return {"ok": True, "buildId": self.build_id}

    def _validate_param_values(self, values: dict) -> dict | None:
        """Validate a set_params request against the loaded schema; return an error
        dict for the first violation, or None when every value is acceptable.

        A schema'd numeric param must get a real number (bool rejected: it is an int
        subclass that silently builds size-1 geometry and then vanishes from
        get_params) inside its [min, max] range -- rejected, not clamped, so the
        agent hears the truth. An unknown key (not a declared param) is rejected.
        Declared non-numeric params (strings the schema carries) stay permitted."""
        declared = set(self._param_values)
        for key, val in values.items():
            if key not in declared:
                valid = ", ".join(sorted(declared)) or "(none)"
                return {
                    "ok": False,
                    "error": f"unknown parameter {key!r}; valid: {valid}",
                }
            spec = self._params_schema.get(key)
            if spec is None:
                continue  # declared but non-numeric (e.g. a string): pass through
            if not self._is_number(val):
                return {
                    "ok": False,
                    "error": f"parameter {key!r} must be a number, got "
                    f"{type(val).__name__} ({val!r})",
                }
            v = float(val)
            lo, hi = spec["min"], spec["max"]
            if v < lo or v > hi:
                return {
                    "ok": False,
                    "error": f"parameter {key!r}={v} is out of range [{lo}, {hi}]",
                }
        return None

    def _check_model_unchanged(self) -> dict | None:
        """Guard set_params against an out-of-band model.py edit. When the file on
        disk no longer matches the source that produced the live build_fn, a rebuild
        here would render the STALE in-memory geometry yet history stages the NEW
        disk bytes -- a snapshot whose code and geometry never coexisted. Return an
        error instructing run_file; None when the file matches (or there is nothing
        to compare)."""
        if self._model_hash is None or not self.model_path:
            return None
        try:
            with open(self.model_path, "rb") as f:
                disk_hash = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return None  # unreadable: let the rebuild surface the real error
        if disk_hash == self._model_hash:
            return None
        return {
            "ok": False,
            "error": "model.py changed on disk since it was loaded; run it again "
            "with run_file before adjusting parameters",
        }

    def set_part_material(self, part_id: str, material) -> dict:
        """Assign (or clear, when ``material`` is None) the material for one part,
        persist the override, and re-render. ``part_id`` is the slugified id that
        render.py writes into model.json."""
        if self._is_assembly_mode() and (guard := self._round_guard()) is not None:
            return guard  # a round composes once at end_round; no mid-round re-render
        # Validate against the last-good snapshot (self._objects), not the live
        # global registry: a failed build can leave partial/stale objects in the
        # registry, and render() below re-renders from self._objects anyway.
        objects = self._objects or []
        valid_ids = set(_node_ids(objects))
        if part_id not in valid_ids:
            return {"ok": False, "error": f"unknown part id {part_id!r}"}
        if material is not None and _materials.RESOLVER.get(material) is None:
            valid = ", ".join(_materials.RESOLVER.names())
            return {"ok": False, "error": f"unknown material {material!r}; valid: {valid}"}

        overrides = dict(self._material_overrides)
        if material is None:
            overrides.pop(part_id, None)
        else:
            overrides[part_id] = material
        self._material_overrides = overrides
        if self.root is not None:
            part_materials.write_overrides(self.root, overrides)
        # Assembly mode must rebuild from the DAG (render() reads the empty global registry).
        if self._is_assembly_mode():
            return self._build_assembly(params=self._param_values)
        return self.render()

    def get_workspace_meta(self) -> dict:
        """Return the workspace's canonical metadata (read fresh from disk)."""
        if self.root is None:
            return {"ok": True, "metadata": workspace_metadata.defaults()}
        return {"ok": True, "metadata": workspace_metadata.load_metadata(self.root)}

    def set_workspace_meta(self, patch: dict, force: bool = False, user: bool = False) -> dict:
        """Apply a partial metadata update (description/tags/proposedName).
        user=True is a UI edit (marks fields user-owned); otherwise it is a Sol
        write honoring provenance (force overrides). Reads fresh, writes atomically."""
        if self.root is None:
            return {"ok": False, "error": "no workspace root"}
        cur = workspace_metadata.load_metadata(self.root)
        if user:
            new = workspace_metadata.apply_user_patch(cur, patch or {})
            if "proposedName" in (patch or {}):
                new = workspace_metadata.apply_patch(
                    new, {"proposedName": patch["proposedName"]}, force=True
                )
        else:
            new = workspace_metadata.apply_patch(cur, patch or {}, force=force)
        workspace_metadata.write_metadata(self.root, new)
        return {"ok": True, "metadata": new}

    def set_workspace_name(self, name: str) -> dict:
        """Set the canonical name (user-initiated). Clears any pending proposal."""
        if self.root is None:
            return {"ok": False, "error": "no workspace root"}
        cur = workspace_metadata.load_metadata(self.root)
        try:
            new = workspace_metadata.set_name(cur, name)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        workspace_metadata.write_metadata(self.root, new)
        return {"ok": True, "name": new["name"]}

    def dismiss_proposed_name(self) -> dict:
        """Dismiss the staged name proposal (records it so Sol won't re-nag)."""
        if self.root is None:
            return {"ok": False, "error": "no workspace root"}
        cur = workspace_metadata.load_metadata(self.root)
        new = workspace_metadata.dismiss_proposed_name(cur)
        workspace_metadata.write_metadata(self.root, new)
        return {"ok": True, "metadata": new}

    def feature_at(self, point, tolerance_mm=None) -> dict:
        """Return the named feature nearest ``point`` (build123d Z-up mm), as
        ``{"ok": True, "match": <feature dict> | null}``. The app converts a
        viewport click (GLB Y-up) to this frame before calling — see the design spec.

        The hit radius is adaptive: it scales with the model's bounding-box
        diagonal (floored at 1mm) so a click that lands slightly off a surface on
        a large model still resolves. Pass ``tolerance_mm`` to override it with an
        explicit hit radius in millimetres."""
        if not point or len(point) != 3:
            return {"ok": False, "error": "point must be [x, y, z] in mm (Z-up)"}
        tol = self._feature_at_tolerance(tolerance_mm)
        rec = feature_geom.nearest(self._features, point, tol=tol)
        return {"ok": True, "match": self._feature_to_dict(rec) if rec is not None else None}

    def _model_diagonal(self) -> float:
        """Bounding-box diagonal of the current model in mm (0.0 if unavailable)."""
        try:
            bb = self._model.bounding_box()
            return (bb.size.X**2 + bb.size.Y**2 + bb.size.Z**2) ** 0.5
        except Exception:  # noqa: BLE001 - no model / unmeasurable
            return 0.0

    def _feature_at_tolerance(self, tolerance_mm) -> float:
        """Resolve the feature_at hit radius: an explicit positive ``tolerance_mm``
        wins; otherwise scale with the model diagonal, floored at the base tolerance."""
        if tolerance_mm is not None:
            try:
                t = float(tolerance_mm)
                if t > 0:
                    return t
            except (TypeError, ValueError):
                pass
        adaptive = self._model_diagonal() * feature_geom.FEATURE_AT_DIAG_FRACTION
        return max(feature_geom.FEATURE_AT_TOLERANCE, adaptive)

    def set_feature(self, name, values) -> dict:
        """Change a named feature by adjusting the parameter(s) that drive it.

        ``values`` is a ``{param: value}`` dict whose keys must be among the
        feature's ``driven_by`` parameters; the change is applied via
        ``set_params`` (so it rebuilds, renders, and commits like any param
        edit). A feature that is not parameter-driven returns a clear error
        directing the caller to edit its source (``inspect_features`` gives the
        line) or wrap it with ``feature(driven_by=...)``.
        """
        by_name = {f.name: f for f in self._features}
        if name not in by_name:
            valid = ", ".join(sorted(by_name)) or "(none)"
            return {"ok": False, "error": f"unknown feature {name!r}; valid: {valid}"}
        rec = by_name[name]
        if getattr(rec, "inferred", False):
            return {
                "ok": False,
                "error": f"feature {name!r} was auto-detected (inferred, confidence "
                f"{rec.confidence}) and has no driving parameter. Confirm it "
                f"visually with capture_views(highlight=[{name!r}]), then edit "
                f"the source directly with execute_script.",
            }
        if not isinstance(values, dict) or not values:
            return {"ok": False, "error": "values must be a non-empty {param: value} dict"}
        driven = list(rec.driven_by)
        if not driven:
            return {
                "ok": False,
                "error": f"feature {name!r} is not parameter-driven; edit its "
                f"source with execute_script, or wrap it with "
                f"feature(driven_by=...) to make it settable",
            }
        # A driven_by typo would otherwise reach build(**merged) as a raw TypeError
        # (skeleton/param build). Catch it here with the available param names.
        unknown = self._unknown_driven_by(rec)
        if unknown:
            valid = ", ".join(sorted(self._param_values)) or "(none)"
            return {
                "ok": False,
                "error": f"feature {name!r} declares driven_by {unknown} which are "
                f"not parameters; available: {valid}. Fix the "
                f"feature(driven_by=...) declaration.",
            }
        bad = [k for k in values if k not in driven]
        if bad:
            return {
                "ok": False,
                "error": f"param(s) {bad} do not drive feature {name!r}; it is driven by {driven}",
            }
        return self.set_params(values)

    def inspect_features(self) -> dict:
        """Return the last-good inventory of declared features.

        Each entry carries the feature's ``name``, ``kind`` (or null), the
        ``driven_by`` param name(s), and the ``source`` line in model.py. This
        is the geometry→source index the agent uses to target an edit (a
        ``driven_by`` feature is then changed via ``set_params``). Independent
        of ``last_ok``: reads the last-good snapshot, like ``get_model_info``.
        """
        return {"features": [self._feature_to_dict(f) for f in self._features]}

    def check_interferences(self) -> dict:
        return self._analysis.check_interferences()

    def analyze_dfm(self, process: str | None = None) -> dict:
        return self._analysis.analyze_dfm(process)

    def _infer_process(self, material_name) -> str:
        return self._analysis._infer_process(material_name)

    def _density_for(self, material_name) -> float:
        return self._analysis._density_for(material_name)

    def measure(self) -> dict:
        return self._analysis.measure()

    def stress_check(self) -> dict:
        return self._analysis.stress_check()

    def tolerance_stack(self, chain) -> dict:
        return self._analysis.tolerance_stack(chain)

    def propose_build(self, brief) -> dict:
        """Persist the build brief Sol is committing to. Validates regardless of root;
        writes the file only when this session has a workspace root (bare sessions skip)."""
        if self.root is not None:
            norm = build_brief.write_build_brief(self.root, brief)
        else:
            norm = build_brief.validate(brief)
        return {"ok": True, "brief": norm}

    def get_build_brief(self) -> dict:
        """Read the current persisted build brief (or None)."""
        brief = build_brief.load_build_brief(self.root) if self.root is not None else None
        return {"ok": True, "brief": brief}

    def set_requirements(self, reqs) -> dict:
        return self._analysis.set_requirements(reqs)

    def check_requirements(self) -> dict:
        return self._analysis.check_requirements()

    def _measure_registry(self, with_dfm: bool) -> dict:
        return self._analysis._measure_registry(with_dfm)

    # -- fabrication (estimate / orient / detect / open / destinations) -------

    def fab_detect(self) -> dict:
        return self._fabrication.fab_detect()

    def fab_profiles(self) -> dict:
        return self._fabrication.fab_profiles()

    def fab_estimate(self, destination_id: str | None = None) -> dict:
        return self._fabrication.fab_estimate(destination_id)

    def fab_orient(self, overhang_deg: float = 45.0) -> dict:
        return self._fabrication.fab_orient(overhang_deg)

    def fab_open(self, destination_id: str | None = None) -> dict:
        return self._fabrication.fab_open(destination_id)

    def list_destinations(self) -> dict:
        return self._fabrication.list_destinations()

    def set_destinations(self, destinations: list) -> dict:
        return self._fabrication.set_destinations(destinations)

    # -- generative exploration (sweep / optimize) --------------------------

    def sweep(self, param: str, values: list, checks: bool = False) -> dict:
        return self._exploration.sweep(param, values, checks)

    def optimize(
        self,
        param: str,
        objective: str = "min_mass",
        steps: int = 9,
        constraints: dict | None = None,
        values: list | None = None,
    ) -> dict:
        return self._exploration.optimize(param, objective, steps, constraints, values)

    def check_motion(
        self,
        part: str,
        kind: str = "revolute",
        axis_origin=None,
        axis_dir=None,
        start: float = 0.0,
        stop: float = 90.0,
        steps: int = 12,
    ) -> dict:
        return self._exploration.check_motion(part, kind, axis_origin, axis_dir, start, stop, steps)

    def converge_to_spec(
        self, objective: str = "min_mass", apply: bool = False, max_evals: int = 24
    ) -> dict:
        return self._exploration.converge_to_spec(objective, apply, max_evals)

    # -- reverse engineering ------------------------------------------------

    def analyze_import(self, name=None) -> dict:
        return self._imports.analyze_import(name)

    # -- history: geometric diff + build report -----------------------------

    def _build_compound(
        self, code: str, param_values: dict | None, *, apply_references: bool = True
    ):
        """Build a Compound from ``code`` (+ optional params) in a fresh registry.
        Used to reconstruct a checkpoint or restore the live model; the caller
        orders the calls so the live registry ends in the right state.

        Applies the workspace's reference fixtures like the normal build path, so
        a diff does not report a solid reference's volume as a phantom change and
        restoring the live registry does not strip references from the next render.
        """
        solidifai.reset_registry()
        solidifai.set_workspace_root(self.root)
        ns: dict = {}
        exec(compile(code, "<diff>", "exec"), ns)
        build_fn = ns.get("build")
        schema = ns.get("PARAMS")
        if callable(build_fn) and isinstance(schema, dict):
            merged = {k: v.get("value") for k, v in schema.items() if isinstance(v, dict)}
            merged.update(param_values or {})
            # Always rebuild explicitly at the merged params. A conventional script
            # runs build(**defaults) at module level during exec, so reset first or
            # this second build stacks a duplicate set of solids onto the registry.
            solidifai.reset_registry()
            build_fn(**merged)
        if apply_references:
            self._apply_references()
        return _compound_from_registry(solidifai._registry())

    def diff_against(self, index: int) -> dict:
        return self._reporting.diff_against(index)

    def build_report(self, views=None) -> dict:
        return self._reporting.build_report(views)

    # -- imports (reference fixtures) ---------------------------------------

    def _apply_references(self) -> None:
        return self._imports._apply_references()

    def _rebuild_preserving_params(self) -> dict:
        """Rebuild after an imports change. Re-runs model.py (so manifest
        references are re-applied via the normal build path) at the current saved
        param values, robust to registry state. Falls back to a references-only
        re-render when there is no model.py.

        Uses the internal _run_script (not run_file) so it bypasses the assembly
        refusal: this is an internal rebuild, not an agent-authored single model."""
        if self.model_path and os.path.exists(self.model_path):
            with open(self.model_path, encoding="utf-8") as f:
                res = self._run_script(f.read())
            if res.get("ok") and self.root is not None and self._build_fn is not None:
                saved = settings.load_params(self.root)
                block = self._params_block()
                if saved and block is not None:
                    res = self.set_params(settings.merge(block["values"], saved))
            return res
        return self._rerender_with_references()

    def _rerender_with_references(self) -> dict:
        """Re-apply references onto the current registry and re-render (bumps
        buildId). Works even with no model.py (references-only workspace)."""
        next_build = self.build_id + 1
        self._apply_references()
        try:
            render_to(
                self.artifacts_dir,
                next_build,
                params=self._last_params_block,
                overrides=self._material_overrides,
            )
            self._model = _compound_from_registry(solidifai._registry())
            self._objects = list(solidifai._registry())
            self._snapshot_features()
        except Exception as exc:  # noqa: BLE001
            self._cleanup_temps()
            self.last_ok = False
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        self.build_id = next_build
        self.last_ok = True
        return {"ok": True, "buildId": self.build_id}

    def stage_import(self, source_path: str) -> dict:
        return self._imports.stage_import(source_path)

    def import_reference(self, source_path: str, name: str | None = None) -> dict:
        return self._imports.import_reference(source_path, name)

    def remove_import(self, import_id: str) -> dict:
        return self._imports.remove_import(import_id)

    def list_imports(self) -> dict:
        return self._imports.list_imports()

    # -- technical drawing --------------------------------------------------

    def create_drawing(self, path: str | None = None, options: dict | None = None) -> dict:
        return self._reporting.create_drawing(path, options)

    def _snapshot_features(self) -> None:
        """Snapshot the last-good feature inventory. Declared ``feature()`` tags
        win; for an untagged build, fall back to best-effort inference over the
        final model (never fails the build)."""
        declared = list(solidifai._feature_registry())
        if declared:
            self._features = self._dedupe_feature_names(declared)
            return
        try:
            inferred = feature_geom.infer(self._model) if self._model is not None else []
            self._features = self._dedupe_feature_names(inferred)
        except Exception:  # noqa: BLE001 - inference is best-effort
            self._features = []

    @staticmethod
    def _dedupe_feature_names(records: list) -> list:
        """Auto-suffix duplicate feature names in place so each feature is
        individually addressable (a second ``port`` becomes ``port_2``), matching
        the show()/node-id dedup convention. The first occurrence keeps its bare
        name; collisions with an existing suffix are re-bumped until unique."""
        counts: dict = {}
        used: set = set()
        for rec in records:
            base = rec.name
            name = base
            while name in used:
                counts[base] = counts.get(base, 1) + 1
                name = f"{base}_{counts[base]}"
            used.add(name)
            rec.name = name
        return records

    def _unknown_driven_by(self, f: solidifai.FeatureRecord) -> list:
        """driven_by names on ``f`` that are not declared parameters (a typo in the
        feature declaration). Empty for a well-wired or non-parametric feature."""
        return [d for d in getattr(f, "driven_by", []) if d not in self._param_values]

    def _feature_to_dict(self, f: solidifai.FeatureRecord) -> dict:
        summary = feature_geom.summarize(getattr(f, "faces", []) or [])
        out = {
            "name": f.name,
            "kind": f.kind,
            "driven_by": list(f.driven_by),
            "source": {"line": f.source_line},
            "center": summary["center"],
            "bbox": summary["bbox"],
            "metrics": summary["metrics"],
            "inferred": bool(getattr(f, "inferred", False)),
            "confidence": getattr(f, "confidence", None),
        }
        part = getattr(f, "part", None)
        if part is not None:
            out["part"] = part
        # Surface a mis-wired declaration so the agent sees it before trying to set it.
        unknown = self._unknown_driven_by(f)
        if unknown:
            valid = ", ".join(sorted(self._param_values)) or "(none)"
            out["warning"] = (
                f"driven_by names {unknown} which are not parameters; "
                f"available: {valid}. Fix the feature(driven_by=...) declaration."
            )
        return out

    def get_model_info(self) -> dict:
        """Return the last-GOOD ``model.json`` contents, or an empty dict if no
        successful build has happened yet.

        This is independent of ``last_ok``: a failed most-recent operation never
        overwrites the artifacts, so this always reflects the last good model.

        ``round_active`` is an additive RUNTIME field (whether an authoring round is
        open) so a stuck round is diagnosable. It is never written into model.json on
        disk, which keeps the single-model byte guarantee intact.
        """
        path = paths.json_path(self.artifacts_dir)
        if not os.path.exists(path):
            return {"round_active": bool(self._round.get("active"))}
        with open(path, encoding="utf-8") as f:
            info = json.load(f)
        info["round_active"] = bool(self._round.get("active"))
        return info

    def render(self) -> dict:
        """Re-render the LAST-GOOD model with the next buildId.

        Renders the last successful build's snapshot (``self._objects``), not the
        live global registry: a failed build can leave partial geometry in the
        registry, and re-rendering that would overwrite the last-good artifacts and
        flip ``last_ok`` back to True while ``model.py`` on disk still holds the
        good source. Mirrors capture_views, which also reads ``self._objects``."""
        # Gate on the snapshot, not self.code: the assembly path composes into
        # self._objects but never sets self.code, so a code-only gate wrongly
        # reports "no model loaded" for a healthy assembly.
        if not self._objects:
            return {"ok": False, "error": "no model loaded"}
        next_build = self.build_id + 1
        try:
            render_to(
                self.artifacts_dir,
                next_build,
                params=self._last_params_block,
                overrides=self._material_overrides,
                objects=self._objects,
            )
        except Exception as exc:  # noqa: BLE001
            return self._build_failed(exc)
        self.build_id = next_build
        self.last_ok = True
        return {"ok": True, "buildId": self.build_id}

    def capture_views(
        self,
        view_names: list | None = None,
        layout: str = "separate",
        color: bool = True,
        explode: float = 0.0,
        highlight: list | None = None,
        resolution: int = 512,
        section: dict | None = None,
        focus: str | list | None = None,
    ) -> dict:
        """Render the last-good model from the requested views; return the
        written PNG paths. ``layout="separate"`` returns one entry per view;
        ``layout="grid"`` tiles them into a single contact sheet. Defaults to
        ``["iso"]`` when no views are given. ``explode`` (0..100, a percent)
        spreads the shown parts radially for THIS render only, so a multi-part
        assembly is captured pulled apart for a fit review — it never mutates
        the saved/exported model; ``0`` renders assembled. ``highlight`` is an
        optional list of feature names (from ``inspect_features``) to render with
        an orange accent overlay. ``resolution`` is the square render edge in px
        (256..2048; default 512). ``section`` ({"axis", "offset_mm"}) renders the
        model plane-cut with magenta cap faces; ``focus`` (feature name or
        [xmin,ymin,zmin,xmax,ymax,zmax]) frames the camera close on that target
        with ~15% margin."""
        err, resolution = validate_capture_args(layout, resolution, section, explode)
        if err is not None:
            return {"ok": False, "error": err}
        if self._model is None:
            return {"ok": False, "error": "no model to capture — run execute_script first"}
        model = self._model  # not None past here; objects are set alongside it
        objects = self._objects or []
        if view_names:
            names = list(view_names)
        elif section is not None:
            names = [_SECTION_FACE_VIEW[section["axis"]], "iso"]
        else:
            names = ["iso"]
        out_dir = scratch.views_dir(self.artifacts_dir, self.build_id)
        try:
            mesh = assemble_capture_mesh(
                model,
                objects,
                explode=explode,
                section=section,
                color=color,
                timeout_s=SECTION_TIMEOUT_S,
            )
            highlight_mesh = resolve_highlight(highlight, self._features)
            focus_bounds, focus_label = resolve_focus(focus, self._features)
        except CaptureError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - tessellation/resolve never crashes
            return {"ok": False, "error": f"capture failed ({type(exc).__name__}): {exc}"}
        vertices, tris, groups, cap_mesh = mesh
        try:
            rendered = views_mod.render_views(
                vertices,
                tris,
                out_dir,
                names,
                groups=groups,
                highlight_mesh=highlight_mesh,
                size=resolution,
                cap_mesh=cap_mesh,
                focus_bounds=focus_bounds,
                focus_label=focus_label,
            )
        except ValueError as exc:  # unknown/malformed view spec
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - GL/IO failures never crash
            return {"ok": False, "error": f"capture failed ({type(exc).__name__}): {exc}"}
        if layout == "grid":
            sheet = os.path.join(out_dir, "contact_sheet.png")
            try:
                path, w, h = montage.grid(
                    [(r["name"], r["path"]) for r in rendered],
                    sheet,
                    tile_px=max(256, resolution // 2),
                )
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"contact sheet failed ({type(exc).__name__}): {exc}"}
            return {
                "ok": True,
                "buildId": self.build_id,
                "layout": "grid",
                "views": [{"name": "contact_sheet", "path": path, "width": w, "height": h}],
                **({"section": section} if section is not None else {}),
            }
        return {
            "ok": True,
            "buildId": self.build_id,
            "layout": "separate",
            "views": rendered,
            **({"section": section} if section is not None else {}),
        }

    def export(self, format: str, path: str | None = None, options: dict | None = None) -> dict:
        """Export the current model in ``format`` with optional ``options``.

        Exports land in the workspace's ``exports/`` folder by default. With no
        ``path``, the file is ``exports/<slug>.<ext>`` where ``slug`` is the
        workspace folder name. A relative ``path`` is resolved under that same
        ``exports/`` folder, so an agent's bare filename still lands in the
        workspace. An absolute ``path`` is honored as given. For a bare session
        (no workspace root) the default falls back to the artifacts scratch dir.
        Returns the resolved path."""
        # Export the last-good snapshot (self._objects), never the live registry:
        # a failed build can leave partial geometry there, and the assembly path
        # never sets self.code. Gating on the snapshot serves both modes.
        if not self._objects:
            return {"ok": False, "error": "no model loaded"}
        base = (
            os.path.join(self.root, "exports")
            if self.root
            else scratch.exports_dir(self.artifacts_dir)
        )
        if not path:
            name = os.path.basename(self.root) if self.root else "model"
            path = os.path.join(base, f"{scratch.slug(name)}.{format.lower()}")
        elif not os.path.isabs(path):
            path = os.path.join(base, path)
        try:
            out = exports_export(format, path, options, objects=self._objects)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": True, "path": out}

    # -- helpers ------------------------------------------------------------

    def _persist_settings(self) -> None:
        """Write the current numeric param values to <root>/settings.json."""
        if self.root is None:
            return
        block = self._params_block()
        settings.write_params(self.root, block["values"] if block else {})

    def _after_build(self, *, structural: bool) -> None:
        """Persist current settings and auto-commit. Best-effort: a git failure
        is logged and never fails the build (the model already rendered)."""
        self._persist_settings()
        if self.history is None or not self.history.enabled():
            return
        try:
            if structural:
                self.history.commit(f"edit (build {self.build_id})", amend=False)
                self._last_param_commit_t = 0.0  # seal any open param burst
            else:
                now = time.monotonic()
                amend = (now - self._last_param_commit_t) < COALESCE_WINDOW
                self.history.commit(f"adjust params (build {self.build_id})", amend=amend)
                self._last_param_commit_t = now
        except Exception:  # noqa: BLE001 - commit is best-effort
            logging.getLogger(__name__).warning("auto-commit failed", exc_info=True)

    def _after_assembly_edit(self, res: dict, message: str) -> dict:
        """Persist settings and commit the whole assembly fileset after a successful
        structural edit, so undo/redo/goto and the structural diff have a snapshot
        to restore and compare. Best-effort: a commit failure never fails the edit
        (the model already composed). Suppressed during startup/restore replay."""
        if self._suppress_persist or not res.get("ok"):
            return res
        self._persist_settings()
        if self.history is None or not self.history.enabled():
            return res
        try:
            self.history.commit(message, amend=False)
            self._last_param_commit_t = 0.0  # seal any open param burst
        except Exception:  # noqa: BLE001 - commit is best-effort
            logging.getLogger(__name__).warning("assembly auto-commit failed", exc_info=True)
        return res

    def _rebuild_after_restore(self) -> dict:
        """Rebuild after history restored an earlier state, suppressing new commits.

        Single-model: re-run the restored model.py + settings.json. Assembly: the
        restored fileset (skeleton + parts + manifest) is already on disk, so reload
        the material overrides and skeleton params, then rebuild the DAG. Returns a
        clean error if the restored state fails to rebuild (normally it can't, since
        only successfully-built states are ever committed)."""
        # Only reachable via undo/redo/restore, which require a real workspace.
        if self.history is None or self.model_path is None:
            return {"ok": False, "error": "history unavailable"}
        self._suppress_persist = True
        try:
            if self._is_assembly_mode():
                res = self._rebuild_assembly_after_restore()
            else:
                res = self.run_file(self.model_path)
                if res.get("ok") and self.root is not None:
                    saved = settings.load_params(self.root)
                    block = self._params_block()
                    if saved and block is not None:
                        res = self.set_params(settings.merge(block["values"], saved))
        finally:
            self._suppress_persist = False
        if not res.get("ok"):
            return {"ok": False, "error": "could not rebuild the restored model state"}
        return {"ok": True, "buildId": self.build_id, "index": self.history.index}

    def _rebuild_assembly_after_restore(self) -> dict:
        """Reload the restored assembly state and rebuild the composed model. The
        fileset is already on disk (history wrote it); reload overrides + skeleton
        params from the restored files, then merge the restored settings.json params
        so a param-only undo/redo lands on the right values."""
        # Only reached on the assembly restore path, where the workspace has a root.
        assert self.root is not None
        self._material_overrides = part_materials.load_overrides(self.root)
        self._load_assembly_params()
        params = dict(self._param_values)
        saved = settings.load_params(self.root)
        if saved:
            params = settings.merge(params, saved)
        res = self._build_assembly(params=params)
        if res.get("ok"):
            self._param_values = params
        return res

    def undo(self) -> dict:
        """Step back one history entry and rebuild the restored model state.

        Works for both single-model and assembly workspaces: in assembly mode the
        whole recursive fileset (skeleton + parts + manifest) is restored and the
        DAG rebuilt. Refused mid-round so the round stays internally consistent."""
        if self._round.get("active"):
            return {"ok": False, "error": "a round is active; end_round first"}
        if self.history is None or not self.history.enabled():
            return {"ok": False, "error": "history unavailable"}
        return self._restore_step(self.history.undo, "nothing to undo")

    def redo(self) -> dict:
        """Step forward one history entry and rebuild the restored model state."""
        if self._round.get("active"):
            return {"ok": False, "error": "a round is active; end_round first"}
        if self.history is None or not self.history.enabled():
            return {"ok": False, "error": "history unavailable"}
        return self._restore_step(self.history.redo, "nothing to redo")

    def goto(self, index: int) -> dict:
        """Jump to history entry ``index`` and rebuild the restored model state."""
        if self._round.get("active"):
            return {"ok": False, "error": "a round is active; end_round first"}
        if self.history is None or not self.history.enabled():
            return {"ok": False, "error": "history unavailable"}
        return self._restore_step(lambda: self.history.goto(int(index)), "invalid history index")

    def _restore_step(self, step, empty_error: str) -> dict:
        """Run a history navigation step (undo/redo/goto) and rebuild the restored
        state, transactionally: the timeline and disk only move if the restored
        state actually rebuilds.

        The step writes files, moves the branch, and saves the timeline; we then
        attempt the rebuild. If the rebuild FAILS (an older state depends on a
        since-deleted asset) or the restore walk RAISES (a corrupt/hand-edited
        fileset whose source escapes the workspace), we roll the whole thing back
        so the cursor never drifts and disk/memory/artifacts stay in sync. Without
        this, every retry stepped the index and rewrote model.py, and the next
        set_params committed code+geometry that never coexisted."""
        assert self.history is not None  # callers gate on history being enabled
        snapshot = None
        try:
            # snapshot_state walks the fileset, so a corrupt/hand-edited manifest
            # (source escaping the workspace) raises HERE, before any mutation --
            # caught below into a clean error with nothing to roll back.
            snapshot = self.history.snapshot_state()
            if not step():
                return {"ok": False, "error": empty_error}
            res = self._rebuild_after_restore()
        except Exception as exc:  # noqa: BLE001
            if snapshot is not None:  # a restore may have partially applied: undo it
                with contextlib.suppress(Exception):
                    self.history.revert_state(snapshot)
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        if not res.get("ok"):
            self.history.revert_state(snapshot)
        return res

    def checkpoint(self, message: str) -> dict:
        """Label the current (tip) state with a message. Refuses while viewing an
        older state, since committing there would discard the redo stack."""
        if self.history is None or not self.history.enabled():
            return {"ok": False, "error": "history unavailable"}
        if self.history.can_redo():
            return {"ok": False, "error": "check out the latest state before checkpointing"}
        try:
            sha = self.history.commit(str(message), amend=True)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"checkpoint failed: {exc}"}
        # Seal any open param-commit burst so the next set_params starts a fresh
        # commit instead of amending (and silently discarding) this checkpoint.
        if sha is not None:
            self._last_param_commit_t = 0.0
            try:
                cr = self.check_requirements()
                summary = cr.get("summary", {})
                pass_map = {r["id"]: r.get("pass") for r in cr.get("requirements", []) if "id" in r}
                self.history.write_compliance(
                    sha,
                    {
                        "met": summary.get("met", 0),
                        "total": summary.get("total", 0),
                        "allMet": summary.get("allMet", True),
                        "pass_map": pass_map,
                    },
                )
            except Exception:  # noqa: BLE001
                pass  # compliance snap is best-effort
        return {"ok": True}

    def history_state(self) -> dict:
        """Return the full timeline ``{entries, index}`` for the history UI."""
        if self.history is None or not self.history.enabled():
            return {"entries": [], "index": -1}
        return {"entries": self.history.entries(), "index": self.history.index}

    def startup(self) -> None:
        """Load the workspace and ensure a first commit exists for a fresh repo.

        For assembly workspaces (assembly.json present) the DAG is built instead
        of running a single model.py. Never raises."""
        if not self.root:
            return
        # Re-opening a workspace clears any authoring round. A crashed orchestrator
        # could leave a round active with no end_round, which would otherwise refuse
        # set_skeleton forever; the round is in-memory and transient, so a fresh open
        # starts clean. (abort_round is the in-session recovery.)
        self._round = {"active": False}
        if not self._is_assembly_mode() and (
            not self.model_path or not os.path.exists(self.model_path)
        ):
            return
        if self.root is not None:
            self._material_overrides = part_materials.load_overrides(self.root)
            self._requirements = requirements_mod.migrate_legacy(
                requirements_mod.load_requirements(self.root)
            )
        self._suppress_persist = True
        try:
            if self._is_assembly_mode():
                self._load_assembly_params()
                res = self._build_assembly(params={})
            else:
                # Non-assembly mode: the guard above returned early if model_path was
                # missing, so it is present here.
                assert self.model_path is not None
                res = self.run_file(self.model_path)
            if res.get("ok") and self.root is not None:
                saved = settings.load_params(self.root)
                block = self._params_block()
                if saved and block is not None:
                    self.set_params(settings.merge(block["values"], saved))
        finally:
            self._suppress_persist = False
        # Fresh repo (no commits yet): write settings.json + the initial commit.
        if self.history is not None and self.history.enabled() and not self.history.commits:
            self._persist_settings()
            try:
                self.history.commit("init", amend=False)
            except Exception:  # noqa: BLE001 - best-effort
                logging.getLogger(__name__).warning("initial commit failed", exc_info=True)

    def _is_assembly_mode(self) -> bool:
        """True when the workspace root holds an assembly.json (assembly build path
        instead of a single model.py)."""
        return self.root is not None and os.path.exists(os.path.join(self.root, "assembly.json"))

    def _load_assembly_params(self) -> None:
        """Populate _params_schema/_param_values from the root skeleton's PARAMS so
        the UI shows sliders and model.json carries them. No build_fn in assembly
        mode; the schema drives build_workspace(params=...) instead."""
        from solidifai_engine.assembly import manifest as manifest_mod
        from solidifai_engine.assembly import runner

        # Assembly mode implies a workspace root on disk.
        assert self.root is not None
        man = manifest_mod.load_manifest(self.root)
        if not man.skeleton:
            self._params_schema, self._param_values = {}, {}
            return
        ns = runner._exec_file(os.path.join(self.root, man.skeleton))
        raw_schema = ns.get("PARAMS")
        schema = raw_schema if isinstance(raw_schema, dict) else {}
        self._param_values = self._default_values(schema)
        self._params_schema = self._normalize_schema(schema)

    def _build_assembly(self, *, params: dict | None = None) -> dict:
        """Build the assembly DAG, render the composed model, and snapshot session
        state. Mirrors execute_script's bookkeeping for the assembly path."""
        from solidifai_engine.assembly import compose, graph
        from solidifai_engine.render import render_to

        next_build = self.build_id + 1
        # NOTE: the parallel warm-pass (solidifai_engine.assembly.parallel) is
        # intentionally NOT wired in here. Forking from the live, long-running
        # engine process (which has accumulated OCC state and runs threads) is
        # catastrophically slow -- measured >60s per build under the test harness
        # vs ~0.2s from a fresh process. The Session builds sequentially, which is
        # already fast via the in-memory cache (B1) + persistent disk cache (B2).
        # parallel.warm_cache_parallel stays available for fresh-process/batch use.
        from solidifai_engine.assembly import manifest as manifest_mod

        # Assembly build path: the workspace always has a root here.
        assert self.root is not None
        assembly_features: list = []
        try:
            objects = graph.build_node(
                self.root,
                params=params or self._param_values,
                parent=None,
                cache=self._node_cache,
                disk=self._disk_cache,
                features_out=assembly_features,
            )
            # Empty composition: branch explicitly on a typed signal (no children vs
            # children-but-no-geometry) instead of matching a render error string.
            if not objects:
                has_children = bool(manifest_mod.load_manifest(self.root).children)
                if not has_children:
                    # Skeleton-only or emptied assembly: benign in-progress state.
                    # Leave the last-good artifacts untouched and report success.
                    self.last_ok = True
                    return {"ok": True, "buildId": self.build_id, "empty": True}
                # Children exist but produced nothing: a real problem, not silent ok.
                # composeEmpty is a typed marker so structural-edit callers can tell
                # this apart from a build crash without matching the error string.
                self.last_ok = False
                return {
                    "ok": False,
                    "composeEmpty": True,
                    "error": "assembly has children but composed to no geometry",
                }
            render_to(
                self.artifacts_dir,
                next_build,
                objects=objects,
                node_ids=compose.path_ids(objects),
                params=self._params_block(params or self._param_values),
                overrides=self._material_overrides,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_ok = False
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        self._model = _compound_from_registry(objects)
        self._objects = objects
        self._snapshot_assembly_features(assembly_features)
        self.build_id = next_build
        self.last_ok = True
        return {"ok": True, "buildId": self.build_id}

    def _snapshot_assembly_features(self, declared: list) -> None:
        """Snapshot the composed assembly's feature inventory. Per-part declared
        features (already namespaced ``<part>/<name>`` and placed in composed
        coordinates by the graph) win; when the whole assembly declares none, fall
        back to best-effort inference over the composed model. Never fails the build."""
        if declared:
            self._features = self._dedupe_feature_names(declared)
            return
        try:
            inferred = feature_geom.infer(self._model) if self._model is not None else []
            self._features = self._dedupe_feature_names(inferred)
        except Exception:  # noqa: BLE001 - inference is best-effort
            self._features = []

    # -- assembly authoring helpers -----------------------------------------

    # A child id becomes a path segment (parts/<id>.py, <id>/), so it must be a
    # plain name: letters, digits, hyphen, underscore. This rejects "..", "/",
    # "\\", absolute paths, dots, and null bytes before any id reaches the disk.
    _CHILD_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

    @classmethod
    def _valid_child_id(cls, child_id) -> bool:
        return isinstance(child_id, str) and bool(cls._CHILD_ID_RE.match(child_id))

    @staticmethod
    def _bad_id_error(child_id) -> dict:
        return {
            "ok": False,
            "error": f"invalid part id {child_id!r}: use letters, digits, hyphen, underscore",
        }

    def _within_root(self, path: str) -> bool:
        """True when path resolves inside the workspace root (symlinks resolved).
        Defense in depth against an inconsistent/hand-edited manifest source."""
        # Only consulted while mutating an assembly, which has a root.
        assert self.root is not None
        root_real = os.path.realpath(self.root)
        target_real = os.path.realpath(path)
        return os.path.commonpath([root_real, target_real]) == root_real

    def _assembly_root_paths(self) -> dict:
        """Absolute paths for the root assembly's managed files."""
        if self.root is None:
            raise RuntimeError("no workspace root")
        return {
            "manifest": os.path.join(self.root, "assembly.json"),
            "skeleton": os.path.join(self.root, "skeleton.py"),
            "parts_dir": os.path.join(self.root, "parts"),
        }

    def _part_source_path(self, child_id: str) -> str:
        assert self.root is not None
        return os.path.join(self.root, "parts", f"{child_id}.py")

    @staticmethod
    def _file_hash(path: str) -> str | None:
        """sha256 of a file's bytes (same hashing the content cache uses), or None
        if the file is missing. Used to snapshot the frozen skeleton at begin_round."""
        import hashlib

        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except OSError:
            return None

    def _rewrite_manifest(self, mutate) -> None:
        """Load the root manifest, apply mutate(man) in place, write it back atomically."""
        from solidifai_engine.assembly import manifest as manifest_mod

        # Manifest rewrites only happen for assembly workspaces, which have a root.
        assert self.root is not None
        man = manifest_mod.load_manifest(self.root)
        mutate(man)
        manifest_mod.write_manifest(self.root, man)

    def _ensure_assembly_root(self, *, skeleton: str | None) -> None:
        """Create assembly.json (and parts/) for a fresh workspace if absent. Idempotent."""
        from solidifai_engine.assembly import manifest as manifest_mod

        paths_ = self._assembly_root_paths()  # raises if root is None
        assert self.root is not None
        os.makedirs(paths_["parts_dir"], exist_ok=True)
        if not os.path.exists(paths_["manifest"]):
            manifest_mod.write_manifest(
                self.root, manifest_mod.Manifest(skeleton=skeleton, children=[])
            )

    # -- assembly authoring tools -------------------------------------------

    def set_skeleton(self, code: str) -> dict:
        """Write skeleton.py, (re)initialize assembly mode, reload params, rebuild.

        On a fresh single-part-or-empty workspace this is the entry point into the
        assembly model: it creates assembly.json with this skeleton and no children
        yet. On an existing assembly it replaces the skeleton and cascades the
        change through _build_assembly."""
        if self.root is None:
            return {"ok": False, "error": "no workspace; cannot author an assembly"}
        if self._round.get("active"):
            return {"ok": False, "error": "the skeleton is frozen during a round; end_round first"}
        try:
            self._ensure_assembly_root(skeleton="skeleton.py")
            # A workspace that started empty has the single-model allowlist
            # gitignore (which would ignore skeleton.py / parts/). Becoming an
            # assembly switches it to the denylist so the whole fileset is tracked.
            if self.history is not None and self.history.enabled():
                self.history.ensure_assembly_gitignore()
            self._rewrite_manifest(lambda m: setattr(m, "skeleton", "skeleton.py"))
            skel_path = self._assembly_root_paths()["skeleton"]
            tmp = paths.write_temp_text(skel_path, code)
            paths.atomic_finalize(tmp, skel_path)
            self._load_assembly_params()
            # A skeleton with no children yet composes to nothing; _build_assembly
            # reports that as a benign empty success (no children -> ok:True empty).
            res = self._build_assembly(params=self._param_values)
            return self._after_assembly_edit(res, "edit skeleton")
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }

    def set_part(
        self,
        part_id: str,
        code: str,
        *,
        attach=None,
        inputs=None,
        shape_inputs=None,
        kind: str = "part",
    ) -> dict:
        """Write parts/<id>.py and ensure its manifest child exists, then rebuild.

        A new id is added as a child wired to attach (a skeleton frame name, or None
        for the node origin) and inputs (skeleton outputs the part may read). Updating
        an existing id rewrites its source; attach/inputs change only when explicitly
        passed, so a source-only edit preserves wiring."""
        if self.root is None:
            return {"ok": False, "error": "no workspace; cannot author a part"}
        if not self._valid_child_id(part_id):
            return self._bad_id_error(part_id)
        if not self._is_assembly_mode():
            return {
                "ok": False,
                "error": "no skeleton yet; call set_skeleton first "
                "(or use execute_script for a single part)",
            }
        from solidifai_engine.assembly import manifest as manifest_mod

        try:
            os.makedirs(self._assembly_root_paths()["parts_dir"], exist_ok=True)
            dest = self._part_source_path(part_id)
            if not self._within_root(dest):  # defense in depth (id already validated)
                return self._bad_id_error(part_id)

            # Snapshot prior state so a build failure is a clean no-op (a broken part
            # must not poison the manifest or leave a half-written source file).
            prior_man = manifest_mod.load_manifest(self.root)
            # Refuse to silently convert an existing sub-assembly into a part: that
            # would rewrite its kind and orphan its <id>/ directory. Make the caller
            # remove it explicitly first.
            existing_child = manifest_mod.child_by_id(prior_man, part_id)
            if existing_child is not None and existing_child.kind != kind:
                return {
                    "ok": False,
                    "error": f"{part_id!r} is a sub-assembly; remove_part it first "
                    f"to replace it with a part",
                }
            prior_src = None
            with contextlib.suppress(OSError), open(dest, encoding="utf-8") as f:
                prior_src = f.read()

            tmp = paths.write_temp_text(dest, code)
            paths.atomic_finalize(tmp, dest)

            def mutate(man):
                existing = manifest_mod.child_by_id(man, part_id)
                entry = manifest_mod.ChildEntry(
                    id=part_id,
                    kind=kind,
                    source=f"parts/{part_id}.py",
                    attach=attach if attach is not None or existing is None else existing.attach,
                    inputs=list(inputs)
                    if inputs is not None
                    else (list(existing.inputs) if existing else []),
                    shape_inputs=list(shape_inputs)
                    if shape_inputs is not None
                    else (list(existing.shape_inputs) if existing else []),
                )
                manifest_mod.upsert_child(man, entry)

            self._rewrite_manifest(mutate)
            # The cache is content-addressed by part_key(source, inputs, path), so
            # rewriting source already changes the key and rebuilds just this part.
            if self._round.get("active"):
                # Deferred-compose mode: build and validate this part in isolation,
                # writing it into the L1+L2 cache under the same key the composer uses,
                # but skip the whole-assembly compose. end_round then HITS cache for
                # this part (zero rebuild). A part that fails or shows nothing is
                # isolated into the round's failed map and rolled back here, so it
                # never aborts the round.
                man = manifest_mod.load_manifest(self.root)
                one = self._build_one_part(manifest_mod.child_by_id(man, part_id), man)
                res = self._record_round_build(one, part_id)
                if not res.get("ok") and prior_src is not None:
                    # A failed EDIT was rolled back to its prior-good version, which
                    # is present and valid: report it as built, not failed. (A failed
                    # NEW part is left in `failed` with its source removed -- isolated
                    # per the round contract, see _rollback_part.)
                    self._rollback_part(dest, prior_man, prior_src)
                    self._round["failed"].pop(part_id, None)
                    self._round["built"].add(part_id)
                elif not res.get("ok"):
                    self._rollback_part(dest, prior_man, prior_src)
                return res
            res = self._build_assembly(params=self._param_values)
            if not res.get("ok"):
                self._rollback_part(dest, prior_man, prior_src)
                return res
            verb = "edit" if prior_src is not None else "add"
            return self._after_assembly_edit(res, f"{verb} part {part_id}")
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }

    def _rollback_part(self, source_path: str, prior_man, prior_src: str | None) -> None:
        """Undo a failed set_part: restore the manifest and the source file to their
        pre-mutation state (delete the file if it did not exist before)."""
        from solidifai_engine.assembly import manifest as manifest_mod

        assert self.root is not None
        with contextlib.suppress(Exception):
            manifest_mod.write_manifest(self.root, prior_man)
        with contextlib.suppress(OSError):
            if prior_src is None:
                os.remove(source_path)
            else:
                tmp = paths.write_temp_text(source_path, prior_src)
                paths.atomic_finalize(tmp, source_path)

    def _build_one_part(self, entry, man) -> dict:
        """Build one part in isolation against the current skeleton and summarize it.

        Builds via graph.build_child, the SAME helper the whole-assembly compose
        uses, writing into the session's L1+L2 caches under the identical content
        key. So a part built here (e.g. during a round) is a cache HIT when the
        composer later places it, and end_round does zero extra part work.

        Resolves the child's inputs, runs the part in its own scope (or reuses a
        cache hit), validates, and returns {"ok": True, "id", "valid", "solids",
        "bbox"}. A part that produces no geometry is an error here (the same I2 guard
        the composer applies), so a no-show() part is isolated rather than silently
        composing to nothing. On any failure returns {"ok": False, "error", ...}.
        Never recomposes; callers decide whether to compose (outside a round) or
        defer (inside one). During a round the frozen skeleton is reused (run once at
        begin_round) instead of re-run per part."""
        from solidifai_engine.assembly import graph, runner

        assert self.root is not None
        try:
            skel = self._round.get("skeleton_result") if self._round.get("active") else None
            if skel is None:
                skel = (
                    runner.run_skeleton(
                        os.path.join(self.root, man.skeleton),
                        params=self._param_values,
                        parent=None,
                    )
                    if man.skeleton
                    else __import__("solidifai", fromlist=["SkeletonResult"]).SkeletonResult()
                )
            objs, _key = graph.build_child(
                self.root,
                skel,
                entry,
                cache=self._node_cache,
                disk=self._disk_cache,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "id": entry.id,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        solids = sum(len(o.shape.solids()) for o in objs)
        valid = all(self._shape_is_valid(o.shape) for o in objs)
        return {
            "ok": True,
            "id": entry.id,
            "valid": valid,
            "solids": solids,
            "bbox": self._objects_bbox(objs),
        }

    def build_part(self, part_id: str) -> dict:
        """Build one part in isolation against the current skeleton and report its
        result (valid, solids, bbox). Outside a round it then recomposes the model so
        the viewport is consistent; inside a round it records the result and defers
        the whole-assembly compose to end_round (deferred=True)."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        if not self._valid_child_id(part_id):
            return self._bad_id_error(part_id)
        from solidifai_engine.assembly import manifest as manifest_mod

        man = manifest_mod.load_manifest(self.root)
        entry = manifest_mod.child_by_id(man, part_id)
        if entry is None:
            return {"ok": False, "error": f"no part {part_id!r} in this assembly"}
        if entry.kind != "part":
            return {"ok": False, "error": f"{part_id!r} is a {entry.kind}, not a part"}
        one = self._build_one_part(entry, man)
        if self._round.get("active"):
            return self._record_round_build(one, part_id)
        if not one.get("ok"):
            return one
        # Recompose so the viewport reflects this part's current source. The
        # part-level result above stands on its own; surface whether the whole
        # assembly still composes via "composed" (another broken part can fail the
        # compose while THIS part is perfectly valid).
        compose_res = self._build_assembly(params=self._param_values)
        result = {
            "ok": True,
            "id": part_id,
            "valid": one["valid"],
            "solids": one["solids"],
            "bbox": one["bbox"],
            "composed": bool(compose_res.get("ok")),
        }
        if not compose_res.get("ok"):
            result["composeError"] = compose_res.get("error")
        return result

    def _record_round_build(self, one: dict, part_id: str) -> dict:
        """Fold an isolated part build into the active round: track built vs failed
        and return the deferred per-part result. On success the result carries
        deferred=True (no compose happened); on failure the part id is recorded in
        the round's failed map and the error is returned for the caller to roll back."""
        if one.get("ok"):
            self._round["failed"].pop(part_id, None)
            self._round["built"].add(part_id)
            return {
                "ok": True,
                "id": part_id,
                "valid": one["valid"],
                "solids": one["solids"],
                "bbox": one["bbox"],
                "deferred": True,
            }
        self._round["built"].discard(part_id)
        self._round["failed"][part_id] = one.get("error", "build failed")
        return {**one, "deferred": True}

    # -- authoring round ----------------------------------------------------

    def _round_guard(self) -> dict | None:
        """Refuse a compose-triggering mutation while a round is open. During a round
        the only allowed structural change is set_part of a part (the deferred path);
        every other mutator that would compose mid-round (set_params, attach,
        set_inputs, remove_part, add_subassembly, set_part_material) is blocked so the
        round stays internally consistent and composes exactly once at end_round."""
        if self._round.get("active"):
            return {"ok": False, "error": "a round is active; end_round first"}
        return None

    def begin_round(self) -> dict:
        """Freeze the skeleton and enter deferred-compose authoring. Returns the
        skeleton contract (params, scalars, frames, shapes) so an orchestrator can hand each
        part its inputs and attach frame. While a round is active, set_part/build_part
        validate each part in isolation but do not recompose; set_skeleton is refused.
        Call end_round to compose and render the whole assembly once."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        if self._round.get("active"):
            return {"ok": False, "error": "a round is already active; end it first"}
        from solidifai_engine.assembly import manifest as manifest_mod
        from solidifai_engine.assembly import runner
        from solidifai_engine.assembly import tree as tree_mod

        skel_path = self._assembly_root_paths()["skeleton"]
        # Run the (now-frozen) skeleton ONCE with the current params and keep the
        # result, so every set_part in this round reuses it instead of re-running the
        # skeleton per part. Params are frozen during a round (set_params is refused),
        # so this result stays valid for the whole round.
        man = manifest_mod.load_manifest(self.root)
        skel_result = None
        if man.skeleton:
            skel_result = runner.run_skeleton(
                os.path.join(self.root, man.skeleton),
                params=self._param_values,
                parent=None,
            )
        self._round = {
            "active": True,
            # Snapshot the frozen skeleton's bytes; end_round re-hashes to catch an
            # out-of-band edit and rebuild fresh rather than composing a stale contract.
            "skeleton_hash": self._file_hash(skel_path),
            "skeleton_result": skel_result,
            "built": set(),
            "failed": {},
            # Snapshot the manifest + part sources so abort_round rolls back the
            # structural writes a set_part makes during the round (new parts get
            # removed, edited parts reverted). Without this, aborted parts persist
            # uncommitted and a later undo silently deletes them.
            "sources_snapshot": self._snapshot_round_sources(),
        }
        return {"ok": True, "skeleton": tree_mod.assembly_tree(self.root)["skeleton"]}

    def _snapshot_round_sources(self) -> dict:
        """Capture assembly.json + every parts/*.py source (as text) at begin_round.
        abort_round replays this to restore the exact pre-round fileset."""
        assert self.root is not None
        paths_ = self._assembly_root_paths()
        manifest_text: str | None = None
        with contextlib.suppress(OSError), open(paths_["manifest"], encoding="utf-8") as f:
            manifest_text = f.read()
        sources: dict = {}
        parts_dir = paths_["parts_dir"]
        if os.path.isdir(parts_dir):
            for name in os.listdir(parts_dir):
                path = os.path.join(parts_dir, name)
                if os.path.isfile(path):
                    with contextlib.suppress(OSError), open(path, encoding="utf-8") as f:
                        sources[path] = f.read()
        return {"manifest": manifest_text, "sources": sources}

    def _restore_round_sources(self, snap: dict) -> None:
        """Restore assembly.json + parts/*.py to the begin_round snapshot: revert
        edited/known files, delete parts written during the round, recreate any that
        were removed. All writes stay inside the workspace root (defense in depth)."""
        assert self.root is not None
        paths_ = self._assembly_root_paths()
        manifest_text = snap.get("manifest")
        if manifest_text is not None and self._within_root(paths_["manifest"]):
            tmp = paths.write_temp_text(paths_["manifest"], manifest_text)
            paths.atomic_finalize(tmp, paths_["manifest"])
        sources: dict = snap.get("sources", {})
        parts_dir = paths_["parts_dir"]
        current: set = set()
        if os.path.isdir(parts_dir):
            current = {
                os.path.join(parts_dir, n)
                for n in os.listdir(parts_dir)
                if os.path.isfile(os.path.join(parts_dir, n))
            }
        # Delete parts that did not exist at begin_round (written during the round).
        for path in current - set(sources):
            if self._within_root(path):
                with contextlib.suppress(OSError):
                    os.remove(path)
        # Restore the snapshot contents (reverts edits, recreates deletions).
        for path, text in sources.items():
            if self._within_root(path):
                with contextlib.suppress(OSError):
                    tmp = paths.write_temp_text(path, text)
                    paths.atomic_finalize(tmp, path)

    def end_round(self) -> dict:
        """Leave deferred-compose mode and compose plus render the whole assembly
        once. Returns the composed model result plus a failed map of any parts that
        did not build during the round (each value is the failure message).

        The parts built during the round are reused from cache here (same content
        key), so this compose does no redundant part work. If the skeleton was edited
        on disk out of band during the round, the frozen contract is stale; the compose
        re-runs the skeleton fresh (so it is still correct) and the result notes
        skeletonChanged=True."""
        if not self._round.get("active"):
            return {"ok": False, "error": "no active round"}
        failed = dict(self._round.get("failed", {}))
        built = sorted(self._round.get("built", set()))
        skel_path = self._assembly_root_paths()["skeleton"]
        skeleton_changed = self._file_hash(skel_path) != self._round.get("skeleton_hash")
        self._round = {"active": False}
        res = self._rebuild_after_structure_edit("author round")
        if isinstance(res, dict):
            res = {**res, "failed": failed, "built": built}
            if skeleton_changed:
                res["skeletonChanged"] = True
        return res

    def abort_round(self) -> dict:
        """Leave deferred-compose mode without composing (discard the round).

        Rolls back the structural writes made during the round: parts added via
        set_part are deleted, edited parts are reverted, and the manifest is
        restored to its begin_round state. The model already reflects the last
        successful compose (compose is deferred during a round), so no rebuild is
        needed."""
        if not self._round.get("active"):
            return {"ok": False, "error": "no active round"}
        snap = self._round.get("sources_snapshot")
        self._round = {"active": False}
        if snap is not None:
            self._restore_round_sources(snap)
        return {"ok": True}

    @staticmethod
    def _shape_is_valid(shape) -> bool:
        """build123d exposes is_valid as a method on raw topology but as a bool
        property on higher-level objects (Part/Compound); accept either. Fail
        closed: a shape with no is_valid is reported invalid, never assumed valid."""
        if not hasattr(shape, "is_valid"):
            return False
        attr = shape.is_valid
        return bool(attr() if callable(attr) else attr)

    @staticmethod
    def _objects_bbox(objects: list) -> dict | None:
        """Axis-aligned bounds of a part's objects ({min, max, size}), or None."""
        if not objects:
            return None
        bb = _compound_from_registry(objects).bounding_box()
        return {
            "min": [bb.min.X, bb.min.Y, bb.min.Z],
            "max": [bb.max.X, bb.max.Y, bb.max.Z],
            "size": [bb.size.X, bb.size.Y, bb.size.Z],
        }

    def attach(self, part_id: str, frame: str | None) -> dict:
        """Place an existing child at a different skeleton frame, then recompose.

        The attach frame is not part of the geometry cache key, so the child is
        reused from cache and only re-placed (a recompose, not a rebuild). Pass
        None to attach at the node origin."""
        return self._reattach_or_rewire(part_id, attach=frame, set_attach=True)

    def set_inputs(self, part_id: str, inputs: list[str]) -> dict:
        """Change which skeleton outputs a child reads, then rebuild it.

        Unlike attach, inputs are part of the cache key, so this rebuilds the
        child against the new scalar set."""
        return self._reattach_or_rewire(part_id, inputs=list(inputs), set_inputs=True)

    def _reattach_or_rewire(
        self,
        part_id: str,
        *,
        attach=None,
        inputs=None,
        set_attach: bool = False,
        set_inputs: bool = False,
    ) -> dict:
        """Shared body for attach/set_inputs: mutate one manifest field, rebuild."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        if (guard := self._round_guard()) is not None:
            return guard
        if not self._valid_child_id(part_id):
            return self._bad_id_error(part_id)
        from solidifai_engine.assembly import manifest as manifest_mod

        # Snapshot the prior manifest so a failed rewire (a bad frame / a non-scalar
        # input) is an atomic no-op. Without this, the mutation persists and bricks
        # every later compose -- even a plain set_params -- on the bad wiring.
        prior_man = manifest_mod.load_manifest(self.root)
        if manifest_mod.child_by_id(prior_man, part_id) is None:
            return {"ok": False, "error": f"no part {part_id!r} in this assembly"}
        try:

            def mutate(man):
                existing = manifest_mod.child_by_id(man, part_id)
                # Presence was verified against the same manifest content above.
                assert existing is not None
                manifest_mod.upsert_child(
                    man,
                    manifest_mod.ChildEntry(
                        id=existing.id,
                        kind=existing.kind,
                        source=existing.source,
                        attach=attach if set_attach else existing.attach,
                        inputs=inputs if set_inputs else list(existing.inputs),
                        shape_inputs=list(existing.shape_inputs),
                    ),
                )

            self._rewrite_manifest(mutate)
            res = self._build_assembly(params=self._param_values)
            if not res.get("ok"):
                manifest_mod.write_manifest(self.root, prior_man)
                self._build_assembly(params=self._param_values)  # restore last-good
                return res
            verb = "attach" if set_attach else "rewire inputs of"
            return self._after_assembly_edit(res, f"{verb} part {part_id}")
        except Exception as exc:  # noqa: BLE001
            with contextlib.suppress(Exception):
                manifest_mod.write_manifest(self.root, prior_man)
                self._build_assembly(params=self._param_values)
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }

    def remove_part(self, part_id: str) -> dict:
        """Drop a child (part or sub-assembly) and delete its source, then rebuild.

        Best-effort on the filesystem: a missing source file is not an error, but
        an unknown child id is."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        if (guard := self._round_guard()) is not None:
            return guard
        if not self._valid_child_id(part_id):
            return self._bad_id_error(part_id)
        from solidifai_engine.assembly import manifest as manifest_mod

        try:
            # load_manifest is the containment chokepoint: a hand-edited source that
            # escapes the workspace fails loudly here, so the deletion below can
            # never run against an out-of-root target. (The _within_root check that
            # follows is defense in depth for any path that still resolves through.)
            entry = manifest_mod.child_by_id(manifest_mod.load_manifest(self.root), part_id)
            if entry is None:
                return {"ok": False, "error": f"no part {part_id!r} in this assembly"}
            target = os.path.join(self.root, entry.source)
            if not self._within_root(target):
                return {
                    "ok": False,
                    "error": f"refusing to delete {entry.source!r}: "
                    "it resolves outside the workspace",
                }
            self._rewrite_manifest(lambda m: manifest_mod.remove_child(m, part_id))
            if entry.kind == "assembly":
                import shutil

                shutil.rmtree(target.rstrip("/"), ignore_errors=True)
            else:
                with contextlib.suppress(OSError):
                    os.remove(target)
            return self._rebuild_after_structure_edit(f"remove part {part_id}")
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }

    def add_subassembly(self, child_id: str, *, attach=None, inputs=None) -> dict:
        """Scaffold a nested sub-assembly node (its own skeleton + parts) wired to a
        skeleton frame, then rebuild.

        Creates <id>/assembly.json with an empty manifest (no skeleton, no children
        yet) and adds an assembly child to the root. Author the sub-node's parts in
        a later phase; here we lay down the scaffold + wiring."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        if (guard := self._round_guard()) is not None:
            return guard
        if not self._valid_child_id(child_id):
            return self._bad_id_error(child_id)
        from solidifai_engine.assembly import manifest as manifest_mod

        try:
            # Refuse to silently convert an existing part into a sub-assembly: that
            # would orphan its parts/<id>.py source. Make the caller remove it first.
            existing_child = manifest_mod.child_by_id(
                manifest_mod.load_manifest(self.root), child_id
            )
            if existing_child is not None and existing_child.kind != "assembly":
                return {
                    "ok": False,
                    "error": f"{child_id!r} is a part; remove_part it first "
                    f"to replace it with a sub-assembly",
                }
            sub_dir = os.path.join(self.root, child_id)
            if not self._within_root(sub_dir):  # defense in depth (id already validated)
                return self._bad_id_error(child_id)
            os.makedirs(sub_dir, exist_ok=True)
            if not os.path.exists(manifest_mod.manifest_path(sub_dir)):
                manifest_mod.write_manifest(
                    sub_dir, manifest_mod.Manifest(skeleton=None, children=[])
                )
            self._rewrite_manifest(
                lambda m: manifest_mod.upsert_child(
                    m,
                    manifest_mod.ChildEntry(
                        id=child_id,
                        kind="assembly",
                        source=f"{child_id}/",
                        attach=attach,
                        inputs=list(inputs) if inputs is not None else [],
                    ),
                )
            )
            return self._rebuild_after_structure_edit(f"add sub-assembly {child_id}")
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }

    def _rebuild_after_structure_edit(self, message: str = "edit assembly") -> dict:
        """Rebuild after a structural edit (remove_part/add_subassembly/end_round).
        An empty composition here is a valid in-progress scaffold, not a failure: a
        freshly added sub-assembly has no geometry until its parts are authored, and
        removing the last part returns to the skeleton-only state. _build_assembly
        flags those cases typed (empty / composeEmpty), so this maps them to a
        benign success WITHOUT masking a real build crash. ``message`` labels the
        history commit taken on success so undo/redo and the diff are meaningful."""
        res = self._build_assembly(params=self._param_values)
        if not res.get("ok") and res.get("composeEmpty"):
            self.last_ok = True
            res = {"ok": True, "buildId": self.build_id, "empty": True}
        return self._after_assembly_edit(res, message)

    def get_assembly_tree(self) -> dict:
        """Nested structure of the assembly (skeleton params/scalars/frames +
        children, recursively). Read-only; does not rebuild."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        from solidifai_engine.assembly import tree as tree_mod

        try:
            return {"ok": True, "tree": tree_mod.assembly_tree(self.root)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def get_part_info(self, part_id: str) -> dict:
        """Source + wiring + last-build summary for one leaf part."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        if not self._valid_child_id(part_id):
            return self._bad_id_error(part_id)
        from solidifai_engine.assembly import compose
        from solidifai_engine.assembly import manifest as manifest_mod

        man = manifest_mod.load_manifest(self.root)
        entry = manifest_mod.child_by_id(man, part_id)
        if entry is None:
            return {"ok": False, "error": f"no part {part_id!r} in this assembly"}
        src_path = os.path.join(self.root, entry.source)
        source = ""
        if os.path.exists(src_path):
            with open(src_path, encoding="utf-8") as f:
                source = f.read()
        # Last-good geometry summary: composed object path ids are "<child>/..."
        # (compose.path_ids == render._node_ids), so a part owns every id whose
        # first segment is its child id.
        objects = self._objects or []
        ids = compose.path_ids(objects) if objects else []
        # Path ids are slugged per segment (compose.path_ids == render._node_ids),
        # so slug the raw manifest id too, or a part id with an uppercase letter or
        # hyphen ('Lid', 'my-part') never matches and reports solids=0.
        target = _slug(part_id)
        solids = sum(
            len(o.shape.solids())
            for o, pid in zip(objects, ids, strict=True)
            if pid == target or pid.split("/", 1)[0] == target
        )
        return {
            "ok": True,
            "id": part_id,
            "kind": entry.kind,
            "attach": entry.attach,
            "inputs": list(entry.inputs),
            "shape_inputs": list(entry.shape_inputs),
            "source": source,
            "solids": solids,
        }

    def export_flat_model(self, *, write: bool = False) -> dict:
        """Flatten the assembly into a single, self-contained, runnable model.py.

        Returns ``{"ok": True, "code": <str>}``: a derived export (the spec's
        'model.py demoted to a derived export') that, run in a plain single-model
        Session, reproduces the composed assembly. With ``write=True`` it also
        writes ``<root>/flat_model.py`` and returns its ``path``. Assembly-only."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace; nothing to flatten"}
        from solidifai_engine.assembly import flatten

        try:
            code = flatten.flatten_to_model(self.root, self._param_values)
        except Exception as exc:  # noqa: BLE001 - never raise across the RPC boundary
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        out: dict = {"ok": True, "code": code}
        if write:
            dest = os.path.join(self.root, "flat_model.py")
            tmp = paths.write_temp_text(dest, code)
            paths.atomic_finalize(tmp, dest)
            out["path"] = dest
        return out

    def check_interfaces(self) -> dict:
        """Validate the assembly's declared wiring and summarize geometric fit.

        Walks the manifest (recursively for sub-assemblies): for each child, every
        ``attach`` must name a frame the node's skeleton publishes (else
        ``missing_attach_frame``) and every ``inputs`` entry must name a published
        scalar (else ``missing_input``), and every ``shape_inputs`` entry must name a published
        shape (else ``missing_shape_input``). attach=None (the node origin) is always
        valid. Folds in the composed-model geometric overlap from
        ``check_interferences()`` under ``interference``. Never raises.

        Scope: this validates the DECLARED wiring is satisfiable, not a richer
        interface-frame mating contract (a part asserting "my frame X must coincide
        with sibling Y's frame Z"). That mate-frame system is a future extension,
        noted here rather than faked."""
        if self.root is None or not self._is_assembly_mode():
            return {"ok": False, "error": "not an assembly workspace"}
        from solidifai_engine.assembly import tree as tree_mod

        issues: list[dict] = []
        try:
            tree = tree_mod.assembly_tree(self.root)
            self._collect_interface_issues(tree, prefix="", issues=issues)
        except Exception as exc:  # noqa: BLE001 - report, never raise across RPC
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        # Fold in the geometric overlap on the last-good composed model (advisory).
        interference = None
        with contextlib.suppress(Exception):
            res = self.check_interferences()
            if res.get("ok"):
                interference = res.get("summary")
        return {"ok": True, "issues": issues, "interference": interference}

    @staticmethod
    def _collect_interface_issues(node: dict, *, prefix: str, issues: list) -> None:
        """Append a wiring issue for every child whose attach/inputs reference a
        skeleton output its node does not publish. ``prefix`` path-qualifies the id
        through nested sub-assemblies (e.g. ``hinge/pin``)."""
        skel = node.get("skeleton") or {}
        frames = set(skel.get("frames") or [])
        scalars = set(skel.get("scalars") or [])
        shapes = set(skel.get("shapes") or [])
        for child in node.get("children") or []:
            cid = f"{prefix}{child['id']}"
            attach = child.get("attach")
            if attach is not None and attach not in frames:
                issues.append(
                    {
                        "id": cid,
                        "issue": "missing_attach_frame",
                        "name": attach,
                        "detail": f"attach frame {attach!r} is not published by the skeleton",
                    }
                )
            for name in child.get("inputs") or []:
                if name not in scalars:
                    issues.append(
                        {
                            "id": cid,
                            "issue": "missing_input",
                            "name": name,
                            "detail": f"input {name!r} is not a scalar published by the skeleton",
                        }
                    )
            for name in child.get("shape_inputs") or []:
                if child.get("kind") != "part":
                    issues.append(
                        {
                            "id": cid,
                            "issue": "shape_input_on_subassembly",
                            "name": name,
                            "detail": f"shape input {name!r} on a sub-assembly is ignored; "
                            f"published shapes do not cross the sub-assembly boundary",
                        }
                    )
                elif name not in shapes:
                    issues.append(
                        {
                            "id": cid,
                            "issue": "missing_shape_input",
                            "name": name,
                            "detail": f"shape input {name!r} is not published by the skeleton",
                        }
                    )
            for name in sorted(
                set(child.get("inputs") or []) & set(child.get("shape_inputs") or [])
            ):
                issues.append(
                    {
                        "id": cid,
                        "issue": "input_name_collision",
                        "name": name,
                        "detail": f"{name!r} is declared as both a scalar input and a shape input",
                    }
                )
            if child.get("kind") == "assembly":
                # A sub-assembly node carries its own skeleton + children under
                # "children"; recurse with the sub-skeleton's published outputs.
                sub_node = {
                    "skeleton": child.get("skeleton"),
                    "children": child.get("children") or [],
                }
                Session._collect_interface_issues(sub_node, prefix=f"{cid}/", issues=issues)

    def _persist_model(self, code: str) -> None:
        """Write ``code`` to ``self.model_path`` atomically (temp + replace)."""
        assert self.model_path is not None  # callers guard; bare sessions never persist
        parent = os.path.dirname(self.model_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = paths.write_temp_text(self.model_path, code)
        paths.atomic_finalize(tmp, self.model_path)

    @staticmethod
    def _default_values(schema: dict) -> dict:
        return {key: spec.get("value") for key, spec in schema.items()}

    @staticmethod
    def _is_number(value) -> TypeGuard[int | float]:
        # bool is a subclass of int but is not a slider value.
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _normalize_schema(cls, schema: dict) -> dict:
        """Return a NUMERIC-ONLY, fully-formed slider schema for the UI and
        model.json.

        For each entry whose ``value`` is a real number (int/float, not bool),
        emit ``{value, min, max, step, unit, desc}`` with value/min/max/step
        coerced to float (min/max default to value, step defaults to 1.0 when
        missing or invalid), unit defaults to "" and is coerced to str, and desc
        defaults to "" and is stripped when a string (non-string values become
        ""). Entries whose value is not numeric are DROPPED -- they get no
        slider, but still reach ``build()`` via ``_param_values``. This
        guarantees the emitted schema is always accepted by the frontend's
        strict validator.
        """
        normalized: dict = {}
        for key, spec in schema.items():
            if not isinstance(spec, dict):
                continue
            value = spec.get("value")
            if not cls._is_number(value):
                continue
            value_f = float(value)

            def _num(raw, default):
                if cls._is_number(raw):
                    return float(raw)
                return default

            raw_desc = spec.get("desc")
            desc = raw_desc.strip() if isinstance(raw_desc, str) else ""
            normalized[key] = {
                "value": value_f,
                "min": _num(spec.get("min"), value_f),
                "max": _num(spec.get("max"), value_f),
                "step": _num(spec.get("step"), 1.0),
                "unit": str(spec.get("unit", "")),
                "desc": desc,
            }
        return normalized

    def _params_block(self, values: dict | None = None):
        """Build the model.json ``params`` block: ``{schema, values}`` where
        schema is the normalized numeric-only slider schema and values is the
        numeric subset (floats) for exactly the schema keys. Returns ``None``
        when no parametric model is loaded."""
        if self._build_fn is None and not self._is_assembly_mode():
            return None
        if not self._params_schema:
            return None
        source = self._param_values if values is None else values
        numeric_values = {
            key: float(source[key])
            for key in self._params_schema
            if key in source and self._is_number(source[key])
        }
        return {
            "schema": dict(self._params_schema),
            "values": numeric_values,
        }

    def _cleanup_temps(self) -> None:
        for tmp in glob.glob(os.path.join(self.artifacts_dir, "*.tmp")):
            with contextlib.suppress(OSError):
                os.remove(tmp)
