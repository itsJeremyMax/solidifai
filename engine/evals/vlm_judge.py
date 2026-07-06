"""VLM rubric judge: a capture_views contact sheet from the grading session is
handed to ``claude -p`` (Read tool only) with the versioned rubric; the reply
must be strict JSON. ``--no-vlm`` skips this entirely at the CLI layer."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from evals.agent_runner import invoke_claude

RUBRIC_PATH = Path(__file__).resolve().parent / "rubric.md"
RUBRIC_AXES = ["proportion", "detail_density", "surface_finish", "realism", "brief_fidelity"]
DEFAULT_VIEWS = ["iso", "front-top-right", "back-top-left", "front"]
JUDGE_TIMEOUT_S = 300


def rubric_version() -> str:
    m = re.search(r"^version:\s*(\S+)", RUBRIC_PATH.read_text(encoding="utf-8"), re.MULTILINE)
    if not m:
        raise ValueError(f"rubric.md has no 'version:' line: {RUBRIC_PATH}")
    return m.group(1)


def capture_grid(gs, views: list[str]) -> str | None:
    """One labeled contact sheet of the grading session's model, or None."""
    res = gs.session.capture_views(view_names=views, layout="grid")
    if not res.get("ok"):
        return None
    views_list = res.get("views") or []
    if not views_list:
        return None
    return views_list[0]["path"]


def build_judge_prompt(brief: str, image_path: str) -> str:
    rubric = RUBRIC_PATH.read_text(encoding="utf-8")
    return (
        "You are grading a 3D model produced by a CAD agent from a user brief.\n"
        f"First, use the Read tool to view the labeled multi-view render grid at: {image_path}\n\n"
        "The user's brief was:\n---\n" + brief.strip() + "\n---\n\n"
        "Score it against this rubric:\n\n" + rubric + "\n"
        "Remember: respond with ONLY the JSON object."
    )


def parse_judge_output(stdout: str) -> dict:
    """Parse ``claude --output-format json`` stdout into validated scores.
    Raises ValueError on any deviation from the contract."""
    envelope = json.loads(stdout)
    if envelope.get("is_error"):
        # claude can exit 0 with is_error:true (refusal/API error); surface it
        # instead of a misleading "no JSON object" message.
        raise ValueError(f"judge envelope is_error: {str(envelope.get('result', ''))[:200]}")
    text = envelope.get("result") or ""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in judge output")
    obj = json.loads(text[start : end + 1])
    scores: dict[str, int] = {}
    rationales: dict[str, str] = {}
    for axis in RUBRIC_AXES:
        entry = obj.get(axis)
        if not isinstance(entry, dict) or not isinstance(entry.get("score"), int):
            raise ValueError(f"judge output missing integer score for {axis!r}")
        if not 1 <= entry["score"] <= 5:
            raise ValueError(f"judge score for {axis!r} out of range: {entry['score']}")
        scores[axis] = entry["score"]
        rationales[axis] = str(entry.get("why", ""))
    return {"scores": scores, "rationales": rationales}


def judge(gs, brief: str, spec: dict, out_dir: str | Path, runner=None) -> dict:
    """Capture, invoke, parse. Always returns a dict; failures carry "error"
    (scored as no-VLM by the scorecard, never a crash)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = rubric_version()
    if not gs.has_model:
        return {"error": "no model to judge", "rubric_version": version}
    grid = capture_grid(gs, spec.get("views") or DEFAULT_VIEWS)
    if grid is None:
        return {"error": "view capture failed", "rubric_version": version}
    image = out_dir / "views.png"
    shutil.copyfile(grid, image)
    res = invoke_claude(
        build_judge_prompt(brief, str(image)),
        cwd=str(out_dir),
        timeout_s=JUDGE_TIMEOUT_S,
        extra_args=["--allowedTools", "Read"],
        runner=runner,
    )
    if res.timed_out or res.exit_code != 0:
        return {
            "error": f"judge invocation failed (exit {res.exit_code}, timed_out={res.timed_out})",
            "rubric_version": version,
            "stderr": res.stderr[-2000:],
        }
    try:
        parsed = parse_judge_output(res.stdout)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        return {
            "error": f"unparseable judge output: {exc}",
            "rubric_version": version,
            "raw": res.stdout[-2000:],
        }
    return {**parsed, "rubric_version": version, "image": str(image)}
