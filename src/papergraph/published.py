"""Exact DOI discovery and explicitly selected public PDF import.

Discovery only contacts metadata APIs. It never follows full-text links. Provider
identity and access reports are evidence, not verification of the PDF's contents.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx

from papergraph.reference_identity import normalize_identifier, stable_key
from papergraph.reference_providers.base import failure_result
from papergraph.reference_providers.crossref import _record_from_item
from papergraph.reference_providers.openalex import _record_from_work

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024


def validate_public_url(url: str) -> str:
    """Require credential-free HTTPS; DNS is checked and pinned at connection."""
    if not isinstance(url, str) or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise ValueError('unsafe_source_url')
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.fragment or parsed.port not in (None, 443)
            or '\\' in url):
        raise ValueError('unsafe_source_url')
    host = parsed.hostname.rstrip('.').lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local')):
        raise ValueError('unsafe_source_url')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not address.is_global:
        raise ValueError('unsafe_source_url')
    return url


def _safe_link(value):
    try:
        return validate_public_url(value)
    except (TypeError, ValueError):
        return None


def _metadata(client, provider, url):
    try:
        with client.stream('GET', url, timeout=8, follow_redirects=False) as response:
            if response.status_code == 404:
                return {'provider': provider, 'outcome': 'empty', 'records': [], 'warnings': []}, None
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('invalid_status')
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_METADATA_BYTES:
                    raise ValueError('metadata_too_large')
            payload = json.loads(data)
        item = payload['message'] if provider == 'crossref' else payload
        record = (_record_from_item if provider == 'crossref' else _record_from_work)(item)
        if not record or not isinstance(item, dict):
            raise ValueError('invalid_record')
        return {'provider': provider, 'outcome': 'ok', 'records': [record], 'warnings': []}, item
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        return failure_result(provider, exc, parsing=not isinstance(exc, httpx.HTTPError)), None


def discover_doi(doi: str, *, client=None) -> dict:
    """Discover exact-identity metadata and body locations without downloading."""
    identity = normalize_identifier(doi, 'doi')
    if isinstance(doi, str) and len(re.findall(r'10\.\d{4,9}/', doi, flags=re.I)) > 1:
        identity['exact_eligible'] = False
        identity['warnings'].append('multiple_doi_identifiers')
    # Do not echo potentially credential-bearing input in responses.
    identity.pop('raw', None)
    result = {
        'discovery_schema_version': 1, 'identity': identity,
        'status': 'invalid_or_ambiguous_input', 'import_status': 'not_imported',
        'metadata': [], 'candidates': [], 'provider_results': [], 'source_issues': [], 'warnings': [],
        'fallback': {'tool': 'workspace_add_pdf_paper',
                     'instruction': 'Provide a legally obtained local born-digital PDF and a local: paper id.'},
        'policy': {'external_references': 'review_plan_only_no_download',
                   'metadata_is_fulltext': False, 'version_equivalence_assumed': False},
    }
    if not identity['exact_eligible']:
        result['warnings'] = identity['warnings']
        return result
    canonical = identity['canonical']
    endpoints = [
        ('crossref', 'https://api.crossref.org/works/' + quote(canonical, safe='')),
        ('openalex', 'https://api.openalex.org/works/https://doi.org/' + quote(canonical, safe='')),
    ]
    owned = client is None
    client = client or httpx.Client(trust_env=False)
    conflict = False
    try:
        for provider, endpoint in endpoints:
            outcome, item = _metadata(client, provider, endpoint)
            result['provider_results'].append(outcome)
            if item is None:
                continue
            record = outcome['records'][0]
            matched = normalize_identifier(record.get('doi'), 'doi')
            if not matched['exact_eligible'] or matched['canonical'] != canonical:
                outcome['outcome'] = 'identity_conflict'
                outcome['warnings'].append('returned_doi_does_not_match')
                conflict = True
                continue
            result['metadata'].append({'provider': provider, 'endpoint': endpoint, 'record': record})
            if provider == 'crossref':
                locations = item.get('link') or []
            else:
                locations = item.get('locations') or []
                if isinstance(locations, list):
                    locations = locations + [item.get(k) for k in ('primary_location', 'best_oa_location') if item.get(k)]
            if not isinstance(locations, list) or any(not isinstance(loc, dict) for loc in locations):
                outcome['outcome'] = 'invalid_response'
                outcome['warnings'].append('invalid_locations')
                continue
            for location in locations:
                raw_pdf_url = location.get('URL') if provider == 'crossref' else location.get('pdf_url')
                pdf_url = _safe_link(raw_pdf_url)
                landing = _safe_link(location.get('landing_page_url'))
                if (raw_pdf_url and not pdf_url) or (location.get('landing_page_url') and not landing):
                    result['source_issues'].append({'provider': provider, 'reason': 'unsafe_or_unsupported_source_url'})
                if not pdf_url and not landing:
                    continue
                is_oa = provider == 'openalex' and location.get('is_oa') is True
                content_type = location.get('content-type') if provider == 'crossref' else ('application/pdf' if pdf_url else None)
                candidate = {
                    'doi': canonical, 'provider': provider, 'source_endpoint': endpoint,
                    'url': pdf_url or landing,
                    'kind': ('pdf' if pdf_url and content_type == 'application/pdf'
                             else 'fulltext_link' if pdf_url else 'landing_page'),
                    'content_type': content_type,
                    'landing_page_url': landing, 'version': location.get('version'),
                    'license': location.get('license'), 'content_verified': False,
                    'access_basis': 'provider_reports_open_access' if is_oa else 'access_unknown',
                    'download_eligible': bool(is_oa and pdf_url),
                    'identity_basis': 'provider_exact_doi',
                }
                candidate['candidate_id'] = stable_key(candidate)
                if candidate not in result['candidates']:
                    result['candidates'].append(candidate)
    finally:
        if owned:
            client.close()
    if conflict:
        result['candidates'] = []
        result['status'] = 'identity_conflict'
    elif any(c['download_eligible'] for c in result['candidates']):
        result['status'] = 'candidates_found'
    elif any(p['outcome'] not in ('ok', 'empty') for p in result['provider_results']):
        result['status'] = 'discovery_incomplete'
    else:
        result['status'] = 'no_public_pdf_candidate'
    result['warnings'] = [
        'Provider access and identity reports do not verify PDF contents or equality of versions.',
        'No public PDF candidate is not proof that no public full text exists.',
    ]
    result['discovery_complete'] = all(p['outcome'] in ('ok', 'empty') for p in result['provider_results'])
    if not result['discovery_complete']:
        result['warnings'].append('Some provider evidence is unavailable, invalid or conflicting; discovery is incomplete.')
    result['action'] = 'review_candidates' if result['candidates'] else 'provide_local_pdf_or_retry'
    return result


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self):
        # Connect to a previously validated numeric IP while retaining TLS hostname
        # verification and SNI. No second DNS lookup or environment proxy is used.
        raw = socket.create_connection((self._address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _public_addresses(host):
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('non_public_source_address')
    return addresses


def download_public_pdf(url: str) -> tuple[bytes, dict]:
    """Bounded HTTPS download with validated, pinned DNS on every redirect."""
    started = time.monotonic()
    redirects = []
    for _ in range(6):
        if time.monotonic() - started > 60:
            raise ValueError('download_deadline_exceeded')
        validate_public_url(url)
        parsed = urlsplit(url)
        addresses = _public_addresses(parsed.hostname)
        connection = _PinnedHTTPSConnection(parsed.hostname, addresses[0], timeout=8)
        try:
            connection.request('GET', (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''),
                               headers={'Accept': 'application/pdf', 'Accept-Encoding': 'identity',
                                        'User-Agent': 'PaperGraph-MCP'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                target = response.getheader('Location')
                if not target:
                    raise ValueError('redirect_without_location')
                redirects.append(url)
                url = urljoin(url, target)
                continue
            if response.status != 200:
                raise ValueError('fulltext_unavailable')
            media = (response.getheader('Content-Type') or '').split(';')[0].strip().lower()
            if media not in ('application/pdf', 'application/octet-stream'):
                raise ValueError('not_pdf_content_type')
            if response.getheader('Content-Encoding') not in (None, 'identity'):
                raise ValueError('encoded_content_not_supported')
            length = response.getheader('Content-Length')
            if length and (int(length) < 0 or int(length) > MAX_PDF_BYTES):
                raise ValueError('pdf_too_large')
            data = bytearray()
            while True:
                if time.monotonic() - started > 60:
                    raise ValueError('download_deadline_exceeded')
                chunk = response.read(min(65536, MAX_PDF_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_PDF_BYTES:
                    raise ValueError('pdf_too_large')
            if not data.startswith(b'%PDF-'):
                raise ValueError('not_pdf_signature')
            if length and len(data) != int(length):
                raise ValueError('incomplete_pdf_response')
            return bytes(data), {'final_url': url, 'redirects': redirects,
                                 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        finally:
            connection.close()
    raise ValueError('too_many_redirects')


def import_doi_candidate(workspace, doi: str, candidate_id: str, *, confirmed: bool = False) -> dict:
    """Re-discover and import one explicitly reviewed root-paper PDF candidate."""
    if confirmed is not True:
        return {'status': 'confirmation_required', 'import_status': 'not_imported',
                'action': 'review_discovery_and_confirm_selected_root_candidate'}
    discovery = discover_doi(doi)
    return _import_discovered_candidate(workspace, discovery, candidate_id)


def _import_discovered_candidate(workspace, discovery, candidate_id):
    candidate = next((c for c in discovery['candidates'] if c['candidate_id'] == candidate_id), None)
    if not candidate or not candidate['download_eligible']:
        return {'status': 'candidate_unavailable_or_changed', 'import_status': 'not_imported', 'discovery': discovery}
    stage = 'download'
    try:
        data, receipt = download_public_pdf(candidate['url'])
        stage = 'source_storage'
        # Content-addressed managed storage adjacent to the workspace. Never
        # overwrite a user's file or remove an existing cached source.
        cache = workspace.path.parent / (workspace.path.name + '.sources')
        cache.mkdir(exist_ok=True)
        if cache.resolve() != workspace.path.parent.resolve() / cache.name:
            raise ValueError('source_cache_redirected')
        path = cache / (receipt['sha256'] + '.pdf')
        if path.is_symlink():
            raise ValueError('source_cache_redirected')
        if not path.exists():
            with path.open('xb') as stream:
                stream.write(data)
        elif path.read_bytes() != data:
            raise ValueError('source_cache_conflict')
        paper_id = 'local:doi-' + stable_key(discovery['identity']['canonical'])[:24]
        provenance = {'candidate': candidate, 'download': receipt,
                      'metadata': discovery['metadata'], 'paper_id': paper_id,
                      'content_identity_verified': False}
        # Receipt identity includes both content and DOI candidate/version.
        receipt_path = cache / (stable_key(provenance) + '.json')
        if receipt_path.is_symlink():
            raise ValueError('source_cache_redirected')
        if not receipt_path.exists():
            with receipt_path.open('x', encoding='utf-8') as stream:
                json.dump(provenance, stream, ensure_ascii=False, indent=2)
        from papergraph.paper_summary import provenance_index_name
        index_path = cache / provenance_index_name(paper_id, receipt['sha256'])
        index = {'paper_id': paper_id, 'pdf_sha256': receipt['sha256'], 'receipt_name': receipt_path.name}
        if index_path.is_symlink():
            raise ValueError('source_cache_redirected')
        if not index_path.exists():
            with index_path.open('x', encoding='utf-8') as stream:
                json.dump(index, stream)
        # Existing indexes retain their original snapshot, never overwrite it.
        stage = 'pdf_extraction_and_import'
        result = workspace.import_pdf(path, paper_id)
        return {'status': 'imported', 'import_status': 'resolved_imported',
                'paper': workspace.get_paper(result.paper_id),
                'evidence_import_summary': result.evidence_import_summary(),
                'provenance': provenance, 'provenance_path': str(receipt_path),
                'warnings': discovery['warnings']}
    except Exception as error:
        # Avoid leaking signed URLs, credentials or provider exception strings.
        known_reasons = {'unsafe_source_url', 'non_public_source_address', 'redirect_without_location',
                        'fulltext_unavailable', 'not_pdf_content_type', 'encoded_content_not_supported',
                        'pdf_too_large', 'download_deadline_exceeded', 'not_pdf_signature',
                        'too_many_redirects', 'source_cache_conflict', 'source_cache_redirected'}
        known_reasons.add('incomplete_pdf_response')
        reason = str(error) if isinstance(error, ValueError) and str(error) in known_reasons else (
            'timeout' if isinstance(error, TimeoutError) else 'fetch_extraction_storage_or_import_failed')
        return {'status': 'failed_import', 'import_status': 'failed_import', 'failure_reason': reason,
                'failure_stage': stage,
                'warning': 'Public PDF fetch, extraction, storage or import failed; no access bypass attempted.',
                'fallback': discovery['fallback']}


def import_root_doi(workspace, doi: str) -> dict:
    """Import only a user-requested root with one eligible public PDF location.

    User authorization for roots does not extend to discovered external literature.
    Multiple versions/locations are exposed for selection, never silently chosen.
    """
    discovery = discover_doi(doi)
    candidates = [candidate for candidate in discovery['candidates'] if candidate['download_eligible']]
    if len(candidates) != 1:
        return {'status': 'selection_required' if len(candidates) > 1 else discovery['status'],
                'import_status': 'not_imported', 'discovery': discovery,
                'action': 'choose_root_candidate' if len(candidates) > 1 else 'provide_local_pdf_or_retry'}
    return _import_discovered_candidate(workspace, discovery, candidates[0]['candidate_id'])
