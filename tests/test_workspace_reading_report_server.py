from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from tests.test_workspace_paper_map_server import load_workspace


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def test_reading_report_mcp_tool_returns_payload(tmp_path: Path):
    load_workspace(tmp_path)

    report = server.workspace_export_paper_reading_report(
        "local:paper",
        max_candidates=1,
    )

    assert report["report_schema_version"] == 1
    assert report["format"] == "markdown"
    assert report["paper_id"] == "local:paper"
    assert report["summary"]["main_candidate_count"] == 1
    assert "## Paper Map" in report["markdown"]
    assert "## External Reading Risks" in report["markdown"]


def test_reading_report_mcp_tool_reports_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_export_paper_reading_report("local:paper")


def test_reading_report_mcp_tool_converts_workspace_errors(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Unknown paper id"):
        server.workspace_export_paper_reading_report("local:missing")
