"""Opt-in reading view; full payload and original evidence IDs stay accessible."""
from copy import deepcopy


def compact_reading(payload):
    payload = deepcopy(payload)
    paper_id = payload['paper']['paper_id']
    target = payload['selection']['target_result_id']
    payload['full_evidence'] = {'tool': 'workspace_get_dependency_reading', 'arguments': {
        'paper_id': paper_id, 'target_result_id': target, 'recursive': payload['reading_path']['recursive'], 'detail': 'full'}}
    payload['result_catalog'] = {'tool': 'workspace_list_results', 'arguments': {'paper_id': paper_id, 'limit': 50, 'offset': 0}}
    # Each occurrence retains its ID and an executable evidence accessor. Full
    # proof/correspondence/coverage warnings stay in the selected path.
    def reduce(value):
        if isinstance(value, list):
            return [reduce(v) for v in value]
        if not isinstance(value, dict):
            return value
        omitted = {'spans', 'source_spans', 'span_trail'}
        if 'result_id' in value and 'statement' in value:
            omitted.add('statement')
        if 'proof_id' in value and 'text' in value:
            omitted.add('text')
        result = {key: reduce(v) for key, v in value.items() if key not in omitted}
        evidence_id = value.get('evidence_id') or value.get('mention_id')
        if evidence_id:
            result['evidence_access'] = {'tool': 'workspace_get_evidence', 'arguments': {'node_or_edge_id': evidence_id}}
        return result
    payload = reduce(payload)
    plan = payload['external_import_plan']
    plan['blocked'] = [{'group_id': g['group_id'], 'blocked_ids': g['blocked_ids'],
                        'reason': g['reason'], 'citation_keys': g['citation_keys'],
                        'evidence_ids': list(dict.fromkeys(e['id'] for e in g['evidence']))}
                       for g in plan.pop('blocked_groups')]
    plan['blocked_count_basis'] = 'unique_external_targets_in_compact_view'
    for candidate in plan['candidates']:
        candidate['evidence_ids'] = list(dict.fromkeys(e['id'] for e in candidate.pop('evidence')))
    return payload
