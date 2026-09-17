"""Deterministic evidence triage for first-reading artifacts."""

from __future__ import annotations

from typing import Any


TRIAGE_SCHEMA_VERSION = 1
EMPTY_DEPENDENCY_MESSAGE = (
    "Empty dependencies mean no supported extraction evidence was found, "
    "not that no mathematical dependencies exist."
)
EXTERNAL_BLOCKER_ACTION = (
    "Provide an arXiv ID, local file, or full bibliographic target before import."
)
CANDIDATE_CAUTION = (
    "This is not a claim that the result is mathematically central."
)


def build_evidence_triage(
    paper_map: dict[str, Any],
    external_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a small first-reading triage payload from existing evidence."""

    del external_plan
    paper = paper_map.get("paper", {})
    route = paper_map.get("reading_route", [])
    external_risks = paper_map.get("external_risks", {})
    external_summary = external_risks.get("summary", {})
    supported_chains = _supported_local_chains(route)
    local_edge_count = len(supported_chains)
    blocked_count = int(external_summary.get("blocked_count", 0) or 0)
    theorem_like_total = int(paper.get("result_count", 0) or 0)
    status = _status(
        theorem_like_total=theorem_like_total,
        local_edge_count=local_edge_count,
        blocked_count=blocked_count,
        warnings=paper_map.get("evidence_quality", {}).get("warnings", []),
    )
    triage = {
        "triage_schema_version": TRIAGE_SCHEMA_VERSION,
        "paper_id": paper.get("paper_id"),
        "status": status,
        "headline": _headline(status),
        "counts": {
            "results_total": theorem_like_total,
            "theorem_like_total": theorem_like_total,
            "local_dependency_edge_count": local_edge_count,
            "external_candidate_count": int(
                external_summary.get("import_candidate_count", 0) or 0
            ),
            "external_blocked_count": blocked_count,
        },
        "supported_local_chains": supported_chains,
        "candidate_starting_point": _candidate_starting_point(paper_map),
        "extraction_limits": _extraction_limits(local_edge_count),
        "external_blockers": _external_blockers(external_risks.get("blocked", [])),
        "next_actions": [],
    }
    triage["next_actions"] = _next_actions(triage)
    return triage


def render_evidence_triage_markdown(triage: dict[str, Any]) -> list[str]:
    """Render an evidence triage payload as Markdown lines."""

    counts = triage.get("counts", {})
    candidate = triage.get("candidate_starting_point")
    lines = [
        f"- Status: `{triage.get('status', 'needs_manual_review')}`",
        f"- Headline: {_text(triage.get('headline', 'Manual review is needed.'))}",
        f"- Supported local dependency chains: {counts.get('local_dependency_edge_count', 0)}",
        f"- External import blockers: {counts.get('external_blocked_count', 0)}",
    ]
    if candidate:
        lines.append(
            "- Candidate starting point: "
            f"`{candidate['result_id']}` "
            f"({candidate['label']}; {candidate['caution']})"
        )

    lines.extend(["", "### What Is Safe To Use", ""])
    chains = triage.get("supported_local_chains", [])
    if chains:
        for chain in chains:
            lines.append(
                "- PaperGraph found supported local dependency evidence: "
                f"`{chain['source_result_id']}` -> `{chain['target_result_id']}`"
                f" ({_text(chain['evidence'])})."
            )
    else:
        lines.append("- No supported local dependency chain was extracted.")

    lines.extend(["", "### What Needs Review", ""])
    for limit in triage.get("extraction_limits", []):
        lines.append(f"- {_text(limit['message'])}")
    for blocker in triage.get("external_blockers", []):
        lines.append(
            f"- Resolve blocked citation `{blocker['citation_key']}` "
            f"({blocker['reason']}): {blocker['next_action']}"
        )

    lines.extend(["", "### Next Actions", ""])
    actions = triage.get("next_actions", [])
    if not actions:
        lines.append("1. Review the detailed evidence sections before interpreting results.")
    for index, action in enumerate(actions, start=1):
        lines.append(f"{index}. {_text(action['label'])}")
    return lines


def _status(
    *,
    theorem_like_total: int,
    local_edge_count: int,
    blocked_count: int,
    warnings: list[dict[str, Any]],
) -> str:
    if blocked_count:
        return "external_blocked"
    if any("proof" in str(warning.get("kind", "")) for warning in warnings):
        return "proofs_missing_or_fragmentary"
    if theorem_like_total >= 3 and local_edge_count <= 1:
        return "sparse_dependencies"
    if local_edge_count:
        return "usable_with_cautions"
    return "needs_manual_review"


def _headline(status: str) -> str:
    if status == "external_blocked":
        return (
            "External references need user-supplied identifiers before PaperGraph "
            "can import and analyze them."
        )
    if status == "proofs_missing_or_fragmentary":
        return (
            "Proof evidence is missing or fragmentary; use this report as a review map."
        )
    if status == "sparse_dependencies":
        return (
            "Local dependency evidence is sparse; use this report as a review map, "
            "not a complete dependency graph."
        )
    if status == "usable_with_cautions":
        return "Some local evidence is usable, but PaperGraph evidence boundaries still apply."
    return "Manual review is needed before interpreting the extracted evidence."


def _supported_local_chains(route: list[dict[str, Any]]) -> list[dict[str, str]]:
    chains = []
    for item in route:
        if item.get("reason") not in {"local_dependency", "proof_evidence"}:
            continue
        evidence = item.get("evidence") or {}
        chains.append(
            {
                "source_result_id": str(evidence.get("result_id") or item["target_id"]),
                "target_result_id": str(item["target_id"]),
                "evidence": str(
                    evidence.get("snippet")
                    or evidence.get("source")
                    or item.get("reason")
                    or "supported local evidence"
                ),
            }
        )
    return chains


def _candidate_starting_point(paper_map: dict[str, Any]) -> dict[str, str] | None:
    result_id = paper_map.get("summary", {}).get("recommended_start_result_id")
    if not result_id:
        return None
    return {
        "result_id": result_id,
        "label": "automatic candidate",
        "caution": CANDIDATE_CAUTION,
    }


def _extraction_limits(local_edge_count: int) -> list[dict[str, str]]:
    if local_edge_count:
        return []
    return [{"kind": "empty_dependency_scope", "message": EMPTY_DEPENDENCY_MESSAGE}]


def _external_blockers(blocked: list[dict[str, Any]]) -> list[dict[str, str]]:
    blockers = []
    for item in blocked:
        blockers.append(
            {
                "citation_key": str(
                    item.get("citation_key")
                    or item.get("key")
                    or item.get("raw_citation")
                    or "unknown"
                ),
                "location": str(item.get("location") or item.get("result_id") or ""),
                "reason": str(item.get("reason") or item.get("message") or "blocked"),
                "next_action": EXTERNAL_BLOCKER_ACTION,
            }
        )
    return blockers


def _next_actions(triage: dict[str, Any]) -> list[dict[str, str]]:
    actions = []
    chains = triage.get("supported_local_chains", [])
    if chains:
        chain = chains[0]
        actions.append(
            {
                "kind": "read_supported_chain",
                "label": (
                    f"Read {chain['target_result_id']} before "
                    f"{chain['source_result_id']}."
                ),
            }
        )
    else:
        actions.append(
            {
                "kind": "manual_review",
                "label": (
                    "Review theorem-like statements manually before treating the "
                    "dependency graph as complete."
                ),
            }
        )
    for blocker in triage.get("external_blockers", []):
        actions.append(
            {
                "kind": "resolve_external_blocker",
                "label": (
                    f"Resolve blocked citation [{blocker['citation_key']}] before "
                    "importing external papers."
                ),
            }
        )
    return actions


def _text(value: Any) -> str:
    return " ".join(str(value).split())
