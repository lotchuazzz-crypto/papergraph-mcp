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
