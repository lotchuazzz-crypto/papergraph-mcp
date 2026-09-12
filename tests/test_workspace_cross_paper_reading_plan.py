from pathlib import Path

import pytest

from papergraph.project import load_project
from papergraph.workspace import Workspace
from tests.test_workspace_external_import_planner import import_import_plan_pdf
from tests.test_workspace_paper_map import import_paper_map_pdf


def import_arxiv_context_paper(workspace: Workspace, tmp_path: Path) -> None:
    tex = tmp_path / "context.tex"
    tex.write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\newtheorem{theorem}{Theorem}",
                r"\begin{document}",
                r"\begin{theorem}\label{main}",
                "Context fixed point theorem.",
                r"\end{theorem}",
                r"\begin{proof}",
                "This is direct.",
                r"\end{proof}",
                r"\end{document}",
            ]
        ),
        encoding="utf-8",
    )
    workspace.import_project(
        "arxiv:2401.12345",
        "arxiv",
        "2401.12345",
        None,
        load_project(tex),
    )


def insert_empty_paper(workspace: Workspace, paper_id: str) -> None:
    workspace._connection.execute(
        """
        INSERT INTO papers (
            paper_id, source_type, source_ref, source_version, title,
            authors_json, main_file, imported_at, parser_version
        ) VALUES (
            ?, 'pdf', ?, NULL, NULL,
            '[]', ?, '2026-09-12T00:00:00+00:00', 'test'
        )
        """,
        (paper_id, f"{paper_id}.pdf", f"{paper_id}.pdf"),
    )
    workspace._connection.commit()


def test_cross_paper_reading_plan_exports_markdown_payload(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_import_plan_pdf(workspace, tmp_path)
        import_arxiv_context_paper(workspace, tmp_path)

        plan = workspace.export_cross_paper_reading_plan(
            ["local:paper", "arxiv:2401.12345"],
            focus="main result",
            max_candidates_per_paper=2,
        )

        assert plan["plan_schema_version"] == 1
        assert plan["format"] == "markdown"
        assert plan["paper_ids"] == ["local:paper", "arxiv:2401.12345"]
        assert plan["focus"] == "main result"
        assert plan["summary"]["paper_count"] == 2
        assert plan["summary"]["recommended_start_paper_id"] == "local:paper"
        assert plan["summary"]["recommended_start_result_id"]
        assert plan["summary"]["cross_paper_edge_count"] == 1
        assert plan["summary"]["evidence_status"] == "usable"
        assert len(plan["papers"]) == 2
        assert plan["cross_paper_edges"][0]["source_paper_id"] == "local:paper"
        assert (
            plan["cross_paper_edges"][0]["target_paper_id"]
            == "arxiv:2401.12345"
        )
        assert plan["recommended_sequence"][0]["role"] == "start"
        assert (
            plan["recommended_sequence"][0]["reason"]
            == "selected_main_candidate"
        )
        markdown = plan["markdown"]
        assert markdown.startswith("# Cross-Paper Reading Plan:")
        assert "## Paper Set" in markdown
        assert "## Recommended Reading Sequence" in markdown
        assert "## Cross-Paper Evidence" in markdown
        assert (
            "`local:paper` cites selected paper `arxiv:2401.12345`"
            in markdown
        )
        assert "## Per-Paper Reading Reports" in markdown
        assert "export-paper-reading-report" in markdown
        assert "Citation evidence does not imply logical dependency" in markdown
    finally:
        workspace.close()


def test_cross_paper_reading_plan_warns_without_edges(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)
        insert_empty_paper(workspace, "local:empty")

        plan = workspace.export_cross_paper_reading_plan(
            ["local:paper", "local:empty"],
        )

        assert plan["cross_paper_edges"] == []
        assert any(
            warning["kind"] == "no_cross_paper_edges"
            for warning in plan["warnings"]
        )
        assert (
            "No selected-paper citation edge was extracted"
            in plan["markdown"]
        )
    finally:
        workspace.close()


def test_cross_paper_reading_plan_rejects_invalid_inputs(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)
        insert_empty_paper(workspace, "local:empty")

        with pytest.raises(ValueError, match="between 2 and 8"):
            workspace.export_cross_paper_reading_plan(["local:paper"])
        with pytest.raises(ValueError, match="between 2 and 8"):
            workspace.export_cross_paper_reading_plan(
                [f"local:p{index}" for index in range(9)]
            )
        with pytest.raises(ValueError, match="distinct"):
            workspace.export_cross_paper_reading_plan(
                ["local:paper", "local:paper"]
            )
        with pytest.raises(KeyError, match="Unknown paper id"):
            workspace.export_cross_paper_reading_plan(
                ["local:paper", "local:missing"]
            )
        with pytest.raises(ValueError, match="max_candidates_per_paper"):
            workspace.export_cross_paper_reading_plan(
                ["local:paper", "local:empty"],
                max_candidates_per_paper=True,
            )
        with pytest.raises(ValueError, match="between 1 and 20"):
            workspace.export_cross_paper_reading_plan(
                ["local:paper", "local:empty"],
                max_candidates_per_paper=0,
            )
    finally:
        workspace.close()


def test_cross_paper_reading_plan_focus_no_match_warns(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_import_plan_pdf(workspace, tmp_path)
        import_arxiv_context_paper(workspace, tmp_path)

        plan = workspace.export_cross_paper_reading_plan(
            ["local:paper", "arxiv:2401.12345"],
            focus="spectral sheaf",
        )

        assert any(
            warning["kind"] == "focus_no_match"
            for warning in plan["warnings"]
        )
        assert plan["summary"]["recommended_start_paper_id"] == "local:paper"
    finally:
        workspace.close()


def test_cross_paper_reading_plan_includes_sparse_paper(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_paper_map_pdf(workspace, tmp_path)
        insert_empty_paper(workspace, "local:empty")

        plan = workspace.export_cross_paper_reading_plan(
            ["local:paper", "local:empty"],
        )

        empty = next(
            paper for paper in plan["papers"] if paper["paper_id"] == "local:empty"
        )
        assert empty["paper_map_summary"]["evidence_status"] == "limited"
        assert any(
            warning["kind"] == "limited_paper"
            for warning in plan["warnings"]
        )
        assert "`local:empty`" in plan["markdown"]
    finally:
        workspace.close()
