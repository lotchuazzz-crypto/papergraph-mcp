import json
from pathlib import Path

import pytest

import papergraph.server as server
from tests.test_cli_paper_map import create_paper_map_workspace


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_plan_starter_project_cli_prints_json(tmp_path: Path, capsys):
    server.main(
        [
            "plan-starter-project",
            "--workspace",
            str(tmp_path / "workspace.sqlite3"),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--pdf",
            f"{tmp_path / 'paper.pdf'}=local:paper",
            "--no-queue",
            "--no-session",
        ]
    )

    payload = read_json(capsys)
    assert payload["status"] == "ready"
    assert payload["planned_papers"][0]["paper_id"] == "local:paper"
    assert payload["planned_artifacts"][1]["path"] == "papergraph-starter-manifest.json"


def test_bootstrap_reading_project_cli_writes_artifacts(tmp_path: Path, capsys):
    workspace_path = create_paper_map_workspace(tmp_path)
    artifact_dir = tmp_path / "artifacts"

    server.main(
        [
            "bootstrap-reading-project",
            "--workspace",
            str(workspace_path),
            "--artifact-dir",
            str(artifact_dir),
            "--project-title",
            "CLI starter",
            "--no-queue",
            "--no-session",
        ]
    )

    payload = read_json(capsys)
    assert payload["status"] == "written"
    assert payload["command"] == "bootstrap-reading-project"
    assert (artifact_dir / "START_HERE.md").exists()
    assert (artifact_dir / "papergraph-starter-manifest.json").exists()


def test_plan_starter_project_cli_reports_invalid_input(tmp_path: Path, capsys):
    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "plan-starter-project",
                "--workspace",
                str(tmp_path / "workspace.sqlite3"),
                "--artifact-dir",
                str(tmp_path / "artifacts"),
                "--pdf",
                str(tmp_path / "paper.pdf"),
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert payload["command"] == "plan-starter-project"
    assert "PATH=PAPER_ID" in payload["message"]
