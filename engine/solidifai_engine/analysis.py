"""Read-only model analysis: interference, DFM, mass properties, stress,
tolerance stacks, and goal-driven requirement checks.

Collaborator of :class:`solidifai_engine.session.Session`; holds a back-reference
to read/write session state (``self.s._objects`` etc.) and to call lifecycle
helpers that stay on Session. Every method here is non-destructive: it never
bumps buildId or flips ``last_ok``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import solidifai
from solidifai_engine import dfm as dfm_rules
from solidifai_engine import interference as itf
from solidifai_engine import materials as _materials
from solidifai_engine import props as props_geom
from solidifai_engine import requirements as requirements_mod
from solidifai_engine import validation as validation_geom
from solidifai_engine.render import _node_ids

if TYPE_CHECKING:
    from solidifai_engine.session import Session


class Analysis:
    def __init__(self, s: Session):
        self.s = s

    def check_interferences(self) -> dict:
        """Advisory interference + connectivity report over the shown parts.

        Pairwise relation between shown objects (overlap / adjacent / clear) and
        the internal topology of each object (single / touching / overlap /
        disjoint). Read-only: never bumps buildId or flips ``last_ok``. The agent
        judges each flag -- an intended fusion or press-fit is fine; an
        interpenetrating mating pair or a floating lump is a defect."""
        objects = self.s._objects
        if not objects:
            return {"ok": False, "error": "no model -- run execute_script first"}

        parts = []
        disjoint = 0
        for o in objects:
            rep = itf.classify_internal(o.shape)
            parts.append(
                {
                    "name": o.name,
                    "solids": rep["solids"],
                    "internal": rep["internal"],
                    "components": rep["components"],
                    "internalOverlaps": rep["internalOverlaps"],
                }
            )
            if rep["internal"] == "disjoint":
                disjoint += 1

        pairs = []
        overlaps = 0
        adjacent = 0
        flags = []
        for i in range(len(objects)):
            for j in range(i + 1, len(objects)):
                rel = itf.classify_pair(objects[i].shape, objects[j].shape)
                pairs.append({"a": objects[i].name, "b": objects[j].name, **rel})
                if rel["relation"] == "overlap":
                    overlaps += 1
                    flags.append(
                        f"{objects[i].name} overlaps {objects[j].name} "
                        f"by {rel['overlapVolume']} mm^3"
                    )
                elif rel["relation"] == "adjacent":
                    adjacent += 1

        for p in parts:
            if p["internal"] == "disjoint":
                flags.append(f"{p['name']} has disconnected/floating components")
            elif p["internal"] == "overlap":
                flags.append(f"{p['name']} has internally overlapping solids")

        return {
            "ok": True,
            "toleranceMm3": itf.TOLERANCE_MM3,
            "parts": parts,
            "pairs": pairs,
            "summary": {
                "overlaps": overlaps,
                "disjoint": disjoint,
                "adjacent": adjacent,
                "flags": flags,
            },
        }

    def analyze_dfm(self, process: str | None = None) -> dict:
        """Advisory DFM (manufacturability) report over the shown parts.

        Measures the last-good geometry for FDM printability: thin walls, steep
        overhangs, long unsupported bridges, tiny holes. Read-only: never bumps
        buildId or flips ``last_ok``. ``process`` overrides the per-part material
        inference; only ``fdm`` is evaluated (others are reported as
        not-yet-supported, never with a wrong number). The agent decides which
        flags matter; nothing is auto-fixed."""
        objects = self.s._objects
        if not objects:
            return {"ok": False, "error": "no model -- run execute_script first"}

        # partId = the same slug node id render.py writes into model.json, so a
        # click on a DFM row selects the right part in the viewport. partName is
        # the human-readable name for display.
        ids = _node_ids(objects)
        parts = []
        summary: dict[str, Any] = {
            "critical": 0,
            "warning": 0,
            "advisory": 0,
            "parts": 0,
            "minWallMm": None,
        }
        for o, pid in zip(objects, ids, strict=True):
            if getattr(o, "role", "part") == "reference":
                parts.append(
                    {
                        "partId": pid,
                        "partName": o.name,
                        "process": "reference",
                        "evaluated": False,
                        "violations": [],
                        "note": "Reference import, not manufactured.",
                    }
                )
                continue
            proc = process or self._infer_process(o.material)
            rep = dfm_rules.analyze_part(o.shape, process=proc)
            entry = {
                "partId": pid,
                "partName": o.name,
                "process": proc,
                "evaluated": rep["evaluated"],
                "violations": rep["violations"],
                "metrics": rep.get("metrics", {}),
            }
            if not rep["evaluated"]:
                entry["note"] = f"DFM rules for '{proc}' are not implemented yet (FDM only in v1)."
            for v in rep["violations"]:
                summary[v["severity"]] = summary.get(v["severity"], 0) + 1
            mw = (rep.get("metrics") or {}).get("minWallMm")
            if mw is not None and (summary["minWallMm"] is None or mw < summary["minWallMm"]):
                summary["minWallMm"] = mw
            parts.append(entry)
        summary["parts"] = len(parts)
        return {
            "ok": True,
            "schema": 1,
            "buildId": self.s.build_id,
            "config": {"fdm": dfm_rules.FDM_DEFAULTS},
            "parts": parts,
            "summary": summary,
        }

    def _infer_process(self, material_name) -> str:
        """Manufacturing process for a part's material name (default fdm)."""
        try:
            mat = _materials.RESOLVER.resolve(material_name)
            return _materials.process_for(mat.name)
        except ValueError:  # unknown material name -> default to fdm
            return "fdm"

    def _density_for(self, material_name) -> float:
        """Density (g/cm^3) for a part's material name; defaults to 1.0."""
        try:
            return float(_materials.RESOLVER.resolve(material_name).density)
        except ValueError:  # unknown material name -> neutral density
            return 1.0

    # -- validation (measure / stress / tolerance) --------------------------

    def measure(self) -> dict:
        """Exact mass properties of the shown parts plus the assembly total.

        Per part: volume, surface area, mass, center of mass, and the inertia
        tensor (principal moments/axes). ``total`` aggregates the solids
        (mass-weighted CoM; inertia about the assembly CoM). Read-only: never
        bumps buildId or flips ``last_ok``. References are listed but excluded
        from the total mass."""
        objects = self.s._objects
        if not objects:
            return {"ok": False, "error": "no model -- run execute_script first"}

        ids = _node_ids(objects)
        parts, solids = [], []
        for o, pid in zip(objects, ids, strict=True):
            if getattr(o, "role", "part") == "reference":
                parts.append({"partId": pid, "partName": o.name, "role": "reference"})
                continue
            mp = props_geom.mass_properties(o.shape, self._density_for(o.material))
            parts.append({"partId": pid, "partName": o.name, "material": o.material, **mp})
            solids.append(mp)
        total = props_geom.aggregate(solids)
        return {
            "ok": True,
            "schema": 1,
            "buildId": self.s.build_id,
            "parts": parts,
            "total": total,
            "summary": {"parts": len(solids), "mass": total["mass"], "unit": "g"},
        }

    def stress_check(self) -> dict:
        """Advisory first-order stress report over the shown parts: sharp
        re-entrant corners where stress concentrates. Geometric heuristic, not a
        solved stress field. Read-only. The agent decides which flags matter;
        nothing is auto-fixed."""
        objects = self.s._objects
        if not objects:
            return {"ok": False, "error": "no model -- run execute_script first"}

        ids = _node_ids(objects)
        parts = []
        counts = {"warning": 0, "advisory": 0}
        for o, pid in zip(objects, ids, strict=True):
            if getattr(o, "role", "part") == "reference":
                continue
            hotspots = validation_geom.stress_hotspots(o.shape)
            for h in hotspots:
                counts[h["severity"]] = counts.get(h["severity"], 0) + 1
            parts.append({"partId": pid, "partName": o.name, "hotspots": hotspots})
        return {
            "ok": True,
            "schema": 1,
            "buildId": self.s.build_id,
            "parts": parts,
            "summary": {**counts, "parts": len(parts)},
        }

    def tolerance_stack(self, chain) -> dict:
        """Worst-case + RSS tolerance stack over an agent-supplied dimension
        chain (pure math; no model needed). See ``validation.tolerance_stack``."""
        return validation_geom.tolerance_stack(chain or [])

    # -- design requirements (goal-driven verification) ---------------------

    def set_requirements(self, reqs) -> dict:
        """Replace the workspace's design requirements and persist them.

        Accepts predicate form ({quantity, op, bound}), assert form ({kind:
        "assert", expr}), and legacy form ({type, target}) -- all legacy entries
        are migrated to predicate form before storage. Malformed entries are dropped.
        """
        migrated = requirements_mod.migrate_legacy(list(reqs or []))
        valid = []
        for r in migrated:
            if not isinstance(r, dict):
                continue
            if (
                "quantity" in r
                and r["quantity"] in requirements_mod.QUANTITIES
                and r.get("op") in requirements_mod.OPS
            ) or (r.get("kind") == "assert" and r.get("expr")):
                valid.append(r)
        self.s._requirements = valid
        if self.s.root is not None:
            requirements_mod.write_requirements(self.s.root, valid)
        return {"ok": True, "count": len(valid)}

    def check_requirements(self) -> dict:
        """Evaluate the stored requirements against the current model: a pass/fail
        per goal plus a met/total summary. Read-only. Mass/size/watertight come
        from the last-good model.json; expensive checks (DFM, interference) run
        only when a requirement needs them. With no model, every requirement is
        ``pass: null`` (not built yet), never a failure.

        Also computes per-result regression deltas against the previous run and
        includes regressed/fixed counts in the summary.
        """
        reqs = self.s._requirements
        ctx: dict = {}
        if self.s._objects:
            info = self.s.get_model_info()
            if info:
                ctx["mass"] = (info.get("mass") or {}).get("value")
                ctx["bbox"] = (info.get("bbox") or {}).get("size")
                ctx["manifold"] = info.get("manifold")
            if requirements_mod.needs(reqs, "dfm_critical"):
                dfm = self.analyze_dfm()
                ctx["dfmCritical"] = dfm["summary"]["critical"] if dfm.get("ok") else None
            if requirements_mod.needs(reqs, "overlaps"):
                itf_rep = self.check_interferences()
                ctx["overlaps"] = itf_rep["summary"]["overlaps"] if itf_rep.get("ok") else None
            if requirements_mod.needs(reqs, "min_wall"):
                ctx["min_wall"] = self._min_wall_mm()
            if requirements_mod.needs(reqs, "min_clearance"):
                ctx["min_clearance"] = self._min_clearance_mm()
        results = requirements_mod.evaluate(reqs, ctx)

        # regression delta: compare against last-persisted results
        prev = requirements_mod.load_state(self.s.root) if self.s.root is not None else None
        deltas = requirements_mod.diff_results(prev, results)
        if self.s.root is not None:
            requirements_mod.write_state(self.s.root, results)

        summary = requirements_mod.delta_summary(deltas)
        met = sum(1 for r in results if r["pass"] is True)
        countable = sum(1 for r in results if r["pass"] is not None)
        summary.update(
            {
                "met": met,
                "total": len(results),
                "allMet": countable == 0 or met == countable,
            }
        )
        return {
            "ok": True,
            "schema": 1,
            "buildId": self.s.build_id,
            "requirements": deltas,
            "summary": summary,
        }

    def _min_wall_mm(self) -> float | None:
        """Minimum wall thickness (mm) across all shown parts, or None."""
        objects = self.s._objects or []
        best: float | None = None
        for o in objects:
            if getattr(o, "role", "part") == "reference":
                continue
            t = dfm_rules.min_wall_mm(o.shape)
            if t is not None and (best is None or t < best):
                best = t
        return best

    def _min_clearance_mm(self) -> float | None:
        """Minimum bbox clearance (mm) between non-overlapping shown parts, or None."""
        objects = self.s._objects or []
        parts = [o for o in objects if getattr(o, "role", "part") != "reference"]
        if len(parts) < 2:
            return None
        return itf.min_clearance_mm([o.shape for o in parts])

    def _measure_registry(self, with_dfm: bool) -> dict:
        """Mass / volume / assembly bbox of the geometry currently in the build123d
        registry (used while a variant is built, before it is discarded)."""
        objs = [o for o in solidifai._registry() if getattr(o, "role", "part") != "reference"]
        if not objs:
            return {"mass": 0.0, "volume": 0.0, "bbox": [0.0, 0.0, 0.0]}
        solids = [props_geom.mass_properties(o.shape, self._density_for(o.material)) for o in objs]
        mins = [min(s["bbox"]["min"][i] for s in solids) for i in range(3)]
        maxs = [max(s["bbox"]["max"][i] for s in solids) for i in range(3)]
        out: dict[str, Any] = {
            "mass": props_geom.aggregate(solids)["mass"],
            "volume": round(sum(s["volume"] for s in solids), 4),
            "bbox": [round(maxs[i] - mins[i], 4) for i in range(3)],
        }
        if with_dfm:
            crit = 0
            for o in objs:
                rep = dfm_rules.analyze_part(o.shape, process="fdm")
                crit += sum(1 for v in rep["violations"] if v["severity"] == "critical")
            out["dfmCritical"] = crit
        return out
