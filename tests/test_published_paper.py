import httpx
import pytest

from papergraph.published import discover_doi, validate_public_url
import papergraph.published as published


def client_for(work, crossref=None, status=200):
    def handler(request):
        if request.url.host == 'api.crossref.org':
            return httpx.Response(200, json={'message': crossref or {'DOI': '10.1234/test', 'title': ['Title']}})
        return httpx.Response(status, json=work)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_exact_doi_discovery_preserves_versions_and_never_fetches_pdf():
    work = {'doi': 'https://doi.org/10.1234/test', 'display_name': 'Title', 'locations': [
        {'is_oa': True, 'pdf_url': 'https://example.org/paper.pdf', 'version': 'acceptedVersion', 'license': 'cc-by'},
        {'is_oa': False, 'pdf_url': 'https://example.org/paywall.pdf'},
    ]}
    result = discover_doi('https://doi.org/10.1234/TEST', client=client_for(work))
    assert result['import_status'] == 'not_imported'
    assert result['status'] == 'candidates_found'
    candidate = result['candidates'][0]
    assert candidate['version'] == 'acceptedVersion'
    assert candidate['access_basis'] == 'provider_reports_open_access'
    assert candidate['content_verified'] is False
    assert not result['candidates'][1]['download_eligible']


@pytest.mark.parametrize('value', ['not doi', '10.1234/a 10.1234/b', '10.1234/a,10.1234/b', 'https://doi.org/10.1234/test?secret=x'])
def test_ambiguous_input_does_not_contact_provider(value):
    result = discover_doi(value, client=client_for({}))
    assert result['status'] == 'invalid_or_ambiguous_input'
    assert result['provider_results'] == []


def test_conflicting_identity_blocks_candidates():
    result = discover_doi('10.1234/test', client=client_for({'doi': '10.1234/other', 'locations': []}))
    assert result['status'] == 'identity_conflict'
    assert result['candidates'] == []


def test_provider_failure_is_not_no_fulltext():
    result = discover_doi('10.1234/test', client=client_for({}, status=429))
    assert result['status'] == 'discovery_incomplete'
    assert result['provider_results'][1]['outcome'] == 'rate_limited'
    assert result['fallback']['tool'] == 'workspace_add_pdf_paper'


@pytest.mark.parametrize('url', ['http://example.org/a', 'https://user:pass@example.org/a', 'https://localhost/a', 'https://127.0.0.1/a', 'https://[::1]/a', 'https://example.org:8443/a'])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


class Response:
    def __init__(self, status=200, headers=None, body=b'%PDF-test'):
        self.status = status
        self.headers = headers or {'Content-Type': 'application/pdf'}
        self.body = body
    def getheader(self, key):
        return self.headers.get(key)
    def read(self, size):
        part, self.body = self.body[:size], self.body[size:]
        return part


def install_connections(monkeypatch, responses):
    calls = []
    class Connection:
        def __init__(self, host, address, timeout):
            calls.append((host, address))
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return responses.pop(0)
        def close(self):
            pass
    monkeypatch.setattr(published, '_PinnedHTTPSConnection', Connection)
    monkeypatch.setattr(published.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('93.184.216.34', 443))])
    return calls


def test_redirect_revalidates_target_before_connecting(monkeypatch):
    calls = install_connections(monkeypatch, [Response(302, {'Location': 'https://127.0.0.1/private'})])
    with pytest.raises(ValueError, match='unsafe_source_url'):
        published.download_public_pdf('https://example.org/paper.pdf')
    assert len(calls) == 1


def test_dns_private_or_mixed_answers_fail_closed(monkeypatch):
    calls = install_connections(monkeypatch, [])
    monkeypatch.setattr(published.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))])
    with pytest.raises(ValueError, match='non_public_source_address'):
        published.download_public_pdf('https://example.org/paper.pdf')
    assert calls == []


@pytest.mark.parametrize('response,code', [
    (Response(headers={'Content-Type': 'text/html'}, body=b'login'), 'not_pdf_content_type'),
    (Response(body=b'<html>'), 'not_pdf_signature'),
    (Response(headers={'Content-Type': 'application/pdf', 'Content-Length': '52428801'}), 'pdf_too_large'),
    (Response(403), 'fulltext_unavailable'),
    (Response(headers={'Content-Type': 'application/pdf', 'Content-Length': '999'}), 'incomplete_pdf_response'),
])
def test_download_rejects_nonbody_or_unavailable_response(monkeypatch, response, code):
    install_connections(monkeypatch, [response])
    with pytest.raises(ValueError, match=code):
        published.download_public_pdf('https://example.org/paper.pdf')


def test_download_limits_actual_stream_and_records_final_url(monkeypatch):
    install_connections(monkeypatch, [Response(body=b'%PDF-' + b'x' * 20)])
    monkeypatch.setattr(published, 'MAX_PDF_BYTES', 10)
    with pytest.raises(ValueError, match='pdf_too_large'):
        published.download_public_pdf('https://example.org/paper.pdf')


def test_selected_import_needs_confirmation_and_preserves_provenance(tmp_path, monkeypatch):
    import fitz
    from papergraph.workspace import Workspace
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Theorem 1.1. Main result.')
    data = document.tobytes()
    document.close()
    discovery = discover_doi('10.1234/test', client=client_for({
        'doi': '10.1234/test', 'locations': [{'is_oa': True, 'pdf_url': 'https://example.org/paper.pdf'}]}))
    monkeypatch.setattr(published, 'discover_doi', lambda doi: discovery)
    calls = install_connections(monkeypatch, [Response(body=data)])
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        candidate_id = discovery['candidates'][0]['candidate_id']
        assert published.import_doi_candidate(workspace, '10.1234/test', candidate_id)['status'] == 'confirmation_required'
        assert not calls and not workspace.list_papers()
        result = published.import_doi_candidate(workspace, '10.1234/test', candidate_id, confirmed=True)
        assert result['import_status'] == 'resolved_imported'
        assert result['provenance']['content_identity_verified'] is False
        assert len(workspace.list_results(result['paper']['paper_id'])) == 1
        assert __import__('pathlib').Path(result['provenance_path']).exists()
        paper = workspace.get_paper(result['paper']['paper_id'])
        assert paper['display_title'] == 'Title'
        assert paper['metadata']['source'] == 'provider_metadata'
        assert paper['metadata']['content_identity_verified'] is False
        assert paper['import_state']['status'] == 'imported'
        assert paper['result_count'] == 1
        report = workspace.export_paper_reading_report(paper['paper_id'])
        assert report['title'] == 'Title'
        assert 'provider_metadata' in report['markdown']
        # Reading metadata survives reopen; a damaged index cannot change body
        # import state or redirect a metadata read outside the managed cache.
        workspace.close()
        workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
        assert workspace.get_paper(paper['paper_id'])['display_title'] == 'Title'
        from papergraph.paper_summary import provenance_index_name
        cache = __import__('pathlib').Path(paper['source_ref']).parent
        index = cache / provenance_index_name(paper['paper_id'], result['provenance']['download']['sha256'])
        index.write_text(__import__('json').dumps({
            'paper_id': paper['paper_id'], 'pdf_sha256': result['provenance']['download']['sha256'],
            'receipt_name': '../untrusted.json'}), encoding='utf-8')
        damaged = workspace.get_paper(paper['paper_id'])
        assert damaged['metadata']['status'] == 'unavailable'
        assert 'invalid' in damaged['metadata']['warning']
        assert damaged['import_state']['body_imported'] is True
        assert damaged['result_count'] == 1
        changed = published.import_doi_candidate(workspace, '10.1234/test', 'stale', confirmed=True)
        assert changed['status'] == 'candidate_unavailable_or_changed'
        assert len(calls) == 1
    finally:
        workspace.close()


def test_malformed_locations_report_incomplete():
    result = discover_doi('10.1234/test', client=client_for({'doi': '10.1234/test', 'locations': 'bad'}))
    assert result['status'] == 'discovery_incomplete'


def test_crossref_links_are_not_access_permissions():
    result = discover_doi('10.1234/test', client=client_for({'doi': '10.1234/test'},
        {'DOI': '10.1234/test', 'link': [{'URL': 'https://example.org/article.pdf', 'content-type': 'application/pdf'}]}))
    assert result['status'] == 'no_public_pdf_candidate'
    assert result['candidates'][0]['access_basis'] == 'access_unknown'
    assert result['candidates'][0]['download_eligible'] is False


def test_crossref_xml_link_not_mislabelled_pdf():
    result = discover_doi('10.1234/test', client=client_for({'doi': '10.1234/test'},
        {'DOI': '10.1234/test', 'link': [{'URL': 'https://example.org/article.xml', 'content-type': 'application/xml'}]}))
    assert result['candidates'][0]['kind'] == 'fulltext_link'
    assert result['candidates'][0]['content_type'] == 'application/xml'


def test_oa_candidates_with_unavailable_provider_report_partial_discovery():
    def handler(request):
        if request.url.host == 'api.crossref.org':
            return httpx.Response(503)
        return httpx.Response(200, json={'doi': '10.1234/test', 'locations': [
            {'is_oa': True, 'pdf_url': 'https://example.org/paper.pdf'}]})
    result = discover_doi('10.1234/test', client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result['status'] == 'candidates_found'
    assert result['discovery_complete'] is False


def test_unique_root_import_is_automatic_without_extra_confirmation(tmp_path, monkeypatch):
    import pymupdf as fitz
    from papergraph.workspace import Workspace
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Theorem 1.1. Root result.')
    data = document.tobytes()
    document.close()
    discovery = discover_doi('10.1234/test', client=client_for({'doi': '10.1234/test',
        'locations': [{'is_oa': True, 'pdf_url': 'https://example.org/paper.pdf'}]}))
    monkeypatch.setattr(published, 'discover_doi', lambda doi: discovery)
    calls = install_connections(monkeypatch, [Response(body=data)])
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        result = published.import_root_doi(workspace, '10.1234/test')
        assert result['status'] == 'imported'
        assert result['import_status'] == 'resolved_imported'
        assert len(calls) == 1
    finally:
        workspace.close()


def test_multiple_root_versions_require_selection_and_never_download(tmp_path, monkeypatch):
    from papergraph.workspace import Workspace
    discovery = discover_doi('10.1234/test', client=client_for({'doi': '10.1234/test', 'locations': [
        {'is_oa': True, 'pdf_url': 'https://example.org/published.pdf', 'version': 'publishedVersion'},
        {'is_oa': True, 'pdf_url': 'https://example.org/preprint.pdf', 'version': 'submittedVersion'}]}))
    monkeypatch.setattr(published, 'discover_doi', lambda doi: discovery)
    calls = install_connections(monkeypatch, [])
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        assert published.import_root_doi(workspace, '10.1234/test')['status'] == 'selection_required'
        assert calls == []
        assert workspace.list_papers() == []
    finally:
        workspace.close()


def test_root_download_failure_has_safe_reason_and_no_import(tmp_path, monkeypatch):
    from papergraph.workspace import Workspace
    discovery = discover_doi('10.1234/test', client=client_for({'doi': '10.1234/test',
        'locations': [{'is_oa': True, 'pdf_url': 'https://example.org/paper.pdf'}]}))
    monkeypatch.setattr(published, 'discover_doi', lambda doi: discovery)
    install_connections(monkeypatch, [Response(headers={'Content-Type': 'text/html'}, body=b'login')])
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        result = published.import_root_doi(workspace, '10.1234/test')
        assert result['status'] == 'failed_import'
        assert result['failure_reason'] == 'not_pdf_content_type'
        assert result['failure_stage'] == 'download'
        assert workspace.list_papers() == []
    finally:
        workspace.close()
