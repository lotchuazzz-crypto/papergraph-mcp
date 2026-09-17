from pathlib import Path

import pytest

from papergraph.workspace import Workspace
from tests.test_reference_search import provider_result
from tests.test_workspace_paper_map import import_paper_map_pdf
from tests.test_workspace_reference_resolution import (
    import_missing_reference_pdf,
    write_target_pdf,
)


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
        assert report["evidence_triage"]["triage_schema_version"] == 1
        assert report["evidence_triage"]["candidate_starting_point"]["label"] == (
            "automatic candidate"
        )
        assert report["sections"][0]["id"] == "paper"
        assert report["warnings"] == report["paper_map"]["evidence_quality"]["warnings"]
        markdown = report["markdown"]
        assert markdown.startswith("# Reading Report:")
        assert "## Paper" in markdown
        assert "## Paper Map" in markdown
        assert "## Evidence Triage" in markdown
        assert "Candidate starting point" in markdown
        assert "## Main-Result Candidates" in markdown
        assert "result text contains a main-result cue" in markdown
        assert "## Candidate Reading Route" in markdown
        assert "## Supported Local Logic Chain" in markdown
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


def test_reading_report_includes_resolved_reference_summary(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]
        workspace.resolve_external_reference(
            "local:paper",
            blocked["blocked_id"],
            {
                "kind": "doi",
                "doi": "10.1000/example",
                "title": "Published target",
            },
        )

        report = workspace.export_paper_reading_report("local:paper")

        assert report["reference_resolutions"]["summary"][
            "resolved_not_imported_count"
        ] == 1
        assert report["evidence_triage"]["resolved_external_references"][
            "resolved_not_imported_count"
        ] == 1
        assert "### Resolved External References" in report["markdown"]
        assert "Resolved, not imported" in report["markdown"]
        assert "10.1000/example" in report["markdown"]
    finally:
        workspace.close()


def test_reading_report_includes_scholarly_reference_search_summary(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]
        workspace.reference_search_provider = lambda query: [
            provider_result(
                "openalex",
                records=[
                    {
                        "kind": "metadata",
                        "title": "Old proceedings note",
                        "authors": ["D. Classic"],
                        "year": "1932",
                        "venue": "Proceedings of the 1932 seminar",
                    }
                ],
            )
        ]
        workspace.search_external_reference("local:paper", blocked["blocked_id"])

        report = workspace.export_paper_reading_report("local:paper")

        assert report["reference_searches"]["summary"]["candidate_count"] == 1
        assert report["evidence_triage"]["scholarly_reference_search"][
            "boundary_count"
        ] == 1
        assert "### Scholarly Reference Candidates" in report["markdown"]
        assert "Old proceedings note" in report["markdown"]
        assert "### Search Boundaries" in report["markdown"]
        assert "The trail stops until the user supplies an importable source" in (
            report["markdown"]
        )
    finally:
        workspace.close()


def test_reading_report_includes_imported_reference_summary(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]
        target_pdf = tmp_path / "target.pdf"
        write_target_pdf(target_pdf)
        workspace.resolve_external_reference(
            "local:paper",
            blocked["blocked_id"],
            {"kind": "pdf", "path": str(target_pdf), "paper_id": "local:ref17"},
        )

        report = workspace.export_paper_reading_report("local:paper")

        assert report["reference_resolutions"]["summary"][
            "resolved_imported_count"
        ] == 1
        assert "Resolved and imported" in report["markdown"]
        assert "local:ref17" in report["markdown"]
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
        assert report["evidence_triage"]["status"] == "needs_manual_review"
        assert report["warnings"][0]["kind"] == "no_results"
        assert "No main-result candidates were found" in report["markdown"]
        assert "No reading route evidence was extracted" in report["markdown"]
        assert "Empty dependencies mean no supported extraction evidence was found" in (
            report["markdown"]
        )
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
