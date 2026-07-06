"""Generative exploration: sweep a parameter across values and pick the best
under an objective. Pure helpers; the Session owns the (non-destructive) build
and measurement of each variant."""

from __future__ import annotations


def linspace(lo: float, hi: float, n: int) -> list:
    """``n`` evenly spaced samples across [lo, hi] inclusive (rounded to 6 dp)."""
    if n <= 1:
        return [round(float(lo), 6)]
    step = (hi - lo) / (n - 1)
    return [round(lo + step * i, 6) for i in range(n)]


def _feasible(v: dict, constraints: dict | None) -> bool:
    if not v.get("ok"):
        return False
    c = constraints or {}
    if (
        c.get("max_size")
        and v.get("bbox")
        and any(v["bbox"][i] > c["max_size"][i] + 1e-6 for i in range(3))
    ):
        return False
    return not (c.get("printable") and v.get("dfmCritical"))


def pick_best(variants: list, objective: str, constraints: dict | None):
    """Return ``(best_variant, feasible_count)`` for ``objective`` (min_mass /
    max_mass) over the feasible variants, or ``(None, 0)`` when none qualify."""
    feasible = [v for v in variants if _feasible(v, constraints)]
    if not feasible:
        return None, 0
    chooser = min if objective == "min_mass" else max
    return chooser(feasible, key=lambda v: v["mass"]), len(feasible)
