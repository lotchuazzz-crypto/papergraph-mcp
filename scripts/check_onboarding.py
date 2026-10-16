from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


PAPERGRAPH_VERSION = "1.2.2"
PAPERGRAPH_SOURCE = (
    "git+https://github.com/lotchuazzz-crypto/"
    "papergraph-mcp.git@v1.2.2"
)
LAUNCH_COMMAND = [
    "uvx",
    "--from",
    PAPERGRAPH_SOURCE,
    "papergraph-mcp",
    "--version",
]
PYPI_SOURCE = f"papergraph-mcp=={PAPERGRAPH_VERSION}"
# v1.2.2 public bytes and fresh Git-free public-index acceptance are recorded in
# docs/reference/v1.2.2-publication.md. Frozen R/tag/package files remain unchanged.
PYPI_PUBLICATION_VERIFIED = True


def inspect_prerequisites(
    locator: Callable[[str], str | None] = shutil.which,
    install_source: str = "pypi",
) -> dict[str, object]:
    if install_source not in ("git", "pypi"):
        raise ValueError(f"Unknown install source: {install_source}")
    commands = {name: locator(name) for name in ("git", "uv", "uvx")}
    required = ["git", "uv", "uvx"] if install_source == "git" else ["uv", "uvx"]
    satisfied = all(commands[name] for name in required)
    verified = PYPI_PUBLICATION_VERIFIED if install_source == 'pypi' else False
    return {
        "platform": platform.system().lower(),
        "commands": commands,
        "install_source": install_source,
        "required_commands": required,
        "prerequisites_satisfied": satisfied,
        "publication_verified": verified,
        "publication_verification_basis": ('recorded_official_index_acceptance' if verified else 'not_checked'),
        "ready_for_smoke_test": bool(satisfied and verified),
    }


def inspect_git_release(expected_source_commit: str, runner=None) -> dict[str, object]:
    """Explicit read-only remote verification, never inferred from local tools.

    The expected source is supplied from reviewed release evidence; accepting
    any available tag without checking its target would not bind the source.
    """
    if not isinstance(expected_source_commit, str) or not re.fullmatch(r'[a-fA-F0-9]{40}', expected_source_commit):
        raise ValueError('Expected source commit must be a 40-character hexadecimal SHA')
    expected_source_commit = expected_source_commit.lower()
    tag = f'refs/tags/v{PAPERGRAPH_VERSION}'
    result = {'publication_verified': False, 'verification_basis': 'live_remote_tag_check',
              'tag': tag, 'expected_source_commit': expected_source_commit, 'target_commit': None}
    command = ['git', 'ls-remote', '--exit-code', '--tags',
               'https://github.com/lotchuazzz-crypto/papergraph-mcp.git', tag, tag + '^{}']
    try:
        completed = (runner or subprocess.run)(command, check=False, capture_output=True,
                                               text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**result, 'reason': 'remote_unavailable', 'detail': str(exc)}
    if completed.returncode not in (0, 2):
        return {**result, 'reason': 'remote_unavailable', 'returncode': completed.returncode,
                'detail': completed.stderr.strip()}
    if completed.returncode == 2:
        return {**result, 'reason': 'tag_missing' if not completed.stdout.strip() else 'invalid_remote_response'}
    refs = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if (len(fields) != 2 or fields[1] not in (tag, tag + '^{}')
                or re.fullmatch(r'[a-fA-F0-9]{40}', fields[0]) is None or fields[1] in refs):
            return {**result, 'reason': 'invalid_remote_response'}
        refs[fields[1]] = fields[0].lower()
    if tag not in refs:
        return {**result, 'reason': 'tag_missing'}
    target = refs.get(tag + '^{}', refs[tag])
    if target != expected_source_commit:
        return {**result, 'target_commit': target, 'reason': 'tag_target_mismatch'}
    return {**result, 'publication_verified': True, 'target_commit': target, 'reason': 'verified',
            'verification_basis': 'live_remote_tag_matches_expected_source_commit'}


def inspect_repository(path: Path) -> dict[str, object]:
    """Compare the checkout with local remote refs, without fetching or switching."""
    result: dict[str, object] = {
        "available": False, "root": None, "branch": None, "head": None,
        "default_branch": None, "default_head": None, "dirty": None,
        "head_matches_default": None, "on_default_branch": None,
        "comparison_basis": None, "freshness_verified": False,
    }

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=path, check=True, capture_output=True,
            text=True, timeout=10,
        ).stdout.strip()

    try:
        result.update(
            root=git("rev-parse", "--show-toplevel"),
            head=git("rev-parse", "HEAD"),
            branch=git("branch", "--show-current") or None,
            dirty=bool(git("status", "--porcelain")), available=True,
        )
        # Do not guess that main is the remote's default branch.
        default_ref = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        default_head = git("rev-parse", "--verify", default_ref + "^{commit}")
        default_branch = default_ref.removeprefix("origin/")
        result.update(
            default_branch=default_branch, default_head=default_head,
            head_matches_default=result["head"] == default_head,
            on_default_branch=result["branch"] == default_branch,
            comparison_basis="local_remote_tracking_ref",
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        result["detail"] = str(exc)
    return result


def validate_launch(
    runner: Callable[..., Any] = subprocess.run,
    install_source: str = "pypi",
    git_release_verification: dict | None = None,
) -> dict[str, object]:
    if install_source not in ("git", "pypi"):
        raise ValueError(f"Unknown install source: {install_source}")
    if install_source == "pypi" and not PYPI_PUBLICATION_VERIFIED:
        return {"ok": False, "reason": "pypi_publication_not_verified", "source": PYPI_SOURCE}
    if install_source == 'git' and not (git_release_verification or {}).get('publication_verified'):
        return {'ok': False, 'reason': 'git_publication_not_verified', 'source': PAPERGRAPH_SOURCE}
    command = LAUNCH_COMMAND if install_source == "git" else [
        "uvx", "--from", PYPI_SOURCE, "papergraph-mcp", "--version",
    ]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "launch_error", "detail": str(exc)}

    version = completed.stdout.strip()
    expected = f"papergraph-mcp {PAPERGRAPH_VERSION}"
    if completed.returncode != 0:
        return {
            "ok": False,
            "reason": "nonzero_exit",
            "returncode": completed.returncode,
            "stderr": completed.stderr.strip(),
        }
    return {
        "ok": version == expected,
        "reason": "ok" if version == expected else "unexpected_version",
        "version": version,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect PaperGraph onboarding prerequisites without changing them."
    )
    parser.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parents[1],
        help="Repository to inspect using local refs only (no network or mutation).",
    )
    parser.add_argument(
        "--install-source", choices=("pypi", "git"), default="pypi",
        help="Verified PyPI launch (default, no Git required), or optional Git-tag launch.",
    )
    parser.add_argument(
        '--verify-git-release', action='store_true',
        help='Read the live Git release tag and compare its target with --expected-source-commit (network, read-only).',
    )
    parser.add_argument('--expected-source-commit', help='Reviewed 40-character source SHA for explicit Git release verification.')
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run the pinned PaperGraph version command (may access the network).",
    )
    args = parser.parse_args(argv)
    if args.verify_git_release and (args.install_source != 'git' or not args.expected_source_commit):
        parser.error('--verify-git-release requires --install-source git and --expected-source-commit')
    if args.expected_source_commit and not args.verify_git_release:
        parser.error('--expected-source-commit requires --verify-git-release')
    result = inspect_prerequisites(install_source=args.install_source)
    result["repository"] = inspect_repository(args.repository)
    if args.verify_git_release:
        try:
            verification = inspect_git_release(args.expected_source_commit)
        except ValueError as exc:
            parser.error(str(exc))
        result['git_release'] = verification
        result['publication_verified'] = verification['publication_verified']
        result['publication_verification_basis'] = verification['verification_basis']
        result['ready_for_smoke_test'] = bool(result['prerequisites_satisfied'] and verification['publication_verified'])
    if args.smoke_test:
        result["launch"] = (validate_launch(install_source='git', git_release_verification=result['git_release'])
                            if args.verify_git_release else validate_launch(install_source=args.install_source))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.smoke_test and not result["launch"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
