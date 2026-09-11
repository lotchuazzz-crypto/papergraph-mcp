import json
from pathlib import Path

import pytest

import papergraph.server as server
from tests.test_cli_paper_map import create_paper_map_workspace


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_export_paper_reading_report_cli_prints_markdown(tmp_path: Path, capsys):
    workspace_path = create_paper_map_workspace(tmp_path)

    server.main(
        [
            "export-paper-reading-report",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--max-candidates",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert output.startswith("# Reading Report:")
    assert "## Main-Result Candidates" in output
    assert "## Next Commands" in output


def test_export_paper_reading_report_cli_writes_output_file(
    tmp_path: Path,
    capsys,
):
    workspace_path = create_paper_map_workspace(tmp_path)
    output_path = tmp_path / "report.md"

    server.main(
        [
            "export-paper-reading-report",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--output",
            str(output_path),
        ]
    )

    payload = read_json(capsys)
    markdown = output_path.read_text(encoding="utf-8")
    assert payload["status"] == "written"
    assert payload["command"] == "export-paper-reading-report"
    assert payload["paper_id"] == "local:paper"
    assert payload["format"] == "markdown"
    assert payload["output"] == str(output_path)
    assert payload["bytes"] == len(output_path.read_bytes())
    assert payload["report_schema_version"] == 1
    assert markdown.startswith("# Reading Report:")
    assert "PaperGraph does not verify proofs." in markdown


def test_export_paper_reading_report_cli_reports_invalid_output_path(
    tmp_path: Path,
    capsys,
):
    workspace_path = create_paper_map_workspace(tmp_path)
    output_path = tmp_path / "missing" / "report.md"

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "export-paper-reading-report",
                "--workspace",
                str(workspace_path),
                "--paper-id",
                "local:paper",
                "--output",
                str(output_path),
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert payload["command"] == "export-paper-reading-report"
    assert "Parent directory does not exist" in payload["message"]
