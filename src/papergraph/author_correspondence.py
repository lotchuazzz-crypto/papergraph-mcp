"""Bounded proof navigation through author-declared result correspondence.

This relation records a source declaration, never verified mathematical equality.
"""
from __future__ import annotations

import re

RELATION = 'author_declared_correspondence'
MAX_CORRESPONDENCE_HOPS = 8
DECLARATION_RE = re.compile(
    r'^(?:Theorem|Lemma|Proposition|Corollary|Claim)\s+[A-Za-z]?\d+(?:\.\d+)*'
    r'\.?\s*\(\s*=\s*(?P<kind>Theorem|Lemma|Proposition|Corollary|Claim)'
    r'\s+(?P<number>[A-Za-z]?\d+(?:\.\d+)*)\s*\)', re.I)


def declared_target(statement):
    match = DECLARATION_RE.match(' '.join(statement.split()))
    return (match['kind'].lower(), match['number']) if match else None


def resolve_proof_entry(workspace, result_id):
    current, visited, trail = result_id, [], []
    base = {'requested_result_id': result_id, 'correspondences': trail,
            'hop_limit': MAX_CORRESPONDENCE_HOPS,
            'mathematical_equivalence_verified': False}
    for depth in range(MAX_CORRESPONDENCE_HOPS + 1):
        if current in visited:
            return {**base, 'status': 'correspondence_cycle',
                    'cycle_path': visited[visited.index(current):] + [current], 'proof': None}
        visited.append(current)
        proof = workspace._direct_proof_for_result(current)
        if proof is not None:
            return {**base, 'status': 'direct' if not trail else 'corresponding_proof',
                    'proof_result_id': current, 'proof': proof}
        result = workspace.get_result(current)
        target = declared_target(result['statement'])
        if target is None:
            return {**base, 'status': 'not_found' if not trail else 'corresponding_proof_not_found', 'proof': None}
        kind, number = target
        candidates = [row[0] for row in workspace._connection.execute(
            'SELECT result_id FROM results WHERE paper_id = ? AND normalized_kind = ? '
            'AND lower(visible_number) = lower(?) ORDER BY result_id',
            (result['paper_id'], kind, number))]
        declaration = {'relation': RELATION, 'source_result_id': current,
                       'target_kind': kind, 'target_number': number,
                       'candidate_result_ids': candidates,
                       'spans': workspace.get_evidence(current)['spans']}
        if len(candidates) != 1:
            trail.append(declaration)
            return {**base, 'status': 'ambiguous_correspondence' if candidates else 'missing_correspondence_target',
                    'candidate_result_ids': candidates, 'proof': None}
        if depth == MAX_CORRESPONDENCE_HOPS:
            return {**base, 'status': 'correspondence_hop_limit', 'proof': None}
        target_id = candidates[0]
        row = workspace._connection.execute(
            'SELECT edge_id FROM evidence_edges WHERE source_id = ? AND target_id = ? '
            'AND relation = ? ORDER BY edge_id LIMIT 1', (current, target_id, RELATION)).fetchone()
        if row is None:
            trail.append(declaration)
            return {**base, 'status': 'correspondence_evidence_not_imported', 'proof': None}
        evidence = workspace.get_evidence(row[0])
        trail.append({**declaration, 'edge_id': row[0], 'target_result_id': target_id,
                      'spans': evidence['spans']})
        current = target_id
    raise AssertionError('unreachable correspondence traversal')


def entry_payload(entry):
    return {key: value for key, value in entry.items() if key != 'proof'}


def entry_warning(entry):
    if entry['status'] == 'direct' or entry['status'] == 'not_found':
        return []
    return [f"Author-declared correspondence proof navigation: {entry['status']}; "
            'the proof belongs to the indicated target, and mathematical equivalence is not verified.']
