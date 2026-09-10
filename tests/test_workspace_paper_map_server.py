from pathlib import Path

import fitz
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server


def write_paper_map_pdf(path: Path) -> None:
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
    write_paper_map_pdf(pdf)
    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")


def test_paper_map_mcp_tool_returns_payload(tmp_path: Path):
    load_workspace(tmp_path)

    paper_map = server.workspace_get_paper_map("local:paper", max_candidates=1)

    assert paper_map["map_schema_version"] == 1
    assert paper_map["paper"]["paper_id"] == "local:paper"
    assert len(paper_map["main_result_candidates"]) == 1
    assert paper_map["external_risks"]["summary"]["import_candidate_count"] == 1


def test_paper_map_mcp_tool_reports_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_get_paper_map("local:paper")


def test_paper_map_mcp_tool_converts_workspace_errors(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Unknown paper id"):
        server.workspace_get_paper_map("local:missing")
