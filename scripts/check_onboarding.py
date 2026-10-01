from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


PAPERGRAPH_VERSION = "1.1.7"
PAPERGRAPH_SOURCE = (
    "git+https://github.com/lotchuazzz-crypto/"
    "papergraph-mcp.git@v1.1.7"
)
LAUNCH_COMMAND = [
    "uvx",
    "--from",
    PAPERGRAPH_SOURCE,
    "papergraph-mcp",
    "--version",
]


def inspect_prerequisites(
    locator: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    commands = {name: locator(name) for name in ("git", "uv", "uvx")}
    return {
        "platform": platform.system().lower(),
        "commands": commands,
        "ready_for_smoke_test": all(commands.values()),
    }


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
) -> dict[str, object]:
    try:
        completed = runner(
            LAUNCH_COMMAND,
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
        "--smoke-test",
        action="store_true",
        help="Run the pinned PaperGraph version command (may access the network).",
    )
    args = parser.parse_args(argv)
    result = inspect_prerequisites()
    result["repository"] = inspect_repository(args.repository)
    if args.smoke_test:
        result["launch"] = validate_launch()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.smoke_test and not result["launch"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
