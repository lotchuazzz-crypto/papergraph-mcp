import pymupdf

from papergraph.workspace import Workspace


def test_pdf_import_state_and_evidence_counts_do_not_use_legacy_zero(tmp_path):
    path = tmp_path / 'paper.pdf'
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Theorem 1.1. Assertion.')
    page.insert_text((72, 105), 'Proof. Direct.')
    document.save(path)
    document.close()
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        workspace.import_pdf(path, 'local:summary')
        paper = workspace.get_paper('local:summary')
        assert paper['theorem_count'] == 0
        assert paper['legacy_counts_basis'] == 'latex_statement_graph'
        assert paper['import_state']['status'] == 'imported'
        assert paper['result_count'] == 1 and paper['proof_count'] == 1
        assert paper['result_kinds'] == {'theorem': 1}
        assert paper['metadata']['status'] == 'unavailable'
        assert workspace.list_papers()[0]['evidence_counts'] == paper['evidence_counts']
        reading = workspace.get_dependency_reading('local:summary')
        assert reading['paper']['result_count'] == 1
    finally:
        workspace.close()
