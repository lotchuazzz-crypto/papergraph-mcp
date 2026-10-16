"""Offline installed CLI/stdio acceptance; writes only a fresh output directory.

Run outside the checkout with the exact installed interpreter. Optional root PDF
and legacy workspace are read/copy inputs; no providers, client config or external
reference downloads are used. Full structured tool responses are retained.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pymupdf
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def pdf_fixture(path, closed):
    doc = pymupdf.open()
    lines = ['Lemma 1.1. Base case.', 'Proof. Direct. QED.',
             'Theorem 1.2. Main result.', 'Proof. We proceed in steps.']
    lines += [f'Step {i}: a bounded synthetic calculation.' for i in range(30)]
    lines[22] = 'DEPENDENCY_MIDDLE. Apply Lemma 1.1 and Lemma 9.9.'
    lines += ['This concludes. QED.' if closed else 'Further discussion continues.']
    lines += ['Unrelated prose uses Lemma 8.8.']
    for start in range(0, len(lines), 12):
        page = doc.new_page()
        for i, line in enumerate(lines[start:start + 12]):
            page.insert_text((60, 60 + i * 45), line)
    doc.save(path)
    doc.close()


async def verify(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records, metrics = [], []
    db = output / 'reading.sqlite3'
    for closed in (True, False):
        pdf_fixture(output / ('closed.pdf' if closed else 'open.pdf'), closed)
    tex = output / 'main.tex'
    tex.write_text(r'\newtheorem{lemma}{Lemma}\begin{lemma}\label{base}Base.\end{lemma}'
        r'\begin{proof}By the definition of even. Apply Lemma 2.14.1 '
        r'and \cite[Theorem 3]{external}.\end{proof}\bibliography{refs}', encoding='utf-8')
    (output / 'refs.bib').write_text('@article{external,title={External target},year={2000}}', encoding='utf-8')
    env = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME')}
    cli = str(Path(sys.executable).with_name('papergraph-mcp.exe' if os.name == 'nt' else 'papergraph-mcp'))
    for name, argv in [('version', ['--version']), ('doctor', ['doctor']),
                       ('dependency-help', ['get-dependency-reading', '--help']),
                       ('source-help', ['read-source-blocks', '--help'])]:
        result = subprocess.run([cli, *argv], cwd=output, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
        save(output / f'cli-{name}.json', {'argv': [cli, *argv], 'cwd': str(output),
             'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        assert result.returncode == 0, result.stderr
        if name == 'version':
            assert result.stdout.strip() == 'papergraph-mcp 1.2.2'
        if name == 'doctor':
            doctor = json.loads(result.stdout)
            assert doctor['recommended_source'] == 'papergraph-mcp==1.2.2'
            assert doctor['git_required_for_default_install'] is False
            assert not any('Git context unavailable' in w for w in doctor['warnings'])
            save(output / 'identity.json', doctor)
    params = StdioServerParameters(command=cli, args=[], cwd=str(output), env=env)
    async with stdio_client(params, errlog=(output / 'mcp-stderr.log').open('w', encoding='utf-8')) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            init = await session.initialize()
            assert init.server_info.version == '1.2.2'
            save(output / 'initialize.json', init.model_dump(mode='json'))
            tools = await session.list_tools()
            save(output / 'tools.json', tools.model_dump(mode='json'))
            schemas = {t.name: t.input_schema for t in tools.tools}
            assert schemas['workspace_get_source_slice']['properties']['context']['maximum'] == 5

            async def call(name, **kw):
                result = await session.call_tool(name, kw)
                raw = result.model_dump(mode='json')
                records.append({'tool': name, 'arguments': kw, 'response': raw})
                metrics.append({'tool': name, 'arguments': kw, 'response_bytes': len(json.dumps(raw).encode())})
                save(output / 'mcp-responses.json', records)
                assert not result.is_error, raw
                texts = [json.loads(c.text) for c in result.content if c.type == 'text']
                if name in ('workspace_list_results', 'workspace_list_papers'):
                    return texts[0] if len(texts) == 1 and isinstance(texts[0], list) else texts
                payload = texts[0]
                # MCP 2 wraps list-returning tools in {"result": [...]}, while
                # dictionary tools retain their original object shape.
                return payload['result'] if isinstance(payload, dict) and set(payload) == {'result'} else payload

            await call('open_workspace', path=str(db))
            for name in ('closed', 'open'):
                await call('workspace_add_pdf_paper', path=str(output / f'{name}.pdf'), paper_id=f'local:{name}')
                rid = f'local:{name}::pdf:theorem:1.2'
                proof = await call('workspace_get_result_proof', result_id=rid)
                assert proof['known']['proof']['text_coverage']['complete'] is False
                source = await call('workspace_get_source_slice', proof_id=proof['known']['proof']['proof_id'], context=5)
                seen, handle = [], source['source_reading']
                handle['arguments']['limit'] = 5
                while handle:
                    page = await call(handle['tool'], **handle['arguments'])
                    assert len(page['blocks']) <= 5 and page['proof_ownership'] == 'not_asserted'
                    seen += page['blocks']
                    handle = page['next']
                assert any('DEPENDENCY_MIDDLE' in b['text'] for b in seen)
                deps = await call('workspace_get_proof_dependencies', result_id=rid)
                if name == 'closed':
                    assert deps['known']['resolved_local_results'][0]['visible_number'] == '1.1'
                    assert [m['raw_text'] for m in deps['unresolved']['local_result_mentions']] == ['Lemma 9.9']
                else:
                    assert not deps['known']['resolved_local_results']
                    assert not deps['unresolved']['local_result_mentions']
            await call('workspace_add_local_paper', path=str(tex), paper_id='local:tex')
            plan = await call('workspace_plan_external_imports_for_result', result_id='local:tex::base')
            assert plan['unresolved_local_mentions'][0]['raw_text'] == 'Lemma 2.14.1'
            assert not any(e['raw_text'] == 'local_result_mentions' for b in plan['blocked'] for e in b['evidence'])
            whole = await call('workspace_plan_external_imports_for_paper', paper_id='local:tex')
            assert len(whole['blocked_groups']) == 1 and len(whole['blocked']) > 1
            for value in (-1, 6, True):
                result = await session.call_tool('workspace_get_source_slice', {'result_id': 'local:tex::base', 'context': value})
                assert result.is_error
                records.append({'tool': 'workspace_get_source_slice', 'arguments': {'context': value}, 'response': result.model_dump(mode='json')})

            if args.root_pdf:
                await call('workspace_add_pdf_paper', path=str(args.root_pdf.resolve()), paper_id='local:root')
                pages = []
                for offset in (0, 50):
                    pages += await call('workspace_list_results', paper_id='local:root', limit=50, offset=offset)
                counts = {kind: sum(r['kind'] == kind for r in pages) for kind in ('theorem', 'lemma', 'proposition')}
                assert counts == {'theorem': 14, 'lemma': 14, 'proposition': 5}, counts
                save(output / 'root-input.json', {'path': str(args.root_pdf), 'sha256': hashlib.sha256(args.root_pdf.read_bytes()).hexdigest(), 'counts': counts})
                for detail in ('full', 'compact'):
                    await call('workspace_get_dependency_reading', paper_id='local:root',
                               target_result_id='local:root::pdf:theorem:1.1', detail=detail)
            if args.legacy_db:
                copied = output / 'legacy-copy.sqlite3'
                with sqlite3.connect(args.legacy_db.resolve().as_uri() + '?mode=ro', uri=True) as original:
                    with sqlite3.connect(copied) as target:
                        original.backup(target)
                await call('open_workspace', path=str(copied))
                papers = await call('workspace_list_papers')
                paper_id = papers[0]['paper_id']
                results = await call('workspace_list_results', paper_id=paper_id)
                result_id = next(r['result_id'] for r in results if r.get('visible_number') == '1.1' and r['kind'] == 'theorem')
                source = await call('workspace_get_source_slice', result_id=result_id)
                await call('workspace_read_source_blocks', **source['source_reading']['arguments'])
                for detail in ('full', 'compact'):
                    await call('workspace_get_dependency_reading', paper_id=paper_id, target_result_id=result_id, detail=detail)
            save(output / 'mcp-responses.json', records)
    # An actual CLI selected-target call against the fresh fixture workspace.
    argv = [cli, 'get-dependency-reading', str(db), 'local:closed', '--target-result-id',
            'local:closed::pdf:theorem:1.2', '--detail', 'compact']
    result = subprocess.run(argv, cwd=output, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
    save(output / 'cli-selected.json', {'argv': argv, 'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['detail'] == 'compact'
    save(output / 'metrics.json', metrics)
    save(output / 'summary.json', {'status': 'passed', 'version': '1.2.2', 'interpreter': sys.executable,
                                 'cli': cli, 'tool_calls': len(records), 'network_used': False})
    print(json.dumps({'status': 'passed', 'output': str(output), 'calls': len(records)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root-pdf', type=Path)
    parser.add_argument('--legacy-db', type=Path)
    asyncio.run(asyncio.wait_for(verify(parser.parse_args()), timeout=300))
