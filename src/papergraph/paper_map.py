"""Evidence-first paper overview assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from papergraph.identity import normalize_paper_id

if TYPE_CHECKING:
    from papergraph.workspace import Workspace


MAIN_RESULT_KINDS = {
    "theorem",
    "proposition",
    "corollary",
    "lemma",
    "definition",
}
WARNING_ORDER = {
    "no_results": 0,
    "no_main_candidate": 1,
    "missing_proof": 2,
    "external_dependencies": 3,
    "unresolved_references": 4,
    "sparse_pdf_text": 5,
}
COUNT_TABLES = {
    "proofs",
    "citation_mentions",
}


def build_paper_map(
    workspace: Workspace,
    paper_id: str,
    max_candidates: int = 5,
) -> dict[str, Any]:
    """Build a deterministic overview for one stored paper."""

    max_candidates = _validate_max_candidates(max_candidates)
    normalized_paper_id = normalize_paper_id(paper_id)
    paper = workspace.get_paper(normalized_paper_id)
    results = _list_all_results(workspace, normalized_paper_id)
    proofs_by_result = {
        result["result_id"]: workspace.get_result_proof(result["result_id"])
        for result in results
    }
    candidates = _main_result_candidates(
        workspace,
        results,
        proofs_by_result,
        max_candidates,
    )
    recommended_start = candidates[0]["result_id"] if candidates else None
    reading_route = (
        _reading_route(workspace, recommended_start) if recommended_start else []
    )
    external_risks = workspace.plan_external_imports_for_paper(normalized_paper_id)
    evidence_quality = _evidence_quality(
        paper,
        results,
        candidates,
        proofs_by_result,
        reading_route,
        external_risks,
    )
    structure = _structure(results)
    route_unresolved_count = sum(
        1 for item in reading_route if item["target_kind"] == "unresolved_stop"
    )
    proof_count = _count_rows(workspace, "proofs", normalized_paper_id)
    citation_count = _count_rows(workspace, "citation_mentions", normalized_paper_id)
    return {
        "map_schema_version": 1,
        "paper": {
            "paper_id": paper["paper_id"],
            "source_type": paper["source_type"],
            "title": paper.get("title"),
            "arxiv_id": (
                paper.get("source_ref")
                if paper.get("source_type") == "arxiv"
                else None
            ),
            "result_count": len(results),
            "proof_count": proof_count,
            "citation_count": citation_count,
        },
        "summary": {
            "main_candidate_count": len(candidates),
            "section_count": len(structure["sections"]),
            "external_risk_count": external_risks["summary"][
                "import_candidate_count"
            ],
            "unresolved_risk_count": (
                external_risks["summary"]["blocked_count"] + route_unresolved_count
            ),
            "recommended_start_result_id": recommended_start,
            "evidence_status": evidence_quality["status"],
        },
        "main_result_candidates": candidates,
        "structure": structure,
        "reading_route": reading_route,
        "external_risks": external_risks,
        "evidence_quality": evidence_quality,
    }


def _validate_max_candidates(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("max_candidates must be an integer")
    if not 1 <= value <= 20:
        raise ValueError("max_candidates must be between 1 and 20")
    return value


def _list_all_results(workspace: Workspace, paper_id: str) -> list[dict[str, Any]]:
    rows = workspace._connection.execute(
        """
        SELECT
            results.result_id, results.paper_id, results.local_id,
            results.kind, results.raw_kind, results.display_kind,
            results.normalized_kind, results.label, results.visible_number,
            results.title, results.statement, results.method,
            results.confidence, papers.source_type
        FROM results
        JOIN papers ON papers.paper_id = results.paper_id
        LEFT JOIN result_source_spans
          ON result_source_spans.result_id = results.result_id
         AND result_source_spans.position = 1
        LEFT JOIN source_spans
          ON source_spans.id = result_source_spans.span_id
        WHERE results.paper_id = ?
        ORDER BY
            COALESCE(source_spans.page, 0),
            COALESCE(source_spans.block_index, 0),
            COALESCE(source_spans.start_offset, 0),
            results.result_id
        """,
        (paper_id,),
    ).fetchall()
    return [
        {
            "result_id": row[0],
            "paper_id": row[1],
            "local_id": row[2],
            "kind": row[3],
            "raw_kind": row[4],
            "display_kind": row[5],
            "normalized_kind": row[6],
            "label": row[7],
            "visible_number": row[8],
            "title": row[9],
            "statement": row[10],
            "method": row[11],
            "confidence": row[12],
            "source_type": row[13],
            "first_location": workspace._first_result_location(row[0]),
        }
        for row in rows
    ]


def _main_result_candidates(
    workspace: Workspace,
    results: list[dict[str, Any]],
    proofs_by_result: dict[str, dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    candidates = []
    eligible = [
        result
        for result in results
        if (result.get("normalized_kind") or result.get("display_kind"))
        in MAIN_RESULT_KINDS
    ]
    for index, result in enumerate(eligible):
        candidate = _candidate_for_result(workspace, result, index, proofs_by_result)
        if candidate is not None:
            candidates.append(candidate)

    if not candidates and eligible:
        path = workspace.get_result_reading_path(eligible[0]["result_id"])
        candidate = _candidate_payload(
            eligible[0],
            [
                {
                    "kind": "early_theorem_signal",
                    "weight": 1,
                    "evidence": "fallback to the first theorem-like record",
                }
            ],
            path,
        )
        candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            -candidate["score"],
            _source_position(candidate["source_span"]),
            candidate["result_id"],
        )
    )
    return candidates[:max_candidates]


def _candidate_for_result(
    workspace: Workspace,
    result: dict[str, Any],
    index: int,
    proofs_by_result: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    path = workspace.get_result_reading_path(result["result_id"])
    reasons = _candidate_reasons(result, index, path)
    if not proofs_by_result[result["result_id"]]["known"]:
        reasons = [
            reason
            for reason in reasons
            if reason["kind"] != "proof_dependency_signal"
        ]
    if not reasons:
        return None
    return _candidate_payload(result, reasons, path)


def _candidate_payload(
    result: dict[str, Any],
    reasons: list[dict[str, Any]],
    path: dict[str, Any],
) -> dict[str, Any]:
    score = sum(reason["weight"] for reason in reasons)
    return {
        "result_id": result["result_id"],
        "display_kind": (
            result.get("normalized_kind")
            or result.get("display_kind")
            or result.get("kind")
        ),
        "label": result.get("label"),
        "title": result.get("title") or result.get("visible_number"),
        "statement_preview": _statement_preview(result.get("statement")),
        "score": score,
        "status": "candidate",
        "reasons": reasons,
        "source_span": result.get("first_location"),
        "reading_path": _reading_path_summary(path),
    }


def _candidate_reasons(
    result: dict[str, Any],
    index: int,
    path: dict[str, Any],
) -> list[dict[str, Any]]:
    text = " ".join(
        str(result.get(key) or "")
        for key in ("label", "title", "visible_number", "statement")
    ).lower()
    reasons = []
    if any(
        token in text
        for token in ("main", "principal", "main theorem", "main result")
    ):
        reasons.append(
            {
                "kind": "title_signal",
                "weight": 4,
                "evidence": "result text contains a main-result cue",
            }
        )
    if result.get("label") and any(
        token in str(result["label"]).lower()
        for token in ("main", "principal", "mainthm", "main-theorem")
    ):
        reasons.append(
            {
                "kind": "label_signal",
                "weight": 4,
                "evidence": f"label {result['label']!r} contains a main-result cue",
            }
        )
    if index < 3 and (
        result.get("normalized_kind") or result.get("display_kind")
    ) in {"theorem", "proposition", "corollary", "lemma"}:
        reasons.append(
            {
                "kind": "early_theorem_signal",
                "weight": 2,
                "evidence": (
                    "result appears among the first theorem-like records"
                ),
            }
        )
    if path["top_down"]:
        reasons.append(
            {
                "kind": "proof_dependency_signal",
                "weight": 1,
                "evidence": "reading path evidence is available",
            }
        )
    if path["external_stops"]:
        reasons.append(
            {
                "kind": "citation_risk_signal",
                "weight": 1,
                "evidence": "reading path includes external stops",
            }
        )
    return reasons


def _reading_path_summary(path: dict[str, Any]) -> dict[str, Any]:
    return {
        "local_result_count": len(path["top_down"]),
        "proof_count": len(path["top_down"]),
        "external_stop_count": len(path["external_stops"]),
        "unresolved_stop_count": len(path["unresolved_stops"]),
        "top_down_result_ids": [
            result["result_id"] for result in path["top_down"]
        ],
        "external_stop_ids": [
            stop["mention_id"] for stop in path["external_stops"]
        ],
        "unresolved_stop_ids": [
            f"{stop['result_id']}:{stop['kind']}"
            for stop in path["unresolved_stops"]
        ],
    }


def _reading_route(workspace: Workspace, result_id: str) -> list[dict[str, Any]]:
    path = workspace.get_result_reading_path(result_id)
    route = [
        {
            "position": 1,
            "target_kind": "result_id",
            "target_id": result_id,
            "priority": "start",
            "reason": "selected_main_candidate",
            "evidence": {"source": "paper_map.main_result_candidates"},
        }
    ]
    for result in path["top_down"]:
        proof = workspace.get_result_proof(result["result_id"]).get("known", {}).get(
            "proof"
        )
        if proof:
            route.append(
                {
                    "position": len(route) + 1,
                    "target_kind": "proof_id",
                    "target_id": proof["proof_id"],
                    "priority": "required"
                    if result["result_id"] == result_id
                    else "recommended",
                    "reason": "proof_evidence",
                    "evidence": {
                        "source": "reading_path.top_down",
                        "result_id": result["result_id"],
                    },
                }
            )
        if result["result_id"] != result_id:
            route.append(
                {
                    "position": len(route) + 1,
                    "target_kind": "result_id",
                    "target_id": result["result_id"],
                    "priority": "recommended",
                    "reason": "local_dependency",
                    "evidence": {"source": "reading_path.top_down"},
                }
            )
    for stop in path["external_stops"]:
        route.append(
            {
                "position": len(route) + 1,
                "target_kind": "external_stop",
                "target_id": stop["mention_id"],
                "priority": "caution",
                "reason": "external_risk",
                "evidence": stop,
            }
        )
    for stop in path["unresolved_stops"]:
        route.append(
            {
                "position": len(route) + 1,
                "target_kind": "unresolved_stop",
                "target_id": f"{stop['result_id']}:{stop['kind']}",
                "priority": "caution",
                "reason": "unresolved_reference",
                "evidence": {
                    "source": "reading_path.unresolved_stops",
                    "result_id": stop["result_id"],
                    "kind": stop["kind"],
                    "mention_count": len(stop["mentions"]),
                },
            }
        )
    return route[:20]


def _structure(results: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(results, key=lambda result: _source_position(result["first_location"]))
    return {
        "sections": [],
        "uncategorized_result_ids": [
            result["result_id"] for result in ordered
        ],
        "result_order": [result["result_id"] for result in ordered],
    }


def _evidence_quality(
    paper: dict[str, Any],
    results: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    proofs_by_result: dict[str, dict[str, Any]],
    reading_route: list[dict[str, Any]],
    external_risks: dict[str, Any],
) -> dict[str, Any]:
    warnings = []
    if not results:
        warnings.append(
            {
                "kind": "no_results",
                "message": "No theorem-like results were found for this paper.",
                "evidence": {"paper_id": paper["paper_id"]},
            }
        )
    elif not candidates:
        warnings.append(
            {
                "kind": "no_main_candidate",
                "message": "No main-result candidate had supported heuristic evidence.",
                "evidence": {"result_count": len(results)},
            }
        )

    missing_proofs = [
        result_id
        for result_id, proof_payload in proofs_by_result.items()
        if not proof_payload.get("known")
    ]
    if missing_proofs and candidates:
        warnings.append(
            {
                "kind": "missing_proof",
                "message": "Some theorem-like results have no proof evidence.",
                "evidence": {"result_ids": missing_proofs[:10]},
            }
        )
    if external_risks["summary"]["import_candidate_count"]:
        warnings.append(
            {
                "kind": "external_dependencies",
                "message": "External import candidates are visible from stored evidence.",
                "evidence": {
                    "import_candidate_count": external_risks["summary"][
                        "import_candidate_count"
                    ]
                },
            }
        )
    if external_risks["summary"]["blocked_count"] or any(
        item["target_kind"] == "unresolved_stop" for item in reading_route
    ):
        warnings.append(
            {
                "kind": "unresolved_references",
                "message": "Unresolved references remain in the paper evidence.",
                "evidence": {"blocked_count": external_risks["summary"]["blocked_count"]},
            }
        )

    if not results:
        status = "limited"
    elif any(proof_payload.get("known") for proof_payload in proofs_by_result.values()):
        status = "usable"
    else:
        status = "sparse"

    warnings.sort(key=lambda warning: (WARNING_ORDER[warning["kind"]], warning["kind"]))
    return {
        "status": status,
        "warnings": warnings,
        "boundaries": [
            "Paper Map does not verify proofs.",
            "Paper Map does not infer hidden mathematical prerequisites.",
            (
                "Empty dependencies mean no supported extraction evidence, "
                "not absence of mathematical dependencies."
            ),
        ],
    }


def _count_rows(workspace: Workspace, table: str, paper_id: str) -> int:
    if table not in COUNT_TABLES:
        raise ValueError(f"Unsupported Paper Map count table: {table}")
    row = workspace._connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE paper_id = ?",
        (paper_id,),
    ).fetchone()
    return int(row[0])


def _source_position(location: dict[str, Any] | None) -> tuple[int, int, int, str]:
    if not location:
        return (0, 0, 0, "")
    return (
        int(location.get("page") or 0),
        int(location.get("block_index") or 0),
        int(location.get("start_offset") or 0),
        str(location.get("span_id") or ""),
    )


def _statement_preview(statement: str | None, limit: int = 160) -> str:
    compact = " ".join((statement or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
