import json
from pathlib import Path

import fitz
import pytest

import papergraph.server as server
from papergraph.workspace import Workspace


def write_paper_map_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Proof. This is direct.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2 and [12, Theorem 3.5].",
        "References",
        "[12] A. Author. Cited paper. arXiv:2401.12345v2.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def create_paper_map_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_paper_map_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
    finally:
        workspace.close()
    return workspace_path


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_get_paper_map_cli_prints_json(tmp_path: Path, capsys):
    workspace_path = create_paper_map_workspace(tmp_path)

    server.main(
        [
            "get-paper-map",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--max-candidates",
            "1",
        ]
    )

    payload = read_json(capsys)
    assert payload["map_schema_version"] == 1
    assert payload["paper"]["paper_id"] == "local:paper"
    assert len(payload["main_result_candidates"]) == 1


def test_get_paper_map_cli_reports_unknown_paper(tmp_path: Path, capsys):
    workspace_path = create_paper_map_workspace(tmp_path)

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "get-paper-map",
                "--workspace",
                str(workspace_path),
                "--paper-id",
                "local:missing",
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert payload["command"] == "get-paper-map"
    assert "Unknown paper id" in payload["message"]
