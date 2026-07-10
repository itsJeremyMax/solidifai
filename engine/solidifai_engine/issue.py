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

# GitHub issue titles are short; cap so a pathological title can't dominate the budget.
_MAX_TITLE = 250
# Free-text fields shortened (in this order) to fit the URL budget. Identity fields
# (template, title, version, os, agent) are never shortened; title is pre-capped above.
_SHRINK_ORDER = ("logs", "steps", "what-happened")

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
_HOME_RE = re.compile(r"(?i)(?:/Users/|/home/|[A-Za-z]:\\Users\\)[A-Za-z0-9._-]+")
_SECRET_RES = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9._\-]{15,}"),
    re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?i)\b(?:authorization|token|api[_-]?key|secret|password)\b\s*[:=]\s*\S+"),
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}"),
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


def _assemble(fields: dict) -> str:
    return f"{NEW_ISSUE}?{urlencode(fields)}"


def _within_budget(fields: dict) -> bool:
    return len(_assemble(fields)) <= _MAX_URL


def _fit_within_budget(fields: dict) -> dict:
    """Shorten free-text fields in priority order until the assembled URL fits the
    budget. Identity fields are untouched, so required context always survives."""
    fields = dict(fields)
    marker = "\n[...truncated]"
    for key in _SHRINK_ORDER:
        if _within_budget(fields):
            break
        if key not in fields:
            continue
        text = fields[key]
        lo, hi, best = 0, len(text), ""
        while lo <= hi:
            mid = (lo + hi) // 2
            cand = text[:mid] + (marker if mid < len(text) else "")
            trial = dict(fields)
            trial[key] = cand
            if len(_assemble(trial)) <= _MAX_URL:
                best, lo = cand, mid + 1
            else:
                hi = mid - 1
        fields[key] = best
    return fields


def _render_preview(fields: dict) -> str:
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
    lines += ["", " | ".join(meta), "", "Logs:", fields.get("logs", "")]
    return "\n".join(lines)


def build_report_issue(params: dict) -> dict:
    """Assemble a prefilled bug-report URL and its human preview. Redacts and
    length-caps unconditionally. Raises ValueError when a required field is empty."""
    title = redact(str(params.get("title", "")).strip())[:_MAX_TITLE]
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
    fields["logs"] = _compose_logs(context, _diagnostics())

    fields = _fit_within_budget(fields)
    return {"url": _assemble(fields), "preview": _render_preview(fields)}
