"""Additive evidence counts and separately attributed published metadata."""
from __future__ import annotations

import json
from pathlib import Path
import re

from papergraph.reference_identity import stable_key

MAX_RECEIPT_BYTES = 2 * 1024 * 1024


def provenance_index_name(paper_id, sha256):
    return stable_key({'paper_id': paper_id, 'pdf_sha256': sha256}) + '.metadata.json'


def _read_json(path):
    if path.is_symlink() or path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError('invalid_provenance_file')
    with path.open('rb') as stream:
        data = stream.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError('invalid_provenance_file')
    return json.loads(data)


def _published_metadata(workspace, paper):
    cache = workspace.path.parent / (workspace.path.name + '.sources')
    source = Path(paper['source_ref'])
    if (not cache.exists() or cache.resolve() != workspace.path.parent.resolve() / cache.name
            or source.parent.resolve() != cache.resolve()
            or not re.fullmatch(r'[0-9a-f]{64}\.pdf', source.name)):
        return None
    sha256 = source.stem
    index_path = cache / provenance_index_name(paper['paper_id'], sha256)
    if not index_path.exists():
        return None
    index = _read_json(index_path)
    if index['paper_id'] != paper['paper_id'] or index['pdf_sha256'] != sha256:
        raise ValueError('mismatched_provenance_index')
    name = index['receipt_name']
    if not isinstance(name, str) or not re.fullmatch(r'[0-9a-f]{64}\.json', name):
        raise ValueError('invalid_provenance_receipt_name')
    provenance = _read_json(cache / name)
    if (stable_key(provenance) + '.json' != name or provenance['paper_id'] != paper['paper_id']
            or provenance['download']['sha256'] != sha256):
        raise ValueError('mismatched_provenance_receipt')
    records = provenance['metadata']
    titles = sorted({r['record']['title'] for r in records
                     if isinstance(r.get('record', {}).get('title'), str) and r['record']['title']})
    authors = {stable_key(r['record']['authors']): r['record']['authors'] for r in records
               if isinstance(r.get('record', {}).get('authors'), list) and r['record']['authors']}
    return {'status': 'available' if len(titles) <= 1 else 'conflicting_titles',
            'source': 'provider_metadata', 'title': titles[0] if len(titles) == 1 else None,
            'title_candidates': titles, 'authors': next(iter(authors.values())) if len(authors) == 1 else [],
            'provider_records': records, 'doi': provenance['candidate']['doi'],
            'reported_source_version': provenance['candidate'].get('version'),
            'provenance_path': str(cache / name), 'content_identity_verified': False,
            'warning': 'Provider metadata is separate from imported PDF text; versions and content identity are not verified.'}


def augment_paper_summary(workspace, paper):
    counts = {}
    for table in ('results', 'proofs', 'bibliography_entries', 'citation_mentions',
                  'local_result_mentions', 'external_result_mentions'):
        counts[table] = workspace._connection.execute(
            f'SELECT COUNT(*) FROM {table} WHERE paper_id = ?', (paper['paper_id'],)).fetchone()[0]
    metadata = {'status': 'stored' if paper.get('title') or paper.get('authors') else 'unavailable',
                'source': 'stored_import_metadata' if paper.get('title') or paper.get('authors') else 'unavailable',
                'title': paper.get('title'), 'authors': paper.get('authors', [])}
    if paper['source_type'] == 'pdf':
        try:
            metadata = _published_metadata(workspace, paper) or metadata
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            metadata = {**metadata, 'warning': 'Published provenance unavailable or invalid; body import state is unchanged.'}
    return {**paper, 'import_state': {'status': 'imported', 'body_imported': True, 'metadata_only': False},
            'legacy_counts_basis': 'latex_statement_graph', 'evidence_counts': counts,
            'result_count': counts['results'], 'proof_count': counts['proofs'],
            'result_kinds': dict(workspace._connection.execute(
                'SELECT normalized_kind, COUNT(*) FROM results WHERE paper_id = ? '
                'GROUP BY normalized_kind ORDER BY normalized_kind', (paper['paper_id'],))),
            'metadata': metadata, 'display_title': paper.get('title') or metadata.get('title'),
            'display_title_basis': 'stored_import_metadata' if paper.get('title') else metadata['source']}
