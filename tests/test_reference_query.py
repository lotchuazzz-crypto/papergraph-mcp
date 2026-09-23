import pytest


def query(raw):
    from papergraph.reference_query import build_query_v2
    return build_query_v2({'evidence': [{'kind':'bibliography_entry', 'evidence_id':'bib:17', 'citation_key':'17', 'raw_text':raw}]})


@pytest.mark.parametrize('raw,title', [
    ('A. Author and B. Writer. "Maps and proofs". 2020.', 'Maps and proofs'),
    (r'A. Author. \emph{Maps {and} $X^2$}. 2020.', 'Maps {and} $X^2$'),
    ('[17] A. Author. Published target. Journal of Examples 2020.', 'Published target'),
    ('É. Auteur (2020). "Étale 映射".', 'Étale 映射'),
    ('A. Author. "One two three four five six seven eight nine ten eleven twelve thirteen fourteen". 2020.', 'One two three four five six seven eight nine ten eleven twelve thirteen fourteen'),
])
def test_supported_titles(raw, title):
    result = query(raw)
    assert result['title_hint'] == title
    assert result['raw_bibliography_text'] == raw
    assert result['year_hint'] == '2020'
    assert result['field_evidence'][0]['evidence_id'] == 'bib:17'


def test_initials_kept():
    assert query('A. Author and B. Writer. "Maps". 2020.')['author_hints'] == ['A. Author', 'B. Writer']


def test_ambiguous_title_and_year_not_guessed():
    result = query('A. Author. "Maps" or "Proofs". 2019; revised 2021.')
    assert result['title_hint'] is None and result['year_hint'] is None
    assert {'uncertain_title', 'conflicting_years'} <= set(result['parse_warnings'])


def test_identifiers_excluded_from_years():
    result = query('doi:10.2020/thing arXiv:2001.12345v2')
    assert result['year_hint'] is None
    assert {i['identity'] for i in result['identifier_hints']} == {'doi:10.2020/thing', 'arxiv:2001.12345'}


def test_malformed_tex_is_uncertain():
    result = query(r'A. Author. \emph{Unclosed title. 2020.')
    assert result['title_hint'] is None
    assert 'uncertain_title' in result['parse_warnings']
