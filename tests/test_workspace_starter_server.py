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


def test_starter_plan_mcp_tool_returns_payload(tmp_path: Path):
    payload = server.workspace_plan_starter_project(
        workspace_path=str(tmp_path / "workspace.sqlite3"),
        artifact_dir=str(tmp_path / "artifacts"),
        papers=[
            {
                "kind": "pdf",
                "path": str(tmp_path / "paper.pdf"),
                "paper_id": "local:paper",
            }
        ],
        create_queue=False,
        create_session=False,
    )

    assert payload["status"] == "ready"
    assert payload["planned_artifacts"][0]["kind"] == "starter_summary"
    assert payload["planned_artifacts"][1]["kind"] == "starter_manifest"


def test_starter_bootstrap_mcp_tool_writes_artifacts_and_opens_workspace(
    tmp_path: Path,
):
    load_workspace(tmp_path)

    payload = server.workspace_bootstrap_reading_project(
        workspace_path=str(tmp_path / "workspace.sqlite3"),
        artifact_dir=str(tmp_path / "artifacts"),
        papers=[],
        create_queue=False,
        create_session=False,
    )

    assert payload["status"] == "written"
    assert (tmp_path / "artifacts" / "START_HERE.md").exists()
    assert (tmp_path / "artifacts" / "papergraph-starter-manifest.json").exists()
    assert server.require_workspace().path == (tmp_path / "workspace.sqlite3").resolve()


def test_starter_mcp_tool_converts_workspace_errors(tmp_path: Path):
    with pytest.raises(ToolError, match="paper_ids must be distinct"):
        server.workspace_plan_starter_project(
            workspace_path=str(tmp_path / "workspace.sqlite3"),
            artifact_dir=str(tmp_path / "artifacts"),
            papers=[
                {"kind": "pdf", "path": str(tmp_path / "a.pdf"), "paper_id": "local:a"},
                {"kind": "pdf", "path": str(tmp_path / "b.pdf"), "paper_id": "local:a"},
            ],
        )
