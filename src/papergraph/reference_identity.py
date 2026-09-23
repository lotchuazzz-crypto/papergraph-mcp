"""Conservative identity normalization and order-independent record grouping."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit, unquote

from papergraph.arxiv import extract_arxiv_id_from_url, InvalidArxivIdError
from papergraph.identity import paper_id_from_arxiv


def stable_key(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def normalize_match_text(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())


def normalize_identifier(value: str, kind: str, *, version: str | None = None) -> dict:
    result = dict(kind=kind, raw=value, canonical=None, identity=None, version=None,
                  valid=False, exact_eligible=False, warnings=[])
    if not isinstance(value, str) or kind not in {'doi', 'arxiv'}:
        result['warnings'] = ['invalid_identifier']
        return result
    text = value.strip()
    while len(text) > 1 and (text[0], text[-1]) in {('<', '>'), ('[', ']'), ('"', '"'), ('(', ')')}:
        text = text[1:-1].strip()
    warnings = result['warnings']
    try:
        if text.startswith(('https://', 'http://')):
            parsed = urlsplit(text)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                warnings.append('identifier_url_components')
            if kind == 'doi':
                if parsed.netloc.lower() not in {'doi.org', 'dx.doi.org'}:
                    raise ValueError('Unsupported DOI host')
                text = unquote(parsed.path.lstrip('/'))
            else:
                text = extract_arxiv_id_from_url(text)
        if kind == 'doi':
            text = re.sub(r'^doi:\s*', '', text, flags=re.I).casefold()
            if not re.fullmatch(r'10\.\d{4,9}/[^\s<>"{}]+', text):
                raise ValueError('Invalid DOI')
            if text.endswith(('.', ',', ';', ':')) or text.count('(') != text.count(')'):
                warnings.append('ambiguous_identifier_punctuation')
            result.update(canonical=text, identity='doi:' + text, valid=True)
        else:
            identity, embedded = paper_id_from_arxiv(text)
            if version and not re.fullmatch(r'v[1-9]\d*', str(version)):
                raise ValueError('Invalid version')
            if version and embedded and version != embedded:
                warnings.append('version_conflict')
            result.update(canonical=identity[6:], identity=identity,
                          version=embedded or version, valid=True)
    except (ValueError, TypeError, InvalidArxivIdError):
        warnings.append('invalid_identifier')
    result['warnings'] = sorted(set(warnings))
    result['exact_eligible'] = result['valid'] and not warnings
    return result


def record_identifiers(record: dict) -> list[dict]:
    return [normalize_identifier(record[field], kind,
                version=record.get('arxiv_version') if kind == 'arxiv' else None)
            for field, kind in [('doi', 'doi'), ('arxiv_id', 'arxiv')]
            if record.get(field)]


def group_reference_records(provider_results: list[dict]) -> list[dict]:
    """Use identifier connected components, never a title-inferred ID bridge."""
    members = {}
    for result in provider_results:
        for record in result.get('records', []):
            if not isinstance(record, dict) or not any(record.get(k) for k in ('doi', 'arxiv_id', 'title', 'url')):
                continue
            member = {'provider': str(result.get('provider', 'unknown')), 'record': copy.deepcopy(record)}
            key = stable_key(member)
            members[key] = {**member, 'record_key': key}
    groups = []
    for key, member in sorted(members.items()):
        record = member['record']
        ids = {i['identity'] for i in record_identifiers(record) if i['exact_eligible']}
        meta = None
        if not ids and all(record.get(f) for f in ('title', 'authors', 'year')):
            meta = stable_key([normalize_match_text(record['title']),
                               [normalize_match_text(a) for a in record['authors']], str(record['year'])])
        matched = [g for g in groups if ids & g['ids'] or (meta and meta == g['meta'])]
        group = {'ids': ids, 'meta': meta, 'members': [member]}
        for previous in matched:
            group['ids'].update(previous['ids'])
            group['members'].extend(previous['members'])
            groups.remove(previous)
        groups.append(group)
    output = []
    for g in groups:
        entries = sorted(g['members'], key=lambda m: m['record_key'])
        conflicts = []
        identifiers = [i for m in entries for i in record_identifiers(m['record'])]
        for field, values in [('doi', {i['identity'] for i in identifiers if i['valid'] and i['kind'] == 'doi'}),
                              ('arxiv_id', {i['identity'] for i in identifiers if i['valid'] and i['kind'] == 'arxiv'}),
                              ('arxiv_version', {i['version'] for i in identifiers if i['version']})]:
            if len(values) > 1:
                conflicts.append({'code': 'version_conflict' if field == 'arxiv_version' else 'identifier_conflict',
                                  'field': field, 'values': sorted(values), 'evidence_refs': [m['record_key'] for m in entries]})
        for i in identifiers:
            for warning in i['warnings']:
                conflicts.append({'code': warning, 'field': i['kind'], 'values': [i['raw']],
                                  'evidence_refs': [m['record_key'] for m in entries]})
        target = {'kind': 'metadata'}
        for field in ('title', 'authors', 'year', 'venue', 'url'):
            values = [m['record'][field] for m in entries if m['record'].get(field)]
            if values:
                target[field] = copy.deepcopy(values[0])
        if not conflicts:
            for i in identifiers:
                if i['exact_eligible']:
                    field = 'arxiv_id' if i['kind'] == 'arxiv' else 'doi'
                    target[field] = i['canonical']
                    if i['version']:
                        target['arxiv_version'] = i['version']
            target['kind'] = 'arxiv' if target.get('arxiv_id') else 'doi' if target.get('doi') else 'metadata'
        output.append({'group_key': stable_key([m['record_key'] for m in entries]),
                       'identifiers': sorted(g['ids']), 'members': entries,
                       'target': target, 'conflicts': sorted(conflicts, key=stable_key)})
    return sorted(output, key=lambda g: g['group_key'])
