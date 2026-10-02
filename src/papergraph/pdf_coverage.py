"""Conservative coverage of stored PDF excerpts, including legacy imports."""

PDF_COVERAGE_WARNING = (
    'PDF text may be incomplete: block extraction does not verify full statements '
    'or proofs. Inspect the continuation source; adjacent context is not proof evidence.'
)


def with_pdf_coverage(workspace, payload, kind, spans):
    if not spans or not any(span['source_type'] == 'pdf' for span in spans):
        return payload
    selector = 'result_id' if kind == 'statement' else 'proof_id'
    arguments = {selector: payload[selector], 'context': 5}
    source = workspace.get_source_slice(**arguments)
    coverage = {
        'status': 'unverified', 'complete': False, 'may_be_truncated': True,
        'basis': 'bounded_pdf_text_blocks', 'captured_span_count': len(spans),
        'completeness_verified': False,
        'mathematical_layout_reconstructed': False,
        'continuation_source': {'tool': 'workspace_get_source_slice', 'arguments': arguments},
        'adjacent_after': [{key: row[key] for key in ('span_id', 'page', 'block_index')}
                           for row in source['slices'] if row['role'] == 'after'],
        'adjacent_context_is_proof_evidence': False,
        'warning': PDF_COVERAGE_WARNING,
    }
    return {**payload, kind + '_complete': False, 'text_coverage': coverage}
