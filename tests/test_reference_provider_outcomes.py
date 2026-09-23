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
