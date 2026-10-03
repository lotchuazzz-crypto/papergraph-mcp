"""Release candidates stay tied to reviewed bytes; publication stays disabled."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = '60977c06217905e5c1db15fbf27aff4ca208a517'
SOURCE_DIGEST = '9e873fd94cfa16b41b67acd2a1b19caab7083717b36e758553873bb9153da58a'


def validator():
    path = ROOT / 'scripts/check_release_artifacts.py'
    assert path.exists(), 'Reviewed-artifact validator has not been implemented'
    spec = importlib.util.spec_from_file_location('release_artifacts', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate(tmp_path, kind, *, source=SOURCE_SHA, dirty=False, version='1.2.0'):
    manifest = json.dumps({'schema_version': 1, 'source_commit': source,
                           'source_tree_sha256': SOURCE_DIGEST,
                           'tracked_dirty': dirty, 'origin': 'git_checkout'}).encode()
    metadata = f'Metadata-Version: 2.3\nName: papergraph-mcp\nVersion: {version}\n'.encode()
    if kind == 'wheel':
        path = tmp_path / 'papergraph_mcp-1.2.0-py3-none-any.whl'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('papergraph/_build_info.json', manifest)
            archive.writestr('papergraph_mcp-1.2.0.dist-info/METADATA', metadata)
    else:
        path = tmp_path / 'papergraph_mcp-1.2.0.tar.gz'
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in [('src/papergraph/_build_info.json', manifest), ('PKG-INFO', metadata)]:
                info = tarfile.TarInfo('papergraph_mcp-1.2.0/' + name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
def test_candidate_checks_metadata_and_embedded_release_identity(tmp_path, kind):
    path, digest = candidate(tmp_path, kind)
    result = validator().validate_distribution(path, digest)
    assert result['sha256'] == digest
    assert result['build_identity']['source_commit'] == SOURCE_SHA
    assert result['build_identity']['tracked_dirty'] is False


def test_downloaded_candidate_cannot_be_replaced_with_different_bytes(tmp_path):
    path, approved_digest = candidate(tmp_path, 'wheel')
    with path.open('ab') as stream:
        stream.write(b'unreviewed replacement')
    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        validator().validate_distribution(path, approved_digest)


@pytest.mark.parametrize('kind', ['wheel', 'sdist'])
@pytest.mark.parametrize('change', [dict(source='a' * 40), dict(dirty=True), dict(version='1.2.1')])
def test_matching_checksum_does_not_excuse_wrong_source_or_version(tmp_path, kind, change):
    path, digest = candidate(tmp_path, kind, **change)
    with pytest.raises(ValueError, match='release identity|package metadata'):
        validator().validate_distribution(path, digest)


def test_release_directory_rejects_extra_files(tmp_path):
    (tmp_path / 'unreviewed.whl').write_bytes(b'foreign artifact')
    with pytest.raises(ValueError, match='exactly the two approved distributions'):
        validator().verify_directory(tmp_path)


@pytest.mark.parametrize('producer,consumer', [('101', '102'), ('101,102', '101'), ('101', None)])
def test_artifact_from_another_or_unknown_run_is_rejected(producer, consumer):
    with pytest.raises(ValueError, match='same workflow run'):
        validator().validate_run_identity(producer, consumer)


def test_artifact_from_current_run_is_accepted():
    validator().validate_run_identity('101', '101')


def workflow(name):
    path = ROOT / '.github/workflows' / name
    assert path.exists(), f'{name} has not been implemented'
    return yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)


def test_manual_workflow_cannot_enable_publication_or_request_credentials():
    draft = workflow('pypi-publish.yml')
    assert set(draft['on']) == {'workflow_dispatch'}
    assert not draft['on']['workflow_dispatch']  # No user input can enable publishing.
    assert draft['jobs']['publish']['if'] == '${{ false }}'
    assert set(draft['jobs']['publish']['needs']) == {'build', 'verify'}
    assert 'refs/heads/main' in draft['jobs']['build']['if']
    for name in ('pypi-publish.yml', 'pypi-preparation.yml', 'pypi-artifact-verification.yml'):
        value = workflow(name)
        assert value['permissions'] == {'contents': 'read'}
        for job in value['jobs'].values():
            assert 'environment' not in job
            assert job.get('permissions', {'contents': 'read'}) == {'contents': 'read'}
            for step in job.get('steps', []):
                assert 'gh-action-pypi-publish' not in step.get('uses', '')
                assert not re.search(r'\b(?:uv\s+publish|twine\s+upload)\b', step.get('run', ''))
                if 'uses' in step:
                    assert re.search(r'@[a-f0-9]{40}$', step['uses'])


def test_only_validated_candidates_are_saved_and_same_run_artifact_is_reused():
    producer = workflow('pypi-preparation.yml')
    assert isinstance(producer['on']['workflow_call'], dict), 'Artifact handoff has not been implemented'
    assert producer['on']['workflow_call']['inputs']['save_artifacts']['default'] == 'false'
    steps = producer['jobs']['prepare']['steps']
    names = [step['name'] for step in steps]
    assert names.index('Verify wheel and sdist in fresh containers without Git') < names.index('Save verified release candidates')
    assert names.index('Verify approved release hashes and manifests') < names.index('Save verified release candidates')
    upload = next(step for step in steps if step['name'] == 'Save verified release candidates')
    assert upload['if'] == '${{ inputs.save_artifacts }}'
    assert upload['with']['overwrite'] == 'false'
    assert upload['with']['if-no-files-found'] == 'error'
    verify = workflow('pypi-artifact-verification.yml')
    download = next(step for step in verify['jobs']['verify']['steps'] if 'download-artifact@' in step.get('uses', ''))
    assert download['with']['artifact-ids'] == '${{ inputs.artifact_id }}'
    assert not ({'github-token', 'repository', 'run-id', 'pattern'} & download['with'].keys())
    assert any('--producer-run-id' in step.get('run', '') for step in verify['jobs']['verify']['steps'])
    ci = workflow('ci.yml')['jobs']
    assert ci['pypi-preparation']['with']['save_artifacts'] == 'true'
    assert ci['pypi-artifact-verification']['needs'] == 'pypi-preparation'
    assert ci['pypi-artifact-verification']['with']['artifact_id'] == '${{ needs.pypi-preparation.outputs.artifact_id }}'
