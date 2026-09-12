import json
from pathlib import Path

import pytest

import papergraph.server as server
from papergraph.workspace import Workspace
from tests.test_workspace_cross_paper_reading_plan import import_arxiv_context_paper
from tests.test_workspace_external_import_planner import import_import_plan_pdf


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def create_cross_paper_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    workspace = Workspace.open(workspace_path)
    try:
        import_import_plan_pdf(workspace, tmp_path)
        import_arxiv_context_paper(workspace, tmp_path)
    finally:
        workspace.close()
    return workspace_path


def test_export_cross_paper_reading_plan_cli_prints_markdown(
    tmp_path: Path,
    capsys,
):
    workspace_path = create_cross_paper_workspace(tmp_path)

    server.main(
        [
            "export-cross-paper-reading-plan",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--paper-id",
            "arxiv:2401.12345",
            "--focus",
            "main",
        ]
    )

    output = capsys.readouterr().out
    assert output.startswith("# Cross-Paper Reading Plan:")
    assert "## Cross-Paper Evidence" in output
    assert "## Next Commands" in output


def test_export_cross_paper_reading_plan_cli_writes_output_file(
    tmp_path: Path,
    capsys,
):
    workspace_path = create_cross_paper_workspace(tmp_path)
    output_path = tmp_path / "cross-paper-plan.md"

    server.main(
        [
            "export-cross-paper-reading-plan",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--paper-id",
            "arxiv:2401.12345",
            "--output",
            str(output_path),
        ]
    )

    payload = read_json(capsys)
    markdown = output_path.read_text(encoding="utf-8")
    assert payload["status"] == "written"
    assert payload["command"] == "export-cross-paper-reading-plan"
    assert payload["paper_ids"] == ["local:paper", "arxiv:2401.12345"]
    assert payload["format"] == "markdown"
    assert payload["output"] == str(output_path)
    assert payload["bytes"] == len(output_path.read_bytes())
    assert payload["plan_schema_version"] == 1
    assert markdown.startswith("# Cross-Paper Reading Plan:")
    assert "PaperGraph does not verify proofs." in markdown


def test_export_cross_paper_reading_plan_cli_reports_invalid_output_path(
    tmp_path: Path,
    capsys,
):
    workspace_path = create_cross_paper_workspace(tmp_path)
    output_path = tmp_path / "missing" / "cross-paper-plan.md"

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "export-cross-paper-reading-plan",
                "--workspace",
                str(workspace_path),
                "--paper-id",
                "local:paper",
                "--paper-id",
                "arxiv:2401.12345",
                "--output",
                str(output_path),
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert payload["command"] == "export-cross-paper-reading-plan"
    assert "Parent directory does not exist" in payload["message"]
