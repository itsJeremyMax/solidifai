"""Pure build-brief conformance evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

VerificationStatus = Literal["pass", "fail", "unknown", "not_applicable"]
FindingSeverity = Literal["critical", "blocking", "warning", "advisory"]
ReadinessLevel = Literal["ready", "needs_attention", "blocked"]


def _finding(id: str, status: VerificationStatus, severity: FindingSeverity, message: str) -> dict:
    return {"id": id, "status": status, "severity": severity, "message": message}


def _status(value: Any, *, applicable: bool = True) -> VerificationStatus:
    if not applicable:
        return "not_applicable"
    if isinstance(value, Mapping):
        value = value.get("status", value.get("pass"))
    if value in {"pass", "fail", "unknown", "not_applicable"}:
        return value
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "unknown"


def _severity(item: Mapping[str, Any], default: FindingSeverity = "blocking") -> FindingSeverity:
    value = item.get("severity", default)
    return value if value in {"critical", "blocking", "warning", "advisory"} else default


def _evaluate_section(
    findings: list[dict],
    brief: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    section: str,
    prefix: str,
    context_key: str,
    message: str,
    default: FindingSeverity = "blocking",
) -> None:
    statuses = context.get(context_key) or {}
    for item in brief.get(section) or []:
        if not isinstance(item, Mapping):
            continue
        item_id = str(item.get("id", prefix))
        findings.append(
            _finding(
                f"{prefix}:{item_id}",
                _status(
                    statuses.get(item_id), applicable=item.get("applicable", True) is not False
                ),
                _severity(item, default),
                f"{message} {item_id}",
            )
        )


def aggregate_readiness(findings: Sequence[Mapping[str, Any]]) -> dict:
    attention = [
        str(f["id"]) for f in findings if f.get("status") in {"fail", "unknown"} and "id" in f
    ]
    blocked = any(
        f.get("status") in {"fail", "unknown"} and f.get("severity") in {"critical", "blocking"}
        for f in findings
    )
    has_attention = any(f.get("status") in {"fail", "unknown"} for f in findings)
    level: ReadinessLevel = (
        "blocked" if blocked else "needs_attention" if has_attention else "ready"
    )
    return {"level": level, "findingIds": attention}


def evaluate(brief: Mapping[str, Any] | None, context: Mapping[str, Any]) -> dict:
    """Evaluate explicit brief obligations only; absent evidence is never a pass."""
    findings: list[dict] = []
    if not brief:
        findings.append(_finding("brief", "unknown", "blocking", "no build brief recorded"))
        return {"findings": findings, "readiness": aggregate_readiness(findings)}

    _evaluate_section(
        findings,
        brief,
        context,
        section="parts",
        prefix="part",
        context_key="part_status",
        message="part",
    )
    _evaluate_section(
        findings,
        brief,
        context,
        section="features",
        prefix="feature",
        context_key="feature_status",
        message="feature",
    )
    _evaluate_section(
        findings,
        brief,
        context,
        section="dimensions",
        prefix="dimension",
        context_key="dimension_status",
        message="dimension",
    )
    for item in brief.get("dimensions") or []:
        if isinstance(item, Mapping) and item.get("drives"):
            item_id = str(item.get("id", "dimension"))
            findings.append(
                _finding(
                    f"parameter-binding:{item_id}",
                    _status((context.get("parameter_binding_status") or {}).get(item_id)),
                    _severity(item),
                    f"parameter binding {item_id}",
                )
            )
    _evaluate_section(
        findings,
        brief,
        context,
        section="interfaces",
        prefix="interface",
        context_key="interface_status",
        message="interface",
    )
    _evaluate_section(
        findings,
        brief,
        context,
        section="references",
        prefix="reference",
        context_key="reference_status",
        message="reference",
    )

    requirement_results = {
        str(item.get("id")): item
        for item in (context.get("requirements_report") or {}).get("results", [])
        if isinstance(item, Mapping)
    }
    for item in brief.get("requirements") or []:
        if not isinstance(item, Mapping):
            continue
        item_id = str(item.get("id", "requirement"))
        result = requirement_results.get(item_id)
        findings.append(
            _finding(
                f"requirements:{item_id}",
                _status(
                    result.get("pass") if result else None,
                    applicable=item.get("applicable", True) is not False,
                ),
                _severity(item),
                f"requirement {item_id}",
            )
        )
    _evaluate_section(
        findings,
        brief,
        context,
        section="assumptions",
        prefix="assumption",
        context_key="assumption_status",
        message="assumption",
    )
    _evaluate_section(
        findings,
        brief,
        context,
        section="manufacturing",
        prefix="manufacturing",
        context_key="manufacturing_status",
        message="manufacturing",
    )
    for item in brief.get("obligations") or []:
        if not isinstance(item, Mapping):
            continue
        item_id = str(item.get("id", "obligation"))
        prefix = "persistence" if item.get("kind") == "persistence" else "obligation"
        findings.append(
            _finding(
                f"{prefix}:{item_id}",
                _status(
                    (context.get(f"{prefix}_status") or {}).get(item_id),
                    applicable=item.get("applicable", True) is not False,
                ),
                _severity(item),
                f"{prefix} {item_id}",
            )
        )
    return {"findings": findings, "readiness": aggregate_readiness(findings)}
