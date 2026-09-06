from pathlib import Path

import fitz
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server


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


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def test_reading_session_mcp_tools_return_payloads(tmp_path: Path):
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_session_pdf(pdf)

    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")

    session = server.workspace_create_reading_session(
        "local:paper",
        label="Main theorem",
        target_result_id="local:paper::pdf:theorem:1.1",
    )
    checkpoint = server.workspace_record_reading_checkpoint(
        session["session_id"],
        "result_id",
        "local:paper::pdf:theorem:1.1",
        "reviewed",
        summary="Statement reviewed.",
        evidence={"source": "mcp"},
    )
    note = server.workspace_add_reading_note(
        session["session_id"],
        "Check whether Lemma 1.2 is sufficient.",
        note_type="question",
    )
    full = server.workspace_get_reading_session(session["session_id"])
    summary = server.workspace_export_reading_session_summary(session["session_id"])

    assert server.workspace_list_reading_sessions()[0]["session_id"] == (
        session["session_id"]
    )
    assert checkpoint["status"] == "reviewed"
    assert note["note_type"] == "question"
    assert full["session"]["counts"] == {"checkpoints": 1, "notes": 1}
    assert summary["progress"]["reviewed"] == 1
    assert summary["open_questions"] == [note]


def test_reading_session_mcp_tools_report_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_create_reading_session("local:paper")


def test_reading_session_mcp_tools_convert_workspace_errors(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Unknown reading session id"):
        server.workspace_get_reading_session("session:missing")
