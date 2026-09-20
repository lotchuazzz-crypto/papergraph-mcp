import asyncio
import json
import os
import subprocess
import sys

import pytest

from papergraph import server
from papergraph.workspace import Workspace
from tests.test_reference_expansion import chain, drain


def test_cli_create_advance_export_and_overwrite(chain, capsys, tmp_path):
    ws, _ = chain
    server.main(["create-reference-expansion", "--workspace", str(ws.path), "--root-paper-id", "arxiv:2401.10001", "--max-depth", "1"])
    run = json.loads(capsys.readouterr().out)
    assert run["policy"]["max_depth"] == 1
    server.main(["advance-reference-expansion", "--workspace", str(ws.path), "--run-id", run["run_id"]])
    result = json.loads(capsys.readouterr().out)
    assert result["usage"]["new_papers"] == 2
    output = tmp_path / "report.md"
    args = ["export-reference-expansion", "--workspace", str(ws.path), "--run-id", run["run_id"], "--format", "markdown", "--output", str(output)]
    server.main(args)
    capsys.readouterr()
    assert "Reference tree" in output.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        server.main(args)
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_reading_report_contains_expansion_progress(chain):
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    drain(ws, run["run_id"])
    report = ws.export_paper_reading_report("arxiv:2401.10001")
    assert report["reference_expansions"][0]["run_id"] == run["run_id"]
    assert "Reference Expansion" in report["markdown"]
    assert "reference_expansions" in report["evidence_triage"]


def test_stdio_mcp_uses_same_saved_state(chain):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    ws, _ = chain
    baseline = ws.create_reference_expansion(["arxiv:2401.10001"])
    drain(ws, baseline["run_id"])  # Preload offline; child processes only reuse papers.
    def payload(result):
        assert not result.is_error
        return result.structured_content or json.loads(result.content[0].text)
    async def exercise():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "papergraph.server"], env=dict(os.environ))
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert "workspace_advance_reference_expansion" in names
                opened = await session.call_tool("open_workspace", {"path": str(ws.path)})
                assert not opened.is_error
                result = await session.call_tool("workspace_create_reference_expansion", {"root_paper_ids": ["arxiv:2401.10001"]})
                assert not result.is_error
                created = payload(result)
                assert created and created["state"] == "ready"
                rid = created["run_id"]
                assert ws.get_reference_expansion(rid)["policy"] == created["policy"]
                advanced = payload(await session.call_tool("workspace_advance_reference_expansion", {"run_id": rid, "max_steps": 100}))
                assert advanced["state"] == "completed" and advanced["usage"]["new_papers"] == 0
                cli = subprocess.run([sys.executable, "-m", "papergraph.server", "get-reference-expansion", "--workspace", str(ws.path), "--run-id", rid], check=True, capture_output=True, text=True)
                assert json.loads(cli.stdout) == payload(await session.call_tool("workspace_get_reference_expansion", {"run_id": rid}))
                report = payload(await session.call_tool("workspace_export_reference_expansion", {"run_id": rid, "format": "markdown"}))
                assert "cycle" in report["markdown"]
                listed = payload(await session.call_tool("workspace_list_reference_expansions", {}))
                assert any(r["run_id"] == rid for r in listed["runs"])
                revised = payload(await session.call_tool("workspace_update_reference_expansion_policy", {"run_id": rid, "limits": {"max_depth": 3}}))
                assert revised["policy"]["max_depth"] == 3
                paused = payload(await session.call_tool("workspace_pause_reference_expansion", {"run_id": rid}))
                assert paused["state"] == "paused"
                cancelled = payload(await session.call_tool("workspace_cancel_reference_expansion", {"run_id": rid}))
                assert cancelled["state"] == "cancelled"
                rejected = await session.call_tool("workspace_decide_reference_expansion", {"run_id": rid, "edge_id": "missing", "decision": {"skip": True}})
                assert rejected.is_error
                error = await session.call_tool("workspace_advance_reference_expansion", {"run_id": "missing"})
                assert error.is_error
    asyncio.run(exercise())
