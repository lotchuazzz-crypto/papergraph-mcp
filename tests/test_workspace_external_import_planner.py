from pathlib import Path

import fitz
import pytest

from papergraph.project import load_project
from papergraph.workspace import Workspace


def write_import_plan_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
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


def import_import_plan_pdf(workspace: Workspace, tmp_path: Path) -> str:
    pdf = tmp_path / "paper.pdf"
    write_import_plan_pdf(pdf)
    workspace.import_pdf(pdf, "local:paper")
    return "local:paper::pdf:theorem:1.1"


def import_arxiv_target(workspace: Workspace, tmp_path: Path) -> None:
    tex = tmp_path / "target.tex"
    tex.write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\newtheorem{theorem}{Theorem}",
                r"\begin{document}",
                r"\begin{theorem}\label{t}",
                "Imported target theorem.",
                r"\end{theorem}",
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


def test_result_plan_groups_external_mentions_by_arxiv(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result_id = import_import_plan_pdf(workspace, tmp_path)

        plan = workspace.plan_external_imports_for_result(result_id)

        assert plan["plan_schema_version"] == 1
        assert plan["scope"] == {
            "kind": "result_id",
            "value": result_id,
            "paper_id": "local:paper",
            "recursive": True,
        }
        assert plan["summary"]["candidate_count"] == 1
        assert plan["summary"]["import_candidate_count"] == 1
        candidate = plan["candidates"][0]
        assert candidate["candidate_id"] == "external-import:arxiv:2401.12345"
        assert candidate["status"] == "import_candidate"
        assert candidate["source"] == {
            "type": "arxiv",
            "arxiv_id": "2401.12345",
            "arxiv_version": "v2",
            "recommended_paper_id": "arxiv:2401.12345",
        }
        assert {item["kind"] for item in candidate["evidence"]} >= {
            "external_result_mention",
            "citation_mention",
            "bibliography_entry",
        }
        assert plan["summary"]["blocked_count"] == 1
        assert plan["blocked"][0]["reason"] == "missing_arxiv_id"
    finally:
        workspace.close()


def test_result_plan_marks_imported_arxiv_candidates(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result_id = import_import_plan_pdf(workspace, tmp_path)
        import_arxiv_target(workspace, tmp_path)

        candidate = workspace.plan_external_imports_for_result(result_id)[
            "candidates"
        ][0]

        assert candidate["status"] == "already_imported"
        assert candidate["source"]["recommended_paper_id"] == "arxiv:2401.12345"
    finally:
        workspace.close()


def test_queue_plan_uses_saved_queue_caution_items(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result_id = import_import_plan_pdf(workspace, tmp_path)
        queue = workspace.create_reading_queue(result_id)

        plan = workspace.plan_external_imports_for_queue(queue["queue_id"])

        assert plan["scope"] == {
            "kind": "queue_id",
            "value": queue["queue_id"],
            "paper_id": "local:paper",
            "recursive": None,
        }
        assert plan["summary"]["candidate_count"] == 1
        assert plan["summary"]["blocked_count"] == 1
        assert all(
            evidence["source"].startswith(("reading_queue", "result"))
            for candidate in plan["candidates"]
            for evidence in candidate["evidence"]
        )
    finally:
        workspace.close()


def test_paper_plan_includes_citation_evidence_without_queue(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_import_plan_pdf(workspace, tmp_path)

        plan = workspace.plan_external_imports_for_paper("local:paper")

        assert plan["scope"] == {
            "kind": "paper_id",
            "value": "local:paper",
            "paper_id": "local:paper",
            "recursive": None,
        }
        assert plan["candidates"][0]["source"]["arxiv_id"] == "2401.12345"
        assert plan["summary"]["import_candidate_count"] == 1
    finally:
        workspace.close()


def test_plan_rejects_non_boolean_recursive(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result_id = import_import_plan_pdf(workspace, tmp_path)

        with pytest.raises(ValueError, match="recursive must be a boolean"):
            workspace.plan_external_imports_for_result(result_id, recursive="yes")
    finally:
        workspace.close()
