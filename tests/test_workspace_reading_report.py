from pathlib import Path

import pytest

from papergraph.workspace import Workspace
from tests.test_workspace_paper_map import import_paper_map_pdf


def test_reading_report_exports_researcher_markdown(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)

        report = workspace.export_paper_reading_report("local:paper")

        assert report["report_schema_version"] == 1
        assert report["format"] == "markdown"
        assert report["paper_id"] == "local:paper"
        assert report["summary"]["evidence_status"] == "usable"
        assert report["summary"]["main_candidate_count"] >= 1
        assert report["summary"]["reading_route_count"] >= 1
        assert report["sections"][0]["id"] == "paper"
        assert report["warnings"] == report["paper_map"]["evidence_quality"]["warnings"]
        markdown = report["markdown"]
        assert markdown.startswith("# Reading Report:")
        assert "## Paper" in markdown
        assert "## Paper Map" in markdown
        assert "## Main-Result Candidates" in markdown
        assert "result text contains a main-result cue" in markdown
        assert "## Recommended Reading Route" in markdown
        assert "## Local Logic Chain" in markdown
        assert "## External Reading Risks" in markdown
        assert "Review candidate: arXiv:2401.12345" in markdown
        assert "## Evidence Quality" in markdown
        assert "PaperGraph does not verify proofs." in markdown
        assert "## Evidence Boundaries" in markdown
        assert "PaperGraph does not perform semantic theorem matching." in markdown
        assert "## Next Commands" in markdown
    finally:
        workspace.close()


def test_reading_report_respects_max_candidates(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)

        report = workspace.export_paper_reading_report(
            "local:paper",
            max_candidates=1,
        )

        assert len(report["paper_map"]["main_result_candidates"]) == 1
        assert report["summary"]["main_candidate_count"] == 1
    finally:
        workspace.close()


def test_reading_report_exports_sparse_empty_paper(tmp_path: Path):
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

        report = workspace.export_paper_reading_report("local:empty")

        assert report["summary"]["evidence_status"] == "limited"
        assert report["warnings"][0]["kind"] == "no_results"
        assert "No main-result candidates were found" in report["markdown"]
        assert "No reading route evidence was extracted" in report["markdown"]
        assert (
            "PaperGraph does not infer hidden mathematical prerequisites."
            in report["markdown"]
        )
    finally:
        workspace.close()


def test_reading_report_rejects_invalid_max_candidates(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)

        with pytest.raises(ValueError, match="max_candidates must be an integer"):
            workspace.export_paper_reading_report("local:paper", max_candidates=True)
        with pytest.raises(ValueError, match="max_candidates must be between 1 and 20"):
            workspace.export_paper_reading_report("local:paper", max_candidates=0)
    finally:
        workspace.close()


def test_reading_report_rejects_unknown_paper(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        with pytest.raises(KeyError, match="Unknown paper id"):
            workspace.export_paper_reading_report("local:missing")
    finally:
        workspace.close()
