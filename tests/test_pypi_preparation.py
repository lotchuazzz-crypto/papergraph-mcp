"""Keep publication evidence, Git-source setup and preparation permissions distinct."""
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


def test_pypi_prerequisites_exclude_git_after_verified_publication():
    module = checker()
    paths = {'git': None, 'uv': '/tools/uv', 'uvx': '/tools/uvx'}
    result = module.inspect_prerequisites(locator=paths.get, install_source='pypi')
    assert result['required_commands'] == ['uv', 'uvx']
    assert result['prerequisites_satisfied'] is True
    assert result['publication_verified'] is True
    assert result['ready_for_smoke_test'] is True
    assert result['commands']['git'] is None


def test_unverified_index_launch_does_not_execute_any_command(monkeypatch):
    module = checker()
    monkeypatch.setattr(module, 'PYPI_PUBLICATION_VERIFIED', False)
    paths = {'git': None, 'uv': '/tools/uv', 'uvx': '/tools/uvx'}
    assert module.inspect_prerequisites(locator=paths.get)['ready_for_smoke_test'] is False
    calls = []
    result = module.validate_launch(runner=lambda *a, **kw: calls.append(a), install_source='pypi')
    assert result['ok'] is False
    assert result['reason'] == 'pypi_publication_not_verified'
    assert calls == []


def test_verified_index_launch_uses_the_versioned_package_not_git():
    module = checker()
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


def test_consumer_cli_failure_preserves_the_actual_stderr():
    spec = importlib.util.spec_from_file_location('no_git_smoke', ROOT / 'scripts/smoke_no_git_distribution.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match='consumer cache is read only'):
        module.run_cli([sys.executable, '-c',
                        'import sys; sys.stderr.write("consumer cache is read only"); sys.exit(2)'],
                       env=None, timeout=10)


def test_default_index_readiness_does_not_require_git():
    module = checker()
    paths = {'git': None, 'uv': '/tools/uv', 'uvx': '/tools/uvx'}
    result = module.inspect_prerequisites(locator=paths.get)
    assert result['install_source'] == 'pypi'
    assert result['ready_for_smoke_test'] is True
    assert module.inspect_prerequisites(locator=paths.get, install_source='git')['ready_for_smoke_test'] is False


def test_explicit_git_launch_preserves_tag_source():
    module = checker()
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, 'papergraph-mcp 1.2.0\n', '')
    assert module.validate_launch(runner=runner, install_source='git')['ok'] is True
    assert calls == [['uvx', '--from', module.PAPERGRAPH_SOURCE, 'papergraph-mcp', '--version']]


def test_cli_default_smoke_dispatches_pypi_and_explicit_git_is_preserved(monkeypatch, capsys):
    import json
    module = checker()
    selected = []
    monkeypatch.setattr(module, 'inspect_repository', lambda path: {'available': False})
    monkeypatch.setattr(module, 'inspect_prerequisites', lambda install_source: {'install_source': install_source})
    def launch(install_source):
        selected.append(install_source)
        return {'ok': True}
    monkeypatch.setattr(module, 'validate_launch', launch)
    assert module.main(['--smoke-test']) == 0
    assert json.loads(capsys.readouterr().out)['install_source'] == 'pypi'
    assert module.main(['--install-source', 'git', '--smoke-test']) == 0
    assert json.loads(capsys.readouterr().out)['install_source'] == 'git'
    assert selected == ['pypi', 'git']
