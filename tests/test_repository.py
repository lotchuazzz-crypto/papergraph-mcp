import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/lotchuazzz-crypto/papergraph-mcp"


def read_toml(relative_path: str) -> dict:
    return tomllib.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_project_metadata_is_discoverable_and_keeps_dependencies_separated():
    configuration = read_toml("pyproject.toml")
    project = configuration["project"]

    assert project["version"] == "0.3.1"
    assert project["dependencies"] == [
        "httpx>=0.27,<1",
        "mcp[cli]>=2,<3",
    ]
    assert set(project["keywords"]) == {
        "mcp",
        "arxiv",
        "latex",
        "mathematics",
        "theorem-graph",
        "ai-agents",
    }
    assert set(project["classifiers"]) >= {
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering",
    }
    assert project["urls"] == {
        "Homepage": REPOSITORY_URL,
        "Repository": REPOSITORY_URL,
        "Issues": f"{REPOSITORY_URL}/issues",
        "Releases": f"{REPOSITORY_URL}/releases",
    }

    development = configuration["dependency-groups"]["dev"]
    assert "pytest>=8" in development
    assert "pyyaml>=6,<7" in development
    assert all("yaml" not in dependency.lower() for dependency in project["dependencies"])


def test_lockfile_matches_project_version():
    lockfile = read_toml("uv.lock")
    package = next(
        package
        for package in lockfile["package"]
        if package["name"] == "papergraph-mcp"
    )

    assert package["version"] == "0.3.1"


def test_ci_workflow_is_cross_platform_locked_and_least_privilege():
    workflow_path = ROOT / ".github" / "workflows" / "ci.yml"
    workflow = yaml.load(
        workflow_path.read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert set(workflow["on"]) == {"pull_request", "push"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "true"

    test_job = workflow["jobs"]["test"]
    matrix = test_job["strategy"]["matrix"]
    assert matrix == {
        "os": ["ubuntu-latest", "windows-latest"],
        "python-version": ["3.10", "3.12"],
    }
    assert test_job["env"]["UV_PYTHON"] == "${{ matrix.python-version }}"
    test_steps = "\n".join(
        step.get("run", "") for step in test_job["steps"]
    )
    assert "uv sync --locked --dev" in test_steps
    assert "uv run pytest -q -p no:cacheprovider" in test_steps

    build_job = workflow["jobs"]["build"]
    assert build_job["needs"] == "test"
    assert build_job["runs-on"] == "ubuntu-latest"
    build_steps = "\n".join(
        step.get("run", "") for step in build_job["steps"]
    )
    assert "uv build" in build_steps
    assert "uv venv .smoke-venv" in build_steps
    assert all(
        token in build_steps
        for token in ('"uv"', '"pip"', '"install"', '"--python"')
    )
    assert "papergraph-mcp --version" in build_steps
    assert "papergraph-mcp 0.3.1" in build_steps
    assert 'version="$(.smoke-venv/bin/papergraph-mcp --version)"' in build_steps


def test_generated_build_directories_are_ignored():
    ignored = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    assert "dist/" in ignored
    assert ".smoke-venv/" in ignored
