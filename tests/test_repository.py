import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.10 CI job
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/lotchuazzz-crypto/papergraph-mcp"


def test_distribution_explicitly_excludes_local_environments():
    import fnmatch
    with (ROOT / 'pyproject.toml').open('rb') as stream:
        config = tomllib.load(stream)
    patterns = config['tool']['hatch']['build']['exclude']
    for directory in ('/.smoke-venv', '/.venv', '/.worktrees', '/.pytest-python312-env', '/docs/sessions', '/dist'):
        assert any(fnmatch.fnmatch(directory, pattern) for pattern in patterns), directory


def read_toml(relative_path: str) -> dict:
    return tomllib.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_distributions_exclude_local_workspaces_and_session_logs():
    configuration = read_toml("pyproject.toml")
    assert {"/docs/sessions", "/.pytest-*"} <= set(configuration["tool"]["hatch"]["build"]["exclude"])
    assert ".pytest-*/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_project_metadata_is_discoverable_and_keeps_dependencies_separated():
    configuration = read_toml("pyproject.toml")
    project = configuration["project"]

    assert project["version"] == "1.2.3"
    assert project["dependencies"] == [
        "httpx>=0.27,<1",
        "mcp[cli]>=2,<3",
        "pybtex>=0.25,<0.27",
        "PyMuPDF>=1.24,<2",
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


def test_lockfile_contains_project_package():
    lockfile = read_toml("uv.lock")
    package = next(
        package
        for package in lockfile["package"]
        if package["name"] == "papergraph-mcp"
    )

    assert package["name"] == "papergraph-mcp"
    assert package["version"] == "1.2.3"


def test_validate_arxiv_request_module_stdout_is_json_only():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "papergraph.server",
            "validate-arxiv-request",
            "[math/0307200](https://arxiv.org/abs/2609.01574)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["status"] == "conflict"
    assert payload["action"] == "ask_user_to_choose"
    assert payload["selected_id"] is None


def test_runtime_and_issue_template_report_the_available_release_version():
    from papergraph.arxiv import _USER_AGENT
    bug_report = read_yaml(".github/ISSUE_TEMPLATE/bug_report.yml")
    version_field = next(
        item
        for item in bug_report["body"]
        if item.get("id") == "version"
    )

    assert _USER_AGENT == f'PaperGraph/1.2.3 (+{REPOSITORY_URL})'
    assert '1.2.3;' in version_field["attributes"]["placeholder"]
    assert 'doctor build_identity' in version_field["attributes"]["placeholder"]


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
    assert "papergraph-mcp 1.2.3" in build_steps
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


def test_readme_is_a_version_pinned_launch_page_with_linked_workflows():
    from tests.doc_contracts import linked_document

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for badge in ("CI", "Python", "MIT", "Release"):
        assert f"![{badge}]" in readme
    pin = "papergraph-mcp==1.2.3"
    for command in ("--version", "doctor"):
        assert f"uvx --from {pin} papergraph-mcp {command}" in readme
    config = json.loads(re.search(r"```json\n(.*?)```", readme, re.S)[1])
    assert config["mcpServers"]["papergraph"] == {
        "command": "uvx", "args": ["--from", pin, "papergraph-mcp"]}
    for target in (
        "docs/walkthroughs/first-workspace.md",
        "docs/reference/v1-core-contract.md",
        ".agents/skills/setting-up-papergraph/SKILL.md",
        "docs/reference/v1.2.2-publication.md",
        "docs/examples/reading-report-example.md",
        "docs/examples/cross-paper-reading-plan-example.md",
        "docs/examples/reference-search-example.json",
        "docs/examples/reference-resolution-example.json",
        "CONTRIBUTING.md", "LICENSE",
    ):
        linked_document(ROOT / "README.md", target)
    assert "Paper Map" in readme and "Evidence Triage" in readme
    assert "Crossref, OpenAlex, and arXiv" in readme
    assert "plan-starter-project" in readme and "bootstrap-reading-project" in readme
    assert "load_arxiv_request" in readme and "conflicting IDs" in readme
    assert "user selection" in readme
    assert "Empty dependencies do not prove independence" in readme
    assert "External references become reviewable plans" in readme
    assert "no workflow bypasses paywalls" in readme
    diagram_path = "docs/assets/papergraph-request-flow.png"
    editable_path = "docs/assets/papergraph-request-flow.drawcms"
    assert f"]({diagram_path})" in readme and f"]({editable_path})" in readme
    assert (ROOT / diagram_path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    diagram = json.loads((ROOT / editable_path).read_text(encoding="utf-8"))
    assert diagram["nodes"] and diagram["edges"]


def test_readme_keeps_the_concise_overview_ahead_of_document_navigation():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Read math papers with evidence, not guesses." in readme
    headings = re.findall(r"^## (.*)$", readme, re.M)
    assert headings == ["What You Can Do", "Quick Start", "Read Your First Paper",
                        "Evidence Boundaries", "Documentation"]
    # Keep the user's short entry point; tutorials carry full executable examples.
    assert len(readme.split()) < 850


def test_linked_core_contract_documents_explicit_cross_paper_evidence():
    from tests.doc_contracts import linked_document

    contract = linked_document(ROOT / "README.md", "docs/reference/v1-core-contract.md")
    assert "explicit" in contract.lower()
    assert "PaperGraph does not perform semantic theorem matching." in contract
    walkthrough = linked_document(ROOT / "README.md", "docs/walkthroughs/first-workspace.md")
    import papergraph.server as server
    for tool in ("workspace_add_arxiv_paper", "workspace_search_theorems",
                 "workspace_get_citations"):
        assert tool in walkthrough and callable(getattr(server, tool))
    assert "does not resolve to `local:paper-b`" in walkthrough
    assert "`target_paper_id: null`" in walkthrough


def test_linked_walkthrough_documents_pdf_evidence_workflow():
    from tests.doc_contracts import linked_document

    guide = linked_document(ROOT / "README.md", "docs/walkthroughs/first-workspace.md")
    for tool in ("workspace_add_pdf_paper", "workspace_get_proof_dependencies",
                 "workspace_get_source_slice", "workspace_read_source_blocks"):
        assert f"`{tool}`" in guide
    for term in ("known", "inferred", "unresolved", "Scanned PDFs",
                 "does not verify proofs", "automatic_ownership_policy",
                 "first physical line", "not automatically join", "Late references remain"):
        assert term in guide


def test_client_matrix_preserves_historical_scope_and_routes_to_current_recipes():
    from tests.doc_contracts import linked_document

    path = ROOT / "docs/reference/client-compatibility.md"
    text = linked_document(ROOT / "README.md", "docs/reference/client-compatibility.md")
    assert "historical v1.1.5 evidence from 2026-09-23" in text
    assert "not a v1.2.2 client" in text
    assert "No new actual-client acceptance" in text
    linked_document(path, "../../.agents/skills/setting-up-papergraph/SKILL.md")
    linked_document(path, "../../.agents/skills/setting-up-papergraph/references/client-configuration.md")
    rows = [line for line in text.splitlines() if line.startswith("| ")][2:]
    assert len(rows) == 5
    assert all("2026-09-23" in row for row in rows)
    assert all("documented_not_run" in row for row in rows[2:])


def test_onboarding_uses_latest_release_pin_and_mentions_id_url_conflicts():
    skill = (
        ROOT / ".agents/skills/setting-up-papergraph/SKILL.md"
    ).read_text(encoding="utf-8")
    prompt = (
        ROOT / ".agents/skills/setting-up-papergraph/references/usage-prompt.md"
    ).read_text(encoding="utf-8")

    assert "papergraph-mcp.git@v1.2.2" in skill
    assert "papergraph-mcp 1.2.2" in skill
    assert "validate_arxiv_request" in skill
    assert "load_arxiv_request" in skill
    assert "If a user provides both an arXiv ID and an arXiv URL" in skill
    assert "ask which one to analyze" in skill
    assert "arXiv ID and arXiv URL" in prompt


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
