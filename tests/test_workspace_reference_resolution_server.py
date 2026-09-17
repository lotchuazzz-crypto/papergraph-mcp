from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from tests.test_workspace_reference_resolution import write_missing_reference_pdf


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def load_workspace_with_missing_reference(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_missing_reference_pdf(pdf)
    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")


def test_reference_resolution_mcp_tools_return_payload(tmp_path: Path):
    load_workspace_with_missing_reference(tmp_path)
    blocked = server.workspace_plan_external_imports_for_paper("local:paper")[
        "blocked"
    ][0]

    result = server.workspace_resolve_external_reference(
        "local:paper",
        blocked["blocked_id"],
        {"kind": "doi", "doi": "10.1000/example"},
    )

    assert result["status"] == "resolved_not_imported"
    listed = server.workspace_list_external_reference_resolutions("local:paper")
    assert listed["summary"]["resolved_not_imported_count"] == 1
    assert listed["resolutions"][0]["resolution_id"] == result["resolution_id"]


def test_reference_resolution_mcp_tools_report_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_list_external_reference_resolutions("local:paper")
