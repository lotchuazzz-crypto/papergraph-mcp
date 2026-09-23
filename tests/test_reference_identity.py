import itertools
import pytest


def identity_module():
    from papergraph import reference_identity
    return reference_identity


@pytest.mark.parametrize('raw,canonical', [('doi:10.1000/ABC','10.1000/abc'),
    ('https://doi.org/10.1000/A(B)','10.1000/a(b)'), ('https://dx.doi.org/10.1000/a%2Fb','10.1000/a/b')])
def test_doi_wrappers(raw, canonical):
    item = identity_module().normalize_identifier(raw, 'doi')
    assert item['canonical'] == canonical and item['exact_eligible']


@pytest.mark.parametrize('raw', ['10.1/bad', 'https://evil.test/10.1000/a', '10.1000/a.', 'https://doi.org/10.1000/a?secret=x'])
def test_uncertain_doi_never_exact(raw):
    assert not identity_module().normalize_identifier(raw, 'doi')['exact_eligible']


def test_arxiv_work_and_version():
    normal = identity_module().normalize_identifier('https://arxiv.org/pdf/math/0301234v2.pdf', 'arxiv')
    assert normal['identity'] == 'arxiv:math/0301234'
    assert normal['version'] == 'v2'
    bad = identity_module().normalize_identifier('2401.12345v1', 'arxiv', version='v2')
    assert 'version_conflict' in bad['warnings'] and not bad['exact_eligible']


def test_bridge_conflict_and_order_invariance():
    records = [{'doi':'10.1000/a','arxiv_id':'2401.12345'}, {'doi':'10.1000/b','arxiv_id':'2401.12345'}]
    outputs = [identity_module().group_reference_records([{'provider':'crossref','records':list(order)}]) for order in itertools.permutations(records)]
    assert outputs[0] == outputs[1]
    group, = outputs[0]
    assert 'identifier_conflict' in {c['code'] for c in group['conflicts']}
    assert group['target']['kind'] == 'metadata' and not group['target'].get('arxiv_id')


def test_metadata_missing_fields_never_collapse():
    groups = identity_module().group_reference_records([{'provider':'crossref','records':[{}, {'title':'Maps'}, {'title':'Maps','year':'2020'}]}])
    assert len(groups) == 2


def test_unicode_and_math_survive():
    assert identity_module().normalize_match_text('  ÉTale  映射 $X^2$ ') == 'étale 映射 $x^2$'
