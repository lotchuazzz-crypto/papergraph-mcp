from papergraph.evidence_triage import (
    build_evidence_triage,
    render_evidence_triage_markdown,
)


def sparse_paper_map() -> dict:
    return {
        "paper": {
            "paper_id": "local:paper",
            "result_count": 29,
            "proof_count": 3,
            "citation_count": 8,
        },
        "summary": {
            "recommended_start_result_id": "local:paper::corollary:2.7",
            "evidence_status": "limited",
            "external_risk_count": 2,
            "unresolved_risk_count": 2,
        },
        "main_result_candidates": [
            {
                "result_id": "local:paper::corollary:2.7",
                "display_kind": "corollary",
                "score": 5,
                "reasons": [{"kind": "paper_map_score", "evidence": "candidate"}],
            }
        ],
        "reading_route": [
            {
                "position": 1,
                "target_id": "local:paper::lemma:2.6",
                "target_kind": "result",
                "priority": "read",
                "reason": "local_dependency",
                "evidence": {
                    "result_id": "local:paper::lemma:4.3",
                    "source": "proof",
                    "snippet": "By Lemma 2.6 (2)",
                },
            }
        ],
        "external_risks": {
            "summary": {
                "import_candidate_count": 0,
                "already_imported_count": 0,
                "blocked_count": 2,
            },
            "blocked": [
                {
                    "citation_key": "17",
                    "location": "Lemma 3.1 proof",
                    "reason": "missing_arxiv_id",
                },
                {
                    "citation_key": "3",
                    "location": "Lemma 5.5 proof",
                    "reason": "missing_arxiv_id",
                },
            ],
        },
        "evidence_quality": {
            "warnings": [
                {
                    "kind": "sparse_proof_evidence",
                    "message": "Several theorem-like results have sparse proof evidence.",
                }
            ]
        },
    }


def test_triage_reports_sparse_dependencies_and_supported_chain():
    triage = build_evidence_triage(sparse_paper_map())

    assert triage["triage_schema_version"] == 1
    assert triage["paper_id"] == "local:paper"
    assert triage["status"] == "external_blocked"
    assert triage["counts"]["results_total"] == 29
    assert triage["counts"]["local_dependency_edge_count"] == 1
    assert triage["supported_local_chains"] == [
        {
            "source_result_id": "local:paper::lemma:4.3",
            "target_result_id": "local:paper::lemma:2.6",
            "evidence": "By Lemma 2.6 (2)",
        }
    ]


def test_triage_labels_candidate_start_without_mathematical_recommendation():
    triage = build_evidence_triage(sparse_paper_map())

    assert triage["candidate_starting_point"] == {
        "result_id": "local:paper::corollary:2.7",
        "label": "automatic candidate",
        "caution": "This is not a claim that the result is mathematically central.",
    }
    rendered = "\n".join(render_evidence_triage_markdown(triage))
    assert "Candidate starting point" in rendered
    assert "automatic candidate" in rendered
    assert "Recommended start result" not in rendered
    assert "main theorem" not in rendered.lower()


def test_triage_renders_external_blockers_as_user_actions():
    triage = build_evidence_triage(sparse_paper_map())

    assert [
        (blocker["citation_key"], blocker["reason"], blocker["next_action"])
        for blocker in triage["external_blockers"]
    ] == [
        (
            "17",
            "missing_arxiv_id",
            "Provide an arXiv ID, local file, or full bibliographic target before import.",
        ),
        (
            "3",
            "missing_arxiv_id",
            "Provide an arXiv ID, local file, or full bibliographic target before import.",
        ),
    ]
    rendered = "\n".join(render_evidence_triage_markdown(triage))
    assert "Resolve blocked citation `17`" in rendered
    assert "Resolve blocked citation `3`" in rendered


def test_triage_summarizes_resolved_external_references():
    triage = build_evidence_triage(
        sparse_paper_map(),
        reference_resolutions={
            "summary": {
                "resolved_imported_count": 1,
                "resolved_not_imported_count": 2,
                "failed_import_count": 0,
            }
        },
    )

    assert triage["resolved_external_references"] == {
        "resolved_imported_count": 1,
        "resolved_not_imported_count": 2,
        "failed_import_count": 0,
    }
    rendered = "\n".join(render_evidence_triage_markdown(triage))
    assert "Resolved and imported references: 1" in rendered
    assert "Resolved but not imported references: 2" in rendered


def test_empty_dependencies_keep_scoped_negative_result_warning():
    paper_map = sparse_paper_map()
    paper_map["reading_route"] = []

    triage = build_evidence_triage(paper_map)

    assert triage["counts"]["local_dependency_edge_count"] == 0
    assert {
        "kind": "empty_dependency_scope",
        "message": (
            "Empty dependencies mean no supported extraction evidence was found, "
            "not that no mathematical dependencies exist."
        ),
    } in triage["extraction_limits"]
    rendered = "\n".join(render_evidence_triage_markdown(triage))
    assert "Empty dependencies mean no supported extraction evidence was found" in rendered
    assert "mathematical independence" not in rendered
