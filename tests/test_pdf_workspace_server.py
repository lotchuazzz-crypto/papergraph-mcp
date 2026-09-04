import asyncio
import json
from pathlib import Path

import fitz
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import papergraph.server as server
import papergraph.workspace as workspace_module


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def call_mcp_tool(name: str, arguments: dict):
    return asyncio.run(server.mcp.call_tool(name, arguments))


def result_json(result):
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


def write_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in [
        "Lemma 1.2. Base estimate.",
        "Theorem 1.1. Main result.",
        "Proof. By Lemma 1.2 and [12, Theorem 3.5].",
        "References",
        "[12] A. Author. Cited paper. arXiv:2401.12345.",
    ]:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    document.save(path)
    document.close()


@pytest.mark.parametrize(
    "call",
    [
        lambda pdf: server.workspace_add_pdf_paper(str(pdf), "local:paper"),
        lambda pdf: server.workspace_list_results(),
        lambda pdf: server.workspace_get_result("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_result_proof("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_proof_dependencies("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_external_result_mentions("local:paper::pdf:theorem:1.1"),
        lambda pdf: server.workspace_get_evidence("local:paper::pdf:theorem:1.1"),
    ],
)
def test_evidence_tools_report_missing_workspace(tmp_path: Path, call):
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    with pytest.raises(ToolError, match="open_workspace"):
        call(pdf)


def test_pdf_evidence_mcp_workflow(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    imported = server.workspace_add_pdf_paper(str(pdf), "local:paper")
    assert imported["paper_id"] == "local:paper"
    assert imported["source_type"] == "pdf"
    assert imported["result_count"] == 2

    results = server.workspace_list_results()
    assert [item["result_id"] for item in results] == [
        "local:paper::pdf:lemma:1.2",
        "local:paper::pdf:theorem:1.1",
    ]

    result = server.workspace_get_result("local:paper::pdf:theorem:1.1")
    assert result["spans"][0]["page"] == 1

    proof = server.workspace_get_result_proof("local:paper::pdf:theorem:1.1")
    assert proof["known"]["proof"]["result_id"] == "local:paper::pdf:theorem:1.1"

    dependencies = server.workspace_get_proof_dependencies("local:paper::pdf:theorem:1.1")
    assert dependencies["known"]["resolved_local_results"][0]["visible_number"] == "1.2"
    assert dependencies["known"]["external_result_mentions"][0]["external_number"] == "3.5"

    evidence = server.workspace_get_evidence("local:paper::pdf:theorem:1.1")
    assert evidence["node_or_edge_id"] == "local:paper::pdf:theorem:1.1"
    assert evidence["spans"][0]["page"] == 1


def test_pdf_import_warnings_are_visible_from_server_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    original_builder = workspace_module.build_pdf_evidence_document

    def builder_with_warning(*args, **kwargs):
        from dataclasses import replace

        document = original_builder(*args, **kwargs)
        return replace(document, warnings=("low confidence PDF section split",))

    monkeypatch.setattr(
        workspace_module,
        "build_pdf_evidence_document",
        builder_with_warning,
    )
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    imported = server.workspace_add_pdf_paper(str(pdf), "local:paper")

    assert imported["warnings"] == ["low confidence PDF section split"]


def test_pdf_evidence_tool_errors_are_translated(tmp_path: Path):
    server.open_workspace(str(tmp_path / "workspace.sqlite3"))

    with pytest.raises(ToolError, match="PDF"):
        server.workspace_add_pdf_paper(str(tmp_path / "missing.pdf"), "local:paper")


def test_mcp_dispatch_for_new_tools(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    write_pdf(pdf)
    call_mcp_tool("open_workspace", {"path": str(tmp_path / "workspace.sqlite3")})
    imported = call_mcp_tool("workspace_add_pdf_paper", {"path": str(pdf), "paper_id": "local:paper"})

    assert result_json(imported)["paper_id"] == "local:paper"
    listed = call_mcp_tool("workspace_list_results", {})
    assert result_json(listed)[0]["paper_id"] == "local:paper"

    result_id = "local:paper::pdf:theorem:1.1"
    dispatch_calls = [
        ("workspace_get_result", {"result_id": result_id}),
        ("workspace_get_result_proof", {"result_id": result_id}),
        ("workspace_get_proof_dependencies", {"result_id": result_id}),
        ("workspace_get_external_result_mentions", {"result_id": result_id}),
        ("workspace_get_evidence", {"node_or_edge_id": result_id}),
    ]
    for tool_name, arguments in dispatch_calls:
        dispatched = call_mcp_tool(tool_name, arguments)
        assert result_json(dispatched) is not None
