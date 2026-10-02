import subprocess

from tests.test_onboarding import load_checker


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def repository(tmp_path):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "--allow-empty", "-m", "initial")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(tmp_path, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    return tmp_path


def test_git_is_required_for_git_source_launch():
    result = load_checker().inspect_prerequisites(
        locator=lambda name: None if name == "git" else "/tools/" + name
    )
    assert result["ready_for_smoke_test"] is False


def test_old_dirty_branch_is_reported_without_mutation(tmp_path):
    path = repository(tmp_path)
    git(path, "switch", "-c", "old-feature")
    git(path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "--allow-empty", "-m", "feature")
    (path / "user-note.txt").write_text("preserve me", encoding="utf-8")
    before = git(path, "status", "--porcelain")
    result = load_checker().inspect_repository(path)
    assert result["branch"] == "old-feature"
    assert result["dirty"] is True
    assert result["head_matches_default"] is False
    assert result["on_default_branch"] is False
    assert result["freshness_verified"] is False
    assert result["comparison_basis"] == "local_remote_tracking_ref"
    assert git(path, "status", "--porcelain") == before
    assert git(path, "branch", "--show-current") == "old-feature"
    assert (path / "user-note.txt").read_text() == "preserve me"


def test_matching_default_and_detached_head_are_distinct(tmp_path):
    path = repository(tmp_path)
    checker = load_checker()
    result = checker.inspect_repository(path)
    assert result["head_matches_default"] is True
    assert result["on_default_branch"] is True
    git(path, "switch", "--detach")
    result = checker.inspect_repository(path)
    assert result["branch"] is None
    assert result["head_matches_default"] is True
    assert result["on_default_branch"] is False


def test_missing_default_ref_is_unknown_not_current(tmp_path):
    path = repository(tmp_path)
    git(path, "update-ref", "-d", "refs/remotes/origin/main")
    result = load_checker().inspect_repository(path)
    assert result["available"] is True
    assert result["head_matches_default"] is None
    assert result["default_head"] is None


def test_nonrepository_is_reported_without_crashing(tmp_path, monkeypatch):
    # Full-suite basetemp may be inside the checkout; block parent discovery.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    result = load_checker().inspect_repository(tmp_path)
    assert result["available"] is False
    assert result["freshness_verified"] is False


def test_missing_git_and_timeout_are_reported(monkeypatch, tmp_path):
    checker = load_checker()
    for error in (OSError("missing git"), subprocess.TimeoutExpired("git", 10)):
        def fail(*args, **kwargs):
            raise error
        monkeypatch.setattr(checker.subprocess, "run", fail)
        assert checker.inspect_repository(tmp_path)["available"] is False
