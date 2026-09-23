"""Versioned, evidence-scoped matching; scores never authorize acquisition."""
from __future__ import annotations

import copy
import re
from difflib import SequenceMatcher
from papergraph.reference_identity import (
    group_reference_records, normalize_match_text as norm, record_identifiers, stable_key,
)

OUTCOMES = {'ok', 'empty', 'partial', 'timeout', 'rate_limited', 'unavailable', 'invalid_response'}
_ACTIONS = {
    'no_candidates': ['provide_identifier', 'refresh_search'],
    'provider_failure': ['refresh_search'], 'partial_provider_failure': ['refresh_search', 'review_candidates'],
    'insufficient_metadata': ['provide_identifier'], 'identifier_conflict': ['review_candidates'],
    'version_conflict': ['review_candidates'], 'ambiguous_candidates': ['review_candidates'],
    'no_importable_source': ['provide_local_pdf', 'skip_reference'],
}
_MESSAGES = {
    'no_candidates': 'No candidates returned; this does not establish that the work does not exist.',
    'provider_failure': 'No provider completed a usable search. Try refreshing later.',
    'partial_provider_failure': 'Some providers did not complete; available evidence may be incomplete.',
    'insufficient_metadata': 'Reference evidence is insufficient to establish an identity.',
    'identifier_conflict': 'Identifier or bibliographic evidence conflicts; select an explicit target.',
    'version_conflict': 'Explicit arXiv versions disagree; review the requested version.',
    'ambiguous_candidates': 'Competing identities require review, including candidates outside the display limit.',
    'no_importable_source': 'No supported importable source was found. This is not evidence of a paywall.',
}


def _boundary(kind, refs=(), candidate_id=None):
    result = {'kind': kind, 'message': _MESSAGES[kind], 'evidence_refs': sorted(set(refs)),
              'next_actions': _ACTIONS[kind]}
    if candidate_id:
        result['candidate_id'] = candidate_id
    return result


def _author(name):
    parts = re.findall(r'[^\W\d_]+', norm(name))
    if not parts:
        return '', ''
    if ',' in str(name):
        family, given = str(name).split(',', 1)
        return norm(family), ''.join(p[0] for p in re.findall(r'[^\W\d_]+', norm(given)))
    return parts[-1], ''.join(p[0] for p in parts[:-1])


def authors_compatible(left, right):
    pairs = [(a, b) for a in map(_author, left) for b in map(_author, right) if a[0] and a[0] == b[0]]
    if not pairs:
        return False
    return all(not a[1] or not b[1] or a[1].startswith(b[1]) or b[1].startswith(a[1]) for a, b in pairs)


def _provider_results(results):
    cleaned = []
    for result in results:
        if not isinstance(result, dict):
            result = {'provider': 'unknown', 'outcome': 'invalid_response'}
        records = result.get('records', [])
        valid = []
        invalid = not isinstance(records, list)
        for record in records if isinstance(records, list) else []:
            if (not isinstance(record, dict) or
                any(not isinstance(record[k], (str, int)) for k in ('title', 'year', 'doi', 'arxiv_id', 'arxiv_version') if record.get(k) is not None) or
                ('authors' in record and not (isinstance(record['authors'], list) and all(isinstance(a, str) for a in record['authors'])))):
                invalid = True
            else:
                valid.append(copy.deepcopy(record))
        outcome = result.get('outcome', 'unavailable' if result.get('warnings') else 'ok' if valid else 'empty')
        if outcome not in OUTCOMES:
            outcome = 'invalid_response'
        if invalid:
            outcome = 'partial' if valid else 'invalid_response'
        # Outcomes, not untrusted exception text, are user-facing diagnostics.
        if result.get('warnings') and outcome in {'ok', 'empty'}:
            outcome = 'partial' if valid else 'unavailable'
        cleaned.append({'provider': str(result.get('provider') or 'unknown'), 'records': valid,
                        'outcome': outcome, 'warnings': [] if outcome in {'ok', 'empty'} else [outcome]})
    return sorted(cleaned, key=stable_key)


def _assess(query, group, healthy):
    target = group['target']
    records = [m['record'] for m in group['members']]
    refs = [m['record_key'] for m in group['members']]
    conflicts = copy.deepcopy(group['conflicts'])
    matched, missing = [], []
    def conflict(code, field, values):
        conflicts.append({'code': code, 'field': field, 'values': values, 'evidence_refs': refs})
    hints = query.get('identifier_hints', [])
    source_ids = {i['identity'] for i in hints if i.get('exact_eligible')}
    ids = set(group['identifiers'])
    exact = bool(source_ids & ids)
    if source_ids and source_ids - ids:
        conflict('identifier_conflict', 'identifiers', sorted(source_ids | ids))
    for hint in hints:
        if hint.get('warnings'):
            conflict('identifier_conflict', 'source_identifier', [hint.get('raw')])
        if hint.get('version') and hint.get('identity') in ids:
            versions = {i['version'] for r in records for i in record_identifiers(r) if i['identity'] == hint['identity']}
            if versions != {hint['version']}:
                conflict('version_conflict', 'arxiv_version', sorted(str(v) for v in versions | {hint['version']}))
    flags = {}
    ratio = 0.0
    for field, source_key in [('title', 'title_hint'), ('authors', 'author_hints'), ('year', 'year_hint')]:
        source = query.get(source_key)
        values = [r[field] for r in records if r.get(field)]
        if not source:
            missing.append({'field': field, 'side': 'query'})
        if not values:
            missing.append({'field': field, 'side': 'candidate'})
        compatible = authors_compatible if field == 'authors' else lambda a, b: norm(a) == norm(b)
        # Within-provider and cross-provider contradictions survive display selection.
        if values and any(not compatible(values[0], v) for v in values[1:]):
            conflict('metadata_conflict', field, values)
        equivalent = bool(source and values and all(compatible(source, v) for v in values))
        flags[field] = equivalent
        if source and values:
            if field == 'title':
                ratio = min(SequenceMatcher(None, norm(source), norm(v)).ratio() for v in values)
            relation = 'exact' if all(source == v for v in values) else 'normalized_equivalent' if equivalent else 'fuzzy' if field == 'title' and ratio >= .85 else 'conflicting'
            matched.append({'field':field, 'relation':relation, 'query_value':source,
                            'candidate_value':values, 'evidence_refs':refs})
            if not equivalent and not (field == 'title' and ratio >= .85):
                conflict('metadata_conflict', field, [source, *values])
    if exact:
        matched.append({'field':'identifiers','relation':'exact','query_value':sorted(source_ids),
                        'candidate_value':sorted(ids),'evidence_refs':refs})
    if any(r.get('is_retracted') or r.get('retracted') or r.get('withdrawn') for r in records):
        conflict('retraction_or_withdrawal', 'status', ['reported'])
    providers = sorted({m['provider'] for m in group['members']})
    corroborated = all(flags.values()) and len(set(providers) - {'source'}) >= 2
    confidence = ('ambiguous' if conflicts else 'strong' if exact or corroborated else
                  'plausible' if flags['title'] or ratio >= .85 and (flags['authors'] or flags['year']) else 'weak')
    identity_status = ('conflict' if conflicts else 'exact_identifier' if exact else
                       'corroborated_metadata' if corroborated else 'partial_match' if confidence == 'plausible' else 'insufficient_evidence')
    importable = bool(target.get('arxiv_id')) and not conflicts
    reasons = sorted({c['code'] for c in conflicts} or {identity_status})
    denial = reasons if conflicts else ['insufficient_identity_evidence'] if confidence != 'strong' else ['partial_provider_failure'] if not exact and not healthy else ['no_importable_source'] if not importable else []
    assessment = {'identity_status':identity_status, 'matched_fields':matched, 'missing_fields':missing,
                  'conflicts':conflicts, 'reason_codes':reasons,
                  'source_status':'review_required' if conflicts else 'arxiv_importable' if importable else 'metadata_only',
                  'auto_selection':{'eligible':not denial, 'reason_codes':denial or reasons, 'policy_version':'unique_strong_v2'}}
    score = float(8*exact + (4 if flags['title'] else 2 if ratio >= .85 else 0) + flags['authors'] + flags['year'])
    return {'candidate_schema_version':2, 'candidate_id':'reference-candidate:' + group['group_key'],
            'target':target, 'score':score, 'confidence':confidence, 'evidence':reasons,
            'providers':providers, 'provider_records':group['members'], 'warnings':sorted({c['code'] for c in conflicts}),
            'assessment':assessment, '_sort':(-int(exact), -int(flags['title']), -int(flags['authors']), -int(flags['year']), -ratio, group['group_key'])}


def rank_candidates_v2(query: dict, provider_results: list[dict], max_candidates: int = 10) -> dict:
    if type(max_candidates) is not int or max_candidates < 1:
        raise ValueError('max_candidates must be a positive integer')
    results = _provider_results(provider_results)
    outcomes = [{'provider':r['provider'], 'outcome':r['outcome']} for r in results]
    failures = [o for o in outcomes if o['outcome'] not in {'ok','empty'}]
    candidates = [_assess(query, g, not failures) for g in group_reference_records(results)]
    strong = [c for c in candidates if c['confidence'] == 'strong']
    blocking = []
    if len(strong) > 1:
        blocking.append({'kind':'ambiguous_candidates','candidate_ids':sorted(c['candidate_id'] for c in strong)})
        for candidate in strong:
            candidate['confidence'] = 'ambiguous'
            candidate['assessment']['reason_codes'] = sorted(set(candidate['assessment']['reason_codes'] + ['ambiguous_candidates']))
    # Conflicting identity components can hide the true match: fail closed globally.
    for candidate in candidates:
        if candidate['assessment']['conflicts']:
            blocking.append({'kind':'identifier_conflict','candidate_ids':[candidate['candidate_id']]})
    if blocking:
        for candidate in candidates:
            candidate['assessment']['auto_selection'].update(eligible=False, reason_codes=['ambiguous_candidates'])
    candidates.sort(key=lambda c: ({'strong':0,'plausible':1,'ambiguous':2,'weak':3}[c['confidence']], c['_sort']))
    for candidate in candidates:
        del candidate['_sort']
    boundaries = []
    if failures:
        boundaries.append(_boundary('provider_failure' if len(failures) == len(outcomes) else 'partial_provider_failure'))
    if not candidates and not failures:
        boundaries.append(_boundary('no_candidates'))
    if blocking:
        boundaries.append(_boundary('ambiguous_candidates', [cid for b in blocking for cid in b['candidate_ids']]))
    for c in candidates:
        a = c['assessment']
        code = 'version_conflict' if any(x['code'] == 'version_conflict' for x in a['conflicts']) else 'identifier_conflict' if a['conflicts'] else 'no_importable_source' if a['source_status'] == 'metadata_only' else 'insufficient_metadata' if c['confidence'] != 'strong' else None
        if code:
            boundaries.append(_boundary(code, [m['record_key'] for m in c['provider_records']], c['candidate_id']))
    total = len(candidates)
    returned = candidates[:max_candidates]
    return {'search_schema_version':2, 'resolver_version':'deterministic_v2', 'query':query,
            'provider_outcomes':outcomes, 'provider_warnings':[{'provider':o['provider'],'warning':o['outcome']} for o in failures],
            'candidates':returned, 'boundaries':boundaries,
            'summary':{'candidate_count':len(returned), 'total_candidate_count':total, 'returned_candidate_count':len(returned),
                       'truncated':total > len(returned), 'blocking_conflicts':sorted(blocking,key=stable_key),
                       'strong_candidate_count':sum(c['confidence']=='strong' for c in returned),
                       'ambiguous_candidate_count':sum(c['confidence']=='ambiguous' for c in returned),
                       'boundary_count':len(boundaries), 'provider_warning_count':len(failures)}}


def select_v2(search: dict) -> dict:
    denied = {'eligible':False, 'reason_codes':['incomplete_assessment'], 'policy_version':'unique_strong_v2'}
    summary = search.get('summary', {})
    candidates = search.get('candidates', [])
    if search.get('resolver_version') != 'deterministic_v2' or not {'total_candidate_count','returned_candidate_count','truncated','blocking_conflicts'} <= summary.keys():
        return denied
    if summary['returned_candidate_count'] != len(candidates):
        return denied
    if summary['blocking_conflicts']:
        return {**denied, 'reason_codes':['ambiguous_candidates']}
    eligible = []
    reasons = []
    for candidate in candidates:
        a = candidate.get('assessment')
        if not a or 'auto_selection' not in a:
            return denied
        reasons.extend(a['auto_selection']['reason_codes'])
        if a['auto_selection'].get('eligible'):
            if candidate['confidence'] != 'strong' or a['conflicts'] or a['source_status'] != 'arxiv_importable' or a['identity_status'] not in {'exact_identifier','corroborated_metadata'}:
                return denied
            eligible.append(candidate)
    if len(eligible) != 1:
        return {**denied, 'reason_codes': sorted(set(reasons)) or ['insufficient_identity_evidence']}
    candidate = eligible[0]
    target = candidate['target']
    identifiers = record_identifiers(target)
    arxiv = next((i for i in identifiers if i['kind']=='arxiv' and i['exact_eligible']), None)
    if not arxiv:
        return denied
    return {'eligible':True, 'policy_version':'unique_strong_v2',
            'reason_codes':candidate['assessment']['auto_selection']['reason_codes'], 'candidate':copy.deepcopy(candidate),
            'identity_target':copy.deepcopy(target),
            'target':{'kind':'arxiv', 'arxiv_id':arxiv['canonical'] + (arxiv['version'] or '')}}
