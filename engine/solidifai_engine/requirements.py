"""Per-workspace design requirements: a small list of goals evaluated against the
live model. Advisory; never mutates geometry. Persistence mirrors settings.py.

Predicate form: ``{id, quantity, op, bound, label?, enabled?}``.
Legacy form (still accepted): ``{id, type, target, label?, enabled?}``.
Assert form: ``{id, kind: "assert", expr, label?, enabled?}``.

A missing measurement yields ``pass: null`` ("not built / not measured yet")
rather than a failure, so an empty model never reads as broken.
"""

from __future__ import annotations

import ast
import json
import os

from solidifai_engine import paths

REQS_NAME = "requirements.json"
SCHEMA = 1
TYPES = {"max_mass", "min_mass", "max_size", "printable", "no_interference", "watertight"}
_AXES = ("X", "Y", "Z")

# ---------------------------------------------------------------------------
# Quantity registry
# ---------------------------------------------------------------------------

# Quantities backed by a vector ctx key (per-axis compare).
_VECTOR = {"size"}

# Maps each quantity name → the ctx dict key where it lives.
_QUANTITY_CTX = {
    "mass": "mass",
    "size": "bbox",
    "size_x": "bbox",
    "size_y": "bbox",
    "size_z": "bbox",
    "dfm_critical": "dfmCritical",
    "overlaps": "overlaps",
    "watertight": "manifold",
    "min_wall": "min_wall",
    "min_clearance": "min_clearance",
}
QUANTITIES = set(_QUANTITY_CTX)
OPS = {"<=", ">=", "within", "=="}


def requirements_path(root: str) -> str:
    return os.path.join(root, REQS_NAME)


def load_requirements(root: str) -> list:
    """Saved requirements list, or ``[]`` when absent or malformed. Never raises."""
    try:
        with open(requirements_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    raw = data.get("requirements") if isinstance(data, dict) else None
    return raw if isinstance(raw, list) else []


def write_requirements(root: str, reqs: list) -> None:
    """Atomically write the requirements list (temp + replace)."""
    path = requirements_path(root)
    payload = {"schema": SCHEMA, "requirements": reqs}
    tmp = paths.write_temp_text(path, json.dumps(payload, indent=2))
    paths.atomic_finalize(tmp, path)


def _label(r: dict) -> str:
    if r.get("label"):
        return r["label"]
    if "quantity" in r:
        q, op, bound = r["quantity"], r["op"], r.get("bound")
        return f"{q} {op} {bound}"
    t, tgt = r.get("type", ""), r.get("target")
    return {
        "max_mass": f"Under {tgt} g",
        "min_mass": f"At least {tgt} g",
        "max_size": f"Fits {tgt} mm" if tgt else "Fits a box",
        "printable": "Printable (FDM)",
        "no_interference": "No interference",
        "watertight": "Watertight",
    }.get(t, t)


def _unit(q: str) -> str | None:
    return {
        "mass": "g",
        "size": "mm",
        "size_x": "mm",
        "size_y": "mm",
        "size_z": "mm",
        "min_wall": "mm",
        "min_clearance": "mm",
    }.get(q)


def _measured(quantity: str, ctx: dict):
    """Read the measurement for ``quantity`` from ctx, or None if absent."""
    key = _QUANTITY_CTX.get(quantity)
    if key is None:
        return None
    val = ctx.get(key)
    if val is None:
        return None
    # size_x/y/z index into the bbox vector
    if quantity in ("size_x", "size_y", "size_z"):
        return val["xyz".index(quantity[-1])]
    return val


def _cmp(op: str, measured, bound) -> bool:
    if op == "<=":
        return measured <= bound
    if op == ">=":
        return measured >= bound
    if op == "within":
        return bound[0] <= measured <= bound[1]
    return measured == bound


def _eval_predicate(r: dict, ctx: dict) -> dict:
    q, op, bound = r["quantity"], r["op"], r.get("bound")
    out = {
        "id": r.get("id"),
        "quantity": q,
        "op": op,
        "bound": bound,
        "label": _label(r),
        "measured": None,
        "unit": _unit(q),
        "pass": None,
        "detail": "",
    }
    measured = _measured(q, ctx)
    if measured is None:
        return out
    if q in _VECTOR:  # per-axis vector compare (size)
        if not isinstance(bound, list):
            return out
        out["measured"] = [round(v, 2) for v in measured]
        over = [i for i in range(3) if not _cmp(op, measured[i], bound[i])]
        out["pass"] = not over
        if over:
            out["detail"] = ", ".join(
                f"{'XYZ'[i]} {round(measured[i], 1)} mm vs {bound[i]} mm" for i in over
            )
        return out
    out["measured"] = round(measured, 2) if isinstance(measured, float) else measured
    out["pass"] = bool(_cmp(op, measured, bound))
    if out["pass"] is False:
        out["detail"] = f"{out['measured']} {_unit(q) or ''} fails {op} {bound}".strip()
    return out


def _eval_one(r: dict, ctx: dict) -> dict:
    t = r["type"]
    out = {
        "id": r.get("id"),
        "type": t,
        "label": _label(r),
        "target": r.get("target"),
        "measured": None,
        "unit": None,
        "pass": None,
        "detail": "",
    }
    if t in ("max_mass", "min_mass"):
        m = ctx.get("mass")
        if m is None:
            return out
        out["measured"], out["unit"] = round(m, 2), "g"
        out["pass"] = m <= r["target"] if t == "max_mass" else m >= r["target"]
        if out["pass"] is False:
            verb = "over" if t == "max_mass" else "under"
            out["detail"] = f"{round(m, 1)} g is {verb} the {r['target']} g goal"
    elif t == "max_size":
        bb = ctx.get("bbox")
        if bb is None or r.get("target") is None:
            return out
        out["measured"], out["unit"] = [round(v, 2) for v in bb], "mm"
        over = [i for i in range(3) if bb[i] > r["target"][i] + 1e-6]
        out["pass"] = not over
        if over:
            out["detail"] = ", ".join(
                f"{_AXES[i]} {round(bb[i], 1)} mm exceeds {r['target'][i]} mm" for i in over
            )
    elif t == "watertight":
        m = ctx.get("manifold")
        if m is None:
            return out
        out["measured"], out["pass"] = bool(m), m is True
        if not m:
            out["detail"] = "Model is not watertight"
    elif t == "printable":
        c = ctx.get("dfmCritical")
        if c is None:
            return out
        out["measured"], out["pass"] = c, c == 0
        if c:
            out["detail"] = f"{c} critical DFM issue(s)"
    elif t == "no_interference":
        c = ctx.get("overlaps")
        if c is None:
            return out
        out["measured"], out["pass"] = c, c == 0
        if c:
            out["detail"] = f"{c} overlapping pair(s)"
    return out


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------

_LEGACY_MAP = {
    "max_mass": lambda t: ("mass", "<=", t),
    "min_mass": lambda t: ("mass", ">=", t),
    "max_size": lambda t: ("size", "<=", t),
    "printable": lambda t: ("dfm_critical", "<=", 0),
    "no_interference": lambda t: ("overlaps", "<=", 0),
    "watertight": lambda t: ("watertight", "==", True),
}


def migrate_legacy(reqs: list) -> list:
    """Map any legacy ``{type,target}`` entries to predicate form; pass predicates through."""
    out = []
    for r in reqs or []:
        if "quantity" in r or r.get("kind") == "assert":
            out.append(r)
            continue
        fn = _LEGACY_MAP.get(r.get("type"))
        if not fn:
            continue
        q, op, bound = fn(r.get("target"))
        entry = {
            "id": r.get("id"),
            "quantity": q,
            "op": op,
            "bound": bound,
            "enabled": r.get("enabled", True),
        }
        if r.get("label"):
            entry["label"] = r["label"]
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# Restricted assert escape hatch
# ---------------------------------------------------------------------------

# Only these AST node types are permitted in assert expressions.
_ALLOWED_AST = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.USub,
)


def _eval_assert(r: dict, ctx: dict) -> dict:
    out = {
        "id": r.get("id"),
        "kind": "assert",
        "label": r.get("label") or "assertion",
        "measured": None,
        "pass": None,
        "detail": "",
        "lowTrust": True,
    }
    expr = r.get("expr", "")
    try:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED_AST):
                out["detail"] = "expression uses an unsupported construct"
                return out
            if isinstance(node, ast.Name) and node.id not in ctx:
                out["detail"] = f"unknown measurement '{node.id}'"
                return out
        out["pass"] = bool(eval(compile(tree, "<assert>", "eval"), {"__builtins__": {}}, dict(ctx)))
    except Exception as exc:  # noqa: BLE001 — never raise out of evaluation
        out["detail"] = f"could not evaluate: {type(exc).__name__}"
    return out


def evaluate(reqs: list, ctx: dict) -> list:
    """Evaluate each enabled requirement against ``ctx``. Missing measurements
    yield ``pass: null``. Disabled requirements are skipped.

    Routes to the appropriate evaluator:
    - predicate form (``quantity`` key) → ``_eval_predicate``
    - assert form (``kind == "assert"``) → ``_eval_assert``
    - legacy form (``type`` key) → ``_eval_one``
    """
    out = []
    for r in reqs:
        if not r.get("enabled", True):
            continue
        if "quantity" in r:
            out.append(_eval_predicate(r, ctx))
        elif r.get("kind") == "assert":
            out.append(_eval_assert(r, ctx))
        else:
            out.append(_eval_one(r, ctx))
    return out


def needs(reqs: list, type_: str) -> bool:
    """True if an enabled requirement of ``type_`` or ``quantity`` exists -- used
    to gate expensive checks (DFM, interference) so the panel stays cheap otherwise."""
    for r in reqs:
        if not r.get("enabled", True):
            continue
        if r.get("type") == type_ or r.get("quantity") == type_:
            return True
    return False


# ---------------------------------------------------------------------------
# Regression delta
# ---------------------------------------------------------------------------


def diff_results(prev: list | None, curr: list) -> list:
    """Annotate each current result with a ``delta`` relative to the previous run.

    ``delta`` is one of: ``"unchanged"``, ``"regressed"``, ``"fixed"``, ``"new"``.
    When ``prev`` is None (first run), every result is ``"unchanged"``.
    """
    prev_pass = {r["id"]: r.get("pass") for r in (prev or [])}
    out = []
    for r in curr:
        pid, now = r.get("id"), r.get("pass")
        if prev is None or pid not in prev_pass:
            delta = "new" if prev is not None else "unchanged"
        else:
            was = prev_pass[pid]
            delta = (
                "regressed"
                if was is True and now is False
                else "fixed"
                if was is False and now is True
                else "unchanged"
            )
        out.append({**r, "delta": delta})
    return out


def delta_summary(deltas: list) -> dict:
    return {
        "regressed": sum(1 for d in deltas if d["delta"] == "regressed"),
        "fixed": sum(1 for d in deltas if d["delta"] == "fixed"),
    }


# ---------------------------------------------------------------------------
# State persistence (last-run results, for regression tracking)
# ---------------------------------------------------------------------------

STATE_NAME = "requirements_state.json"


def state_path(root: str) -> str:
    return os.path.join(root, STATE_NAME)


def load_state(root: str) -> list | None:
    """Load the last-run results, or None if absent or unreadable."""
    try:
        with open(state_path(root), encoding="utf-8") as f:
            return json.load(f).get("results")
    except (OSError, ValueError):
        return None


def write_state(root: str, results: list) -> None:
    """Atomically persist the latest evaluation results for regression tracking."""
    path = state_path(root)
    tmp = paths.write_temp_text(path, json.dumps({"schema": SCHEMA, "results": results}, indent=2))
    paths.atomic_finalize(tmp, path)
