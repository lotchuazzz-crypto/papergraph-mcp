from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from tests.test_workspace_reading import (
    write_recursive_dependency_pdf,
    write_slice_pdf,
)


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def test_reading_bridge_mcp_tools_return_payloads(tmp_path: Path):
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_slice_pdf(pdf)

    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")

    bundle = server.workspace_export_reading_bundle("local:paper")
    context = server.workspace_export_result_reading_context(
        "local:paper::pdf:theorem:1.1"
    )
    source_slice = server.workspace_get_source_slice(
        proof_id="local:paper::proof:1",
        context=1,
    )

    assert bundle["bridge_schema_version"] == "1"
    assert context["result"]["result_id"] == "local:paper::pdf:theorem:1.1"
    assert source_slice["bounded"] is True


def test_reading_path_mcp_tool_returns_recursive_path(tmp_path: Path):
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "recursive.pdf"
    write_recursive_dependency_pdf(pdf)

    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")

    path = server.workspace_get_result_reading_path(
        "local:paper::pdf:theorem:1.3",
        recursive=True,
    )

    assert [node["result_id"] for node in path["bottom_up"]] == [
        "local:paper::pdf:lemma:1.1",
        "local:paper::pdf:lemma:1.2",
        "local:paper::pdf:theorem:1.3",
    ]


def test_source_slice_mcp_tool_converts_errors_to_tool_error(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="Exactly one source slice selector"):
        server.workspace_get_source_slice()
