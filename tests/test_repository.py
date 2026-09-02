import tomllib
from pathlib import Path


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
