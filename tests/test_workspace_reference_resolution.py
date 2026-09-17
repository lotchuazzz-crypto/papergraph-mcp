from pathlib import Path

import fitz
import pytest

import papergraph.workspace as workspace_module
from papergraph.arxiv import ArxivProject
from papergraph.workspace import Workspace


def write_missing_reference_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Theorem 1.1. Main result.",
        "Proof. By [17, Theorem 2.1].",
        "References",
        "[17] A. Author. Published target. Journal of Examples 2020.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def import_missing_reference_pdf(workspace: Workspace, tmp_path: Path) -> None:
    pdf = tmp_path / "source.pdf"
    write_missing_reference_pdf(pdf)
    workspace.import_pdf(pdf, "local:paper")


def write_target_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Theorem 2.1. Imported target theorem.", fontsize=11)
    document.save(path)
    document.close()


def write_arxiv_target_project(path: Path) -> Path:
    path.mkdir()
    main = path / "main.tex"
    main.write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\newtheorem{theorem}{Theorem}",
                r"\begin{document}",
                r"\begin{theorem}\label{t}",
                "Imported arXiv target theorem.",
                r"\end{theorem}",
                r"\end{document}",
            ]
        ),
        encoding="utf-8",
    )
    return main


def test_resolve_blocked_reference_to_doi_records_not_imported(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]

        result = workspace.resolve_external_reference(
            "local:paper",
            blocked["blocked_id"],
            {
                "kind": "doi",
                "doi": "10.1000/example",
                "title": "Published target",
                "authors": ["Ada Lovelace"],
                "year": "2020",
                "venue": "Journal of Examples",
            },
        )

        assert result["resolution_schema_version"] == 1
        assert result["status"] == "resolved_not_imported"
        assert result["import"] == {
            "attempted": False,
            "paper_id": None,
            "reason": "target_not_importable_without_local_source",
        }
        assert result["source"]["paper_id"] == "local:paper"
        assert result["source"]["blocked_id"] == blocked["blocked_id"]
        assert result["source"]["review"]["citation_keys"] == ["17"]
        assert result["target"] == {
            "kind": "doi",
            "doi": "10.1000/example",
            "title": "Published target",
            "authors": ["Ada Lovelace"],
            "year": "2020",
            "venue": "Journal of Examples",
        }

        listed = workspace.list_external_reference_resolutions("local:paper")
        assert listed["summary"]["resolved_not_imported_count"] == 1
        assert listed["summary"]["resolved_imported_count"] == 0
        assert listed["summary"]["failed_import_count"] == 0
        assert listed["resolutions"][0]["resolution_id"] == result["resolution_id"]
    finally:
        workspace.close()


def test_resolve_blocked_reference_to_pdf_imports_target(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        target_pdf = tmp_path / "target.pdf"
        write_target_pdf(target_pdf)
        blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]

        result = workspace.resolve_external_reference(
            "local:paper",
            blocked["blocked_id"],
            {"kind": "pdf", "path": str(target_pdf), "paper_id": "local:ref17"},
        )

        assert result["status"] == "resolved_imported"
        assert result["import"]["attempted"] is True
        assert result["import"]["paper_id"] == "local:ref17"
        assert workspace.get_paper("local:ref17")["source_type"] == "pdf"
    finally:
        workspace.close()


def test_resolve_blocked_reference_to_arxiv_imports_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        arxiv_main = write_arxiv_target_project(tmp_path / "arxiv-target")

        def prepare(arxiv_id: str, main_file: str | None, refresh: bool):
            assert arxiv_id == "2401.12345v2"
            assert main_file is None
            assert refresh is False
            return ArxivProject("2401.12345v2", arxiv_main.parent, arxiv_main, True)

        monkeypatch.setattr(workspace_module, "prepare_arxiv_project", prepare)
        blocked_id = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0][
            "blocked_id"
        ]

        result = workspace.resolve_external_reference(
            "local:paper",
            blocked_id,
            {"kind": "arxiv", "arxiv_id": "2401.12345v2"},
        )

        assert result["status"] == "resolved_imported"
        assert result["import"]["paper_id"] == "arxiv:2401.12345"
        imported = workspace.get_paper("arxiv:2401.12345")
        assert imported["source_type"] == "arxiv"
        assert imported["source_version"] == "v2"
    finally:
        workspace.close()


def test_resolve_blocked_reference_to_metadata_is_idempotent(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        blocked_id = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0][
            "blocked_id"
        ]
        target = {
            "kind": "metadata",
            "title": "Published target",
            "authors": ["Ada Lovelace", "Emmy Noether"],
            "year": "2020",
            "venue": "Journal of Examples",
        }

        first = workspace.resolve_external_reference("local:paper", blocked_id, target)
        second = workspace.resolve_external_reference("local:paper", blocked_id, target)

        assert second["resolution_id"] == first["resolution_id"]
        listed = workspace.list_external_reference_resolutions()
        assert listed["summary"]["total_count"] == 1
        assert listed["resolutions"][0]["target"]["kind"] == "metadata"
    finally:
        workspace.close()


def test_resolve_blocked_reference_to_url_records_not_imported(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_missing_reference_pdf(workspace, tmp_path)
        blocked_id = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0][
            "blocked_id"
        ]

        result = workspace.resolve_external_reference(
            "local:paper",
            blocked_id,
            {
                "kind": "url",
                "url": "https://publisher.example/paper",
                "title": "Publisher page",
            },
        )

        assert result["status"] == "resolved_not_imported"
        assert result["target"]["url"] == "https://publisher.example/paper"
        assert result["import"]["attempted"] is False
    finally:
        workspace.close()
