from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
from tests.test_reference_search import provider_result
from tests.test_workspace_reference_resolution import write_missing_reference_pdf


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def load_workspace_with_missing_reference(tmp_path: Path) -> dict:
    workspace_path = tmp_path / "workspace.sqlite3"
    pdf = tmp_path / "paper.pdf"
    write_missing_reference_pdf(pdf)
    server.open_workspace(str(workspace_path))
    server.workspace_add_pdf_paper(str(pdf), "local:paper")
    return server.workspace_plan_external_imports_for_paper("local:paper")["blocked"][0]


def test_reference_search_mcp_tools_return_payload(tmp_path: Path):
    blocked = load_workspace_with_missing_reference(tmp_path)
    server.require_workspace().reference_search_provider = lambda query: [
        provider_result(
            "crossref",
            records=[
                {
                    "kind": "doi",
                    "doi": "10.1000/example",
                    "title": "Published target",
                    "authors": ["A. Author"],
                    "year": "2020",
                }
            ],
        )
    ]

    search = server.workspace_search_external_reference(
        "local:paper",
        blocked["blocked_id"],
    )

    assert search["summary"]["candidate_count"] == 1
    candidate_id = search["candidates"][0]["candidate_id"]
    listed = server.workspace_list_external_reference_searches("local:paper")
    assert listed["summary"]["search_run_count"] == 1

    applied = server.workspace_resolve_external_reference_candidate(
        "local:paper",
        blocked["blocked_id"],
        candidate_id,
    )

    assert applied["resolution"]["target"]["doi"] == "10.1000/example"


def test_reference_search_mcp_tools_report_missing_workspace():
    with pytest.raises(ToolError, match="open_workspace"):
        server.workspace_search_external_reference("local:paper", "blocked")
