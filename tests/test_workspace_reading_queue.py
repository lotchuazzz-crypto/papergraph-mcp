import sqlite3
from pathlib import Path

import fitz
import pytest

from papergraph.workspace import SCHEMA_VERSION, Workspace


def write_queue_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Proof. This is direct.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2, Lemma 9.9, and [12, Theorem 3.5].",
        "References",
        "[12] A. Author. Cited paper. arXiv:2401.12345v2.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


def import_queue_pdf(tmp_path: Path, paper_id: str = "local:paper") -> tuple[Path, str]:
    workspace_path = tmp_path / f"{paper_id.replace(':', '-')}.sqlite3"
    pdf = tmp_path / f"{paper_id.replace(':', '-')}.pdf"
    write_queue_pdf(pdf)
    workspace = Workspace.open(workspace_path)
    try:
        workspace.import_pdf(pdf, paper_id)
    finally:
        workspace.close()
    return workspace_path, f"{paper_id}::pdf:theorem:1.1"


def test_schema_v5_initializes_reading_queue_tables(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        assert SCHEMA_VERSION == 5
        tables = {
            row[0]
            for row in workspace._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"reading_queues", "reading_queue_items"} <= tables
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("5",)
    finally:
        workspace.close()


def test_v4_workspace_migrates_to_v5_without_losing_session_state(tmp_path: Path):
    workspace_path, result_id = import_queue_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        session = workspace.create_reading_session(
            "local:paper",
            target_result_id=result_id,
        )
    finally:
        workspace.close()

    with sqlite3.connect(workspace_path) as connection:
        connection.execute("DROP TABLE reading_queue_items")
        connection.execute("DROP TABLE reading_queues")
        connection.execute(
            "UPDATE workspace_meta SET value = '4' WHERE key = 'schema_version'"
        )

    workspace = Workspace.open(workspace_path)
    try:
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("5",)
        assert workspace.get_result(result_id)["result_id"] == result_id
        assert workspace.get_reading_session(session["session_id"])["session"][
            "session_id"
        ] == session["session_id"]
        assert workspace.list_reading_queues() == []
    finally:
        workspace.close()


def test_create_reading_queue_orders_targets_by_evidence_path(tmp_path: Path):
    workspace_path, result_id = import_queue_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        queue = workspace.create_reading_queue(
            result_id,
            label="Main theorem queue",
            recursive=True,
        )

        assert queue["queue_id"].startswith("queue:main-theorem-queue:")
        assert queue["paper_id"] == "local:paper"
        assert queue["target_result_id"] == result_id
        assert queue["label"] == "Main theorem queue"
        assert queue["status"] == "active"
        assert queue["counts"] == {"items": 6}

        full = workspace.get_reading_queue(queue["queue_id"])
        items = full["items"]
        assert [
            (item["position"], item["target_kind"], item["target_id"], item["priority"])
            for item in items
        ] == [
            (1, "result_id", "local:paper::pdf:theorem:1.1", "required"),
            (2, "proof_id", "local:paper::proof:2", "required"),
            (3, "result_id", "local:paper::pdf:lemma:1.2", "recommended"),
            (4, "proof_id", "local:paper::proof:1", "recommended"),
            (5, "external_stop", "local:paper::external-mention:1", "caution"),
            (
                6,
                "unresolved_stop",
                "local:paper::pdf:theorem:1.1:local_result_mentions",
                "caution",
            ),
        ]
        assert items[0]["reason"] == "selected_result"
        assert items[4]["evidence"]["source"] == "reading_path.external_stops"
        assert items[5]["evidence"]["source"] == "reading_path.unresolved_stops"
        assert items[5]["evidence"]["mention_count"] == 1
    finally:
        workspace.close()


def test_create_reading_queue_omits_duplicate_targets(tmp_path: Path):
    workspace_path, result_id = import_queue_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        queue = workspace.create_reading_queue(result_id)
        full = workspace.get_reading_queue(queue["queue_id"])
        pairs = [(item["target_kind"], item["target_id"]) for item in full["items"]]

        assert len(pairs) == len(set(pairs))
    finally:
        workspace.close()


def test_list_and_get_reading_queues_are_deterministic(tmp_path: Path):
    workspace_path, result_id = import_queue_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        first = workspace.create_reading_queue(result_id, label="First queue")
        second = workspace.create_reading_queue(result_id, label="Second queue")

        listed = workspace.list_reading_queues(paper_id="local:paper")

        assert [queue["queue_id"] for queue in listed] == [
            second["queue_id"],
            first["queue_id"],
        ]
        full = workspace.get_reading_queue(second["queue_id"])
        assert full["queue"]["queue_id"] == second["queue_id"]
        assert full["items"][0]["target_id"] == result_id
    finally:
        workspace.close()


def test_apply_reading_queue_to_session_creates_queued_checkpoints(
    tmp_path: Path,
):
    workspace_path, result_id = import_queue_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        queue = workspace.create_reading_queue(result_id)
        session = workspace.create_reading_session(
            "local:paper",
            target_result_id=result_id,
        )

        applied = workspace.apply_reading_queue_to_session(
            queue["queue_id"],
            session["session_id"],
        )

        assert applied["queue"]["queue_id"] == queue["queue_id"]
        assert applied["session"]["session_id"] == session["session_id"]
        assert len(applied["applied"]) == queue["counts"]["items"]
        summary = workspace.export_reading_session_summary(session["session_id"])
        assert summary["progress"]["queued"] == queue["counts"]["items"]
        assert summary["progress"]["total_checkpoints"] == queue["counts"]["items"]
        assert summary["next_actions"] == ["continue_queued_targets"]
        checkpoint = summary["blocked_targets"]
        assert checkpoint == []
    finally:
        workspace.close()


def test_apply_reading_queue_rejects_cross_paper_session(tmp_path: Path):
    workspace_path, result_id = import_queue_pdf(tmp_path)
    workspace = Workspace.open(workspace_path)
    try:
        other_pdf = tmp_path / "other.pdf"
        write_queue_pdf(other_pdf)
        workspace.import_pdf(other_pdf, "local:other")
        queue = workspace.create_reading_queue(result_id)
        other_session = workspace.create_reading_session("local:other")

        with pytest.raises(ValueError, match="does not belong to the same paper"):
            workspace.apply_reading_queue_to_session(
                queue["queue_id"],
                other_session["session_id"],
            )
    finally:
        workspace.close()
