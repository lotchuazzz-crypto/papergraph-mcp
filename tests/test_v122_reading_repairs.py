from contextlib import closing
import asyncio
import json

import pytest

from papergraph.evidence import SourceSpanEvidence
from papergraph.evidence_extractors import build_pdf_evidence_document
from papergraph.workspace import Workspace
from papergraph import server


def document(*, closed=True):
    texts = ['Lemma 1.1. Base case.', 'Proof. Direct. QED.',
             'Theorem 1.2. Long assertion.', 'Proof. We proceed in several steps.']
    texts += [f'Step {i}: intermediate reasoning.' for i in range(30)]
    texts[20] = 'DEPENDENCY_MIDDLE. Apply Lemma 1.1 and Lemma 9.9.'
    texts += ['The argument concludes. QED.' if closed else 'The argument continues.']
    texts += ['Unrelated prose refers to Lemma 8.8.']
    spans = tuple(SourceSpanEvidence('local:long', 'pdf', 'long.pdf', i // 10 + 1, i % 10,
                   0, len(text), None, text, 'pdf_text_block', 1.0) for i, text in enumerate(texts))
    return build_pdf_evidence_document('local:long', 'long.pdf', spans)


def test_unanchored_long_proof_middle_and_all_raw_blocks_reachable_after_restart(tmp_path):
    doc = document(closed=False)
    db = tmp_path / 'reading.sqlite3'
    with closing(Workspace.open(db)) as ws:
        ws.import_evidence_document(doc)
        proof = ws.get_result_proof(doc.results[1].result_id)['known']['proof']
        assert proof['text_coverage']['complete'] is False
        locator = ws.get_source_slice(proof_id=proof['proof_id'])['source_reading']['arguments']['span_id']
        assert isinstance(locator, str) and locator
        # Emulates v1.2.2's null-ID source rows; no migration/reimport is required.
        assert ws._connection.execute('SELECT count(*) FROM source_spans WHERE span_id IS NULL').fetchone()[0]
    with closing(Workspace.open(db)) as ws:
        seen, args = [], {'span_id': locator, 'limit': 5}
        while args:
            page = ws.read_source_blocks(**args)
            assert len(page['blocks']) <= 5
            assert page['proof_ownership'] == 'not_asserted'
            seen += page['blocks']
            args = page['next']['arguments'] if page['next'] else None
        assert len(seen) == len(doc.spans) - 3
        assert len({r['span_id'] for r in seen}) == len(seen)
        assert any('DEPENDENCY_MIDDLE' in r['text'] for r in seen)
        assert all(r['role'] == 'raw_source' for r in seen)
        deps = ws.get_proof_dependencies(doc.results[1].result_id)
        assert deps['known']['resolved_local_results'] == []
        assert deps['unresolved']['local_result_mentions'] == []


def test_explicit_closed_proof_includes_late_dependency_but_not_adjacent_prose(tmp_path):
    doc = document()
    proof = doc.proofs[1]
    assert len(proof.span_indices) > 20
    assert 'DEPENDENCY_MIDDLE' in proof.text and 'Unrelated prose' not in proof.text
    with closing(Workspace.open(tmp_path / 'ws.sqlite3')) as ws:
        ws.import_evidence_document(doc)
        deps = ws.get_proof_dependencies(doc.results[1].result_id)
        assert [r['visible_number'] for r in deps['known']['resolved_local_results']] == ['1.1']
        assert [m['raw_text'] for m in deps['unresolved']['local_result_mentions']] == ['Lemma 9.9']
        assert deps['proof_coverage']['association_boundary'] == 'explicit_terminal_marker'
        assert deps['proof_coverage']['complete'] is False
        plan = ws.plan_external_imports_for_result(doc.results[1].result_id)
        assert not plan['blocked']
        assert plan['unresolved_local_mentions'][0]['raw_text'] == 'Lemma 9.9'
        assert plan['unresolved_local_mentions'][0]['spans']
        queue = ws.create_reading_queue(doc.results[1].result_id)
        qplan = ws.plan_external_imports_for_queue(queue['queue_id'])
        assert not qplan['blocked']
        assert qplan['unresolved_local_mentions'][0]['raw_text'] == 'Lemma 9.9'


def test_ordinary_definition_of_is_not_a_number_but_valid_references_survive(tmp_path):
    from papergraph.project import load_project
    tex = tmp_path / 'main.tex'
    tex.write_text(r'\newtheorem{lemma}{Lemma}\begin{lemma}\label{base}Base.\end{lemma}'
        r'\begin{proof}By the definition of even, definition of odd. '
        r'Apply Lemma 2.14.1, Definition A and \ref{missing}.\end{proof}')
    with closing(Workspace.open(tmp_path / 'ws.sqlite3')) as ws:
        ws.import_project('local:tex', 'local', str(tex), None, load_project(tex))
        deps = ws.get_proof_dependencies('local:tex::base')
        mentions = deps['unresolved']['local_result_mentions']
        assert not any(m['raw_text'] == 'definition of' for m in mentions)
        assert {m['raw_text'] for m in mentions} >= {'Lemma 2.14.1', 'Definition A', r'\ref{missing}'}
        plan = ws.plan_external_imports_for_result('local:tex::base')
        assert not plan['blocked']
        assert {m['raw_text'] for m in plan['unresolved_local_mentions']} == {m['raw_text'] for m in mentions}


def test_schema_and_runtime_bounds_are_consistent(tmp_path):
    schemas = {tool.name: tool.input_schema for tool in asyncio.run(server.mcp.list_tools())}
    context = schemas['workspace_get_source_slice']['properties']['context']
    assert (context['minimum'], context['maximum']) == (0, 5)
    limit = schemas['workspace_read_source_blocks']['properties']['limit']
    assert (limit['minimum'], limit['maximum']) == (1, 50)
    candidate = schemas['workspace_get_dependency_reading']['properties']['max_candidates']
    assert (candidate['minimum'], candidate['maximum']) == (1, 20)
    with closing(Workspace.open(tmp_path / 'ws.sqlite3')) as ws:
        ws.import_evidence_document(document())
        rid = 'local:long::pdf:theorem:1.2'
        for value in (0, 5):
            ws.get_source_slice(result_id=rid, context=value)
        for value in (-1, 6, True, 1.2):
            with pytest.raises(ValueError):
                ws.get_source_slice(result_id=rid, context=value)


def test_compact_reading_keeps_access_to_full_evidence_without_catalog(tmp_path):
    with closing(Workspace.open(tmp_path / 'ws.sqlite3')) as ws:
        ws.import_evidence_document(document())
        rid = 'local:long::pdf:theorem:1.2'
        full = ws.get_dependency_reading('local:long', rid)
        compact = ws.get_dependency_reading('local:long', rid, detail='compact')
        assert full['results'] and compact['results'] == []
        assert compact['main_result_candidates'] == []
        assert ws.get_dependency_reading(**compact['full_evidence']['arguments']) == full
        assert len(json.dumps(compact)) < len(json.dumps(full)) * .75
        assert compact['reading_path']['edge_evidence']
        def accessors(value):
            if isinstance(value, dict):
                if 'evidence_access' in value:
                    yield value['evidence_access']
                for child in value.values():
                    yield from accessors(child)
            elif isinstance(value, list):
                for child in value:
                    yield from accessors(child)
        handles = list(accessors(compact))
        assert handles
        for handle in handles:
            assert ws.get_evidence(**handle['arguments'])


def test_blocker_display_groups_all_evidence_and_keeps_legacy_ids(tmp_path):
    from papergraph.project import load_project
    from papergraph.evidence_triage import build_evidence_triage
    tex = tmp_path / 'main.tex'
    tex.write_text(r'\newtheorem{theorem}{Theorem}\begin{theorem}\label{main}Main.\end{theorem}'
        r'\begin{proof}Apply \cite[Theorem 1]{external}.\end{proof}\bibliography{refs}')
    (tmp_path / 'refs.bib').write_text('@article{external,title={External target},year={2000}}')
    with closing(Workspace.open(tmp_path / 'ws.sqlite3')) as ws:
        ws.import_project('local:tex', 'local', str(tex), None, load_project(tex))
        plan = ws.plan_external_imports_for_paper('local:tex')
        assert len(plan['blocked']) > 1 and len(plan['blocked_groups']) == 1
        group, = plan['blocked_groups']
        assert set(group['blocked_ids']) == {b['blocked_id'] for b in plan['blocked']}
        assert {e['id'] for e in group['evidence']} == {e['id'] for b in plan['blocked'] for e in b['evidence']}
        triage = build_evidence_triage(ws.get_paper_map('local:tex'))
        assert len(triage['external_blockers']) == 1
        assert triage['counts']['external_blocked_count'] == 1
        assert len([a for a in triage['next_actions'] if a['kind'] == 'resolve_external_blocker']) == 1
        from papergraph.workspace import _blocked_external_reference
        for old in group['blocked_ids']:
            assert _blocked_external_reference(plan, old)['blocked_id'] == old


def test_new_search_ids_are_bounded_and_legacy_snapshot_still_loads(tmp_path):
    from papergraph.reference_search import search_run_id, candidate_id_for
    long = 'bibliography ' * 300
    run = search_run_id('local:test', long, {'title_hint': long}, 3)
    candidate = candidate_id_for('local:test', long, {'title': long})
    assert len(run) < 100 and len(candidate) < 100
    assert run == search_run_id('local:test', long, {'title_hint': long}, 3)
    assert run != search_run_id('local:test', long, {'title_hint': long}, 4)


@pytest.mark.parametrize('boundary', ['Theorem 2.1. New result.', 'Proof. A different proof.',
                                     '2. New section', 'References'])
def test_proof_association_does_not_cross_explicit_boundaries(boundary):
    texts = ['Theorem 1.1. Claim.', 'Proof. Start.', 'An incomplete step.', boundary,
             'Apply Lemma 9.9. QED.']
    spans = tuple(SourceSpanEvidence('local:bound', 'pdf', 'bound.pdf', 1, i,
                  0, len(t), None, t, 'pdf_text_block', 1.0) for i, t in enumerate(texts))
    doc = build_pdf_evidence_document('local:bound', 'bound.pdf', spans)
    assert doc.proofs[0].span_indices == (1,)
    assert 'Lemma 9.9' not in doc.proofs[0].text


def test_blocker_aggregation_never_merges_same_key_from_different_papers():
    from papergraph.external_aggregation import aggregate_blockers
    items = [{'blocked_id': str(i), 'reason': 'missing_arxiv_id', 'evidence': [
        {'kind': 'citation_mention', 'id': f'{paper}::cite:1', 'paper_id': paper,
         'citation_key': 'same', 'source': 'test', 'raw_text': '[same]'}]}
        for i, paper in enumerate(('local:a', 'local:b'))]
    assert len(aggregate_blockers(items)) == 2
