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
from solidifai_engine import converge as converge_mod
from solidifai_engine import dfm as dfm_rules
from solidifai_engine import explore as explore_mod
from solidifai_engine import interference as itf
from solidifai_engine import requirements as requirements_mod

if TYPE_CHECKING:
    from solidifai_engine.session import Session


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
        part: str,
        kind: str = "revolute",
        axis_origin=None,
        axis_dir=None,
        start: float = 0.0,
        stop: float = 90.0,
        steps: int = 12,
    ) -> dict:
        """Sweep one shown part through a range and report where it collides with
        the other parts. ``kind`` is ``revolute`` (rotate start..stop degrees about
        the axis) or ``prismatic`` (translate start..stop mm along axis_dir).
        Read-only: never renders or bumps buildId. ``clearThrough`` is how far from
        ``start`` the motion stays collision-free."""
        from build123d import Axis, Vector

        objs = self.s._objects or []
        moving = next((o for o in objs if o.name == part), None)
        if moving is None:
            return {"ok": False, "error": f"part '{part}' not found"}
        others = [o for o in objs if o is not moving and getattr(o, "role", "part") != "reference"]
        if not others:
            return {"ok": False, "error": "need at least two parts to check motion"}

        origin = Vector(*(axis_origin or [0.0, 0.0, 0.0]))
        direction = Vector(*(axis_dir or [0.0, 0.0, 1.0]))
        axis = Axis(origin, direction)
        n = max(2, int(steps))
        span = float(stop) - float(start)
        samples: list[dict[str, Any]] = []
        collides, first = False, None
        clear_through = float(stop)
        last_clear = float(start)
        for i in range(n):
            at = float(start) + span * i / (n - 1)
            try:
                if kind == "prismatic":
                    shape = moving.shape.translate(direction.normalized() * at)
                else:
                    shape = moving.shape.rotate(axis, at)
            except Exception as exc:  # noqa: BLE001 - a degenerate pose fails its step only
                samples.append({"at": round(at, 3), "collides": False, "error": str(exc)})
                continue
            hit = next(
                (
                    o.name
                    for o in others
                    if itf.classify_pair(shape, o.shape).get("relation") == "overlap"
                ),
                None,
            )
            step: dict[str, Any] = {"at": round(at, 3), "collides": hit is not None}
            if hit is not None:
                step["with"] = hit
                if first is None:
                    first = {"at": round(at, 3), "with": hit}
                    clear_through = round(last_clear, 3)
                    collides = True
            else:
                last_clear = at
            samples.append(step)
        return {
            "ok": True,
            "part": part,
            "kind": kind,
            "range": [float(start), float(stop)],
            "collides": collides,
            "firstCollision": first,
            "clearThrough": clear_through,
            "steps": samples,
        }
