import pytest
from papergraph.reference_expansion_policy import validate_policy
from tests.test_reference_expansion import chain, drain


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
