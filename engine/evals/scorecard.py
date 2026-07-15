"""Scorecard assembly: composite = 0.6 programmatic + 0.4 VLM (trend line only;
the per-task per-grader values are the real signal and are preserved in full)."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from evals.vlm_judge import RUBRIC_AXES

PROGRAMMATIC_WEIGHT = 0.6
VLM_WEIGHT = 0.4
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"


def vlm_score(judge_result: dict | None) -> float | None:
    """Mean of the five rubric scores normalized to 0..1, or None when the
    judge was skipped/failed (composite then falls back to programmatic)."""
    if not judge_result or "scores" not in judge_result:
        return None
    scores = judge_result["scores"]
    vals = [(float(scores[a]) - 1.0) / 4.0 for a in RUBRIC_AXES if a in scores]
    if len(vals) != len(RUBRIC_AXES):
        return None
    return round(sum(vals) / len(vals), 4)


def composite(programmatic: float, vlm: float | None) -> float:
    if vlm is None:
        return round(programmatic, 4)
    return round(PROGRAMMATIC_WEIGHT * programmatic + VLM_WEIGHT * vlm, 4)


def grade_result(
    *, programmatic: dict | float, vlm: dict | None, vlm_required: bool, agent: dict | None = None
) -> dict:
    """Turn grading evidence into an honest terminal state.

    Numeric scores describe only complete attempts. Agent and grader failures are
    operationally incomplete, while a required-but-missing visual judgment is
    inconclusive rather than silently converted into a programmatic-only score.
    """
    if isinstance(programmatic, dict):
        pscore = float(programmatic.get("programmatic_score", 0.0))
        graders = programmatic.get("graders", [])
        grader_error = bool(programmatic.get("error")) or any(
            str(g.get("detail", "")).startswith("grader crashed:") for g in graders
        )
        programmatic_failed = any(g.get("passed") is False for g in graders)
    else:
        pscore = float(programmatic)
        grader_error = False
        programmatic_failed = pscore < 1.0

    if agent is not None and (
        agent.get("timed_out") is True
        or agent.get("exit_code") != 0
        or agent.get("envelope_valid") is False
    ):
        return {"terminal_status": "infra_error", "gate_passed": False, "composite": None}
    if grader_error:
        return {"terminal_status": "inconclusive", "gate_passed": False, "composite": None}

    explicit_skip = bool(vlm and vlm.get("status") == "skipped" and vlm.get("reason") == "--no-vlm")
    vscore = vlm_score(vlm)
    if explicit_skip and vlm_required:
        return {"terminal_status": "inconclusive", "gate_passed": False, "composite": None}
    # A programmatic-only score is valid solely when the caller explicitly
    # selected --no-vlm. Any requested judge failure is incomplete evidence.
    if not explicit_skip and vscore is None:
        return {"terminal_status": "inconclusive", "gate_passed": False, "composite": None}
    terminal_status = "failed" if programmatic_failed else "passed"
    return {
        "terminal_status": terminal_status,
        "gate_passed": terminal_status == "passed",
        "composite": composite(pscore, None if explicit_skip else vscore),
    }


def summarize_task(runs: list[dict]) -> dict:
    # Only completed pass/fail runs are quality measurements. Inconclusive and
    # infra-error attempts remain visible below, but must not poison a trend.
    comps = [
        r["composite"]
        for r in runs
        if r.get("terminal_status", "passed") in {"passed", "failed"}
        and isinstance(r.get("composite"), (int, float))
    ]
    incomplete = len(runs) - len(comps)
    return {
        "composite_mean": round(sum(comps) / len(comps), 4) if comps else None,
        "composite_min": min(comps) if comps else None,
        "composite_max": max(comps) if comps else None,
        "quality_runs": len(comps),
        "incomplete_runs": incomplete,
    }


def build_scorecard(
    *,
    tier: str,
    task_results: dict[str, list[dict]],
    repeats: int,
    rubric_ver: str | None,
    vlm_enabled: bool,
    baseline: dict | None,
) -> dict:
    # A baseline recorded under a different rubric is not comparable: suppress
    # deltas rather than report misleading regressions/improvements.
    base_rubric_ver = (baseline or {}).get("rubric_version")
    baseline_stale = bool(base_rubric_ver and rubric_ver and base_rubric_ver != rubric_ver)
    if baseline_stale:
        baseline = None
    tasks = {}
    for name, runs in task_results.items():
        summary = summarize_task(runs)
        base = (baseline or {}).get("tasks", {}).get(name)
        tasks[name] = {
            "runs": runs,
            **summary,
            "baseline": base,
            "delta": None
            if base is None or summary["composite_mean"] is None
            else round(summary["composite_mean"] - base, 4),
        }
    comps = [t["composite_mean"] for t in tasks.values() if t["composite_mean"] is not None]
    return {
        "schema": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tier": tier,
        "repeats": repeats,
        "vlm": vlm_enabled,
        "rubric_version": rubric_ver,
        "baseline_stale": baseline_stale,
        "baseline_rubric_version": base_rubric_ver,
        "composite": round(sum(comps) / len(comps), 4) if comps else None,
        "tasks": tasks,
    }


def _md_escape(text: object) -> str:
    """Keep free-form strings (part names, grader detail, LLM rationales) from
    breaking the markdown table/list structure."""
    flat = " ".join(str(text).split())
    return flat.replace("|", "\\|")


def render_report(card: dict) -> str:
    head = f"# Eval report — {card['created']} (tier: {card['tier']}, repeats: {card['repeats']})"
    weights = (
        f"programmatic {PROGRAMMATIC_WEIGHT} / VLM {VLM_WEIGHT}, rubric v{card['rubric_version']}"
        if card["vlm"]
        else "VLM skipped; composite = programmatic only"
    )
    lines = [head, "", f"Composite: **{card['composite']}** ({weights})", ""]
    if card.get("baseline_stale"):
        lines += [
            f"baseline stale (rubric v{card['rubric_version']} "
            f"vs v{card['baseline_rubric_version']}); deltas suppressed",
            "",
        ]
    lines += ["| task | composite | min..max | baseline | delta |", "|---|---|---|---|---|"]
    for name, t in sorted(card["tasks"].items()):
        rng = f"{t['composite_min']}..{t['composite_max']}"
        lines.append(
            f"| {_md_escape(name)} | {t['composite_mean']} | {rng} "
            f"| {t['baseline']} | {t['delta']} |"
        )
        if t["incomplete_runs"]:
            lines.append(f"|  | incomplete runs: {t['incomplete_runs']} |  |  |  |")
    for name, t in sorted(card["tasks"].items()):
        lines += ["", f"## {_md_escape(name)}"]
        for i, run in enumerate(t["runs"], 1):
            status = run.get("terminal_status", "passed")
            gate = run.get("gate_passed", True)
            lines.append(
                f"- run {i}: {status} (gate {gate}), composite {run['composite']} "
                f"(programmatic {run['programmatic']['programmatic_score']}, "
                f"vlm {run['vlm_score']})"
            )
            for g in run["programmatic"]["graders"]:
                mark = "PASS" if g["passed"] else ("SKIP" if g["passed"] is None else "FAIL")
                lines.append(
                    f"  - {_md_escape(g['name'])}: {mark} "
                    f"(score {g['score']}) {_md_escape(g['detail'])}".rstrip()
                )
            vlm = run.get("vlm") or {}
            for axis, score in (vlm.get("scores") or {}).items():
                why = (vlm.get("rationales") or {}).get(axis, "")
                lines.append(f"  - vlm/{_md_escape(axis)}: {score}/5 {_md_escape(why)}".rstrip())
            if vlm.get("error"):
                lines.append(f"  - vlm: ERROR {_md_escape(vlm['error'])}")
            if run.get("error"):
                lines.append(f"  - run failed: {_md_escape(run['error'])}")
    return "\n".join(lines) + "\n"


def load_baseline(path: str | Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def baseline_from_scorecard(card: dict) -> dict:
    return {
        "schema": 1,
        "recorded": card["created"],
        "rubric_version": card["rubric_version"],
        "tasks": {
            n: t["composite_mean"]
            for n, t in card["tasks"].items()
            if t["composite_mean"] is not None
        },
    }


def _json_sanitize(obj: object) -> object:
    """Grader data can carry nan/inf (e.g. degenerate mass/stress); map them to
    None so scorecard.json stays strict, loadable JSON."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    return obj


def write_run_outputs(run_dir: str | Path, card: dict) -> None:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    safe = _json_sanitize(card)
    (run_dir / "scorecard.json").write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
    (run_dir / "report.md").write_text(render_report(card), encoding="utf-8")
