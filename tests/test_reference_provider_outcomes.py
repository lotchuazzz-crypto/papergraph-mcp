import httpx
import pytest
from papergraph.reference_providers.crossref import CrossrefReferenceProvider
from papergraph.reference_providers.openalex import OpenAlexReferenceProvider
from papergraph.reference_providers.arxiv import ArxivReferenceProvider


@pytest.mark.parametrize('cls',[CrossrefReferenceProvider,OpenAlexReferenceProvider,ArxivReferenceProvider])
def test_rate_limit_is_sanitized(cls):
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429,request=req)))
    result = cls(client=client).search({'title_hint':'secret-query'})
    assert result['outcome'] == 'rate_limited'
    assert 'secret-query' not in str(result)


def test_malformed_crossref_sibling_is_isolated():
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200,
        json={'message':{'items':[None,{'DOI':'10.1000/maps','title':['Maps']}]}})))
    result = CrossrefReferenceProvider(client=client).search({})
    assert result['outcome'] == 'partial' and len(result['records']) == 1


def test_wrong_atom_root_is_not_successful_empty():
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text='<error>bad</error>')))
    assert ArxivReferenceProvider(client=client).search({})['outcome'] == 'invalid_response'


def test_invalid_atom_sibling_preserves_valid_entry():
    atom = '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>bad</id></entry><entry><id>https://arxiv.org/abs/2401.12345</id></entry></feed>'
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=atom)))
    result = ArxivReferenceProvider(client=client).search({})
    assert result['outcome'] == 'partial'
    assert result['records'][0]['arxiv_id'] == '2401.12345'


@pytest.mark.parametrize('cls',[CrossrefReferenceProvider,OpenAlexReferenceProvider,ArxivReferenceProvider])
def test_timeout_is_safe_and_request_is_not_retried(cls):
    requests = []
    def timeout(request):
        requests.append(request)
        raise httpx.ReadTimeout('secret-token-in-exception', request=request)
    client = httpx.Client(transport=httpx.MockTransport(timeout))
    result = cls(client=client).search({})
    assert result['outcome'] == 'timeout' and len(requests) == 1
    assert 'secret-token' not in str(result)
