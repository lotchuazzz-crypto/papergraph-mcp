from papergraph.evidence import SourceSpanEvidence
from papergraph.evidence_extractors import build_pdf_evidence_document
from papergraph.workspace import Workspace


def import_blocks(tmp_path, texts):
    spans = tuple(SourceSpanEvidence(
        paper_id='local:correspondence', source_type='pdf', source_ref='paper.pdf',
        page=1, block_index=index, start_offset=0, end_offset=len(text), bbox=None,
        text=text, method='pdf_text_block', confidence=1.0,
    ) for index, text in enumerate(texts))
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    workspace.import_evidence_document(build_pdf_evidence_document(
        'local:correspondence', 'paper.pdf', spans))
    return workspace


def rid(number, kind='theorem'):
    return f'local:correspondence::pdf:{kind}:{number}'


def test_explicit_correspondence_preserves_nodes_and_supplies_traced_proof_entry(tmp_path):
    workspace = import_blocks(tmp_path, [
        'Theorem 1.1 (= Theorem 3.1). Introductory assertion.',
        'Lemma 2.6. Base assertion.', 'Proof of Lemma 2.6. Direct.',
        'Proposition 2.17. Prerequisite.', 'Proof of Proposition 2.17. By Lemma 2.6.',
        'Theorem 3.1. Detailed assertion.', 'Proof of Theorem 3.1. By Proposition 2.17.',
    ])
    try:
        assert len(workspace.list_results()) == 4
        proof = workspace.get_result_proof(rid('1.1'))
        assert proof['known']['proof']['result_id'] == rid('3.1')
        entry = proof['proof_entry']
        assert entry['status'] == 'corresponding_proof'
        assert entry['mathematical_equivalence_verified'] is False
        edge = entry['correspondences'][0]
        assert edge['relation'] == 'author_declared_correspondence'
        assert edge['spans'][0]['block_index'] == 0
        direct = workspace.get_proof_dependencies(rid('1.1'))
        assert [r['result_id'] for r in direct['known']['resolved_local_results']] == [rid('2.17', 'proposition')]
        recursive = workspace.get_proof_dependencies(rid('1.1'), recursive=True)
        assert {r['result_id'] for r in recursive['known']['resolved_local_results']} == {
            rid('2.17', 'proposition'), rid('2.6', 'lemma')}
        path = workspace.get_result_reading_path(rid('1.1'))
        assert [r['result_id'] for r in path['bottom_up']] == [
            rid('2.6', 'lemma'), rid('2.17', 'proposition'), rid('1.1')]
        assert path['edge_evidence'][0]['proof_result_id'] == rid('3.1')
        assert 'corresponding_proof' in path['edge_evidence'][0]['relation']
        report = workspace.export_paper_reading_report('local:correspondence')
        assert 'declared correspondence' in report['markdown']
        assert f"`{rid('1.1')}` explicitly mentions" not in report['markdown']
        assert report['evidence_triage']['supported_local_chains'][0]['proof_result_id'] == rid('3.1')
        context = workspace.export_result_reading_context(rid('1.1'))
        assert context['proof']['proof_entry']['proof_result_id'] == rid('3.1')
        assert context['dependencies']['proof_entry']['correspondences'][0]['edge_id'] == edge['edge_id']
        bundle = workspace.export_reading_bundle('local:correspondence')
        assert bundle['dependency_index'][rid('1.1')]['proof_entry']['proof_result_id'] == rid('3.1')
        queue = workspace.create_reading_queue(rid('1.1'))
        full_queue = workspace.get_reading_queue(queue['queue_id'])
        result_items = [item['target_id'] for item in full_queue['items'] if item['target_kind'] == 'result_id']
        # Queues retain their exploration order; the path supplies prerequisite order.
        assert result_items == [rid('1.1'), rid('2.17', 'proposition'), rid('2.6', 'lemma')]
        assert any(item['target_id'] == proof['known']['proof']['proof_id']
                   for item in full_queue['items'] if item['target_kind'] == 'proof_id')
    finally:
        workspace.close()


def test_ambiguous_correspondence_never_selects_duplicate_number(tmp_path):
    workspace = import_blocks(tmp_path, [
        'Theorem 1.1 (= Theorem 3.1). Introductory assertion.',
        'Theorem 3.1. First assertion.', 'Proof. Direct.',
        'Theorem 3.1. Another assertion.', 'Proof. Direct.',
    ])
    try:
        result = workspace.get_result_proof(rid('1.1'))
        assert result['known'] == {}
        assert result['proof_entry']['status'] == 'ambiguous_correspondence'
        assert len(result['proof_entry']['candidate_result_ids']) == 2
    finally:
        workspace.close()


def test_correspondence_cycle_and_missing_target_stay_unresolved(tmp_path):
    workspace = import_blocks(tmp_path, [
        'Theorem 1.1 (= Theorem 2.1). First.',
        'Theorem 2.1 (= Theorem 1.1). Second.',
        'Theorem 1.2 (= Theorem 9.9). Missing.',
    ])
    try:
        assert workspace.get_result_proof(rid('1.1'))['proof_entry']['status'] == 'correspondence_cycle'
        assert workspace.get_result_proof(rid('1.2'))['proof_entry']['status'] == 'missing_correspondence_target'
        assert workspace.get_proof_dependencies(rid('1.1'))['known']['resolved_local_results'] == []
        path = workspace.get_result_reading_path(rid('1.1'))
        assert path['order_status'] == 'correspondence_blocked'
        assert path['bottom_up'] == []
    finally:
        workspace.close()


def test_correspondence_multi_hop_is_bounded(tmp_path):
    texts = [f'Theorem {i}.1 (= Theorem {i+1}.1). Assertion.' for i in range(1, 11)]
    workspace = import_blocks(tmp_path, texts + ['Theorem 11.1. End.', 'Proof. Direct.'])
    try:
        assert workspace.get_result_proof(rid('1.1'))['proof_entry']['status'] == 'correspondence_hop_limit'
        assert workspace.get_result_proof(rid('9.1'))['proof_entry']['status'] == 'corresponding_proof'
    finally:
        workspace.close()


def test_ordinary_reference_does_not_create_correspondence(tmp_path):
    workspace = import_blocks(tmp_path, [
        'Theorem 1.1. This is related to Theorem 3.1.',
        'Theorem 3.1. Assertion.', 'Proof. Direct.',
    ])
    try:
        assert workspace.get_result_proof(rid('1.1'))['known'] == {}
    finally:
        workspace.close()


def test_own_proof_takes_priority_over_declared_correspondence(tmp_path):
    workspace = import_blocks(tmp_path, [
        'Theorem 1.1 (= Theorem 3.1). Introductory assertion.',
        'Proof of Theorem 1.1. Direct argument.',
        'Theorem 3.1. Detailed assertion.', 'Proof of Theorem 3.1. Another argument.',
    ])
    try:
        result = workspace.get_result_proof(rid('1.1'))
        assert result['proof_entry']['status'] == 'direct'
        assert result['proof_entry']['correspondences'] == []
        assert result['known']['proof']['result_id'] == rid('1.1')
    finally:
        workspace.close()
