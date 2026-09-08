import json
from pathlib import Path

import fitz
import pytest

import papergraph.server as server
from papergraph.workspace import Workspace


def write_import_plan_pdf(path: Path) -> None:
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


def create_import_plan_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_import_plan_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
        workspace.create_reading_queue("local:paper::pdf:theorem:1.1")
    finally:
        workspace.close()
    return workspace_path


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_plan_external_imports_for_result_cli_prints_json(tmp_path: Path, capsys):
    workspace_path = create_import_plan_workspace(tmp_path)

    server.main(
        [
            "plan-external-imports-for-result",
            "--workspace",
            str(workspace_path),
            "--result-id",
            "local:paper::pdf:theorem:1.1",
        ]
    )

    payload = read_json(capsys)
    assert payload["scope"]["kind"] == "result_id"
    assert payload["candidates"][0]["source"]["arxiv_id"] == "2401.12345"


def test_external_import_planner_cli_round_trip(tmp_path: Path, capsys):
    workspace_path = create_import_plan_workspace(tmp_path)

    server.main(["list-reading-queues", "--workspace", str(workspace_path)])
    queue_id = json.loads(capsys.readouterr().out)[0]["queue_id"]

    server.main(
        [
            "plan-external-imports-for-queue",
            "--workspace",
            str(workspace_path),
            "--queue-id",
            queue_id,
        ]
    )
    queue_plan = read_json(capsys)
    assert queue_plan["summary"]["candidate_count"] == 1

    server.main(
        [
            "plan-external-imports-for-paper",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
        ]
    )
    paper_plan = read_json(capsys)
    assert paper_plan["scope"]["kind"] == "paper_id"
    assert paper_plan["summary"]["import_candidate_count"] == 1


def test_plan_external_imports_cli_reports_unknown_queue(tmp_path: Path, capsys):
    workspace_path = create_import_plan_workspace(tmp_path)

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "plan-external-imports-for-queue",
                "--workspace",
                str(workspace_path),
                "--queue-id",
                "queue:missing",
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert payload["command"] == "plan-external-imports-for-queue"
    assert "Unknown reading queue id" in payload["message"]
