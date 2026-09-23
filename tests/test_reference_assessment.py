import copy
import pytest
from papergraph.reference_identity import normalize_identifier


def rank(query, records, limit=10):
    from papergraph.reference_assessment import rank_candidates_v2
    return rank_candidates_v2(query, records, limit)


def provider(records, name='crossref', outcome='ok'):
    return {'provider':name, 'records':records, 'warnings':[], 'outcome':outcome}


def test_presence_is_not_matching():
    result = rank({}, [provider([{'doi':'10.1000/unrelated'}], p) for p in ['crossref','openalex']])
    c, = result['candidates']
    assert c['confidence'] == 'weak' and c['score'] == 0
    assert not c['assessment']['auto_selection']['eligible']


def test_truncated_ambiguity_stays_blocked():
    q = {'title_hint':'Maps', 'author_hints':['A. Author'], 'year_hint':'2020'}
    records = [{'title':'Maps','authors':['A. Author'],'year':'2020','arxiv_id':a}
               for a in ['2401.12345','2401.12346']]
    result = rank(q, [provider(records,p) for p in ['crossref','openalex']],1)
    assert result['summary']['total_candidate_count'] == 2 and result['summary']['truncated']
    assert result['summary']['blocking_conflicts']
    assert not result['candidates'][0]['assessment']['auto_selection']['eligible']


def test_exact_arxiv_can_survive_unrelated_provider_timeout():
    q = {'identifier_hints':[normalize_identifier('2401.12345','arxiv')]}
    result = rank(q, [provider([{'arxiv_id':'2401.12345'}]), provider([], 'arxiv','timeout')])
    c, = result['candidates']
    assert c['confidence'] == 'strong'
    assert c['assessment']['auto_selection']['eligible']


@pytest.mark.parametrize('change', [{'year':'2021'}, {'authors':['B. Other']}, {'title':'Different work'}, {'is_retracted':True}, {'arxiv_version':'v2'}])
def test_exact_identifier_cannot_override_conflict(change):
    q = {'identifier_hints':[normalize_identifier('2401.12345v1','arxiv')],
         'title_hint':'Maps', 'author_hints':['A. Author'], 'year_hint':'2020'}
    r = {'arxiv_id':'2401.12345','arxiv_version':'v1','title':'Maps','authors':['A. Author'],'year':'2020',**change}
    c, = rank(q,[provider([r])])['candidates']
    assert not c['assessment']['auto_selection']['eligible']


def test_corroborated_metadata_and_doi_availability():
    q = {'title_hint':'Maps','author_hints':['A. Author'],'year_hint':'2020'}
    rec = {'title':'Maps','authors':['Alice Author'],'year':'2020','doi':'10.1000/maps'}
    c, = rank(q,[provider([rec],p) for p in ['crossref','openalex']])['candidates']
    assert c['confidence'] == 'strong'
    assert c['assessment']['source_status'] == 'metadata_only'
    assert not c['assessment']['auto_selection']['eligible']


def test_missing_summary_fails_closed():
    from papergraph.reference_assessment import select_v2
    assert not select_v2({'candidates':[]})['eligible']


def test_order_invariance_and_malformed_sibling():
    records = [None, {'doi':'10.1000/a','title':'Maps'}, {'doi':'10.1000/b','title':'Proofs'}]
    a = [provider(records,'crossref'),provider(records,'openalex')]
    b = copy.deepcopy(list(reversed(a)))
    for p in b:
        p['records'].reverse()
    assert rank({}, a) == rank({},b)


def test_empty_and_failed_providers_are_different():
    empty = rank({},[provider([],outcome='empty')])
    failure = rank({},[provider([],outcome='timeout')])
    assert 'no_candidates' in {b['kind'] for b in empty['boundaries']}
    assert 'provider_failure' in {b['kind'] for b in failure['boundaries']}
