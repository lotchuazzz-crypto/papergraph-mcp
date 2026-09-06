from pathlib import Path

import fitz
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server


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


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def test_reading_queue_mcp_tools_return_payloads(tmp_path: Path):
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_queue_pdf(pdf)

    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")

    queue = server.workspace_create_reading_queue(
        "local:paper::pdf:theorem:1.1",
        label="Main theorem queue",
    )
    session = server.workspace_create_reading_session(
        "local:paper",
        target_result_id="local:paper::pdf:theorem:1.1",
    )
    applied = server.workspace_apply_reading_queue_to_session(
        queue["queue_id"],
        session["session_id"],
    )
    full = server.workspace_get_reading_queue(queue["queue_id"])

    assert server.workspace_list_reading_queues()[0]["queue_id"] == queue["queue_id"]
    assert full["queue"]["counts"]["items"] == 5
    assert full["items"][0]["target_kind"] == "result_id"
    assert applied["queue"]["queue_id"] == queue["queue_id"]
    assert len(applied["applied"]) == 5


def test_reading_queue_mcp_tools_report_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_create_reading_queue("local:paper::pdf:theorem:1.1")


def test_reading_queue_mcp_tools_convert_workspace_errors(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Unknown reading queue id"):
        server.workspace_get_reading_queue("queue:missing")
