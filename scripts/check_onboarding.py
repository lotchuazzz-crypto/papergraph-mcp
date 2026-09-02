from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from collections.abc import Callable, Sequence
from typing import Any


PAPERGRAPH_VERSION = "0.4.0"
PAPERGRAPH_SOURCE = (
    "git+https://github.com/lotchuazzz-crypto/"
    "papergraph-mcp.git@v0.4.0"
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
        "ready_for_smoke_test": bool(commands["uv"] and commands["uvx"]),
    }


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
        "--smoke-test",
        action="store_true",
        help="Run the pinned PaperGraph version command (may access the network).",
    )
    args = parser.parse_args(argv)
    result = inspect_prerequisites()
    if args.smoke_test:
        result["launch"] = validate_launch()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.smoke_test and not result["launch"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
