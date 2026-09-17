from pathlib import Path

import fitz

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
