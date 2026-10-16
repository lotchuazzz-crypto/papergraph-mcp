"""Recorded acceptance enables this version; unverified releases still fail closed."""
import importlib.util
from pathlib import Path


def load_checker():
    path = Path(__file__).parents[1] / 'scripts/check_onboarding.py'
    spec = importlib.util.spec_from_file_location('v121_guard', path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def test_verified_release_is_ready_without_git_and_launches_the_pinned_index_package():
    checker = load_checker()
    assert checker.PAPERGRAPH_VERSION == '1.2.2'
    assert checker.PYPI_PUBLICATION_VERIFIED is True
    result = checker.inspect_prerequisites(locator={'uv': '/tools/uv', 'uvx': '/tools/uvx'}.get)
    assert result['commands']['git'] is None
    assert result['publication_verified'] is True
    assert result['ready_for_smoke_test'] is True
    calls = []

    def runner(command, **kwargs):
        from subprocess import CompletedProcess
        calls.append(command)
        return CompletedProcess(command, 0, 'papergraph-mcp 1.2.2\n', '')

    assert checker.validate_launch(runner=runner)['ok'] is True
    assert calls == [['uvx', '--from', 'papergraph-mcp==1.2.2', 'papergraph-mcp', '--version']]


def test_unverified_patch_does_not_launch_or_claim_public_index_readiness():
    checker = load_checker()
    checker.PYPI_PUBLICATION_VERIFIED = False
    result = checker.inspect_prerequisites(locator={'uv': '/tools/uv', 'uvx': '/tools/uvx'}.get)
    assert result['prerequisites_satisfied'] is True
    assert result['publication_verified'] is False
    assert result['ready_for_smoke_test'] is False
    calls = []
    result = checker.validate_launch(runner=lambda *a, **kw: calls.append(a))
    assert result['reason'] == 'pypi_publication_not_verified'
    assert result['source'] == 'papergraph-mcp==1.2.2'
    assert calls == []
