from pathlib import Path

import fitz
import pytest

from papergraph.workspace import Workspace


def write_paper_map_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Introduction",
        "Lemma 1.2. Base estimate.",
        "Proof. This is direct.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2, Lemma 9.9, and [12, Theorem 3.5].",
        "References",
        "[12] A. Author. Cited paper. arXiv:2401.12345v2.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def import_paper_map_pdf(workspace: Workspace, tmp_path: Path) -> str:
    pdf = tmp_path / "paper-map.pdf"
    write_paper_map_pdf(pdf)
    workspace.import_pdf(pdf, "local:paper")
    return "local:paper::pdf:theorem:1.1"


def test_paper_map_returns_researcher_overview(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result_id = import_paper_map_pdf(workspace, tmp_path)

        paper_map = workspace.get_paper_map("local:paper")

        assert paper_map["map_schema_version"] == 1
        assert paper_map["paper"]["paper_id"] == "local:paper"
        assert paper_map["paper"]["result_count"] == 2
        assert paper_map["paper"]["proof_count"] == 2
        assert paper_map["summary"]["recommended_start_result_id"] == result_id
        assert paper_map["summary"]["main_candidate_count"] >= 1
        assert paper_map["summary"]["external_risk_count"] == 1
        assert paper_map["summary"]["unresolved_risk_count"] == 1
        assert paper_map["summary"]["evidence_status"] == "usable"
        candidate = paper_map["main_result_candidates"][0]
        assert candidate["result_id"] == result_id
        assert candidate["display_kind"] == "theorem"
        assert candidate["status"] == "candidate"
        assert candidate["statement_preview"]
        assert {reason["kind"] for reason in candidate["reasons"]} >= {
            "title_signal",
            "early_theorem_signal",
            "proof_dependency_signal",
            "citation_risk_signal",
        }
        assert candidate["reading_path"]["local_result_count"] == 2
        assert candidate["reading_path"]["external_stop_count"] == 1
        assert candidate["reading_path"]["unresolved_stop_count"] == 1
        assert paper_map["structure"]["result_order"] == [
            "local:paper::pdf:lemma:1.2",
            "local:paper::pdf:theorem:1.1",
        ]
        assert paper_map["reading_route"][0]["target_id"] == result_id
        assert paper_map["reading_route"][0]["priority"] == "start"
        assert any(
            item["target_kind"] == "external_stop" and item["priority"] == "caution"
            for item in paper_map["reading_route"]
        )
        assert paper_map["external_risks"]["candidates"][0]["review"][
            "citation_keys"
        ] == ["12"]
        assert (
            "Paper Map does not verify proofs."
            in paper_map["evidence_quality"]["boundaries"]
        )
    finally:
        workspace.close()


def test_paper_map_respects_max_candidates(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)

        paper_map = workspace.get_paper_map("local:paper", max_candidates=1)

        assert len(paper_map["main_result_candidates"]) == 1
    finally:
        workspace.close()


def test_paper_map_reports_limited_empty_paper(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace._connection.execute(
            """
            INSERT INTO papers (
                paper_id, source_type, source_ref, source_version, title,
                authors_json, main_file, imported_at, parser_version
            ) VALUES (
                'local:empty', 'pdf', 'empty.pdf', NULL, NULL,
                '[]', 'empty.pdf', '2026-09-10T00:00:00+00:00', 'test'
            )
            """
        )
        workspace._connection.commit()

        paper_map = workspace.get_paper_map("local:empty")

        assert paper_map["main_result_candidates"] == []
        assert paper_map["summary"]["recommended_start_result_id"] is None
        assert paper_map["summary"]["evidence_status"] == "limited"
        assert paper_map["evidence_quality"]["warnings"][0]["kind"] == "no_results"
    finally:
        workspace.close()


def test_paper_map_rejects_invalid_max_candidates(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)

        with pytest.raises(ValueError, match="max_candidates must be an integer"):
            workspace.get_paper_map("local:paper", max_candidates=True)
        with pytest.raises(ValueError, match="max_candidates must be between 1 and 20"):
            workspace.get_paper_map("local:paper", max_candidates=0)
        with pytest.raises(ValueError, match="max_candidates must be between 1 and 20"):
            workspace.get_paper_map("local:paper", max_candidates=21)
    finally:
        workspace.close()


def test_paper_map_rejects_unknown_paper(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(KeyError, match="Unknown paper id"):
            workspace.get_paper_map("local:missing")
    finally:
        workspace.close()
