"""Feasibility search over declared parameters: pick a parameter assignment that
satisfies the spec predicates, optionally minimizing a secondary objective.

Pure helpers; the Session builds and measures each candidate non-destructively
(mirroring how explore.pick_best is pure while Session.sweep builds).
"""

from __future__ import annotations

from solidifai_engine import explore
from solidifai_engine import requirements as rq


def candidate_grid(params: dict, max_evals: int = 24) -> list[dict]:
    """Coarse coordinate grid over each param's [min, max] range, capped to
    ~max_evals total.  Params with no range (or min == max) are skipped.

    The budget is spread evenly across the varying axes via an n-th-root
    heuristic; with a single axis we take min(max_evals, 12) samples.
    """
    names = [
        n
        for n, s in params.items()
        if s.get("min") is not None and s.get("max") is not None and s["min"] != s["max"]
    ]
    if not names:
        return []

    per = min(max_evals, 12) if len(names) == 1 else max(2, int(max_evals ** (1.0 / len(names))))

    axes = {n: explore.linspace(params[n]["min"], params[n]["max"], per) for n in names}

    # Build the Cartesian product incrementally.
    stack: list[dict] = [{}]
    for n in names:
        stack = [{**c, n: v} for c in stack for v in axes[n]]

    return stack[:max_evals]


def _ctx_from(cand: dict) -> dict:
    """Extract the measurement ctx dict from a candidate dict."""
    return {
        "mass": cand.get("mass"),
        "bbox": cand.get("bbox"),
        "manifold": cand.get("manifold"),
        "dfmCritical": cand.get("dfmCritical"),
        "overlaps": cand.get("overlaps"),
        "min_wall": cand.get("min_wall"),
        "min_clearance": cand.get("min_clearance"),
    }


def _passes(cand: dict, preds: list) -> bool:
    """True when every applicable predicate passes for this candidate."""
    results = rq.evaluate(preds, _ctx_from(cand))
    return bool(results) and all(r["pass"] is True for r in results)


def _satisfied_count(cand: dict, preds: list) -> int:
    """Number of predicates that pass for this candidate (used to rank misses)."""
    return sum(1 for r in rq.evaluate(preds, _ctx_from(cand)) if r["pass"] is True)


def pick_feasible(
    cands: list[dict],
    preds: list[dict],
    objective: str = "min_mass",
) -> tuple[dict | None, int, dict | None]:
    """Select the best feasible candidate satisfying all predicates.

    Returns ``(best, feasible_count, closest_miss)``.
    - ``best`` — the feasible candidate that best satisfies ``objective``.
    - ``feasible_count`` — how many candidates were feasible.
    - ``closest_miss`` — when none are feasible, the ok candidate that
      satisfies the most predicates; None when all candidates failed to build.
    """
    ok = [c for c in cands if c.get("ok")]
    feasible = [c for c in ok if _passes(c, preds)]

    if feasible:
        chooser = min if objective == "min_mass" else max
        return chooser(feasible, key=lambda c: c.get("mass", 0)), len(feasible), None

    closest = max(ok, key=lambda c: _satisfied_count(c, preds), default=None)
    return None, 0, closest
