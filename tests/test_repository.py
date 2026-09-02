import re
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/lotchuazzz-crypto/papergraph-mcp"


def read_toml(relative_path: str) -> dict:
    return tomllib.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_project_metadata_is_discoverable_and_keeps_dependencies_separated():
    configuration = read_toml("pyproject.toml")
    project = configuration["project"]

    assert project["version"] == "0.4.0"
    assert project["dependencies"] == [
        "httpx>=0.27,<1",
        "mcp[cli]>=2,<3",
        "pybtex>=0.25,<0.27",
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
    assert "tomli>=2,<3; python_version < '3.11'" in development
    assert all("yaml" not in dependency.lower() for dependency in project["dependencies"])


def test_lockfile_matches_project_version():
    lockfile = read_toml("uv.lock")
    package = next(
        package
        for package in lockfile["package"]
        if package["name"] == "papergraph-mcp"
    )

    assert package["version"] == "0.4.0"


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
    assert "papergraph-mcp 0.4.0" in build_steps
    assert 'version="$(.smoke-venv/bin/papergraph-mcp --version)"' in build_steps


def test_generated_build_directories_are_ignored():
    ignored = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    assert "dist/" in ignored
    assert ".smoke-venv/" in ignored


def read_yaml(relative_path: str) -> dict:
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


def test_bug_report_form_collects_reproduction_and_protects_private_data():
    form = read_yaml(".github/ISSUE_TEMPLATE/bug_report.yml")
    fields = {
        item["id"]: item
        for item in form["body"]
        if "id" in item
    }

    assert form["name"] == "Bug report"
    assert form["description"]
    assert "bug" in form["labels"]
    assert set(fields) >= {
        "version",
        "operating_system",
        "python_version",
        "input_type",
        "reproduction",
        "expected",
        "actual",
        "logs",
    }
    for field_id in set(fields) - {"logs"}:
        assert fields[field_id]["validations"]["required"] is True

    visible_text = (ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text(
        encoding="utf-8"
    ).lower()
    assert "private paper" in visible_text
    assert "token" in visible_text
    assert "secret" in visible_text


def test_feature_request_form_focuses_on_the_problem():
    form = read_yaml(".github/ISSUE_TEMPLATE/feature_request.yml")
    field_ids = {
        item["id"]
        for item in form["body"]
        if "id" in item
    }

    assert form["name"] == "Feature request"
    assert form["description"]
    assert "enhancement" in form["labels"]
    assert field_ids >= {"problem", "outcome", "alternatives", "context"}


def test_issue_configuration_disables_blank_issues():
    configuration = read_yaml(".github/ISSUE_TEMPLATE/config.yml")

    assert configuration == {
        "blank_issues_enabled": False,
        "contact_links": [],
    }


def test_pull_request_template_requires_testing_and_sensitive_data_review():
    template = (ROOT / ".github/pull_request_template.md").read_text(
        encoding="utf-8"
    )

    for heading in (
        "## Summary",
        "## Motivation",
        "## Testing",
        "## Compatibility",
        "## Documentation",
    ):
        assert heading in template
    assert "sensitive data" in template.lower()
    assert "deterministic" in template.lower()


def test_contributing_guide_documents_reproducible_development():
    guide = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    normalized_guide = " ".join(guide.split())

    assert "uv sync" in guide
    assert "uv run pytest -q -p no:cacheprovider" in guide
    assert "uv run pytest tests/test_arxiv.py -q -p no:cacheprovider" in guide
    assert "live arXiv" in guide
    for forbidden_artifact in (
        "manuscripts",
        "cache data",
        "credentials",
        "generated distributions",
    ):
        assert forbidden_artifact in normalized_guide


def test_readme_is_a_version_pinned_launch_page_with_verified_demo():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    pinned_source = (
        "git+https://github.com/lotchuazzz-crypto/"
        "papergraph-mcp.git@v0.4.0"
    )

    for badge in ("CI", "Python", "MIT", "Release"):
        assert f"![{badge}]" in readme
    assert (
        f"uvx --from {pinned_source} papergraph-mcp --version"
        in readme
    )
    assert '"command": "uvx"' in readme
    assert pinned_source in readme

    for tool_name in (
        "load_paper",
        "load_arxiv_paper",
        "list_theorems",
        "get_theorem",
        "get_dependencies",
        "where_used",
    ):
        assert f"`{tool_name}`" in readme

    for tool_name in (
        "open_workspace",
        "workspace_add_local_paper",
        "workspace_add_arxiv_paper",
        "workspace_list_papers",
        "workspace_get_paper",
        "workspace_search_theorems",
        "workspace_get_dependencies",
        "workspace_get_citations",
    ):
        assert f"`{tool_name}`" in readme

    assert 'arxiv_id="math/0307200"' in readme
    assert '"path": "main.tex"' in readme
    assert '"cached": false' in readme
    assert '"nodes": 7' in readme
    assert "```mermaid" in readme
    assert "100 MiB" in readme
    assert "500 MiB" in readme
    assert "10,000" in readme

    lowered = readme.lower()
    assert "no pdf fallback" in lowered
    assert "arbitrary urls are not accepted" in lowered
    assert "main_file" in readme
    assert "[Contributing](CONTRIBUTING.md)" in readme
    assert "[MIT License](LICENSE)" in readme


def test_readme_documents_v040_cross_paper_graph():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "v0.4.0" in readme
    assert "SQLite" in readme
    assert "workspace_add_arxiv_paper" in readme
    assert "workspace_search_theorems" in readme
    assert "workspace_get_citations" in readme
    assert "explicit" in readme.lower()
    assert "semantic" in readme.lower()


def test_readme_relative_links_resolve_inside_repository():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    relative_targets = re.findall(
        r"(?<!!)\[[^]]+\]\((?!https?://|#)([^)]+)\)",
        readme,
    )

    assert relative_targets
    for target in relative_targets:
        path_text = target.split("#", 1)[0]
        assert (ROOT / path_text).exists(), target
