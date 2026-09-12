from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from papergraph.workspace import Workspace
from tests.test_workspace_cross_paper_reading_plan import import_arxiv_context_paper
from tests.test_workspace_external_import_planner import import_import_plan_pdf


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def load_cross_paper_workspace(tmp_path: Path) -> None:
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        import_import_plan_pdf(workspace, tmp_path)
        import_arxiv_context_paper(workspace, tmp_path)
    finally:
        workspace.close()
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))


def test_cross_paper_reading_plan_mcp_tool_returns_payload(tmp_path: Path):
    load_cross_paper_workspace(tmp_path)

    plan = server.workspace_export_cross_paper_reading_plan(
        ["local:paper", "arxiv:2401.12345"],
        focus="main",
        max_candidates_per_paper=1,
    )

    assert plan["plan_schema_version"] == 1
    assert plan["format"] == "markdown"
    assert plan["summary"]["paper_count"] == 2
    assert plan["summary"]["cross_paper_edge_count"] == 1
    assert "## Cross-Paper Evidence" in plan["markdown"]


def test_cross_paper_reading_plan_mcp_tool_reports_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_export_cross_paper_reading_plan(
            ["local:paper", "arxiv:2401.12345"],
        )


def test_cross_paper_reading_plan_mcp_tool_converts_workspace_errors(
    tmp_path: Path,
):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Unknown paper id"):
        server.workspace_export_cross_paper_reading_plan(
            ["local:paper", "local:missing"],
        )
