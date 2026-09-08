from pathlib import Path

import fitz
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server


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


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def load_workspace(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_import_plan_pdf(pdf)

    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")


def test_external_import_planner_mcp_tools_return_payloads(tmp_path: Path):
    load_workspace(tmp_path)
    result_id = "local:paper::pdf:theorem:1.1"

    result_plan = server.workspace_plan_external_imports_for_result(result_id)
    queue = server.workspace_create_reading_queue(result_id)
    queue_plan = server.workspace_plan_external_imports_for_queue(queue["queue_id"])
    paper_plan = server.workspace_plan_external_imports_for_paper("local:paper")

    assert result_plan["candidates"][0]["source"]["arxiv_id"] == "2401.12345"
    assert queue_plan["scope"]["kind"] == "queue_id"
    assert paper_plan["summary"]["import_candidate_count"] == 1


def test_external_import_planner_mcp_tools_report_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_plan_external_imports_for_result(
            "local:paper::pdf:theorem:1.1"
        )


def test_external_import_planner_mcp_tools_convert_workspace_errors(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Unknown reading queue id"):
        server.workspace_plan_external_imports_for_queue("queue:missing")
