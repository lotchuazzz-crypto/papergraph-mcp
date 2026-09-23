import pytest
from papergraph.reference_expansion_policy import validate_policy
from tests.test_reference_expansion import chain, drain, workspace


def test_new_default_and_old_resolver():
    from papergraph.reference_expansion_policy import resolver_for_policy
    assert validate_policy(None)['auto_select_policy'] == 'unique_strong_v2'
    assert resolver_for_policy({'auto_select_policy':'unique_strong_v1'}) == 'legacy_v1'
    with pytest.raises(ValueError):
        validate_policy({'auto_select_policy':'unique_strong_v1','resolver_version':'deterministic_v2'})


def test_new_chain_uses_v2_and_retains_budgets(chain):
    ws, _ = chain
    run = ws.create_reference_expansion(['arxiv:2401.10001'], {'max_depth':3})
    assert run['policy']['auto_select_policy'] == 'unique_strong_v2'
    assert run['policy']['resolver_version'] == 'deterministic_v2'
    completed = drain(ws,run['run_id'])
    assert completed['usage']['new_papers'] == 2
    assert all(e.get('decision',{}).get('policy_version') == 'unique_strong_v2' for e in completed['edges'])
    with pytest.raises(ValueError):
        ws.update_reference_expansion_policy(run['run_id'],{'auto_select_policy':'unique_strong_v1'})


def test_explicit_v1_remains_legacy(chain):
    ws, _ = chain
    run = ws.create_reference_expansion(['arxiv:2401.10001'],{'auto_select_policy':'unique_strong_v1'})
    assert run['policy']['resolver_version'] == 'legacy_v1'
    assert drain(ws,run['run_id'])['state'] == 'completed'


def test_direct_reference_conflicting_version_never_imports(chain, monkeypatch):
    ws, calls = chain
    original = ws.plan_external_imports_for_paper
    def plan(paper_id):
        result = original(paper_id)
        for item in result['candidates']:
            item['source']['arxiv_version'] = 'v1'
            item['evidence'].append({'kind':'bibliography_entry','raw_text':'arXiv:' + item['source']['arxiv_id'] + 'v2'})
        return result
    monkeypatch.setattr(ws,'plan_external_imports_for_paper',plan)
    run = ws.create_reference_expansion(['arxiv:2401.10001'])
    result = drain(ws,run['run_id'])
    assert result['state'] == 'waiting' and calls == []
    assert result['usage']['new_papers'] == result['usage']['searches'] == 0
    assert all(e['state'] == 'needs_review' for e in result['edges'])


@pytest.mark.parametrize('policy', ['unique_strong_v1','unique_strong_v2'])
def test_expansion_cache_is_policy_pinned(workspace, policy):
    ws = workspace
    blocked = ws.plan_external_imports_for_paper('local:paper')['blocked'][0]['blocked_id']
    calls = []
    ws.reference_search_provider = lambda q: calls.append(q) or []
    resolver = 'legacy_v1' if policy.endswith('v1') else 'deterministic_v2'
    ws.search_external_reference('local:paper',blocked,max_candidates=100,resolver_version=resolver)
    # A newer incompatible snapshot must not hide the compatible earlier one.
    ws.search_external_reference('local:paper',blocked,max_candidates=100,resolver_version='deterministic_v2' if policy.endswith('v1') else 'legacy_v1')
    run = ws.create_reference_expansion(['local:paper'],{'auto_select_policy':policy})
    done = drain(ws,run['run_id'])
    edge = next(e for e in done['edges'] if e['blocked_id'] == blocked)
    assert edge['search']['search_schema_version'] == (1 if policy.endswith('v1') else 2)
    assert done['usage']['searches'] == len(done['edges']) - 1


def test_migrated_paused_v1_resumes_without_new_defaults(tmp_path, monkeypatch):
    import json
    import sqlite3
    from pathlib import Path
    from contextlib import closing
    from papergraph.workspace import Workspace
    fixtures = Path(__file__).parent / 'fixtures/reference_quality'
    path = tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript((fixtures/'schema8.sql').read_text(encoding='utf-8'))
    old = json.loads((fixtures/'schema8-manifest.json').read_text(encoding='utf-8'))['run']
    with closing(Workspace.open(path)) as ws:
        # Preserve historical evidence/fingerprint. Replace only acquisition for
        # this synthetic fixture, whose original source paths were anonymized.
        monkeypatch.setattr(ws,'_import_reference_target',lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('offline fixture')))
        ws.reference_search_provider = lambda q: []
        resumed = drain(ws,old['run_id'])
        assert resumed['policy'] == old['policy']
        assert resumed['policy']['auto_select_policy'] == 'unique_strong_v1'
        assert resumed['usage']['new_papers'] == old['usage']['new_papers']
        assert resumed['state'] != 'paused'
        assert resumed['edges']
        assert any(e.get('decision',{}).get('policy_version') == 'unique_strong_v1' for e in resumed['edges'])
        assert all(e.get('decision',{}).get('policy_version','unique_strong_v1') == 'unique_strong_v1' for e in resumed['edges'])
