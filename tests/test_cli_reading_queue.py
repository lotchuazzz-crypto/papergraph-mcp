import json
from pathlib import Path

import fitz
import pytest

import papergraph.server as server
from papergraph.workspace import Workspace


def write_queue_pdf(path: Path) -> None:
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


def create_queue_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_queue_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
    finally:
        workspace.close()
    return workspace_path


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_create_reading_queue_cli_prints_json(tmp_path: Path, capsys):
    workspace_path = create_queue_workspace(tmp_path)

    server.main(
        [
            "create-reading-queue",
            "--workspace",
            str(workspace_path),
            "--result-id",
            "local:paper::pdf:theorem:1.1",
            "--label",
            "Main theorem queue",
        ]
    )

    payload = read_json(capsys)
    assert payload["paper_id"] == "local:paper"
    assert payload["target_result_id"] == "local:paper::pdf:theorem:1.1"
    assert payload["status"] == "active"
    assert payload["counts"] == {"items": 5}


def test_reading_queue_cli_round_trip(tmp_path: Path, capsys):
    workspace_path = create_queue_workspace(tmp_path)
    server.main(
        [
            "create-reading-queue",
            "--workspace",
            str(workspace_path),
            "--result-id",
            "local:paper::pdf:theorem:1.1",
        ]
    )
    queue_id = read_json(capsys)["queue_id"]

    server.main(["list-reading-queues", "--workspace", str(workspace_path)])
    listed = json.loads(capsys.readouterr().out)
    assert [item["queue_id"] for item in listed] == [queue_id]

    server.main(
        [
            "get-reading-queue",
            "--workspace",
            str(workspace_path),
            "--queue-id",
            queue_id,
        ]
    )
    full = read_json(capsys)
    assert full["queue"]["counts"] == {"items": 5}
    assert full["items"][0]["target_kind"] == "result_id"

    server.main(
        [
            "create-reading-session",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--target-result-id",
            "local:paper::pdf:theorem:1.1",
        ]
    )
    session_id = read_json(capsys)["session_id"]

    server.main(
        [
            "apply-reading-queue-to-session",
            "--workspace",
            str(workspace_path),
            "--queue-id",
            queue_id,
            "--session-id",
            session_id,
        ]
    )
    applied = read_json(capsys)
    assert len(applied["applied"]) == 5

    server.main(
        [
            "export-reading-session-summary",
            "--workspace",
            str(workspace_path),
            "--session-id",
            session_id,
        ]
    )
    summary = read_json(capsys)
    assert summary["progress"]["queued"] == 5
    assert summary["next_actions"] == ["continue_queued_targets"]


def test_get_reading_queue_cli_reports_unknown_queue(tmp_path: Path, capsys):
    workspace_path = create_queue_workspace(tmp_path)

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "get-reading-queue",
                "--workspace",
                str(workspace_path),
                "--queue-id",
                "queue:missing",
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert payload["command"] == "get-reading-queue"
    assert "Unknown reading queue id" in payload["message"]
