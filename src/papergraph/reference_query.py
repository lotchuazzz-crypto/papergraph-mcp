"""Bounded bibliography hints; uncertain text remains evidence, not identity."""
from __future__ import annotations

import re
from papergraph.reference_identity import normalize_identifier, stable_key

_IDENTIFIERS = re.compile(
    r'https?://(?:dx\.)?doi\.org/[^\s<>"{}]+|(?:doi:\s*)?10\.\d{4,9}/[^\s<>"{}]+'
    r'|https?://(?:www\.|export\.)?arxiv\.org/(?:abs|pdf)/[^\s<>"{}]+'
    r'|arxiv:\s*(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(?:v\d+)?', re.I)
_YEAR = re.compile(r'\b(?:18|19|20)\d{2}\b')


def _title_spans(text):
    spans = [(m.start(), m.end(), m.group(1), 'quoted_title')
             for m in re.finditer(r'["“]([^"”]+)["”]', text)]
    malformed = False
    for m in re.finditer(r'\\(?:emph|textit|textbf)\s*\{', text):
        depth = 1
        end = m.end()
        while end < len(text) and depth:
            if text[end] == '{':
                depth += 1
            elif text[end] == '}':
                depth -= 1
            end += 1
        if depth:
            malformed = True
        else:
            spans.append((m.start(), end, text[m.end():end-1], 'tex_title'))
    if spans or malformed:
        return spans, malformed
    # A period after a one-letter initial is not a sentence boundary.
    parts = []
    start = 0
    for m in re.finditer(r'\.\s+', text):
        word = re.search(r'(\w+)$', text[:m.start()])
        if word and len(word[1]) == 1:
            continue
        parts.append((start, m.start(), text[start:m.start()].strip()))
        start = m.end()
    parts.append((start, len(text), text[start:].strip()))
    if len(parts) >= 3 and _authors(parts[0][2]) and _YEAR.search(' '.join(p[2] for p in parts[2:])):
        p = parts[1]
        if not _YEAR.search(p[2]) and not _IDENTIFIERS.search(p[2]):
            return [(p[0], p[1], p[2], 'delimited_title')], False
    return [], False


def _authors(prefix):
    prefix = re.sub(r'\(?\b(?:18|19|20)\d{2}\b\)?', '', prefix).strip(' .,;:')
    if not prefix or any(c in prefix for c in '\\{}:"'):
        return []
    names = re.split(r'\s+and\s+|;\s*|,\s*(?=[^\W\d_]\.)', prefix)
    return [n.strip(' ,;') for n in names if len(n.split()) >= 2]


def build_query_v2(blocked: dict) -> dict:
    entries = blocked.get('evidence', [])
    citations, bibliographies, hints, field_evidence = [], [], [], []
    titles, authors, years, warnings = [], [], set(), set()
    for entry in entries:
        raw = str(entry.get('raw_text') or '')
        if not raw.strip():
            continue
        bucket = bibliographies if entry.get('kind') == 'bibliography_entry' else citations
        if raw not in bucket:
            bucket.append(raw)
        def evidence(field, value, rule, confidence='explicit'):
            field_evidence.append({'field': field, 'value': value,
                'evidence_id': entry.get('evidence_id') or entry.get('id'),
                'excerpt': raw[:500], 'rule': rule, 'confidence': confidence})
        text = re.sub(r'^\s*\[[^\]]+\]\s*', '', raw)
        matches = list(_IDENTIFIERS.finditer(text))
        for match in matches:
            value = match.group().strip()
            kind = 'arxiv' if 'arxiv' in value.casefold() else 'doi'
            value = re.sub(r'(?i)^arxiv:\s*', 'arxiv:', value)
            item = normalize_identifier(value, kind)
            hints.append(item)
            evidence(kind, value, 'explicit_identifier')
        for match in reversed(matches):
            text = text[:match.start()] + ' ' * (match.end()-match.start()) + text[match.end():]
        if entry.get('kind') != 'bibliography_entry':
            continue
        spans, malformed = _title_spans(text)
        for _, _, title, rule in spans:
            evidence('title', title, rule, 'heuristic' if rule == 'delimited_title' else 'explicit')
        if len({s[2] for s in spans}) > 1:
            warnings.add('conflicting_titles')
        if malformed or len({s[2] for s in spans}) != 1:
            warnings.add('uncertain_title')
        else:
            start, end, title, rule = spans[0]
            titles.append(title)
            parsed_authors = _authors(text[:start])
            if parsed_authors:
                authors.append(parsed_authors)
                evidence('authors', parsed_authors, 'author_prefix', 'heuristic')
            text = text[:start] + ' ' * (end-start) + text[end:]
        found = set(_YEAR.findall(text))
        years.update(found)
        for year in sorted(found):
            evidence('year', year, 'year_token', 'heuristic')
    if len(set(titles)) > 1:
        warnings.add('uncertain_title')
        warnings.add('conflicting_titles')
    if len(years) > 1:
        warnings.add('conflicting_years')
    if len({tuple(a) for a in authors}) > 1:
        warnings.add('conflicting_authors')
    return {'query_schema_version': 2, 'parser_version': 'bibliography_hints_v2',
            'citation_keys': sorted({str(e['citation_key']).strip() for e in entries if e.get('citation_key')}),
            'raw_citation_texts': citations, 'raw_bibliography_text': ' '.join(bibliographies),
            'title_hint': titles[0] if titles and 'uncertain_title' not in warnings else None,
            'author_hints': authors[0] if authors and 'conflicting_authors' not in warnings else [],
            'year_hint': next(iter(years)) if len(years) == 1 else None,
            'identifier_hints': sorted({stable_key(i): i for i in hints}.values(), key=stable_key),
            'field_evidence': field_evidence, 'parse_warnings': sorted(warnings)}
