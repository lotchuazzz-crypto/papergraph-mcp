from subprocess import CompletedProcess, TimeoutExpired

import pytest

from tests.test_onboarding import load_checker


EXPECTED = 'a' * 40
TAG = 'refs/tags/v1.2.3'


def test_git_prerequisites_do_not_claim_unchecked_publication(monkeypatch):
    checker = load_checker()
    def unexpected(*args, **kwargs):
        raise AssertionError('Local prerequisite inspection must not contact a remote')
    monkeypatch.setattr(checker.subprocess, 'run', unexpected)
    result = checker.inspect_prerequisites(locator=lambda name: '/tools/' + name, install_source='git')
    assert result['prerequisites_satisfied'] is True
    assert result['publication_verified'] is False
    assert result['publication_verification_basis'] == 'not_checked'
    assert result['ready_for_smoke_test'] is False


def test_unverified_git_launch_never_executes_tag_install():
    calls = []
    result = load_checker().validate_launch(install_source='git', runner=lambda *a, **kw: calls.append(a))
    assert result['reason'] == 'git_publication_not_verified'
    assert calls == []


@pytest.mark.parametrize('stdout,returncode,reason', [
    ('', 2, 'tag_missing'),
    ('', 0, 'tag_missing'),
    (f'{"b" * 40}\t{TAG}\n', 0, 'tag_target_mismatch'),
    (f'{EXPECTED}\t{TAG}\n{"b" * 40}\t{TAG}\n', 0, 'invalid_remote_response'),
    ('not a ref', 0, 'invalid_remote_response'),
    ('', 128, 'remote_unavailable'),
])
def test_git_remote_failures_never_verify_publication(stdout, returncode, reason):
    checker = load_checker()
    def runner(command, **kwargs):
        return CompletedProcess(command, returncode, stdout, 'remote failure')
    result = checker.inspect_git_release(EXPECTED, runner=runner)
    assert result['publication_verified'] is False
    assert result['reason'] == reason


@pytest.mark.parametrize('annotated', [True, False])
def test_live_git_tag_must_match_explicit_reviewed_source(annotated):
    checker, calls = load_checker(), []
    output = (f'{"b" * 40}\t{TAG}\n{EXPECTED}\t{TAG}^{{}}\n' if annotated
              else f'{EXPECTED}\t{TAG}\n')
    def runner(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, output, '')
    result = checker.inspect_git_release(EXPECTED, runner=runner)
    assert result['publication_verified'] is True
    assert result['target_commit'] == EXPECTED
    assert result['verification_basis'] == 'live_remote_tag_matches_expected_source_commit'
    assert calls == [['git', 'ls-remote', '--exit-code', '--tags',
                      'https://github.com/lotchuazzz-crypto/papergraph-mcp.git', TAG, TAG + '^{}']]


def test_git_timeout_is_unknown_and_invalid_expected_sha_does_not_query():
    checker = load_checker()
    def timeout(command, **kwargs):
        raise TimeoutExpired(command, 30)
    assert checker.inspect_git_release(EXPECTED, runner=timeout)['reason'] == 'remote_unavailable'
    with pytest.raises(ValueError, match='40-character'):
        checker.inspect_git_release('main', runner=lambda *a, **kw: pytest.fail('must not query'))


def test_cli_exposes_explicit_remote_verification_failure(monkeypatch, capsys):
    import json
    checker = load_checker()
    monkeypatch.setattr(checker, 'inspect_repository', lambda path: {'available': False})
    monkeypatch.setattr(checker, 'inspect_prerequisites', lambda install_source: {
        'install_source': install_source, 'prerequisites_satisfied': True,
        'publication_verified': False, 'ready_for_smoke_test': False})
    monkeypatch.setattr(checker.subprocess, 'run', lambda command, **kwargs:
        CompletedProcess(command, 2, '', ''))
    assert checker.main(['--install-source', 'git', '--verify-git-release',
                         '--expected-source-commit', EXPECTED, '--smoke-test']) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['publication_verified'] is False
    assert result['ready_for_smoke_test'] is False
    assert result['git_release']['reason'] == 'tag_missing'
    assert result['launch']['reason'] == 'git_publication_not_verified'
