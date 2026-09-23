import pytest
from papergraph import reference_search as search


def test_version_validation_precedes_work():
    assert hasattr(search, 'validate_resolver_version')
    with pytest.raises(ValueError, match='Unsupported resolver'):
        search.validate_resolver_version('future')


def test_legacy_identifier_only_agreement_is_frozen():
    result = search.rank_reference_candidates({}, [
        {'provider': p, 'records': [{'doi': '10.1000/example'}], 'warnings': []}
        for p in ('crossref', 'openalex')], resolver_version='legacy_v1')
    c, = result['candidates']
    assert (c['score'], c['confidence'], c['evidence']) == (2.5, 'strong', ['doi_present', 'provider_agreement'])
    assert result['search_schema_version'] == 1


def test_legacy_query_punctuation_is_frozen():
    query = search.build_reference_search_query({'evidence': [
        {'kind': 'bibliography_entry', 'raw_text': 'A. Author. Published target. 2020.'}
    ]}, resolver_version='legacy_v1')
    assert query['title_hint'] == 'Published target'
    assert query['author_hints'] == ['A']
    assert query['year_hint'] == '2020'
