"""Deterministic Markdown cross-paper reading plan assembly."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from papergraph.identity import normalize_paper_id

if TYPE_CHECKING:
    from papergraph.workspace import Workspace


PLAN_SCHEMA_VERSION = 1
MAX_PAPER_COUNT = 8
REQUIRED_BOUNDARIES = [
    "PaperGraph does not verify proofs.",
    "PaperGraph does not infer hidden mathematical prerequisites.",
    "PaperGraph does not perform semantic theorem matching.",
    (
        "Citation evidence does not imply logical dependency unless supported "
        "by reading-path evidence."
    ),
    (
        "Empty cross-paper edges mean no supported extraction evidence was found, "
        "not that no relationship exists."
    ),
]
WARNING_ORDER = {
    "focus_no_match": 0,
    "no_cross_paper_edges": 1,
    "limited_paper": 2,
    "sparse_paper": 3,
    "external_dependencies": 4,
    "unresolved_references": 5,
    "edge_resolution_limited": 6,
}


def build_cross_paper_reading_plan(
    workspace: Workspace,
    paper_ids: list[str],
    focus: str | None = None,
    max_candidates_per_paper: int = 3,
) -> dict[str, Any]:
    """Build a deterministic Markdown reading plan for selected papers."""

    normalized_ids = _validate_paper_ids(workspace, paper_ids)
    max_candidates_per_paper = _validate_max_candidates_per_paper(
        max_candidates_per_paper
    )
    normalized_focus = _normalize_focus(focus)
    paper_maps = [
        workspace.get_paper_map(
            paper_id,
            max_candidates=max_candidates_per_paper,
        )
        for paper_id in normalized_ids
    ]
    papers = _paper_summaries(paper_maps)
    cross_edges = _cross_paper_edges(workspace, normalized_ids)
    external_risks = _external_risks(workspace, normalized_ids, cross_edges)
    recommended_sequence, focus_matched = _recommended_sequence(
        normalized_ids,
        paper_maps,
        cross_edges,
        normalized_focus,
    )
    warnings = _warnings(
        paper_maps,
        cross_edges,
        external_risks,
        normalized_focus,
        focus_matched,
    )
    summary = _summary(
        normalized_ids,
        paper_maps,
        cross_edges,
        external_risks,
        recommended_sequence,
    )
    plan: dict[str, Any] = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "format": "markdown",
        "paper_ids": normalized_ids,
        "focus": normalized_focus,
        "summary": summary,
        "papers": papers,
        "cross_paper_edges": cross_edges,
        "recommended_sequence": recommended_sequence,
        "external_risks": external_risks,
        "warnings": warnings,
        "evidence_boundaries": REQUIRED_BOUNDARIES,
    }
    plan["markdown"] = render_cross_paper_reading_plan_markdown(plan)
    return plan


def render_cross_paper_reading_plan_markdown(
    plan_model: dict[str, Any],
) -> str:
    """Render a cross-paper reading plan payload as Markdown."""

    focus = plan_model.get("focus")
    title = focus or f"{len(plan_model['paper_ids'])} papers"
    summary = plan_model["summary"]
    lines = [
        f"# Cross-Paper Reading Plan: {_text(title)}",
        "",
        "## Scope",
        "",
        f"- Paper count: {summary['paper_count']}",
        f"- Paper IDs: {', '.join(f'`{paper_id}`' for paper_id in plan_model['paper_ids'])}",
        f"- Focus: {_code_or_none(focus)}",
        f"- Plan format: `{plan_model['format']}`",
        f"- Plan schema version: {plan_model['plan_schema_version']}",
        "",
        "## Paper Set",
        "",
    ]
    lines.extend(_render_paper_set(plan_model["papers"]))
    lines.extend(["", "## Recommended Reading Sequence", ""])
    lines.extend(_render_sequence(plan_model["recommended_sequence"]))
    lines.extend(["", "## Cross-Paper Evidence", ""])
    lines.extend(_render_edges(plan_model["cross_paper_edges"]))
    lines.extend(["", "## Per-Paper Main Candidates", ""])
    lines.extend(_render_candidates(plan_model["papers"]))
    lines.extend(["", "## Per-Paper Reading Reports", ""])
    lines.extend(_render_report_commands(plan_model["papers"]))
    lines.extend(["", "## External Reading Risks", ""])
    lines.extend(_render_external_risks(plan_model["external_risks"]))
    lines.extend(["", "## Evidence Quality", ""])
    lines.extend(_render_warnings(plan_model["warnings"], plan_model["papers"]))
    lines.extend(["", "## Evidence Boundaries", ""])
    lines.extend(f"- {boundary}" for boundary in plan_model["evidence_boundaries"])
    lines.extend(["", "## Next Commands", "", "```powershell"])
    start_paper = summary["recommended_start_paper_id"] or plan_model["paper_ids"][0]
    lines.extend(
        [
            f"papergraph-mcp --workspace <WORKSPACE> get-paper-map {start_paper}",
            (
                "papergraph-mcp --workspace <WORKSPACE> "
                f"plan-external-imports-for-paper {start_paper}"
            ),
        ]
    )
    for paper in plan_model["papers"]:
        lines.append(paper["single_paper_report_command"])
    lines.append("```")
    return "\n".join(lines).rstrip() + "\n"


def _validate_paper_ids(workspace: Workspace, paper_ids: list[str]) -> list[str]:
    if not isinstance(paper_ids, list):
        raise ValueError("paper_ids must be a list")
    if not 2 <= len(paper_ids) <= MAX_PAPER_COUNT:
        raise ValueError("paper_ids must contain between 2 and 8 distinct IDs")
    normalized_ids = [normalize_paper_id(paper_id) for paper_id in paper_ids]
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError("paper_ids must be distinct")
    for paper_id in normalized_ids:
        workspace.get_paper(paper_id)
    return normalized_ids


def _validate_max_candidates_per_paper(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_candidates_per_paper must be an integer")
    if not 1 <= value <= 20:
        raise ValueError("max_candidates_per_paper must be between 1 and 20")
    return value


def _normalize_focus(focus: str | None) -> str | None:
    if focus is None:
        return None
    compact = " ".join(str(focus).split())
    return compact or None


def _focus_tokens(focus: str | None) -> set[str]:
    if focus is None:
        return set()
    return {token for token in focus.lower().split() if len(token) >= 3}


def _paper_summaries(paper_maps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    papers = []
    for paper_map in paper_maps:
        paper = paper_map["paper"]
        papers.append(
            {
                "paper_id": paper["paper_id"],
                "title": paper.get("title"),
                "paper_map_summary": paper_map["summary"],
                "paper": paper,
                "main_result_candidates": paper_map["main_result_candidates"],
                "reading_route_preview": paper_map["reading_route"][:5],
                "single_paper_report_command": (
                    "papergraph-mcp --workspace <WORKSPACE> "
                    f"export-paper-reading-report --paper-id {paper['paper_id']}"
                ),
                "warnings": paper_map["evidence_quality"]["warnings"],
            }
        )
    return papers


def _cross_paper_edges(
    workspace: Workspace,
    selected_paper_ids: list[str],
) -> list[dict[str, Any]]:
    selected = set(selected_paper_ids)
    input_index = {paper_id: index for index, paper_id in enumerate(selected_paper_ids)}
    edges_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for source_paper_id in selected_paper_ids:
        for citation in workspace.get_citations(source_paper_id):
            target = citation.get("target_paper_id")
            if target in selected and target != source_paper_id:
                mention_id = (
                    f"citation:{source_paper_id}:{citation.get('citation_key')}"
                )
                edge = {
                    "source_paper_id": source_paper_id,
                    "target_paper_id": target,
                    "kind": "citation_evidence",
                    "citation_key": citation.get("citation_key"),
                    "source_result_id": None,
                    "source_proof_id": None,
                    "mention_id": mention_id,
                    "raw_text": citation.get("command") or citation.get("citation_key"),
                    "evidence": citation,
                }
                edges_by_key[(source_paper_id, target, mention_id)] = edge

        plan = workspace.plan_external_imports_for_paper(source_paper_id)
        for candidate in plan.get("candidates", []):
            target = (candidate.get("source") or {}).get("recommended_paper_id")
            if target in selected and target != source_paper_id:
                edge = _edge_from_import_candidate(source_paper_id, target, candidate)
                edges_by_key[
                    (source_paper_id, target, edge["mention_id"])
                ] = edge

    return sorted(
        edges_by_key.values(),
        key=lambda edge: (
            input_index[edge["source_paper_id"]],
            input_index[edge["target_paper_id"]],
            edge["mention_id"],
        ),
    )


def _edge_from_import_candidate(
    source_paper_id: str,
    target_paper_id: str,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    evidence = candidate.get("evidence") or []
    mention_id = (
        next(
            (
                item.get("evidence_id")
                for item in evidence
                if item.get("kind")
                in {"external_result_mention", "citation_mention"}
                and item.get("evidence_id")
            ),
            None,
        )
        or candidate["candidate_id"]
    )
    review = candidate.get("review") or {}
    citation_keys = review.get("citation_keys") or []
    raw_texts = review.get("raw_texts") or []
    local_result_ids = review.get("local_result_ids") or []
    proof_ids = review.get("proof_ids") or []
    return {
        "source_paper_id": source_paper_id,
        "target_paper_id": target_paper_id,
        "kind": "citation_evidence",
        "citation_key": citation_keys[0] if citation_keys else None,
        "source_result_id": local_result_ids[0] if local_result_ids else None,
        "source_proof_id": proof_ids[0] if proof_ids else None,
        "mention_id": mention_id,
        "raw_text": raw_texts[0] if raw_texts else None,
        "evidence": {
            "source": "external_import_plan",
            "candidate_id": candidate["candidate_id"],
            "status": candidate.get("status"),
            "review": review,
        },
    }


def _external_risks(
    workspace: Workspace,
    selected_paper_ids: list[str],
    cross_edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected = set(selected_paper_ids)
    selected_edge_targets = {
        (edge["source_paper_id"], edge["target_paper_id"]) for edge in cross_edges
    }
    risks = []
    for source_paper_id in selected_paper_ids:
        plan = workspace.plan_external_imports_for_paper(source_paper_id)
        for candidate in plan.get("candidates", []):
            source = candidate.get("source") or {}
            target = source.get("recommended_paper_id")
            if target in selected and (source_paper_id, target) in selected_edge_targets:
                continue
            risks.append(
                {
                    "source_paper_id": source_paper_id,
                    "kind": "external_candidate",
                    "status": candidate.get("status"),
                    "target_paper_id": target,
                    "candidate": candidate,
                }
            )
        for item in plan.get("blocked", []):
            risks.append(
                {
                    "source_paper_id": source_paper_id,
                    "kind": "blocked",
                    "status": "blocked",
                    "target_paper_id": item.get("paper_id"),
                    "candidate": item,
                }
            )
    return risks


def _recommended_sequence(
    paper_ids: list[str],
    paper_maps: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    focus: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    input_index = {paper_id: index for index, paper_id in enumerate(paper_ids)}
    outgoing_edge_sources = {edge["source_paper_id"] for edge in edges}
    candidate_rows = []
    tokens = _focus_tokens(focus)
    for paper_map in paper_maps:
        paper_id = paper_map["paper"]["paper_id"]
        for candidate_index, candidate in enumerate(paper_map["main_result_candidates"]):
            focus_match = _candidate_matches_focus(candidate, tokens)
            candidate_rows.append(
                {
                    "paper_id": paper_id,
                    "candidate": candidate,
                    "candidate_index": candidate_index,
                    "focus_match": focus_match,
                }
            )

    if candidate_rows:
        candidate_rows.sort(
            key=lambda row: (
                not row["focus_match"] if tokens else False,
                row["paper_id"] not in outgoing_edge_sources,
                -int(row["candidate"].get("score") or 0),
                input_index[row["paper_id"]],
                _source_position(row["candidate"].get("source_span")),
                row["candidate"]["result_id"],
            )
        )
        start_row = candidate_rows[0]
        focus_matched = any(row["focus_match"] for row in candidate_rows) if tokens else False
    else:
        start_row = None
        focus_matched = False

    sequence = []
    included: set[str] = set()
    if start_row is not None:
        paper_id = start_row["paper_id"]
        candidate = start_row["candidate"]
        sequence.append(
            {
                "position": 1,
                "paper_id": paper_id,
                "result_id": candidate["result_id"],
                "role": "start",
                "reason": "selected_main_candidate",
                "evidence": {
                    "source": "paper_map.main_result_candidates",
                    "score": candidate.get("score"),
                    "focus": focus,
                    "focus_match": bool(tokens and start_row["focus_match"]),
                },
            }
        )
        included.add(paper_id)

    for edge in edges:
        if edge["target_paper_id"] not in included:
            sequence.append(
                {
                    "position": len(sequence) + 1,
                    "paper_id": edge["target_paper_id"],
                    "result_id": None,
                    "role": "context",
                    "reason": "selected_paper_citation",
                    "evidence": {
                        "source": "cross_paper_edges",
                        "source_paper_id": edge["source_paper_id"],
                        "mention_id": edge["mention_id"],
                    },
                }
            )
            included.add(edge["target_paper_id"])

    for paper_map in paper_maps:
        paper_id = paper_map["paper"]["paper_id"]
        if paper_id in included:
            continue
        candidates = paper_map["main_result_candidates"]
        sequence.append(
            {
                "position": len(sequence) + 1,
                "paper_id": paper_id,
                "result_id": candidates[0]["result_id"] if candidates else None,
                "role": "continue" if candidates else "review",
                "reason": "input_order",
                "evidence": {"source": "paper_ids.input_order"},
            }
        )
        included.add(paper_id)

    return sequence, focus_matched


def _candidate_matches_focus(candidate: dict[str, Any], tokens: set[str]) -> bool:
    if not tokens:
        return False
    haystack = " ".join(
        [
            str(candidate.get("label") or ""),
            str(candidate.get("title") or ""),
            str(candidate.get("statement_preview") or ""),
            " ".join(
                str(reason.get("evidence") or "")
                for reason in candidate.get("reasons", [])
            ),
        ]
    ).lower()
    return all(token in haystack for token in tokens)


def _summary(
    paper_ids: list[str],
    paper_maps: list[dict[str, Any]],
    cross_edges: list[dict[str, Any]],
    external_risks: list[dict[str, Any]],
    sequence: list[dict[str, Any]],
) -> dict[str, Any]:
    statuses = [paper_map["summary"]["evidence_status"] for paper_map in paper_maps]
    if any(status == "usable" for status in statuses):
        status = "usable"
    elif any(status == "sparse" for status in statuses):
        status = "sparse"
    else:
        status = "limited"
    start = sequence[0] if sequence else {}
    return {
        "paper_count": len(paper_ids),
        "recommended_start_paper_id": start.get("paper_id"),
        "recommended_start_result_id": start.get("result_id"),
        "main_candidate_count": sum(
            len(paper_map["main_result_candidates"]) for paper_map in paper_maps
        ),
        "cross_paper_edge_count": len(cross_edges),
        "external_risk_count": sum(
            1 for risk in external_risks if risk["kind"] == "external_candidate"
        ),
        "unresolved_risk_count": sum(
            1 for risk in external_risks if risk["kind"] == "blocked"
        ),
        "evidence_status": status,
    }


def _warnings(
    paper_maps: list[dict[str, Any]],
    cross_edges: list[dict[str, Any]],
    external_risks: list[dict[str, Any]],
    focus: str | None,
    focus_matched: bool,
) -> list[dict[str, Any]]:
    warnings = []
    if focus and not focus_matched:
        warnings.append(
            {
                "kind": "focus_no_match",
                "message": "Focus text did not match extracted candidate evidence.",
                "evidence": {"focus": focus},
            }
        )
    if not cross_edges:
        warnings.append(
            {
                "kind": "no_cross_paper_edges",
                "message": (
                    "No selected-paper citation edge was extracted between "
                    "the selected papers."
                ),
                "evidence": {"edge_count": 0},
            }
        )
    sparse_ids = [
        paper_map["paper"]["paper_id"]
        for paper_map in paper_maps
        if paper_map["summary"]["evidence_status"] == "sparse"
    ]
    limited_ids = [
        paper_map["paper"]["paper_id"]
        for paper_map in paper_maps
        if paper_map["summary"]["evidence_status"] == "limited"
    ]
    if limited_ids:
        warnings.append(
            {
                "kind": "limited_paper",
                "message": "One or more selected papers has limited evidence.",
                "evidence": {"paper_ids": limited_ids},
            }
        )
    if sparse_ids:
        warnings.append(
            {
                "kind": "sparse_paper",
                "message": "One or more selected papers has sparse evidence.",
                "evidence": {"paper_ids": sparse_ids},
            }
        )
    external_count = sum(
        1 for risk in external_risks if risk["kind"] == "external_candidate"
    )
    blocked_count = sum(1 for risk in external_risks if risk["kind"] == "blocked")
    if external_count:
        warnings.append(
            {
                "kind": "external_dependencies",
                "message": "External import candidates remain outside the selected set.",
                "evidence": {"external_risk_count": external_count},
            }
        )
    if blocked_count:
        warnings.append(
            {
                "kind": "unresolved_references",
                "message": "Unresolved references remain in the selected evidence.",
                "evidence": {"blocked_count": blocked_count},
            }
        )
    warnings.sort(
        key=lambda warning: (
            WARNING_ORDER[warning["kind"]],
            warning["kind"],
            json.dumps(warning.get("evidence"), sort_keys=True),
        )
    )
    return warnings


def _render_paper_set(papers: list[dict[str, Any]]) -> list[str]:
    lines = []
    for paper in papers:
        metadata = paper["paper"]
        summary = paper["paper_map_summary"]
        lines.append(f"- `{paper['paper_id']}`")
        lines.append(f"  - Title: {_text(metadata.get('title') or 'Unknown')}")
        lines.append(f"  - Result count: {metadata['result_count']}")
        lines.append(f"  - Proof count: {metadata['proof_count']}")
        lines.append(f"  - Citation count: {metadata['citation_count']}")
        lines.append(f"  - Evidence status: `{summary['evidence_status']}`")
        lines.append(
            "  - Recommended start result: "
            f"{_code_or_none(summary['recommended_start_result_id'])}"
        )
    return lines


def _render_sequence(sequence: list[dict[str, Any]]) -> list[str]:
    if not sequence:
        return ["No reading sequence could be built from supported evidence."]
    lines = []
    for item in sequence:
        result = f" / `{item['result_id']}`" if item.get("result_id") else ""
        lines.append(
            f"{item['position']}. `{item['paper_id']}`{result} "
            f"{item['role']} - {item['reason']} "
            f"(evidence: {_compact_json(item.get('evidence'))})"
        )
    return lines


def _render_edges(edges: list[dict[str, Any]]) -> list[str]:
    if not edges:
        return [
            (
                "No selected-paper citation edge was extracted between "
                "the selected papers."
            )
        ]
    lines = []
    for edge in edges:
        lines.append(
            f"- `{edge['source_paper_id']}` cites selected paper "
            f"`{edge['target_paper_id']}`."
        )
        lines.append(f"  - Mention: `{edge['mention_id']}`")
        lines.append(f"  - Citation key: {_code_or_none(edge.get('citation_key'))}")
        if edge.get("source_result_id"):
            lines.append(f"  - Source result: `{edge['source_result_id']}`")
        if edge.get("source_proof_id"):
            lines.append(f"  - Source proof: `{edge['source_proof_id']}`")
        if edge.get("raw_text"):
            lines.append(f"  - Raw text: {_text(edge['raw_text'])}")
    return lines


def _render_candidates(papers: list[dict[str, Any]]) -> list[str]:
    lines = []
    for paper in papers:
        lines.append(f"### {_text(paper['paper_id'])}")
        candidates = paper["main_result_candidates"]
        if not candidates:
            lines.append("- No main-result candidates were found.")
            continue
        for candidate in candidates:
            lines.append(
                f"- `{candidate['result_id']}` "
                f"({candidate.get('display_kind') or 'result'}), "
                f"score {candidate.get('score')}"
            )
            if candidate.get("title"):
                lines.append(f"  - Title: {_text(candidate['title'])}")
            for reason in candidate.get("reasons", []):
                lines.append(
                    f"  - `{reason['kind']}` weight {reason['weight']}: "
                    f"{_text(reason['evidence'])}"
                )
    return lines


def _render_report_commands(papers: list[dict[str, Any]]) -> list[str]:
    lines = ["```powershell"]
    lines.extend(paper["single_paper_report_command"] for paper in papers)
    lines.append("```")
    return lines


def _render_external_risks(risks: list[dict[str, Any]]) -> list[str]:
    if not risks:
        return ["No external risks outside the selected set were found."]
    lines = []
    for risk in risks:
        candidate = risk["candidate"]
        if risk["kind"] == "blocked":
            reason = candidate.get("reason") or candidate.get("message") or "blocked"
            lines.append(f"- `{risk['source_paper_id']}` blocked: {_text(reason)}")
            continue
        source = candidate.get("source") or {}
        arxiv_id = source.get("arxiv_id") or risk.get("target_paper_id")
        lines.append(
            f"- `{risk['source_paper_id']}` external candidate: "
            f"{_text(arxiv_id or candidate.get('candidate_id'))}"
        )
        review = candidate.get("review") or {}
        if review.get("citation_keys"):
            lines.append(
                "  - Citation keys: "
                + ", ".join(str(key) for key in review["citation_keys"])
            )
        if review.get("evidence_summary"):
            lines.append(f"  - Review summary: {_text(review['evidence_summary'])}")
    return lines


def _render_warnings(
    warnings: list[dict[str, Any]],
    papers: list[dict[str, Any]],
) -> list[str]:
    lines = []
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning['kind']}`: {_text(warning['message'])}")
            if warning.get("evidence"):
                lines.append(f"  - Evidence: {_compact_json(warning['evidence'])}")
    else:
        lines.append("- No plan-level evidence-quality warnings were produced.")
    for paper in papers:
        for warning in paper["warnings"]:
            lines.append(
                f"- `{paper['paper_id']}` `{warning['kind']}`: "
                f"{_text(warning['message'])}"
            )
    return lines


def _source_position(location: dict[str, Any] | None) -> tuple[int, int, int, str]:
    if not location:
        return (0, 0, 0, "")
    return (
        int(location.get("page") or 0),
        int(location.get("block_index") or 0),
        int(location.get("start_offset") or 0),
        str(location.get("span_id") or ""),
    )


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
