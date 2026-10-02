import json
import subprocess


def test_candidate_has_no_fictional_release_tag(monkeypatch):
    import papergraph.diagnostics as diagnostics
    monkeypatch.setattr(diagnostics, 'distribution_version', lambda _: '1.2.0.dev0')
    result = diagnostics.environment_diagnostics()
    assert result['release_tag'] is None
    assert result['build_identity']['channel'] == 'development_candidate'
    assert result['recommended_source'].endswith('@v1.1.7')
    assert result['recommended_source_role'] == 'stable_release_not_running_candidate'


def test_build_identity_preserves_source_commit_across_archive_and_detects_edits(tmp_path):
    from papergraph.build_identity import build_source_identity
    package = tmp_path / 'src' / 'papergraph'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'sample.py').write_text('value = 1\n', encoding='utf-8')
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="papergraph-mcp"\n', encoding='utf-8')
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Fixture',
                    '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'Fixture'],
                   check=True, capture_output=True)
    identity = build_source_identity(tmp_path)
    assert len(identity['source_commit']) == 40
    assert identity['tracked_dirty'] is False
    assert 'path' not in json.dumps(identity)
    # A source archive inside another repository must not inherit its parent's Git identity.
    archive = tmp_path / 'archive'
    archive_package = archive / 'src' / 'papergraph'
    archive_package.mkdir(parents=True)
    for name in ('__init__.py', 'sample.py'):
        (archive_package / name).write_bytes((package / name).read_bytes())
    (archive / 'pyproject.toml').write_bytes((tmp_path / 'pyproject.toml').read_bytes())
    (archive_package / '_build_info.json').write_text(json.dumps(identity), encoding='utf-8')
    assert build_source_identity(archive) == identity
    (archive_package / 'sample.py').write_text('value = 2\n', encoding='utf-8')
    changed = build_source_identity(archive)
    assert changed['source_commit'] is None
    assert changed['source_tree_sha256'] != identity['source_tree_sha256']
    assert changed['origin'] == 'source_archive_unknown'
