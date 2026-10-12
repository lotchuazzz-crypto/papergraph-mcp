"""New package metadata must not inherit the previous release's acceptance."""
import importlib.util
from pathlib import Path


def test_unverified_patch_does_not_launch_or_claim_public_index_readiness():
    path = Path(__file__).parents[1] / 'scripts/check_onboarding.py'
    spec = importlib.util.spec_from_file_location('v121_guard', path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    assert checker.PAPERGRAPH_VERSION == '1.2.1'
    assert checker.PYPI_PUBLICATION_VERIFIED is False
    result = checker.inspect_prerequisites(locator={'uv': '/tools/uv', 'uvx': '/tools/uvx'}.get)
    assert result['prerequisites_satisfied'] is True
    assert result['publication_verified'] is False
    assert result['ready_for_smoke_test'] is False
    calls = []
    result = checker.validate_launch(runner=lambda *a, **kw: calls.append(a))
    assert result['reason'] == 'pypi_publication_not_verified'
    assert result['source'] == 'papergraph-mcp==1.2.1'
    assert calls == []
