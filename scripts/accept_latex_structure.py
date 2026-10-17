"""Local CLI/stdio acceptance for an installed package; never downloads papers.

Run with an isolated installed interpreter and a fresh --output outside Git.
The default synthetic fixture contains no private research. --tex reads a local
project without modifying it. All responses remain in the chosen output folder.
"""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SYNTHETIC = r'''
\title[Short]{Synthetic parser acceptance}
\newtheorem{assertion}{Theorem}[section]
\newtheorem{auxiliary}[assertion]{Lemma}
\newtheorem{step}[assertion]{Proposition}
\section{Introduction}
\begin{assertion}[Main]\label{main}Synthetic claim.\end{assertion}
\section{Ingredients}
\begin{auxiliary}\label{base}Base.\end{auxiliary}
\begin{proof}$R[w]$ and $[12]P$. Use \cite{external}.\end{proof}
\begin{auxiliary}\label{middle}Middle.\end{auxiliary}
\begin{proof}By \ref{base}.\end{proof}
\begin{step}\label{last}Last.\end{step}
\begin{proof}By \ref{middle}.\end{proof}
\begin{proof}[Proof of Theorem~\ref{main}]By \ref{last}.\end{proof}
\begin{thebibliography}{9}
\bibitem{external}A. Author, Synthetic. arXiv:2401.12346.
\end{thebibliography}
'''


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


async def accept(args, root, tex):
    import papergraph
    from papergraph.parser import latex_project_to_evidence_document
    from papergraph.project import load_project

    paper, target = args.paper_id, args.paper_id + '::' + args.target
    workspace = root / 'workspace.sqlite3'
    environment = dict(os.environ, PYTHONUTF8='1')
    environment.pop('PYTHONPATH', None)
    commands = []

    def cli(name, *arguments):
        argv = [sys.executable, '-m', 'papergraph.server', *map(str, arguments)]
        run = subprocess.run(argv, cwd=root, env=environment, capture_output=True, timeout=90)
        (root / (name + '.stdout.txt')).write_bytes(run.stdout)
        (root / (name + '.stderr.txt')).write_bytes(run.stderr)
        commands.append({'name': name, 'argv': argv, 'exit_code': run.returncode})
        save(root / 'commands.json', commands)
        assert run.returncode == 0, (name, run.stderr.decode('utf-8', errors='replace'))
        return json.loads(run.stdout) if name != 'version' else run.stdout.decode().strip()

    version = cli('version', '--version')
    doctor = cli('doctor', 'doctor')
    starter = ['--workspace', workspace, '--artifact-dir', root / 'artifacts',
               '--tex', str(tex) + '=' + paper, '--no-session', '--no-queue']
    plan = cli('plan', 'plan-starter-project', *starter)
    assert plan['status'] == 'ready' and not workspace.exists()
    cli('bootstrap', 'bootstrap-reading-project', *starter)
    cli_reading = cli('cli-reading', 'get-dependency-reading', workspace, paper,
                      '--target-result-id', target, '--detail', 'compact')
    cli('cli-external-plan', 'plan-external-imports-for-paper', '--workspace', workspace, '--paper-id', paper)
    document = latex_project_to_evidence_document(paper, 'local', str(tex), None, load_project(tex))
    save(root / 'document.json', asdict(document))
    for span in document.spans:
        source = tex.parent / span.source_ref
        assert source.read_text(encoding='utf-8', errors='replace')[span.start_offset:span.end_offset] == span.text

    parameters = StdioServerParameters(command=sys.executable, args=['-m', 'papergraph.server'],
                                      cwd=str(root), env=environment)
    calls = []
    with (root / 'stdio.stderr.txt').open('w', encoding='utf-8') as stderr:
        async with stdio_client(parameters, errlog=stderr) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                save(root / 'initialize.json', initialized.model_dump(mode='json'))
                schema = await session.list_tools()
                save(root / 'tools.json', schema.model_dump(mode='json'))

                async def call(name, arguments, filename):
                    calls.append({'tool': name, 'arguments': arguments})
                    result = await session.call_tool(name, arguments)
                    save(root / (filename + '.json'), result.model_dump(mode='json'))
                    assert not result.is_error, result
                    values = [json.loads(c.text) for c in result.content if c.type == 'text']
                    return values[0] if len(values) == 1 else values

                await call('open_workspace', {'path': str(workspace)}, 'open')
                results, offset = [], 0
                while True:
                    page = await call('workspace_list_results', {'paper_id': paper, 'limit': 100, 'offset': offset}, 'results-' + str(offset))
                    batch = page if isinstance(page, list) else ([page] if 'result_id' in page else page.get('results', []))
                    results.extend(batch)
                    if len(batch) < 100:
                        break
                    offset += 100
                assert {r['result_id'] for r in results} == {r.result_id for r in document.results}
                for recursive in (False, True):
                    await call('workspace_get_proof_dependencies', {'result_id': target, 'recursive': recursive}, 'dependencies-' + str(recursive))
                path = await call('workspace_get_result_reading_path', {'result_id': target, 'recursive': True}, 'reading-path')
                mcp_reading = await call('workspace_get_dependency_reading', {'paper_id': paper, 'target_result_id': target, 'detail': 'compact'}, 'mcp-reading')
                assert mcp_reading == cli_reading
                await call('workspace_plan_external_imports_for_paper', {'paper_id': paper}, 'external-plan')
                await call('workspace_get_paper_map', {'paper_id': paper}, 'paper-map')
                await call('workspace_get_result_proof', {'result_id': target}, 'target-proof')
                await call('workspace_list_external_reference_resolutions', {'paper_id': paper}, 'resolutions')
                await call('workspace_list_external_reference_searches', {'paper_id': paper}, 'searches')
                save(root / 'stdio-calls.json', calls)
    if args.tex is None:
        assert len(document.results) == 4 and len(document.proofs) == 4
        assert [r.visible_number for r in document.results] == ['1.1', '2.1', '2.2', '2.3']
        assert [p.result_id for p in document.proofs] == [paper + '::' + x for x in ('base', 'middle', 'last', 'main')]
        assert [m.raw_key for m in document.citation_mentions] == ['external']
        assert [n['result_id'] for n in path['bottom_up']] == [paper + '::' + x for x in ('base', 'middle', 'last', 'main')]
    summary = {'status': 'passed', 'version': version, 'python': sys.executable,
               'package_file': papergraph.__file__, 'build_identity': doctor['build_identity'],
               'result_count': len(document.results), 'proof_count': len(document.proofs),
               'owned_proof_count': sum(p.result_id is not None for p in document.proofs),
               'citation_count': len(document.citation_mentions), 'bibliography_count': len(document.bibliography_entries),
               'stdio_tool_count': len(schema.tools), 'stdio_calls': len(calls),
               'order_status': path['order_status'], 'source_spans_verified': len(document.spans),
               'input_sha256': hashlib.sha256(tex.read_bytes()).hexdigest(),
               'input': 'supplied_local_tex' if args.tex else 'synthetic', 'external_downloads': 'not_run'}
    save(root / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tex', type=Path)
    parser.add_argument('--paper-id', default='local:acceptance')
    parser.add_argument('--target', default='main', help='Local result label (without paper prefix)')
    args = parser.parse_args()
    root = args.output.resolve()
    repository = Path(__file__).resolve().parents[1]
    if root == repository or repository in root.parents:
        parser.error('--output must be outside the repository')
    root.mkdir(parents=True, exist_ok=False)
    tex = args.tex.resolve() if args.tex else root / 'synthetic.tex'
    if args.tex is None:
        tex.write_text(SYNTHETIC, encoding='utf-8')
    asyncio.run(asyncio.wait_for(accept(args, root, tex), timeout=240))


if __name__ == '__main__':
    main()
