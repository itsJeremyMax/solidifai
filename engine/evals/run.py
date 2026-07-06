"""Eval runner: ``python -m evals.run --tier smoke|full [...]``.

Module level stays import-light (task discovery + spec validation only) so the
spec tests run fast; heavy engine imports happen lazily inside the run helpers.
"""

from __future__ import annotations

import contextlib
import json
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
    }
)
DIM_KINDS = frozenset({"bbox_sorted", "mass", "hole", "center_distance", "feature"})


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
    if spec.get("schema") != 1:
        problems.append("schema must be 1")
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
    vscore = sc.vlm_score(vlm)
    return {
        "workspace": str(workspace),
        "agent": agent,
        "programmatic": programmatic,
        "vlm": vlm,
        "vlm_score": vscore,
        "composite": sc.composite(programmatic["programmatic_score"], vscore),
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
    return grade_workspace_dir(task, str(ws_dir), out_dir, no_vlm=no_vlm, agent=agent)


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
        task_results[task.name] = [
            grade_workspace_dir(task, args.grade_only, run_dir, no_vlm=args.no_vlm)
        ]
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
                    runs.append(
                        {
                            "workspace": str(ws),
                            "error": str(exc),
                            "composite": 0.0,
                            "programmatic": {"programmatic_score": 0.0, "graders": []},
                            "vlm": None,
                            "vlm_score": None,
                        }
                    )
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
