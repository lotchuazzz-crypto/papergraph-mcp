"""Public-index acceptance cannot publish or silently use a local package."""
import importlib.util
import os
from pathlib import Path
import re
import sys

import pytest
import yaml

from tests.test_pypi_publish_draft import validator

ROOT = Path(__file__).resolve().parents[1]


def smoke():
    spec = importlib.util.spec_from_file_location('index_smoke', ROOT / 'scripts/smoke_no_git_distribution.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_index_command_is_fixed_to_public_version_and_not_a_local_artifact():
    command = smoke().consumer_command('/tools/uvx', public_index=True)
    assert command == ['/tools/uvx', '--no-config', '--no-env-file', '--default-index',
                       'https://pypi.org/simple', '--from', 'papergraph-mcp==1.2.0', 'papergraph-mcp']


def test_artifact_command_preserves_the_existing_consumer():
    artifact = Path('/dist/release.whl')
    assert smoke().consumer_command('/tools/uvx', artifact) == [
        '/tools/uvx', '--from', str(artifact), 'papergraph-mcp']


def test_index_command_cannot_substitute_a_local_artifact():
    with pytest.raises(ValueError):
        smoke().consumer_command('/tools/uvx', Path('/dist/release.whl'), public_index=True)


def test_public_index_identity_accepts_only_the_reviewed_source():
    identity = dict(validator().EXPECTED_IDENTITY, channel='release_version')
    smoke().validate_public_identity(identity)


@pytest.mark.parametrize('field,value', [
    ('source_commit', '0' * 40), ('source_tree_sha256', '0' * 64),
    ('tracked_dirty', True), ('origin', 'unknown'), ('schema_version', 2),
])
def test_public_index_identity_rejects_wrong_or_unknown_provenance(field, value):
    identity = dict(validator().EXPECTED_IDENTITY, channel='release_version')
    identity[field] = value
    with pytest.raises(RuntimeError, match='reviewed public release identity'):
        smoke().validate_public_identity(identity)


def test_public_index_environment_removes_index_and_checkout_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv('UV_INDEX', 'https://other.invalid/simple')
    monkeypatch.setenv('UV_INDEX_URL', 'https://other.invalid/simple')
    monkeypatch.setenv('UV_FIND_LINKS', '/local/packages')
    monkeypatch.setenv('PYTHONPATH', '/checkout/src')
    monkeypatch.setenv('PYTHONHOME', '/checkout/python')
    module = smoke()
    env = module.consumer_environment(tmp_path / 'cache', tmp_path / 'tools', public_index=True)
    assert not {'UV_INDEX', 'UV_INDEX_URL', 'UV_FIND_LINKS', 'PYTHONPATH', 'PYTHONHOME'} & env.keys()
    assert env['PATH'] == os.environ['PATH']  # No hiding an installed Git executable.
    assert env['UV_CACHE_DIR'] == str(tmp_path / 'cache')
    assert env['UV_TOOL_DIR'] == str(tmp_path / 'tools')
    assert env['UV_PYTHON_DOWNLOADS'] == 'never'


def test_public_index_cli_uses_fixed_source_and_no_artifact(monkeypatch):
    module = smoke()
    calls = []

    async def verify(artifact, expected_sha, *, public_index=False):
        calls.append((artifact, expected_sha, public_index))

    monkeypatch.setattr(module, 'verify', verify)
    monkeypatch.setattr(module, 'check_environment', lambda: None)
    monkeypatch.setattr(sys, 'argv', ['smoke', '--public-index'])
    module.main()
    assert calls == [(None, validator().SOURCE_SHA, True)]


@pytest.mark.parametrize('arguments', [
    ['--public-index', '--artifact', '/dist/release.whl'],
    ['--public-index', '--expected-sha', '0' * 40],
])
def test_index_cli_rejects_artifact_or_source_overrides_before_verification(monkeypatch, arguments):
    module = smoke()
    calls = []
    monkeypatch.setattr(module, 'check_environment', lambda: calls.append('environment'))
    monkeypatch.setattr(sys, 'argv', ['smoke', *arguments])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert calls == []


def test_index_workflow_is_manual_main_only_and_has_no_publishing_permissions():
    path = ROOT / '.github/workflows/pypi-index-verification.yml'
    assert path.exists(), 'Public-index verification workflow has not been implemented'
    text = path.read_text(encoding='utf-8')
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'workflow_dispatch'}
    assert not workflow['on']['workflow_dispatch']
    assert workflow['permissions'] == {'contents': 'read'}
    assert len(workflow['jobs']) == 1
    job = next(iter(workflow['jobs'].values()))
    assert "github.ref == 'refs/heads/main'" in job['if']
    assert "github.repository == 'lotchuazzz-crypto/papergraph-mcp'" in job['if']
    assert job['runs-on'] == 'ubuntu-latest'
    assert 'environment' not in job
    assert job.get('permissions', {'contents': 'read'}) == {'contents': 'read'}
    uses = [step['uses'] for step in job['steps'] if 'uses' in step]
    assert len(uses) == 1 and uses[0].startswith('actions/checkout@')
    assert re.search(r'@[a-f0-9]{40}$', uses[0])
    assert job['steps'][0]['with']['persist-credentials'] == 'false'
    assert 'id-token' not in text and 'secrets.' not in text
    assert not re.search(r'\b(?:uv\s+publish|twine\s+upload|uv\s+build)\b', text)


def test_index_consumer_has_fresh_container_and_index_install_not_a_local_mount():
    path = ROOT / '.github/workflows/pypi-index-verification.yml'
    assert path.exists(), 'Public-index verification workflow has not been implemented'
    text = path.read_text(encoding='utf-8')
    assert 'python:3.12-slim-bookworm' in text and '.RepoDigests' in text
    assert '--read-only' in text and '--cap-drop=ALL' in text
    assert '--security-opt=no-new-privileges' in text and '--tmpfs /tmp:' in text
    assert 'target=/checks,readonly' in text
    assert 'target=/dist' not in text and 'release-source' not in text
    assert text.index('--check-environment') < text.index('pip install')
    assert 'test ! -e "$UV_CACHE_DIR"' in text
    assert '--default-index https://pypi.org/simple' in text
    assert '--with papergraph-mcp==1.2.0' in text
    assert '--public-index' in text and '--artifact' not in text
