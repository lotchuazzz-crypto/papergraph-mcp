#!/usr/bin/env bash
set -euo pipefail

dist_dir="$(realpath "$1")"
checks_dir="$(cd "$(dirname "$0")" && pwd)"
image=python:3.12-slim-bookworm
docker pull "$image"
docker image inspect --format '{{json .RepoDigests}}' "$image"

for artifact in papergraph_mcp-1.2.0-py3-none-any.whl papergraph_mcp-1.2.0.tar.gz; do
  test -f "$dist_dir/$artifact"
  docker run --rm --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --tmpfs /tmp:rw,exec,size=2g \
    --mount "type=bind,source=$dist_dir,target=/dist,readonly" \
    --mount "type=bind,source=$checks_dir,target=/checks,readonly" \
    --workdir /tmp "$image" sh -eu -c '
      python /checks/smoke_no_git_distribution.py --check-environment
      python -m venv /tmp/tools
      /tmp/tools/bin/python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: uv
      # Add uv to the existing container PATH; do not hide any system directories.
      export PATH="/tmp/tools/bin:$PATH"
      export UV_CACHE_DIR=/tmp/uv-bootstrap-cache
      export UV_PYTHON_DOWNLOADS=never
      test ! -e "$UV_CACHE_DIR"
      # Readiness checks do not launch/download; artifact acceptance follows below.
      python /checks/check_onboarding.py > /tmp/pypi-check.json
      python /checks/check_onboarding.py --install-source git > /tmp/git-check.json
      python -c '\''import json; p=json.load(open("/tmp/pypi-check.json")); g=json.load(open("/tmp/git-check.json")); assert p["commands"]["git"] is None; assert p["install_source"] == "pypi"; assert p["required_commands"] == ["uv", "uvx"]; assert p["prerequisites_satisfied"] is True; assert p["publication_verified"] is True; assert p["ready_for_smoke_test"] is True; assert "launch" not in p; assert g["required_commands"] == ["git", "uv", "uvx"]; assert g["ready_for_smoke_test"] is False; print(json.dumps({"pypi_prerequisites_without_git": "passed", "git_source_without_git": "not_ready"}))'\''
      uv run --no-project --with "/dist/$1" python /checks/smoke_no_git_distribution.py \
        --artifact "/dist/$1" --expected-sha 60977c06217905e5c1db15fbf27aff4ca208a517
    ' sh "$artifact"
done
