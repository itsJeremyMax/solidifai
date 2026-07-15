"""Eval runner: ``python -m evals.run --tier smoke|full [...]``.

Module level stays import-light (task discovery + spec validation only) so the
spec tests run fast; heavy engine imports happen lazily inside the run helpers.
"""

from __future__ import annotations

import contextlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
TASKS_DIR = EVALS_DIR / "tasks"
SMOKE_TASKS = ["washer-spec", "phone-stand", "pi-case"]
DEFAULT_TIMEOUT_S = 900  # hard per-task agent timeout; spec.json "timeout_s" overrides

KNOWN_GRADERS = frozenset(
    {
        "requirements",
        "dfm",
        "watertight",
        "interference",
        "stress",
        "dim_match",
        "containment",
        "stability",
        "motion",
        "semantic",
    }
)
DIM_KINDS = frozenset({"bbox_sorted", "mass", "hole", "center_distance", "feature"})
SEMANTIC_KINDS = frozenset(
    {
        "part_count",
        "part_name",
        "part_faces",
        "feature",
        "hole_pattern",
        "cavity",
        "cavity_pattern",
        "interface",
        "motion",
        "radial_gear",
        "gopro_two_prong",
        "hinge_topology",
        "wall_hook",
        "l_bracket",
        "reference_port_pattern",
        "vent_open_area",
    }
)


def _finite_positive(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _semantic_problem(req: object) -> str | None:
    if not isinstance(req, dict) or not isinstance(req.get("id"), str) or not req["id"]:
        return "semantic requirement needs a non-empty string id"
    kind = req.get("kind")
    common = {"id", "kind"}
    allowed: dict[str, set[str]] = {
        "part_count": common | {"count", "min", "max"},
        "part_name": common | {"name", "count"},
        "part_faces": common | {"name", "min"},
        "feature": common | {"name", "metric", "range"},
        "hole_pattern": common | {"count", "diameter_mm", "tolerance_mm"},
        "cavity": common | {"size_mm", "tolerance_mm"},
        "cavity_pattern": common | {"size_mm", "centers_mm", "tolerance_mm"},
        "interface": common | {"parts", "tolerance_mm"},
        "motion": common | {"part", "range_deg"},
        "radial_gear": common | {"name", "tooth_count", "module_mm", "module_tolerance_mm"},
        "gopro_two_prong": common
        | {"name", "prong_thickness_mm", "prong_gap_mm", "pin_hole_diameter_mm", "tolerance_mm"},
        "hinge_topology": common | {"leaves", "pin", "knuckles_per_leaf", "tolerance_mm"},
        "wall_hook": common
        | {
            "name",
            "mount_hole_diameter_mm",
            "mount_hole_count",
            "wall_thickness_mm",
            "min_projection_mm",
            "min_retaining_rise_mm",
            "tolerance_mm",
        },
        "l_bracket": common
        | {
            "name",
            "mount_axis",
            "span_axis",
            "rise_axis",
            "min_mount_thickness_mm",
            "min_span_mm",
            "min_rise_mm",
            "min_projection_mm",
            "tolerance_mm",
        },
        "reference_port_pattern": common
        | {"reference", "axis", "side", "openings", "tolerance_mm"},
        "vent_open_area": common | {"min_open_area_mm2", "axis", "min_count", "tolerance_mm"},
    }
    if kind not in SEMANTIC_KINDS or set(req) - allowed.get(kind, set()):
        return f"semantic requirement {req['id']!r} has invalid kind or keys"
    if kind == "part_count":
        has_count = "count" in req
        has_range = "min" in req or "max" in req
        if has_count == has_range:
            return f"semantic requirement {req['id']!r} needs count or min/max, not both"
        if has_range and not {"min", "max"} <= set(req):
            return f"semantic requirement {req['id']!r} needs both min and max"
        values = [req[k] for k in ("count", "min", "max") if k in req]
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in values):
            return f"semantic requirement {req['id']!r} needs positive integer count/min/max"
        if has_range and req["min"] > req["max"]:
            return f"semantic requirement {req['id']!r} needs min <= max"
    elif kind in {"part_name", "feature"} and (
        not isinstance(req.get("name"), str) or not req["name"]
    ):
        return f"semantic requirement {req['id']!r} needs name"
    elif (
        kind == "part_name"
        and "count" in req
        and (
            not isinstance(req["count"], int) or isinstance(req["count"], bool) or req["count"] < 1
        )
    ):
        return f"semantic requirement {req['id']!r} needs positive integer count"
    elif kind == "part_faces":
        if (
            not isinstance(req.get("name"), str)
            or not req["name"]
            or not isinstance(req.get("min"), int)
            or isinstance(req["min"], bool)
            or req["min"] < 1
        ):
            return f"semantic requirement {req['id']!r} needs name and integer min"
    elif kind == "feature":
        has_metric = "metric" in req
        has_range = "range" in req
        if has_metric != has_range:
            return f"semantic requirement {req['id']!r} needs metric and range together"
        if has_metric and (not isinstance(req["metric"], str) or not req["metric"]):
            return f"semantic requirement {req['id']!r} needs a non-empty metric"
        if has_range and (
            not isinstance(req["range"], list)
            or len(req["range"]) != 2
            or not all(_finite_positive(v) for v in req["range"])
            or req["range"][0] > req["range"][1]
        ):
            return f"semantic requirement {req['id']!r} has invalid metric range"
    elif kind == "hole_pattern":
        if (
            not isinstance(req.get("count"), int)
            or isinstance(req["count"], bool)
            or req["count"] < 1
            or not _finite_positive(req.get("diameter_mm"))
            or not _finite_positive(req.get("tolerance_mm"))
        ):
            return (
                f"semantic requirement {req['id']!r} needs count, finite diameter_mm "
                "and tolerance_mm"
            )
    elif kind == "cavity":
        if (
            not isinstance(req.get("size_mm"), list)
            or len(req["size_mm"]) != 3
            or not all(_finite_positive(v) for v in req["size_mm"])
            or not _finite_positive(req.get("tolerance_mm"))
        ):
            return (
                f"semantic requirement {req['id']!r} needs finite positive size_mm and tolerance_mm"
            )
    elif kind == "cavity_pattern":
        centers = req.get("centers_mm")
        sizes = req.get("size_mm")
        uniform_sizes = (
            isinstance(sizes, list) and len(sizes) == 3 and all(_finite_positive(v) for v in sizes)
        )
        per_region_sizes = (
            isinstance(sizes, list)
            and sizes
            and all(
                isinstance(size, list) and len(size) == 3 and all(_finite_positive(v) for v in size)
                for size in sizes
            )
        )
        if (
            not isinstance(centers, list)
            or len(centers) < 2
            or not all(
                isinstance(center, list)
                and len(center) == 3
                and all(_finite_number(v) for v in center)
                for center in centers
            )
            or not (uniform_sizes or per_region_sizes)
            or (per_region_sizes and isinstance(sizes, list) and len(sizes) != len(centers))
            or not _finite_positive(req.get("tolerance_mm"))
        ):
            return (
                f"semantic requirement {req['id']!r} needs two or more finite centers_mm, "
                "finite positive size_mm and tolerance_mm"
            )
    elif kind == "interface":
        parts = req.get("parts")
        if (
            not isinstance(parts, list)
            or len(parts) != 2
            or not all(isinstance(p, str) and p for p in parts)
            or parts[0] == parts[1]
        ):
            return f"semantic requirement {req['id']!r} needs two distinct part names"
        if "tolerance_mm" in req and not _finite_positive(req["tolerance_mm"]):
            return f"semantic requirement {req['id']!r} needs finite positive tolerance_mm"
    elif kind == "motion":
        span = req.get("range_deg")
        if (
            not isinstance(req.get("part"), str)
            or not req["part"]
            or not isinstance(span, list)
            or len(span) != 2
            or not all(_finite_number(v) for v in span)
            or span[0] >= span[1]
        ):
            return f"semantic requirement {req['id']!r} needs part and ascending finite range_deg"
    elif kind == "radial_gear":
        if (
            not isinstance(req.get("name"), str)
            or not req["name"]
            or not isinstance(req.get("tooth_count"), int)
            or isinstance(req["tooth_count"], bool)
            or req["tooth_count"] < 3
            or not _finite_positive(req.get("module_mm"))
            or not _finite_positive(req.get("module_tolerance_mm"))
        ):
            return f"semantic requirement {req['id']!r} needs tooth_count and module geometry"
    elif kind == "gopro_two_prong":
        if (
            not isinstance(req.get("name"), str)
            or not req["name"]
            or not all(
                _finite_positive(req.get(key))
                for key in (
                    "prong_thickness_mm",
                    "prong_gap_mm",
                    "pin_hole_diameter_mm",
                    "tolerance_mm",
                )
            )
        ):
            return f"semantic requirement {req['id']!r} needs prong and aligned pin-hole geometry"
    elif kind == "hinge_topology":
        leaves = req.get("leaves")
        if (
            not isinstance(leaves, list)
            or len(leaves) != 2
            or not all(isinstance(name, str) and name for name in leaves)
            or leaves[0] == leaves[1]
            or not isinstance(req.get("pin"), str)
            or not req["pin"]
            or not isinstance(req.get("knuckles_per_leaf"), int)
            or isinstance(req["knuckles_per_leaf"], bool)
            or req["knuckles_per_leaf"] < 1
            or not _finite_positive(req.get("tolerance_mm"))
        ):
            return f"semantic requirement {req['id']!r} needs leaves, pin, and knuckle topology"
    elif kind == "wall_hook":
        has_mount_fields = "mount_hole_diameter_mm" in req or "mount_hole_count" in req
        if (
            not isinstance(req.get("name"), str)
            or not req["name"]
            or not all(
                _finite_positive(req.get(key))
                for key in (
                    "min_projection_mm",
                    "min_retaining_rise_mm",
                    "tolerance_mm",
                )
            )
            or (
                has_mount_fields
                and (
                    not isinstance(req.get("mount_hole_count"), int)
                    or isinstance(req["mount_hole_count"], bool)
                    or req["mount_hole_count"] < 1
                    or not _finite_positive(req.get("mount_hole_diameter_mm"))
                )
            )
            or (not has_mount_fields and not _finite_positive(req.get("wall_thickness_mm")))
        ):
            return f"semantic requirement {req['id']!r} needs mounting and load-path geometry"
    elif kind == "l_bracket":
        axes = [req.get("mount_axis"), req.get("span_axis"), req.get("rise_axis")]
        if (
            not isinstance(req.get("name"), str)
            or not req["name"]
            or any(axis not in {"x", "y", "z"} for axis in axes)
            or len(set(axes)) != 3
            or not all(
                _finite_positive(req.get(key))
                for key in (
                    "min_mount_thickness_mm",
                    "min_span_mm",
                    "min_rise_mm",
                    "min_projection_mm",
                    "tolerance_mm",
                )
            )
        ):
            return f"semantic requirement {req['id']!r} needs distinct axes and finite leg geometry"
    elif kind == "reference_port_pattern":
        openings = req.get("openings")
        if (
            not isinstance(req.get("reference"), str)
            or not req["reference"]
            or req.get("axis") not in {"x", "y", "z"}
            or req.get("side") not in {"min", "max"}
            or not isinstance(openings, list)
            or not openings
            or not all(
                isinstance(opening, dict)
                and set(opening) == {"offset_mm", "size_mm"}
                and isinstance(opening["offset_mm"], list)
                and len(opening["offset_mm"]) == 2
                and all(_finite_number(value) for value in opening["offset_mm"])
                and isinstance(opening["size_mm"], list)
                and len(opening["size_mm"]) == 3
                and all(_finite_positive(value) for value in opening["size_mm"])
                for opening in openings
            )
            or not _finite_positive(req.get("tolerance_mm"))
        ):
            return f"semantic requirement {req['id']!r} needs reference-relative opening geometry"
    elif kind == "vent_open_area":
        if (
            req.get("axis") not in {"x", "y", "z"}
            or not _finite_positive(req.get("min_open_area_mm2"))
            or not isinstance(req.get("min_count"), int)
            or isinstance(req["min_count"], bool)
            or req["min_count"] < 1
            or not _finite_positive(req.get("tolerance_mm"))
        ):
            return f"semantic requirement {req['id']!r} needs vent area and axis geometry"
    return None


@dataclass
class Task:
    name: str
    brief: str
    spec: dict
    timeout_s: int


def discover_tasks(tasks_dir: Path = TASKS_DIR) -> list[str]:
    """Task names = subdirs of tasks/ that carry a spec.json."""
    if not Path(tasks_dir).is_dir():
        return []
    return sorted(p.name for p in Path(tasks_dir).iterdir() if (p / "spec.json").is_file())


def load_task(name: str, tasks_dir: Path = TASKS_DIR) -> Task:
    d = Path(tasks_dir) / name
    if not d.is_dir():
        raise ValueError(f"task {name!r}: directory not found in {tasks_dir}")
    brief = (d / "brief.md").read_text(encoding="utf-8").strip()
    spec = json.loads((d / "spec.json").read_text(encoding="utf-8"))
    problems = validate_spec(spec)
    if problems:
        raise ValueError(f"task {name!r}: " + "; ".join(problems))
    if not brief:
        raise ValueError(f"task {name!r}: empty brief.md")
    return Task(
        name=name,
        brief=brief,
        spec=spec,
        timeout_s=int(spec.get("timeout_s", DEFAULT_TIMEOUT_S)),
    )


def validate_spec(spec: dict) -> list[str]:
    """Return a list of problems (empty = valid). Requirements are validated
    against the engine's own predicate schema so spec.json and the live
    requirements.json can never drift apart."""
    from solidifai_engine import requirements as requirements_mod

    problems: list[str] = []
    if spec.get("schema") not in {1, 2}:
        problems.append("schema must be 1 or 2")
    graders = spec.get("graders")
    if not isinstance(graders, list) or not graders:
        problems.append("graders must be a non-empty list")
        graders = []
    for g in graders:
        if g not in KNOWN_GRADERS:
            problems.append(f"unknown grader {g!r}")
    for r in spec.get("requirements", []):
        ok_bound = "bound" in r
        if r.get("op") == "within":
            ok_bound = isinstance(r.get("bound"), (list | tuple)) and len(r["bound"]) == 2
        ok_pred = (
            r.get("quantity") in requirements_mod.QUANTITIES
            and r.get("op") in requirements_mod.OPS
            and ok_bound
        )
        ok_assert = r.get("kind") == "assert" and r.get("expr")
        if not (ok_pred or ok_assert):
            problems.append(f"invalid requirement {r.get('id')!r}")
    for e in spec.get("expected_dims", []):
        if e.get("kind") not in DIM_KINDS:
            problems.append(f"expected_dims: unknown kind {e.get('kind')!r}")
        elif not isinstance(e.get("expected"), (int | float)) or not isinstance(
            e.get("tol"), (int | float)
        ):
            problems.append(f"expected_dims: {e.get('kind')} entry needs numeric expected + tol")
    for v in (spec.get("containment") or {}).get("volumes", []):
        size = v.get("size_mm")
        if not (isinstance(size, list) and len(size) == 3):
            problems.append(f"containment volume {v.get('name')!r} needs size_mm [x,y,z]")
    t = spec.get("timeout_s")
    if t is not None and (not isinstance(t, int) or t <= 0):
        problems.append("timeout_s must be a positive integer")
    if "motion" in graders and not isinstance(spec.get("motion"), dict):
        problems.append("motion grader needs a 'motion' config object")
    if "containment" in graders and not (spec.get("containment") or {}).get("volumes"):
        problems.append("containment grader needs containment.volumes")
    semantics = spec.get("semantic_requirements")
    if spec.get("schema") == 2 and not spec.get("calibration") and not isinstance(semantics, list):
        problems.append("semantic_requirements must contain a task-specific criterion")
    if semantics is not None:
        if not isinstance(semantics, list) or (not semantics and not spec.get("calibration")):
            problems.append(
                "semantic_requirements must be a non-empty list for non-calibration tasks"
            )
        else:
            ids: set[str] = set()
            for req in semantics:
                problem = _semantic_problem(req)
                if problem:
                    problems.append(problem)
                if isinstance(req, dict) and req.get("id") in ids:
                    problems.append(f"duplicate semantic requirement id {req['id']!r}")
                if isinstance(req, dict) and isinstance(req.get("id"), str):
                    ids.add(req["id"])
    if spec.get("schema") == 2 and not spec.get("calibration") and "semantic" not in graders:
        problems.append("non-calibration schema 2 task needs semantic grader")
    return problems


def tier_tasks(tier: str, tasks_dir: Path = TASKS_DIR) -> list[str]:
    if tier == "smoke":
        return list(SMOKE_TASKS)
    if tier == "full":
        return discover_tasks(tasks_dir)
    raise ValueError(f"unknown tier {tier!r} (expected 'smoke' or 'full')")


# -- orchestration (heavy imports stay inside these helpers) -------------------


def _run_id() -> str:
    import os
    import time

    # random suffix: same-second concurrent runs must never share a run dir
    # (and through it the workspaces root + engine sockets)
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{os.urandom(3).hex()}"


def grade_workspace_dir(
    task: Task, workspace: str, out_dir: Path, *, no_vlm: bool, agent: dict | None = None
) -> dict:
    """Grade one produced workspace in a FRESH engine session (+ VLM judge
    unless --no-vlm). The agent dict is run metadata only — never graded."""
    from evals import scorecard as sc
    from evals import vlm_judge
    from evals.graders import grade_workspace, open_grading_session

    gs = open_grading_session(workspace)
    try:
        programmatic = grade_workspace(gs, task.spec)
        vlm = None
        if not no_vlm:
            vlm = vlm_judge.judge(
                gs, task.brief, task.spec, out_dir / f"{task.name}-{Path(workspace).name}-judge"
            )
    finally:
        gs.close()
    if no_vlm:
        vlm = {"status": "skipped", "reason": "--no-vlm"}
    result = {
        "workspace": str(workspace),
        "agent": agent,
        "programmatic": programmatic,
        "vlm": vlm,
        "vlm_score": sc.vlm_score(vlm),
    }
    return {
        **result,
        **sc.grade_result(
            programmatic=programmatic,
            vlm=vlm,
            vlm_required=bool(task.spec.get("vlm_required")),
            agent=agent,
        ),
    }


def _infra_error_result(workspace: str | Path, exc: Exception) -> dict:
    return {
        "workspace": str(workspace),
        "error": str(exc),
        "terminal_status": "infra_error",
        "gate_passed": False,
        "composite": None,
        "programmatic": {"programmatic_score": 0.0, "graders": []},
        "vlm": None,
        "vlm_score": None,
    }


def run_task_once(task: Task, ws_dir: Path, out_dir: Path, *, no_vlm: bool) -> dict:
    """Provision -> engine up -> headless agent -> engine down -> grade."""
    import sys

    from evals.agent_runner import EngineProcess, run_agent
    from evals.provision import provision_workspace

    provision_workspace(ws_dir, sys.executable)
    engine = EngineProcess(str(ws_dir))
    engine.start()
    try:
        agent = run_agent(
            task.brief,
            str(ws_dir),
            timeout_s=task.timeout_s,
            transcript_path=out_dir / f"{task.name}-{ws_dir.name}-transcript.json",
        )
    finally:
        engine.stop()
    graded = grade_workspace_dir(task, str(ws_dir), out_dir, no_vlm=no_vlm, agent=agent)
    if "terminal_status" not in graded:
        from evals import scorecard as sc

        graded.update(
            sc.grade_result(
                programmatic=graded["programmatic"],
                vlm=graded.get("vlm"),
                vlm_required=bool(task.spec.get("vlm_required")),
                agent=agent,
            )
        )
    return graded


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="evals.run", description=__doc__)
    parser.add_argument("--tier", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--tasks", help="comma-separated task names (overrides --tier)")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--grade-only", metavar="WORKSPACE", help="regrade an existing workspace; no agent run"
    )
    parser.add_argument("--no-vlm", action="store_true")
    parser.add_argument("--runs-dir", default=str(EVALS_DIR / "runs"))
    parser.add_argument(
        "--workspaces-root",
        default="/tmp/sf-evals",
        help="MUST be short: the engine socket lives under it (AF_UNIX ~104-char cap)",
    )
    parser.add_argument(
        "--record-baseline", action="store_true", help="write evals/baseline.json from this run"
    )
    args = parser.parse_args(argv)

    from evals import scorecard as sc

    names = (
        [t.strip() for t in args.tasks.split(",") if t.strip()]
        if args.tasks
        else tier_tasks(args.tier)
    )
    if args.grade_only and len(names) != 1:
        parser.error("--grade-only needs exactly one task: --tasks <name>")
    tasks = [load_task(n) for n in names]

    run_dir = Path(args.runs_dir) / _run_id()
    run_dir.mkdir(parents=True, exist_ok=True)

    task_results: dict[str, list[dict]] = {}
    if args.grade_only:
        tier = "grade-only"
        task = tasks[0]
        try:
            result = grade_workspace_dir(task, args.grade_only, run_dir, no_vlm=args.no_vlm)
        except Exception as exc:  # noqa: BLE001 - retain grade-only diagnostics too
            result = _infra_error_result(args.grade_only, exc)
        task_results[task.name] = [result]
    else:
        from evals.agent_runner import ensure_claude

        ensure_claude()  # fail fast with a clear message before provisioning anything
        tier = "custom" if args.tasks else args.tier
        ws_root = Path(args.workspaces_root) / run_dir.name
        for task in tasks:
            runs = []
            for r in range(1, max(1, args.repeats) + 1):
                ws = ws_root / f"{task.name}-r{r}"
                ws.mkdir(parents=True, exist_ok=True)
                try:
                    runs.append(run_task_once(task, ws, run_dir, no_vlm=args.no_vlm))
                except Exception as exc:  # noqa: BLE001 - one broken task never sinks the run
                    runs.append(_infra_error_result(ws, exc))
            task_results[task.name] = runs
        # convenience pointer from the (gitignored) run dir to the workspaces
        with contextlib.suppress(OSError):
            (run_dir / "workspaces").symlink_to(ws_root)

    rubric_ver = None
    if not args.no_vlm:
        from evals.vlm_judge import rubric_version

        rubric_ver = rubric_version()
    card = sc.build_scorecard(
        tier=tier,
        task_results=task_results,
        repeats=args.repeats,
        rubric_ver=rubric_ver,
        vlm_enabled=not args.no_vlm,
        baseline=sc.load_baseline(sc.BASELINE_PATH),
    )
    sc.write_run_outputs(run_dir, card)
    if args.record_baseline:
        sc.BASELINE_PATH.write_text(
            json.dumps(sc.baseline_from_scorecard(card), indent=2) + "\n", encoding="utf-8"
        )
    print((run_dir / "report.md").read_text(encoding="utf-8"))
    print(f"scorecard: {run_dir / 'scorecard.json'}")
    return (
        0
        if all(
            run.get("gate_passed", run.get("terminal_status", "passed") == "passed")
            for runs in task_results.values()
            for run in runs
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
