"""Actual CLI and stdio MCP smoke for local unreleased v1.2.0 work.

Uses a generated paper fixture and temporary workspace, not a downloaded paper.
Run from the development checkout with its .venv Python.
"""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pymupdf as fitz
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    with tempfile.TemporaryDirectory(prefix='papergraph-v120-') as directory:
        root = Path(directory)
        workspace = root / 'workspace.sqlite3'
        pdf = root / 'fixture.pdf'
        cycle_tex = root / 'cycle.tex'
        cycle_tex.write_text('\n'.join([
            r'\documentclass{article}', r'\newtheorem{theorem}{Theorem}', r'\begin{document}',
            r'\begin{theorem}\label{A}Main theorem.\end{theorem}',
            r'\begin{proof}By \ref{B}.\end{proof}', r'\begin{theorem}\label{B}Other result.\end{theorem}',
            r'\begin{proof}By \ref{A}.\end{proof}', r'\end{document}',
        ]), encoding='utf-8')
        document = fitz.open()
        page = document.new_page()
        for index, line in enumerate([
            'Theorem 0.1 (= Theorem 1.2). Introductory result.',
            'Theorem 0.1 also explains the application.',
            'Lemma 1.1. Base result.', 'Proof. Direct.',
            'Theorem 1.2. Main result.', 'Proof. By Lemma 1.1.',
        ]):
            page.insert_text((72, 72 + index * 18), line)
        document.save(pdf)
        document.close()
        cli = subprocess.run([sys.executable, '-m', 'papergraph.server', 'discover-doi', 'invalid'],
                             capture_output=True, text=True, check=True)
        assert json.loads(cli.stdout)['status'] == 'invalid_or_ambiguous_input'
        parameters = StdioServerParameters(command=sys.executable, args=['-m', 'papergraph.server'])
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                assert 'discover_doi_paper' in tools
                assert 'workspace_import_doi_candidate' in tools
                assert 'workspace_add_doi_paper' in tools
                async def call(name, arguments):
                    result = await session.call_tool(name, arguments)
                    assert not result.is_error, result
                    return json.loads(next(c.text for c in result.content if c.type == 'text'))
                result = await call('discover_doi_paper', {'doi': 'invalid'})
                assert result['status'] == 'invalid_or_ambiguous_input'
                await call('open_workspace', {'path': str(workspace)})
                invalid = await call('workspace_add_doi_paper', {'doi': 'invalid'})
                assert invalid['import_status'] == 'not_imported'
                result = await call('workspace_import_doi_candidate', {'doi': '10.1234/test', 'candidate_id': 'unreviewed'})
                assert result['status'] == 'confirmation_required'
                await call('workspace_add_pdf_paper', {'path': str(pdf), 'paper_id': 'local:smoke'})
                alias = await call('workspace_get_result_proof', {'result_id': 'local:smoke::pdf:theorem:0.1'})
                assert alias['proof_entry']['status'] == 'corresponding_proof'
                assert alias['known']['proof']['result_id'] == 'local:smoke::pdf:theorem:1.2'
                path = await call('workspace_get_result_reading_path', {'result_id': 'local:smoke::pdf:theorem:1.2'})
                assert [item['result_id'] for item in path['bottom_up']] == [
                    'local:smoke::pdf:lemma:1.1', 'local:smoke::pdf:theorem:1.2']
                assert 'workspace_get_dependency_reading' in tools
                overview = await call('workspace_get_dependency_reading', {
                    'paper_id': 'local:smoke', 'target_result_id': 'local:smoke::pdf:theorem:1.2'})
                assert overview['selection']['basis'] == 'user_selected'
                assert overview['reading_path']['order_status'] == 'dependency_first'
                assert overview['statement_graph']['status'] == 'not_available_for_result'
                assert overview['paper']['result_count'] == 3
                assert overview['paper']['import_state']['body_imported'] is True
                assert overview['paper']['legacy_counts_basis'] == 'latex_statement_graph'
                await call('workspace_add_local_paper', {'path': str(cycle_tex), 'paper_id': 'local:cycle'})
                cycle = await call('workspace_get_result_reading_path', {'result_id': 'local:cycle::A'})
                assert cycle['order_status'] == 'cycle_blocked' and cycle['bottom_up'] == []
                bundle = await call('workspace_export_reading_bundle', {'paper_id': 'local:cycle'})
                assert bundle['completeness_check']['circular_deps']
                context = await call('workspace_export_result_reading_context', {'result_id': 'local:cycle::A'})
                assert any('cycle' in warning for warning in context['warnings'])
        cli = subprocess.run([sys.executable, '-m', 'papergraph.server', 'get-dependency-reading',
                              str(workspace), 'local:smoke', '--target-result-id',
                              'local:smoke::pdf:theorem:1.2'], capture_output=True, text=True, check=True)
        assert json.loads(cli.stdout) == overview
        print(json.dumps({'cli': 'passed', 'stdio_initialize_tools_and_calls': 'passed',
                          'input': 'generated_local_fixture', 'live_download': 'not_run'}))


if __name__ == '__main__':
    asyncio.run(main())
