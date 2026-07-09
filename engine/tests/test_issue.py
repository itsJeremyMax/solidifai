"""report_issue URL builder: field mapping, OS/arch, redaction, length cap."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from solidifai_engine import appinfo, issue


@pytest.fixture(autouse=True)
def _version(monkeypatch):
    monkeypatch.setenv(appinfo.ENV_APP_VERSION, "0.5.0")


def _q(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def test_maps_required_fields_to_form_ids():
    out = issue.build_report_issue(
        {"title": "Cube stays empty", "what_happened": "asked for a 20mm cube; viewport empty"}
    )
    q = _q(out["url"])
    assert q["template"] == "bug_report.yml"
    assert q["title"] == "Cube stays empty"
    assert q["what-happened"] == "asked for a 20mm cube; viewport empty"
    assert q["version"] == "0.5.0"
    assert "issues/new" in out["url"]


def test_optional_steps_and_agent():
    out = issue.build_report_issue(
        {
            "title": "t",
            "what_happened": "w",
            "steps": "1. open\n2. run",
            "agent": "Claude Code",
        }
    )
    q = _q(out["url"])
    assert q["steps"] == "1. open\n2. run"
    assert q["agent"] == "Claude Code"


def test_unknown_agent_is_dropped():
    out = issue.build_report_issue({"title": "t", "what_happened": "w", "agent": "Cursor"})
    assert "agent" not in _q(out["url"])


def test_os_darwin_apple_silicon(monkeypatch):
    monkeypatch.setattr(issue.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(issue.platform, "machine", lambda: "arm64")
    assert issue.os_dropdown() == "macOS (Apple Silicon)"


def test_os_darwin_intel(monkeypatch):
    monkeypatch.setattr(issue.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(issue.platform, "machine", lambda: "x86_64")
    assert issue.os_dropdown() == "macOS (Intel)"


def test_os_windows_and_linux(monkeypatch):
    monkeypatch.setattr(issue.platform, "system", lambda: "Windows")
    assert issue.os_dropdown() == "Windows"
    monkeypatch.setattr(issue.platform, "system", lambda: "Linux")
    assert issue.os_dropdown() == "Linux"


def test_unknown_os_is_omitted(monkeypatch):
    monkeypatch.setattr(issue.platform, "system", lambda: "SunOS")
    assert issue.os_dropdown() is None
    out = issue.build_report_issue({"title": "t", "what_happened": "w"})
    assert "os" not in _q(out["url"])


def test_redacts_home_path():
    assert issue.redact("failed at /Users/jeremy/Code/x.py") == "failed at ~/Code/x.py"
    assert issue.redact("at /home/alice/proj") == "at ~/proj"


def test_redacts_secrets():
    assert "[redacted]" in issue.redact("token=ghp_ABCDEFGHIJKLMNOPQRSTUVWX1234")
    assert "sk-" not in issue.redact("key sk-ABCDEFGHIJKLMNOPQRSTUV")


def test_redaction_applies_to_built_url():
    out = issue.build_report_issue(
        {"title": "t", "what_happened": "crash in /Users/bob/ws/model.py"}
    )
    assert "/Users/bob" not in out["url"]
    assert "%2FUsers%2Fbob" not in out["url"]


def test_length_cap_truncates_context_but_keeps_required(monkeypatch):
    out = issue.build_report_issue({"title": "t", "what_happened": "w", "context": "X" * 40000})
    assert len(out["url"]) <= issue._MAX_URL
    q = _q(out["url"])
    assert q["title"] == "t" and q["what-happened"] == "w" and q["version"] == "0.5.0"
    assert "truncated" in q.get("logs", "")


def test_requires_title_and_what_happened():
    with pytest.raises(ValueError):
        issue.build_report_issue({"title": "", "what_happened": "w"})
    with pytest.raises(ValueError):
        issue.build_report_issue({"title": "t", "what_happened": ""})


def test_preview_is_returned_and_shows_public_fields():
    out = issue.build_report_issue({"title": "Empty viewport", "what_happened": "no cube"})
    assert "Empty viewport" in out["preview"]
    assert "no cube" in out["preview"]
