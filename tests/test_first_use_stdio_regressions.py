import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_first_use_real_stdio_schema_plan_citation_and_restart(tmp_path):
    tex = tmp_path / 'main.tex'
    tex.write_text(r'\begin{theorem}\label{main}Synthetic.\end{theorem}'
                   r'\begin{proof}Apply \cite{external}.\end{proof}\bibliography{refs}')
    (tmp_path / 'refs.bib').write_text('@article{external, arxiv={2401.12346}}')
    db = tmp_path / 'reading data' / 'ws.sqlite3'
    planned = tmp_path / 'plan only' / 'ws.sqlite3'
    records = {}

    def payload(result):
        assert not result.is_error, result
        return result.structured_content or json.loads(result.content[0].text)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'papergraph.server'], env=dict(os.environ))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                init = await session.initialize()
                assert init.server_info.version == '1.2.2'
                schemas = {t.name: t.input_schema for t in (await session.list_tools()).tools}
                limits = schemas['workspace_list_results']['properties']
                assert limits['limit']['minimum'] == 1 and limits['limit']['maximum'] == 100
                assert limits['offset']['minimum'] == 0
                kinds = schemas['workspace_record_reading_checkpoint']['properties']['target_kind']['enum']
                assert 'result_id' in kinds and 'result' not in kinds
                records['schemas'] = schemas
                result = payload(await session.call_tool('workspace_plan_starter_project', {
                    'workspace_path': str(planned), 'artifact_dir': None,
                    'papers': [{'kind': 'local_tex', 'path': str(tex), 'paper_id': 'local:test'}]}))
                assert result['status'] == 'ready' and not planned.parent.exists()
                records['plan'] = result
                payload(await session.call_tool('open_workspace', {'path': str(db)}))
                payload(await session.call_tool('workspace_add_local_paper', {'path': str(tex), 'paper_id': 'local:test'}))
                rid = 'local:test::main'
                deps = payload(await session.call_tool('workspace_get_proof_dependencies', {'result_id': rid}))
                assert deps['known']['citation_mentions'][0]['raw_key'] == 'external'
                assert deps['known']['resolved_external_results'] == []
                plan = payload(await session.call_tool('workspace_plan_external_imports_for_result', {'result_id': rid}))
                assert plan['candidates'][0]['source']['arxiv_id'] == '2401.12346'
                records['dependencies'], records['target_plan'] = deps, plan
                for limit in (0, 101, True):
                    assert (await session.call_tool('workspace_list_results', {'limit': limit})).is_error
                reading = payload(await session.call_tool('workspace_create_reading_session', {'paper_id': 'local:test', 'target_result_id': rid}))
                queue = payload(await session.call_tool('workspace_create_reading_queue', {'result_id': rid}))
                sid, qid = reading['session_id'], queue['queue_id']
                assert queue['sequence_policy'] == 'exploration_queue_not_topological'
                payload(await session.call_tool('workspace_record_reading_checkpoint', {
                    'session_id': sid, 'target_kind': 'result_id', 'target_id': rid, 'status': 'reviewed'}))
                payload(await session.call_tool('workspace_add_reading_note', {
                    'session_id': sid, 'text': 'Synthetic question', 'note_type': 'question',
                    'target_kind': 'result_id', 'target_id': rid}))
                records['before'] = payload(await session.call_tool('workspace_get_reading_session', {'session_id': sid}))
                records['queue'] = payload(await session.call_tool('workspace_get_reading_queue', {'queue_id': qid}))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                payload(await session.call_tool('open_workspace', {'path': str(db)}))
                restored = payload(await session.call_tool('workspace_get_reading_session', {'session_id': sid}))
                restored_queue = payload(await session.call_tool('workspace_get_reading_queue', {'queue_id': qid}))
                assert restored == records['before']
                assert restored_queue == records['queue']
                records['after'] = restored
        (tmp_path / 'stdio-evidence.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    asyncio.run(asyncio.wait_for(run(), timeout=90))


def test_real_stdio_original_file_spans_and_bibtex_identity(tmp_path):
    main = tmp_path / 'main.tex'
    main.write_text(r'Prefix.\input{chapter}\bibliography{refs}')
    (tmp_path / 'chapter.tex').write_text(r'\begin{theorem}\label{main}Claim.\end{theorem}'
                                        r'\begin{proof}Before \input{step} after.\end{proof}')
    (tmp_path / 'step.tex').write_text(r'\cite{external}')
    actual = '@article{external,title={Actual},arxiv={2001.00001}}'
    (tmp_path / 'refs.bib').write_text('@comment{external, ignored}\n'
        '@article{other,title={Example @article{external,title={Decoy},arxiv={2401.99999}}}}\n' + actual)
    records = {}

    def payload(result):
        assert not result.is_error, result
        return result.structured_content or json.loads(result.content[0].text)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'papergraph.server'], env=dict(os.environ))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                payload(await session.call_tool('open_workspace', {'path': str(tmp_path / 'ws.sqlite3')}))
                payload(await session.call_tool('workspace_add_local_paper', {'path': str(main), 'paper_id': 'local:span'}))
                rid = 'local:span::main'
                deps = payload(await session.call_tool('workspace_get_proof_dependencies', {'result_id': rid}))
                assert deps['known']['resolved_external_results'] == []
                plan = payload(await session.call_tool('workspace_plan_external_imports_for_result', {'result_id': rid}))
                assert plan['candidates'][0]['source']['arxiv_id'] == '2001.00001'
                records['dependencies'], records['plan'] = deps, plan
                mention = deps['known']['citation_mentions'][0]['mention_id']
                for target in (rid, 'local:span::proof:1', 'local:span::bib:external', mention):
                    evidence = payload(await session.call_tool('workspace_get_evidence', {'node_or_edge_id': target}))
                    assert evidence['spans']
                    for span in evidence['spans']:
                        raw = (tmp_path / span['source_ref']).read_text(encoding='utf-8')
                        assert raw[span['start_offset']:span['end_offset']] == span['excerpt']
                    records[target] = evidence
                assert records['local:span::bib:external']['spans'][0]['excerpt'] == actual
        (tmp_path / 'original-span-stdio-evidence.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    asyncio.run(asyncio.wait_for(run(), timeout=90))
