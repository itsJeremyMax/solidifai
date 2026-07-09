"""Build a prefilled GitHub bug-report URL from context the engine can safely
gather. Mirrors the field-id contract of .github/ISSUE_TEMPLATE/bug_report.yml --
the same contract the GUI path uses in src/lib/help.ts (keep the two in sync). This
is the ONLY place the engine assembles the issue URL, so redaction and length
limits are enforced once. Nothing here submits anything; the returned URL is a
link the user reviews and clicks.
"""

from __future__ import annotations

import platform
import re
from urllib.parse import urlencode

from solidifai_engine import appinfo
from solidifai_engine.protocol import PROTOCOL_VERSION

REPO_URL = "https://github.com/itsJeremyMax/solidifai"
NEW_ISSUE = f"{REPO_URL}/issues/new"
TEMPLATE = "bug_report.yml"

# Keep the assembled URL under a safe browser/server query budget. GitHub and
# proxies vary; 6 KB leaves generous headroom while carrying real context.
_MAX_URL = 6000

# The exact agent options in bug_report.yml; anything else is dropped (GitHub
# ignores an unmatched dropdown value, but we normalise for a clean preview).
_AGENT_OPTIONS = {"Claude Code", "Codex", "opencode", "Not agent-related"}


def os_dropdown() -> str | None:
    """Map the running platform to an exact bug_report.yml OS option. The engine
    can tell Apple Silicon from Intel, which the frozen webview UA cannot."""
    system = platform.system()
    mach = platform.machine().lower()
    if system == "Darwin":
        if mach in ("arm64", "aarch64"):
            return "macOS (Apple Silicon)"
        if mach in ("x86_64", "amd64"):
            return "macOS (Intel)"
        return None
    if system == "Windows":
        return "Windows"
    if system == "Linux":
        return "Linux"
    return None


# Home-dir prefix (incl. the username segment) -> collapse to ~; the rest of the
# path is kept so the report still reads. Covers unix and Windows.
_HOME_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^/\\\s]+")
_SECRET_RES = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\b(?:authorization|token|api[_-]?key|secret|password)\b\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
)


def redact(text: str) -> str:
    """Strip home-dir paths and secret-looking strings from free text before it
    enters a public URL. A backstop under the skill's curation guidance."""
    if not text:
        return text
    out = _HOME_RE.sub("~", text)
    for rx in _SECRET_RES:
        out = rx.sub("[redacted]", out)
    return out


def _fence(text: str) -> str:
    return f"```\n{text}\n```"


def _diagnostics() -> str:
    """A safe, path-free build fingerprint appended to the logs field."""
    return "\n".join(
        [
            f"app        {appinfo.app_version()}",
            f"python     {platform.python_version()}",
            f"machine    {platform.system()} {platform.machine()}",
            f"protocol   {PROTOCOL_VERSION}",
        ]
    )


def _compose_logs(context: str, diag: str) -> str:
    if context:
        return f"{context}\n\n{_fence(diag)}"
    return _fence(diag)


def _assemble(fields: dict, logs: str) -> str:
    full = dict(fields)
    if logs:
        full["logs"] = logs
    return f"{NEW_ISSUE}?{urlencode(full)}"


def _truncate_to_fit(fields: dict, logs: str) -> str:
    """Largest logs prefix (plus a marker) that keeps the whole URL within budget.
    Required fields already live in `fields`, so they always survive."""
    marker = "\n[...truncated]"
    lo, hi, best = 0, len(logs), ""
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = logs[:mid] + (marker if mid < len(logs) else "")
        if len(_assemble(fields, cand)) <= _MAX_URL:
            best, lo = cand, mid + 1
        else:
            hi = mid - 1
    return best


def _render_preview(fields: dict, logs: str) -> str:
    lines = [
        f"Title: {fields['title']}",
        "",
        "What happened:",
        fields["what-happened"],
    ]
    if fields.get("steps"):
        lines += ["", "Steps to reproduce:", fields["steps"]]
    meta = [f"Version: {fields.get('version', '')}", f"OS: {fields.get('os', '')}"]
    if fields.get("agent"):
        meta.append(f"Agent: {fields['agent']}")
    lines += ["", " | ".join(meta), "", "Logs:", logs]
    return "\n".join(lines)


def build_report_issue(params: dict) -> dict:
    """Assemble a prefilled bug-report URL and its human preview. Redacts and
    length-caps unconditionally. Raises ValueError when a required field is empty."""
    title = redact(str(params.get("title", "")).strip())
    what = redact(str(params.get("what_happened", "")).strip())
    steps = redact(str(params.get("steps") or "").strip())
    context = redact(str(params.get("context") or "").strip())
    agent = params.get("agent") if params.get("agent") in _AGENT_OPTIONS else None

    if not title:
        raise ValueError("report_issue requires a non-empty title")
    if not what:
        raise ValueError("report_issue requires a non-empty what_happened")

    fields: dict = {"template": TEMPLATE, "title": title, "what-happened": what}
    if steps:
        fields["steps"] = steps
    fields["version"] = appinfo.app_version()
    os_opt = os_dropdown()
    if os_opt:
        fields["os"] = os_opt
    if agent:
        fields["agent"] = agent

    logs = _compose_logs(context, _diagnostics())
    if len(_assemble(fields, logs)) > _MAX_URL:
        logs = _truncate_to_fit(fields, logs)

    return {"url": _assemble(fields, logs), "preview": _render_preview(fields, logs)}
