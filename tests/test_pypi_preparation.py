"""Keep preparation distinct from index publication and Git-source setup."""
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def checker():
    spec = importlib.util.spec_from_file_location('pypi_checker', ROOT / 'scripts/check_onboarding.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pypi_prerequisites_exclude_git_but_do_not_claim_publication():
    module = checker()
    paths = {'git': None, 'uv': '/tools/uv', 'uvx': '/tools/uvx'}
    result = module.inspect_prerequisites(locator=paths.get, install_source='pypi')
    assert result['required_commands'] == ['uv', 'uvx']
    assert result['prerequisites_satisfied'] is True
    assert result['publication_verified'] is False
    assert result['ready_for_smoke_test'] is False
    assert result['commands']['git'] is None


def test_unverified_index_launch_does_not_execute_any_command():
    module = checker()
    calls = []
    result = module.validate_launch(runner=lambda *a, **kw: calls.append(a), install_source='pypi')
    assert result['ok'] is False
    assert result['reason'] == 'pypi_publication_not_verified'
    assert calls == []


def test_verified_index_launch_uses_the_versioned_package_not_git(monkeypatch):
    module = checker()
    monkeypatch.setattr(module, 'PYPI_PUBLICATION_VERIFIED', True, raising=False)
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, 'papergraph-mcp 1.2.0\n', '')

    result = module.validate_launch(runner=runner, install_source='pypi')
    assert result['ok'] is True
    assert calls == [['uvx', '--from', 'papergraph-mcp==1.2.0', 'papergraph-mcp', '--version']]


def test_preparation_workflow_cannot_publish_or_request_oidc():
    path = ROOT / '.github/workflows/pypi-preparation.yml'
    text = path.read_text(encoding='utf-8')
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'workflow_dispatch', 'workflow_call'}
    assert workflow['permissions'] == {'contents': 'read'}
    for job in workflow['jobs'].values():
        assert 'environment' not in job
        assert job.get('permissions', {'contents': 'read'}) == {'contents': 'read'}
        for step in job['steps']:
            if 'uses' in step:
                assert re.search(r'@[a-f0-9]{40}$', step['uses'])
    assert 'id-token' not in text
    assert 'secrets.' not in text
    assert not re.search(r'\b(?:uv\s+publish|twine\s+upload)\b', text)
    assert '60977c06217905e5c1db15fbf27aff4ca208a517' in text
    ci = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    assert ci['jobs']['pypi-preparation']['uses'] == './.github/workflows/pypi-preparation.yml'


def test_no_git_consumer_guard_rejects_a_host_with_git():
    if shutil.which('git') is None:
        pytest.skip('This negative test requires a host with Git; the container covers absence.')
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/smoke_no_git_distribution.py'),
                             '--check-environment'], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Git must be absent' in result.stderr
