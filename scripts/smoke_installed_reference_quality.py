"""Run with an isolated wheel interpreter, outside the checkout, without PYTHONPATH."""
from __future__ import annotations

import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import fitz
import papergraph
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from papergraph.workspace import Workspace


def cli(*args):
    return subprocess.run([sys.executable, '-m', 'papergraph.server', *args],
                          check=True, capture_output=True, text=True, timeout=30).stdout


async def protocol(path, baseline, search):
    params = StdioServerParameters(command=sys.executable, args=['-m','papergraph.server'], env=dict(os.environ))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            assert not (await session.call_tool('open_workspace', {'path':str(path)})).is_error
            result = await session.call_tool('workspace_list_external_reference_searches', {'paper_id':'local:paper'})
            assert not result.is_error
            assert (result.structured_content or json.loads(result.content[0].text)) == baseline
            result = await session.call_tool('workspace_search_external_reference', {
                'paper_id':'local:paper', 'blocked_id':search['source']['blocked_id'], 'resolver_version':'future'})
            assert result.is_error


def main():
    assert 'site-packages' in str(Path(papergraph.__file__).resolve())
    assert cli('--version').strip() == 'papergraph-mcp 1.1.5'
    doctor = json.loads(cli('doctor'))
    assert doctor['version'] == '1.1.5'
    # Outside a Git checkout, the existing diagnostic legitimately notes missing
    # Git context; this is not an installation warning.
    assert all(w.startswith('Git context unavailable;') for w in doctor['warnings'])
    with tempfile.TemporaryDirectory(prefix='papergraph-wheel-') as temp:
        root = Path(temp)
        pdf = root/'source.pdf'
        with fitz.open() as doc:
            page = doc.new_page()
            for i, line in enumerate(['Theorem 1.1. Main result.', 'Proof. By [17, Theorem 2.1].',
                'References', '[17] A. Author. Published target. Journal of Examples 2020.']):
                page.insert_text((72,72+i*18),line,fontsize=11)
            doc.save(pdf)
        path = root/'workspace.sqlite3'
        with closing(Workspace.open(path)) as ws:
            ws.import_pdf(pdf,'local:paper')
            blocked = ws.plan_external_imports_for_paper('local:paper')['blocked'][0]['blocked_id']
            ws.reference_search_provider = lambda query: [{'provider':'crossref','outcome':'ok','records':[
                {'doi':'10.1000/target','title':'Published target','authors':['A. Author'],'year':'2020'}]}]
            search = ws.search_external_reference('local:paper',blocked,providers=['crossref'])
            assert search['candidates'][0]['assessment']
            baseline = ws.list_external_reference_searches('local:paper')
        assert json.loads(cli('list-external-reference-searches','--workspace',str(path),'--paper-id','local:paper')) == baseline
        asyncio.run(asyncio.wait_for(protocol(path,baseline,search), timeout=45))
    print(json.dumps({'version':'1.1.5','installed_package':str(papergraph.__file__),
                      'cli_snapshot_parity':True,'mcp_stdio_snapshot_parity':True,'invalid_version_rejected':True}))


if __name__ == '__main__':
    main()
