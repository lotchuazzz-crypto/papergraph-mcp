"""Deterministic Markdown reading report assembly."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from papergraph.workspace import Workspace


REPORT_SCHEMA_VERSION = 1
REQUIRED_BOUNDARIES = [
    "PaperGraph does not verify proofs.",
    "PaperGraph does not infer hidden mathematical prerequisites.",
    "PaperGraph does not perform semantic theorem matching.",
    (
        "Empty dependencies mean no supported extraction evidence was found, "
        "not that no mathematical dependencies exist."
    ),
]


def build_paper_reading_report(
    workspace: Workspace,
    paper_id: str,
    max_candidates: int = 5,
) -> dict[str, Any]:
    """Build a deterministic Markdown reading report for one stored paper."""

    paper_map = workspace.get_paper_map(paper_id, max_candidates=max_candidates)
    summary = {
        "recommended_start_result_id": paper_map["summary"][
            "recommended_start_result_id"
        ],
        "main_candidate_count": paper_map["summary"]["main_candidate_count"],
        "reading_route_count": len(paper_map["reading_route"]),
        "external_risk_count": paper_map["summary"]["external_risk_count"],
        "unresolved_risk_count": paper_map["summary"]["unresolved_risk_count"],
        "evidence_status": paper_map["summary"]["evidence_status"],
    }
    sections = _sections_from_paper_map(paper_map, summary)
    report: dict[str, Any] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "format": "markdown",
        "paper_id": paper_map["paper"]["paper_id"],
        "title": paper_map["paper"].get("title"),
        "summary": summary,
        "sections": sections,
        "warnings": paper_map["evidence_quality"]["warnings"],
        "paper_map": paper_map,
    }
    report["markdown"] = render_paper_reading_report_markdown(report)
    return report


def render_paper_reading_report_markdown(report_model: dict[str, Any]) -> str:
    """Render a report payload as GitHub-flavored Markdown."""

    paper_map = report_model["paper_map"]
    paper = paper_map["paper"]
    summary = report_model["summary"]
    title = report_model.get("title") or report_model["paper_id"]
    lines = [
        f"# Reading Report: {_text(title)}",
        "",
        "## Paper",
        "",
        f"- Paper ID: `{paper['paper_id']}`",
        f"- Source type: `{paper['source_type']}`",
        f"- Title: {_text(paper.get('title') or 'Unknown')}",
        f"- Result count: {paper['result_count']}",
        f"- Proof count: {paper['proof_count']}",
        f"- Citation count: {paper['citation_count']}",
        f"- Report format: `{report_model['format']}`",
        f"- Report schema version: {report_model['report_schema_version']}",
        "",
        "## Paper Map",
        "",
        f"- Recommended start result: {_code_or_none(summary['recommended_start_result_id'])}",
        f"- Evidence status: `{summary['evidence_status']}`",
        f"- Main-result candidates: {summary['main_candidate_count']}",
        f"- Reading route items: {summary['reading_route_count']}",
        f"- External risks: {summary['external_risk_count']}",
        f"- Unresolved risks: {summary['unresolved_risk_count']}",
        "",
        "## Main-Result Candidates",
        "",
    ]
    lines.extend(_render_main_candidates(paper_map["main_result_candidates"]))
    lines.extend(
        [
            "",
            "## Recommended Reading Route",
            "",
        ]
    )
    lines.extend(_render_reading_route(paper_map["reading_route"]))
    lines.extend(
        [
            "",
            "## Local Logic Chain",
            "",
        ]
    )
    lines.extend(_render_logic_chain(paper_map["reading_route"]))
    lines.extend(
        [
            "",
            "## External Reading Risks",
            "",
        ]
    )
    lines.extend(_render_external_risks(paper_map["external_risks"]))
    lines.extend(
        [
            "",
            "## Evidence Quality",
            "",
        ]
    )
    lines.extend(_render_warnings(report_model["warnings"]))
    lines.extend(
        [
            "",
            "## Evidence Boundaries",
            "",
        ]
    )
    lines.extend(f"- {boundary}" for boundary in REQUIRED_BOUNDARIES)
    lines.extend(
        [
            "",
            "## Next Commands",
            "",
            "```powershell",
            (
                "papergraph-mcp --workspace <WORKSPACE> get-paper-map "
                f"{paper['paper_id']}"
            ),
            (
                "papergraph-mcp --workspace <WORKSPACE> create-reading-queue "
                f"{summary['recommended_start_result_id'] or '<RESULT_ID>'}"
            ),
            (
                "papergraph-mcp --workspace <WORKSPACE> "
                f"plan-external-imports-for-paper {paper['paper_id']}"
            ),
            "```",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _sections_from_paper_map(
    paper_map: dict[str, Any],
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {"id": "paper", "title": "Paper", "items": [paper_map["paper"]]},
        {"id": "paper-map", "title": "Paper Map", "items": [summary]},
        {
            "id": "main-result-candidates",
            "title": "Main-Result Candidates",
            "items": paper_map["main_result_candidates"],
        },
        {
            "id": "recommended-reading-route",
            "title": "Recommended Reading Route",
            "items": paper_map["reading_route"],
        },
        {
            "id": "external-reading-risks",
            "title": "External Reading Risks",
            "items": [paper_map["external_risks"]],
        },
        {
            "id": "evidence-quality",
            "title": "Evidence Quality",
            "items": paper_map["evidence_quality"]["warnings"],
        },
        {
            "id": "evidence-boundaries",
            "title": "Evidence Boundaries",
            "items": REQUIRED_BOUNDARIES,
        },
    ]


def _render_main_candidates(candidates: list[dict[str, Any]]) -> list[str]:
    if not candidates:
        return ["No main-result candidates were found from supported evidence."]
    lines: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        heading_parts = [
            f"{index}. `{candidate['result_id']}`",
            str(candidate.get("display_kind") or "result"),
        ]
        if candidate.get("title"):
            heading_parts.append(f"- {_text(candidate['title'])}")
        lines.append(" ".join(heading_parts))
        lines.append(f"   - Score: {candidate['score']}")
        if candidate.get("statement_preview"):
            lines.append(f"   - Statement: {_text(candidate['statement_preview'])}")
        lines.append("   - Reasons:")
        for reason in candidate["reasons"]:
            lines.append(
                "     - "
                f"`{reason['kind']}` weight {reason['weight']}: "
                f"{_text(reason['evidence'])}"
            )
    return lines


def _render_reading_route(route: list[dict[str, Any]]) -> list[str]:
    if not route:
        return ["No reading route evidence was extracted for this paper."]
    lines = []
    for item in route:
        evidence = _compact_json(item.get("evidence"))
        lines.append(
            f"{item['position']}. `{item['target_id']}` "
            f"{item['priority']} - {item['reason']} "
            f"({item['target_kind']}; evidence: {evidence})"
        )
    return lines


def _render_logic_chain(route: list[dict[str, Any]]) -> list[str]:
    dependencies = [
        item for item in route if item["reason"] in {"local_dependency", "proof_evidence"}
    ]
    if not dependencies:
        return [
            "No local dependency evidence was extracted for the recommended route."
        ]
    lines = []
    for item in dependencies:
        evidence = item.get("evidence") or {}
        source = evidence.get("source", "reading_route")
        result_id = evidence.get("result_id") or item["target_id"]
        lines.append(
            f"- `{result_id}` uses local evidence involving `{item['target_id']}` "
            f"from `{source}`."
        )
    return lines


def _render_external_risks(external_risks: dict[str, Any]) -> list[str]:
    summary = external_risks.get("summary", {})
    lines = [
        f"- Import candidates: {summary.get('import_candidate_count', 0)}",
        f"- Already imported: {summary.get('already_imported_count', 0)}",
        f"- Blocked items: {summary.get('blocked_count', 0)}",
    ]
    candidates = external_risks.get("candidates", [])
    if candidates:
        for candidate in candidates:
            source = candidate.get("source") or {}
            arxiv_id = (
                candidate.get("arxiv_id")
                or source.get("arxiv_id")
                or candidate.get("paper_id")
            )
            if arxiv_id:
                lines.append(f"- Review candidate: arXiv:{arxiv_id}")
            review = candidate.get("review") or {}
            if review.get("citation_keys"):
                keys = ", ".join(str(key) for key in review["citation_keys"])
                lines.append(f"  - Citation keys: {keys}")
            snippets = review.get("cited_result_snippets") or review.get("raw_texts")
            if snippets:
                lines.append("  - Cited-result snippets:")
                for snippet in snippets:
                    lines.append(f"    - {_text(snippet)}")
            if review.get("evidence_summary"):
                lines.append(f"  - Review summary: {_text(review['evidence_summary'])}")
    else:
        lines.append("- No external import candidates were found.")

    already_imported = external_risks.get("already_imported", [])
    for item in already_imported:
        lines.append(f"- Already imported: `{item.get('paper_id')}`")

    blocked = external_risks.get("blocked", [])
    for item in blocked:
        lines.append(
            "- Blocked: "
            f"{_text(item.get('reason') or item.get('message') or _compact_json(item))}"
        )
    return lines


def _render_warnings(warnings: list[dict[str, Any]]) -> list[str]:
    if not warnings:
        return ["No evidence-quality warnings were produced."]
    lines = []
    for warning in warnings:
        lines.append(f"- `{warning['kind']}`: {_text(warning['message'])}")
        if warning.get("evidence"):
            lines.append(f"  - Evidence: {_compact_json(warning['evidence'])}")
    return lines


def _compact_json(value: Any) -> str:
    if value is None:
        return "`None`"
    return "`" + json.dumps(value, sort_keys=True, ensure_ascii=False) + "`"


def _code_or_none(value: str | None) -> str:
    if value is None:
        return "`None`"
    return f"`{value}`"


def _text(value: Any) -> str:
    compact = " ".join(str(value).split())
    return (
        compact.replace("\\", "\\\\")
        .replace("`", "\\`")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )
