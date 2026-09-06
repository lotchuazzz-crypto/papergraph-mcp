import sqlite3
from pathlib import Path

import fitz
import pytest

from papergraph.workspace import SCHEMA_VERSION, Workspace


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


def import_session_pdf(tmp_path: Path) -> tuple[Path, str]:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_session_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, "local:paper")
    finally:
        workspace.close()
    return workspace_path, "local:paper::pdf:theorem:1.1"


def test_schema_v4_initializes_reading_session_tables(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        assert SCHEMA_VERSION == 4
        tables = {
            row[0]
            for row in workspace._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "reading_sessions",
            "reading_checkpoints",
            "reading_notes",
        } <= tables
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("4",)
    finally:
        workspace.close()


def test_v3_workspace_migrates_to_v4_without_losing_evidence(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    with sqlite3.connect(workspace_path) as connection:
        connection.execute("DROP TABLE reading_notes")
        connection.execute("DROP TABLE reading_checkpoints")
        connection.execute("DROP TABLE reading_sessions")
        connection.execute(
            "UPDATE workspace_meta SET value = '3' WHERE key = 'schema_version'"
        )

    workspace = Workspace.open(workspace_path)
    try:
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("4",)
        assert workspace.get_result(result_id)["result_id"] == result_id
        assert workspace.list_reading_sessions() == []
    finally:
        workspace.close()


def test_create_reading_session_returns_active_session(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        session = workspace.create_reading_session(
            "local:paper",
            target_result_id=result_id,
        )

        assert session["session_id"].startswith("session:local-paper-pdf-theorem-1-1:")
        assert session["paper_id"] == "local:paper"
        assert session["target_result_id"] == result_id
        assert session["label"] == result_id
        assert session["status"] == "active"
        assert session["counts"] == {"checkpoints": 0, "notes": 0}
        assert session["created_at"] == session["updated_at"]
    finally:
        workspace.close()


def test_create_reading_session_validates_target_belongs_to_paper(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        other_pdf = tmp_path / "other.pdf"
        write_session_pdf(other_pdf)
        workspace.import_pdf(other_pdf, "local:other")

        with pytest.raises(ValueError, match="does not belong to paper"):
            workspace.create_reading_session(
                "local:other",
                target_result_id=result_id,
            )
    finally:
        workspace.close()


def test_list_and_get_reading_sessions_are_deterministic(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        first = workspace.create_reading_session("local:paper", label="First pass")
        second = workspace.create_reading_session(
            "local:paper",
            label="Focused proof",
            target_result_id=result_id,
        )

        listed = workspace.list_reading_sessions(paper_id="local:paper")
        assert [session["session_id"] for session in listed] == [
            second["session_id"],
            first["session_id"],
        ]
        full = workspace.get_reading_session(second["session_id"])
        assert full["session"]["session_id"] == second["session_id"]
        assert full["checkpoints"] == []
        assert full["notes"] == []
    finally:
        workspace.close()


def test_record_reading_checkpoint_updates_unique_target(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        session = workspace.create_reading_session(
            "local:paper",
            target_result_id=result_id,
        )

        first = workspace.record_reading_checkpoint(
            session["session_id"],
            "result_id",
            result_id,
            "queued",
            summary="Queued for L3 reading.",
            evidence={"source": "reading_path"},
        )
        second = workspace.record_reading_checkpoint(
            session["session_id"],
            "result_id",
            result_id,
            "reviewed",
            summary="Statement and proof source slice reviewed.",
            evidence={"source_handles": [{"kind": "result_id", "value": result_id}]},
        )

        assert first["checkpoint_id"] == second["checkpoint_id"]
        assert second["status"] == "reviewed"
        assert second["summary"] == "Statement and proof source slice reviewed."
        assert second["evidence"]["source_handles"][0]["value"] == result_id
        full = workspace.get_reading_session(session["session_id"])
        assert full["session"]["counts"] == {"checkpoints": 1, "notes": 0}
        assert full["checkpoints"] == [second]
    finally:
        workspace.close()


def test_record_reading_checkpoint_validates_inputs(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        session = workspace.create_reading_session("local:paper")

        with pytest.raises(ValueError, match="Invalid reading checkpoint status"):
            workspace.record_reading_checkpoint(
                session["session_id"],
                "result_id",
                result_id,
                "done",
            )
        with pytest.raises(ValueError, match="Invalid reading target kind"):
            workspace.record_reading_checkpoint(
                session["session_id"],
                "citation",
                result_id,
                "queued",
            )
        with pytest.raises(KeyError, match="Unknown result id"):
            workspace.record_reading_checkpoint(
                session["session_id"],
                "result_id",
                "local:paper::pdf:theorem:9.9",
                "queued",
            )
    finally:
        workspace.close()


def test_add_reading_note_validates_and_updates_session(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        session = workspace.create_reading_session("local:paper")

        note = workspace.add_reading_note(
            session["session_id"],
            "Does Lemma 1.2 need an external estimate?",
            note_type="question",
            target_kind="result_id",
            target_id=result_id,
        )

        assert note["note_type"] == "question"
        assert note["target_id"] == result_id
        assert note["text"].startswith("Does Lemma 1.2")
        full = workspace.get_reading_session(session["session_id"])
        assert full["session"]["counts"] == {"checkpoints": 0, "notes": 1}
        assert full["notes"] == [note]

        with pytest.raises(ValueError, match="reading note text cannot be empty"):
            workspace.add_reading_note(session["session_id"], " ")
        with pytest.raises(ValueError, match="target_id is required"):
            workspace.add_reading_note(
                session["session_id"],
                "Missing target id.",
                target_kind="result_id",
            )
    finally:
        workspace.close()


def test_export_reading_session_summary_reports_recovery_state(tmp_path: Path):
    workspace_path, result_id = import_session_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        session = workspace.create_reading_session(
            "local:paper",
            label="Main theorem pass",
            target_result_id=result_id,
        )
        workspace.record_reading_checkpoint(
            session["session_id"],
            "result_id",
            result_id,
            "blocked",
            summary="Need to inspect Lemma 1.2 proof.",
        )
        workspace.record_reading_checkpoint(
            session["session_id"],
            "unresolved_stop",
            "local:paper::unresolved:lemma-1.2",
            "queued",
            summary="Resolve local mention.",
        )
        question = workspace.add_reading_note(
            session["session_id"],
            "Is the bootstrap estimate stated before the theorem?",
            note_type="question",
        )

        summary = workspace.export_reading_session_summary(session["session_id"])

        assert summary["session"]["session_id"] == session["session_id"]
        assert summary["paper"]["paper_id"] == "local:paper"
        assert summary["target_result"]["result_id"] == result_id
        assert summary["progress"] == {
            "total_checkpoints": 2,
            "reviewed": 0,
            "blocked": 1,
            "queued": 1,
            "skipped": 0,
        }
        assert summary["blocked_targets"][0]["target_id"] == result_id
        assert summary["open_questions"] == [question]
        assert summary["next_actions"] == [
            "review_blocked_targets",
            "continue_queued_targets",
            "answer_or_retire_open_questions",
        ]
        assert summary["source_policy"]["proof_verification"] is False
    finally:
        workspace.close()
