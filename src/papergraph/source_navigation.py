"""Read-only raw-block locators, also available for legacy null-ID PDF rows."""
from hashlib import sha256
import json


def block_locator(row):
    if row['span_id']:
        return row['span_id']
    # Content/coordinates bind locators to this exact extraction, never DB row IDs.
    identity = [row[key] for key in ('paper_id', 'source_type', 'source_ref',
                'page', 'block_index', 'start_offset', 'end_offset', 'text')]
    return 'source-block:' + sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def locate(workspace, span_id):
    rows = workspace._connection.execute('''SELECT id, span_id, paper_id, source_type,
        source_ref, page, block_index, start_offset, end_offset, bbox_json, text,
        method, confidence FROM source_spans WHERE span_id IS NULL''').fetchall()
    from papergraph.workspace import _source_slice_record_from_row
    return [record for row in rows
            if block_locator(record := _source_slice_record_from_row(row)) == span_id]


def read_blocks(workspace, span_id, limit=20):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError('limit must be an integer from 1 through 50')
    anchors = workspace._source_slice_anchor_rows('span_id', span_id)
    if len(anchors) != 1:
        raise KeyError(f'Unknown or ambiguous source block: {span_id}')
    anchor = anchors[0]
    rows = workspace._source_slice_rows_for_source(anchor['paper_id'], anchor['source_type'], anchor['source_ref'])
    start = next(i for i, row in enumerate(rows) if row['id'] == anchor['id'])
    from papergraph.workspace import _source_slice_from_row
    end = min(start + limit, len(rows))
    return {'paper_id': anchor['paper_id'], 'source_ref': anchor['source_ref'],
            'blocks': [_source_slice_from_row(row, 'raw_source') for row in rows[start:end]],
            'bounded': True, 'limit': limit, 'proof_ownership': 'not_asserted',
            'next': {'tool': 'workspace_read_source_blocks',
                     'arguments': {'span_id': block_locator(rows[end]), 'limit': limit}} if end < len(rows) else None}
