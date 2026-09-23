import asyncio
from contextlib import closing
import json
import os
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from papergraph.workspace import Workspace
from tests.test_reference_search import import_search_source_pdf


def test_v2_snapshot_cli_and_real_stdio_parity(tmp_path):
    path = tmp_path / "workspace.sqlite3"
    with closing(Workspace.open(path)) as ws:
        blocked = import_search_source_pdf(ws, tmp_path)
        ws.reference_search_provider = lambda q: [{"provider": "crossref", "outcome": "ok", "warnings": [],
            "records": [{"doi": "10.1000/maps", "title": "Published target", "authors": ["A. Author"], "year": "2020"}]}]
        snapshot = ws.search_external_reference("local:paper", blocked["blocked_id"], providers=["crossref"])
        baseline = ws.list_external_reference_searches("local:paper")
        assert snapshot["candidates"][0]["assessment"]
    cli = subprocess.run([sys.executable, "-m", "papergraph.server", "list-external-reference-searches",
                          "--workspace", str(path), "--paper-id", "local:paper"],
                         check=True, capture_output=True, text=True, timeout=30)
    assert json.loads(cli.stdout) == baseline
    bad_cli = subprocess.run([sys.executable, "-m", "papergraph.server", "search-external-reference",
                              "--workspace", str(path), "--paper-id", "local:paper", "--blocked-id", blocked["blocked_id"],
                              "--resolver-version", "future"], capture_output=True, text=True, timeout=30)
    assert bad_cli.returncode != 0 and "future" in bad_cli.stderr

    def payload(result):
        assert not result.is_error
        return result.structured_content or json.loads(result.content[0].text)

    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "papergraph.server"], env=dict(os.environ))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                payload(await session.call_tool("open_workspace", {"path": str(path)}))
                assert payload(await session.call_tool("workspace_list_external_reference_searches", {"paper_id": "local:paper"})) == baseline
                args = {"paper_id": "local:paper", "blocked_id": blocked["blocked_id"], "providers": ["crossref"], "resolver_version": "deterministic_v2"}
                assert payload(await session.call_tool("workspace_search_external_reference", args)) == snapshot
                result = await session.call_tool("workspace_search_external_reference", {**args, "resolver_version": "future"})
                assert result.is_error
    asyncio.run(asyncio.wait_for(exercise(), timeout=45))
