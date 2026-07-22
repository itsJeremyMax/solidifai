"""Generative exploration: parameter sweeps, single-parameter optimization, and
range-of-motion / collision checks for assemblies.

Collaborator of :class:`solidifai_engine.session.Session`; holds a back-reference
to read session state and call lifecycle helpers that stay on Session. Sweeps are
non-destructive: the live model snapshot is untouched and the registry is rebuilt
to the live params before returning.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import solidifai
from solidifai.skeleton_api import UNVERIFIED_JOINT_KINDS, VERIFIED_JOINT_KINDS
from solidifai_engine import converge as converge_mod
from solidifai_engine import dfm as dfm_rules
from solidifai_engine import explore as explore_mod
from solidifai_engine import interference as itf
from solidifai_engine import requirements as requirements_mod

if TYPE_CHECKING:
    from solidifai_engine.session import Session


_PART_MOTION_KINDS = ("revolute", "prismatic")


def _sampled_verification(
    *,
    requested: int,
    actual: int,
    span: float,
    unit: str,
    spacing_samples: int | None = None,
    failed: int = 0,
) -> dict[str, Any]:
    grid_samples = actual if spacing_samples is None else spacing_samples
    result = {
        "method": "sampled",
        "continuousProof": False,
        "samples": actual,
        "samplesRequested": requested,
        "samplesActual": actual,
        "spacing": {
            "value": round(span / (grid_samples - 1), 3) if grid_samples > 1 else 0.0,
            "unit": unit,
        },
        "note": "Sampled clearance is not a continuous proof.",
    }
    if failed:
        result["failedSamples"] = failed
    return result


class Exploration:
    def __init__(self, s: Session):
        self.s = s

    def sweep(self, param: str, values: list, checks: bool = False) -> dict:
        """Build the model at each value of ``param`` (other params held at their
        current values), measure each, and return a table. Non-destructive: never
        renders, bumps buildId, or changes the live model -- the registry is
        rebuilt to the live params before returning. Requires a parametric model.
        Set ``checks=True`` to also count critical DFM issues per variant (slow)."""
        if not callable(self.s._build_fn):
            return {"ok": False, "error": "no parametric model loaded (script has no PARAMS/build)"}
        if param not in self.s._param_values:
            return {"ok": False, "error": f"unknown parameter '{param}'"}
        unit = (self.s.get_params()["schema"].get(param) or {}).get("unit")
        variants = []
        try:
            for v in values or []:
                merged = dict(self.s._param_values)
                merged[param] = v
                try:
                    solidifai.reset_registry()
                    solidifai.set_workspace_root(self.s.root)
                    self.s._build_fn(**merged)
                    variants.append({"value": v, "ok": True, **self.s._measure_registry(checks)})
                except Exception as exc:  # noqa: BLE001 - a bad value fails just its row
                    variants.append(
                        {"value": v, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
                    )
        finally:
            # Restore the registry to the live model so nothing downstream sees a
            # variant's geometry (the live snapshot in self._model is untouched).
            try:
                solidifai.reset_registry()
                solidifai.set_workspace_root(self.s.root)
                self.s._build_fn(**self.s._param_values)
            except Exception:  # noqa: BLE001 - best effort; live params built fine once
                pass
        return {"ok": True, "param": param, "unit": unit, "variants": variants}

    def optimize(
        self,
        param: str,
        objective: str = "min_mass",
        steps: int = 9,
        constraints: dict | None = None,
        values: list | None = None,
    ) -> dict:
        """Sample ``param`` across its range (or explicit ``values``), sweep, and
        return the feasible variant that minimizes/maximizes mass. ``constraints``
        may include ``max_size: [x,y,z]`` and ``printable: true`` (the latter runs
        per-variant DFM)."""
        if not callable(self.s._build_fn):
            return {"ok": False, "error": "no parametric model loaded (script has no PARAMS/build)"}
        if param not in self.s._param_values:
            return {"ok": False, "error": f"unknown parameter '{param}'"}
        if values is None:
            sch = self.s.get_params()["schema"].get(param) or {}
            lo, hi = sch.get("min"), sch.get("max")
            if lo is None or hi is None or lo == hi:
                return {"ok": False, "error": f"parameter '{param}' has no range to optimize over"}
            values = explore_mod.linspace(lo, hi, max(2, int(steps)))
        needs_dfm = bool((constraints or {}).get("printable"))
        swept = self.sweep(param, values, checks=needs_dfm)
        best, feasible = explore_mod.pick_best(swept["variants"], objective, constraints)
        return {
            "ok": True,
            "param": param,
            "objective": objective,
            "best": best,
            "feasibleCount": feasible,
            "evaluated": swept["variants"],
        }

    # -- converge to spec ---------------------------------------------------

    def converge_to_spec(
        self,
        objective: str = "min_mass",
        apply: bool = False,
        max_evals: int = 24,
    ) -> dict:
        """Non-destructive feasibility search over the declared PARAMS grid.

        Builds each candidate combination, measures it, and picks the best
        assignment that satisfies every enabled (non-assert) requirement.
        The live registry is always restored in a finally block, and
        ``self.s.build_id`` is never bumped. When ``apply=True`` and a feasible
        candidate is found, ``set_params`` is called to commit it.

        Returns:
            ok, found, buildIdBefore, evaluated, objective, params, before,
            after, closestMiss, notAddressable
        """
        if not callable(self.s._build_fn):
            return {"ok": False, "error": "no parametric model loaded (script has no PARAMS/build)"}

        # Capture build_id before anything runs so the return value is stable.
        build_id_before = self.s.build_id

        # Predicates only: skip assert-form (not addressable by params).
        preds = [r for r in self.s._requirements if r.get("kind") != "assert"]

        schema = self.s.get_params()["schema"]
        grid = converge_mod.candidate_grid(schema, max_evals)

        # Capture requirements state before the search.
        before = self.s.check_requirements()["requirements"]

        needs_dfm = requirements_mod.needs(preds, "dfm_critical")
        needs_min_wall = requirements_mod.needs(preds, "min_wall")
        needs_min_clearance = requirements_mod.needs(preds, "min_clearance")

        cands: list[dict] = []
        try:
            for combo in grid:
                merged = {**self.s._param_values, **combo}
                try:
                    solidifai.reset_registry()
                    solidifai.set_workspace_root(self.s.root)
                    self.s._build_fn(**merged)
                    m = self.s._measure_registry(needs_dfm)
                    # Augment measurement with gated expensive quantities.
                    if needs_min_wall:
                        m["min_wall"] = self._registry_min_wall()
                    if needs_min_clearance:
                        m["min_clearance"] = self._registry_min_clearance()
                    cands.append({"params": combo, "ok": True, **m})
                except Exception:  # noqa: BLE001 — a bad combo fails only its row
                    cands.append({"params": combo, "ok": False})
        finally:
            # Restore the live model so nothing downstream sees a variant.
            solidifai.reset_registry()
            solidifai.set_workspace_root(self.s.root)
            with contextlib.suppress(Exception):  # best effort; live params built fine before
                self.s._build_fn(**self.s._param_values)

        # Addressability: a predicate is addressable only if its quantity's
        # measured value varies across the ok candidates. Constant quantities
        # (e.g. watertight=True for every build) cannot be fixed by adjusting
        # params and are reported separately.
        addressable, not_addr = self._split_addressable(preds, cands)

        best, feasible, closest = converge_mod.pick_feasible(cands, addressable, objective)
        found = best is not None

        if found and apply:
            self.s.set_params(best["params"])

        # Predict after-results from the best candidate's measurements.
        after = None
        if found:
            ctx = converge_mod._ctx_from(best)
            after = requirements_mod.evaluate(preds, ctx)

        return {
            "ok": True,
            "found": found,
            "buildIdBefore": build_id_before,
            "evaluated": len(cands),
            "objective": objective,
            "params": best["params"] if best is not None else None,
            "before": before,
            "after": after,
            "closestMiss": closest,
            "notAddressable": [
                {"id": r.get("id"), "label": requirements_mod._label(r)} for r in not_addr
            ],
        }

    def _registry_min_wall(self) -> float | None:
        """Min wall (mm) across all non-reference objects in the current registry."""
        best: float | None = None
        for o in solidifai._registry():
            if getattr(o, "role", "part") == "reference":
                continue
            t = dfm_rules.min_wall_mm(o.shape)
            if t is not None and (best is None or t < best):
                best = t
        return best

    def _registry_min_clearance(self) -> float | None:
        """Min clearance (mm) between non-reference parts in the current registry."""
        shapes = [
            o.shape for o in solidifai._registry() if getattr(o, "role", "part") != "reference"
        ]
        return itf.min_clearance_mm(shapes) if len(shapes) >= 2 else None

    @staticmethod
    def _split_addressable(preds: list, cands: list) -> tuple[list, list]:
        """Partition predicates into (addressable, not_addressable).

        A predicate is addressable when its measured quantity's value varies
        across the ok candidates. A constant quantity cannot be influenced by
        adjusting params, so the predicate is not relevant for feasibility
        scoring (it would incorrectly rule out all candidates).
        """
        ok_cands = [c for c in cands if c.get("ok")]
        if not ok_cands:
            # No data: treat all predicates as addressable.
            return preds, []

        # Map each quantity to the ctx key it reads from.
        from solidifai_engine.requirements import _QUANTITY_CTX  # noqa: PLC0415

        addressable, not_addr = [], []
        for r in preds:
            q = r.get("quantity")
            ctx_key = _QUANTITY_CTX.get(q)
            if ctx_key is None:
                addressable.append(r)
                continue
            # Collect measured values across all ok candidates.
            vals = [c.get(ctx_key) for c in ok_cands if c.get(ctx_key) is not None]
            if len(vals) == 0:
                # Never measured — params can't affect what was never computed.
                not_addr.append(r)
                continue
            if len(vals) == 1:
                # Single data point: can't determine variation, assume addressable.
                addressable.append(r)
                continue
            # If all values are identical, the quantity is constant across params.
            first = vals[0]
            if all(v == first for v in vals[1:]):
                not_addr.append(r)
            else:
                addressable.append(r)

        return addressable, not_addr

    # -- motion / range-of-motion (assemblies) ------------------------------

    def check_motion(
        self,
        part: str | None = None,
        kind: str = "revolute",
        axis_origin=None,
        axis_dir=None,
        start=None,
        stop=None,
        steps: int = 12,
        joint: str | None = None,
    ) -> dict:
        """Sweep a moving part (or a declared joint) through a range and report
        where it collides with the other parts.

        Part mode (``part`` named): ``kind`` is ``revolute`` (rotate start..stop
        degrees about the axis) or ``prismatic`` (translate start..stop mm along
        axis_dir). Joint mode (``joint`` named): drive a skeleton-declared joint
        through its limits (or a passed start/stop), moving every occurrence of the
        joint's first ``between`` child. Read-only: never renders or bumps buildId.
        ``clearThrough`` is how far from ``start`` the motion stays collision-free."""
        from build123d import Axis, Vector

        if joint is not None:
            return self._check_motion_joint(joint, start=start, stop=stop, steps=steps)

        if part is None:
            return {"ok": False, "error": "check_motion needs a part name or a joint name"}
        if kind not in _PART_MOTION_KINDS:
            return {
                "ok": False,
                "code": "unsupported_motion_kind",
                "error": f"unsupported motion kind {kind!r}; expected revolute or prismatic",
                "kind": kind,
                "supportedKinds": list(_PART_MOTION_KINDS),
            }
        objs = self.s._objects or []
        moving = next((o for o in objs if o.name == part), None)
        if moving is None:
            return {"ok": False, "error": f"part '{part}' not found"}
        others = [o for o in objs if o is not moving and getattr(o, "role", "part") != "reference"]
        if not others:
            return {"ok": False, "error": "need at least two parts to check motion"}

        origin = Vector(*(axis_origin or [0.0, 0.0, 0.0]))
        direction = Vector(*(axis_dir or [0.0, 0.0, 1.0]))
        if direction.length == 0:
            return {"ok": False, "error": "axis_dir must be a non-zero vector"}
        axis = Axis(origin, direction)
        lo = 0.0 if start is None else float(start)
        hi = 90.0 if stop is None else float(stop)

        def transform(at):
            if kind == "prismatic":
                return [moving.shape.translate(direction.normalized() * at)]
            return [moving.shape.rotate(axis, at)]

        body = self._sweep(
            transform,
            others,
            lo,
            hi,
            steps,
            unit="mm" if kind == "prismatic" else "deg",
        )
        return {"ok": True, "part": part, "kind": kind, **body}

    def _sweep(
        self, transform, statics: list, start: float, stop: float, steps: int, *, unit: str
    ) -> dict:
        """Step a set of moving bodies (produced by ``transform(at)``) through
        start..stop and test each against ``statics`` for overlap at every step.
        Shared by part-mode and joint-mode check_motion so both report identically."""
        n = max(2, int(steps))
        span = float(stop) - float(start)
        samples: list[dict[str, Any]] = []
        collides, first = False, None
        clear_through: float | None = float(stop)
        last_clear: float | None = None
        verification_blocked = False
        failed_samples = 0
        successful_samples = 0
        for i in range(n):
            at = float(start) + span * i / (n - 1)
            try:
                moved = transform(at)
            except Exception as exc:  # noqa: BLE001 - a degenerate pose fails its step only
                failed_samples += 1
                if not verification_blocked:
                    clear_through = round(last_clear, 3) if last_clear is not None else None
                    verification_blocked = True
                samples.append({"at": round(at, 3), "collides": None, "error": str(exc)})
                continue
            successful_samples += 1
            hit = None
            for shape in moved:
                hit = next(
                    (
                        o.name
                        for o in statics
                        if itf.classify_pair(shape, o.shape).get("relation") == "overlap"
                    ),
                    None,
                )
                if hit is not None:
                    break
            step: dict[str, Any] = {"at": round(at, 3), "collides": hit is not None}
            if hit is not None:
                step["with"] = hit
                if first is None:
                    first = {"at": round(at, 3), "with": hit}
                    if not verification_blocked:
                        clear_through = round(last_clear, 3) if last_clear is not None else None
                        verification_blocked = True
                    collides = True
            elif not verification_blocked:
                last_clear = at
            samples.append(step)
        result = {
            "ok": failed_samples == 0,
            "range": [float(start), float(stop)],
            "collides": collides,
            "firstCollision": first,
            "clearThrough": clear_through,
            "steps": samples,
            "verification": _sampled_verification(
                requested=int(steps),
                actual=successful_samples,
                span=span,
                unit=unit,
                spacing_samples=n,
                failed=failed_samples,
            ),
        }
        if failed_samples:
            result.update(
                {
                    "code": "motion_pose_failed",
                    "error": (
                        "motion verification incomplete: "
                        f"{failed_samples} of {n} sampled poses failed"
                    ),
                }
            )
        return result

    def _root_skeleton(self):
        """Run the root skeleton at the live params to read its frames + joints, or
        None when the workspace has no root skeleton."""
        import os

        from solidifai_engine.assembly import manifest as manifest_mod
        from solidifai_engine.assembly import runner

        root = self.s.root
        if root is None:
            return None
        man = manifest_mod.load_manifest(root)
        if not man.skeleton:
            return None
        return runner.run_skeleton(
            os.path.join(root, man.skeleton), params=self.s._param_values, parent=None
        )

    @staticmethod
    def _belongs_to_child(name: str, child_id: str) -> bool:
        """True when a composed object name belongs to ``child_id`` or one of its
        occurrences (``wheel/...`` or ``wheel@2/...``). Matches on the raw path name
        (not the slugged node id) so the ``@`` occurrence marker is exact."""
        first = name.split("/", 1)[0]
        return first == child_id or first.startswith(f"{child_id}@")

    def _check_motion_joint(self, joint_name: str, *, start, stop, steps: int) -> dict:
        """Drive a skeleton-declared joint through its range and report collisions.

        Sweeps only the currently verifiable joint kinds: rotation for revolute and
        translation for slider, about/along the joint frame axis. Declared joint
        kinds remain source-compatible, but cylindrical, planar, and ball are
        declaration-compatible only and return an explicit unsupported verification
        result. For supported kinds, every occurrence of the joint's first
        ``between`` child is transformed per step and tested against the rest of
        the model."""
        from build123d import Axis, Location, Pos, Vector

        if self.s.root is None or not self.s._is_assembly_mode():
            return {"ok": False, "error": "joint motion needs an assembly workspace"}
        skel = self._root_skeleton()
        if skel is None:
            return {"ok": False, "error": "assembly has no skeleton; no joints to drive"}
        joints = getattr(skel, "joints", []) or []
        jrec = next((j for j in joints if j.get("name") == joint_name), None)
        if jrec is None:
            avail = ", ".join(j.get("name", "?") for j in joints) or "(none)"
            return {"ok": False, "error": f"joint '{joint_name}' not found; declared: {avail}"}

        kind = jrec["kind"]
        if kind == "rigid":
            return {
                "ok": True,
                "joint": joint_name,
                "kind": kind,
                "range": [0.0, 0.0],
                "collides": False,
                "firstCollision": None,
                "clearThrough": 0.0,
                "steps": [],
                "note": "rigid joint has no degree of freedom to sweep",
                "verification": {
                    "method": "static",
                    "continuousProof": False,
                    "samples": 0,
                    "samplesRequested": 0,
                    "samplesActual": 0,
                    "spacing": None,
                    "note": "No motion to verify for a rigid joint.",
                },
            }
        if kind in UNVERIFIED_JOINT_KINDS:
            return {
                "ok": False,
                "code": "unsupported_joint_motion",
                "error": (
                    f"joint {joint_name!r} kind {kind!r} is declared but not verifiable"
                    " by check_motion"
                ),
                "joint": joint_name,
                "kind": kind,
                "verifiedJoints": list(VERIFIED_JOINT_KINDS),
            }
        between = jrec.get("between")
        if not between:
            return {
                "ok": False,
                "error": f"joint '{joint_name}' has no `between`; declare "
                f"between=[moving_id, ground_id] so motion knows which child to sweep",
            }
        moving_id = between[0]
        frame_name = jrec.get("frame")
        if frame_name not in skel.frames:
            return {
                "ok": False,
                "error": f"joint frame '{frame_name}' is not published by the skeleton",
            }
        floc = skel.frames[frame_name]
        origin = floc.position
        # The joint axis is in the frame's LOCAL orientation; rotate it into world.
        local_axis = Vector(*jrec.get("axis", [0.0, 0.0, 1.0]))
        rot_only = Location((0.0, 0.0, 0.0), floc.orientation)
        world_dir = (rot_only * Pos(local_axis.X, local_axis.Y, local_axis.Z)).position
        if world_dir.length == 0:
            world_dir = local_axis
        axis = Axis(origin, world_dir)

        objs = self.s._objects or []
        moving = [o for o in objs if self._belongs_to_child(o.name, moving_id)]
        if not moving:
            return {"ok": False, "error": f"joint child '{moving_id}' has no composed geometry"}
        statics = [
            o
            for o in objs
            if not self._belongs_to_child(o.name, moving_id)
            and getattr(o, "role", "part") != "reference"
        ]
        if not statics:
            return {"ok": False, "error": "need another part for the joint to move against"}

        rotary = kind == "revolute"
        lims = jrec.get("limits")
        default_hi = 90.0 if rotary else 10.0
        lo = float(start) if start is not None else (float(lims[0]) if lims else 0.0)
        hi = float(stop) if stop is not None else (float(lims[1]) if lims else default_hi)

        def transform(at):
            if rotary:
                return [o.shape.rotate(axis, at) for o in moving]
            offset = world_dir.normalized() * at
            return [o.shape.translate(offset) for o in moving]

        body = self._sweep(transform, statics, lo, hi, steps, unit="deg" if rotary else "mm")
        return {"ok": True, "joint": joint_name, "kind": kind, "moving": moving_id, **body}
