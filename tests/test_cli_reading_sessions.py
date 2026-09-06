import json
from pathlib import Path

import fitz
import pytest

import papergraph.server as server
from papergraph.workspace import Workspace


def write_session_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def create_session_workspace(tmp_path: Path) -> Path:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_session_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
    finally:
        workspace.close()
    return workspace_path


def read_json(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def test_create_reading_session_cli_prints_json(tmp_path: Path, capsys):
    workspace_path = create_session_workspace(tmp_path)

    server.main(
        [
            "create-reading-session",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
            "--label",
            "Main theorem",
            "--target-result-id",
            "local:paper::pdf:theorem:1.1",
        ]
    )

    payload = read_json(capsys)
    assert payload["paper_id"] == "local:paper"
    assert payload["target_result_id"] == "local:paper::pdf:theorem:1.1"
    assert payload["status"] == "active"


def test_reading_session_cli_round_trip(tmp_path: Path, capsys):
    workspace_path = create_session_workspace(tmp_path)
    server.main(
        [
            "create-reading-session",
            "--workspace",
            str(workspace_path),
            "--paper-id",
            "local:paper",
        ]
    )
    session_id = read_json(capsys)["session_id"]

    server.main(
        [
            "record-reading-checkpoint",
            "--workspace",
            str(workspace_path),
            "--session-id",
            session_id,
            "--target-kind",
            "result_id",
            "--target-id",
            "local:paper::pdf:theorem:1.1",
            "--status",
            "reviewed",
            "--summary",
            "Statement checked.",
            "--evidence-json",
            '{"source":"cli"}',
        ]
    )
    checkpoint = read_json(capsys)
    assert checkpoint["status"] == "reviewed"
    assert checkpoint["evidence"] == {"source": "cli"}

    server.main(
        [
            "add-reading-note",
            "--workspace",
            str(workspace_path),
            "--session-id",
            session_id,
            "--text",
            "Check Lemma 1.2 next.",
            "--note-type",
            "question",
        ]
    )
    note = read_json(capsys)
    assert note["note_type"] == "question"

    server.main(
        [
            "get-reading-session",
            "--workspace",
            str(workspace_path),
            "--session-id",
            session_id,
        ]
    )
    full = read_json(capsys)
    assert full["session"]["counts"] == {"checkpoints": 1, "notes": 1}

    server.main(["list-reading-sessions", "--workspace", str(workspace_path)])
    listed = json.loads(capsys.readouterr().out)
    assert [item["session_id"] for item in listed] == [session_id]

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
    assert summary["progress"]["reviewed"] == 1
    assert summary["open_questions"] == [note]


def test_record_reading_checkpoint_cli_reports_malformed_evidence_json(
    tmp_path: Path,
    capsys,
):
    workspace_path = create_session_workspace(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        session_id = workspace.create_reading_session("local:paper")["session_id"]
    finally:
        workspace.close()

    with pytest.raises(SystemExit) as caught:
        server.main(
            [
                "record-reading-checkpoint",
                "--workspace",
                str(workspace_path),
                "--session-id",
                session_id,
                "--target-kind",
                "result_id",
                "--target-id",
                "local:paper::pdf:theorem:1.1",
                "--status",
                "queued",
                "--evidence-json",
                "{not-json",
            ]
        )

    assert caught.value.code == 1
    payload = read_json(capsys)
    assert payload["status"] == "error"
    assert payload["command"] == "record-reading-checkpoint"
    assert "evidence-json" in payload["message"]
