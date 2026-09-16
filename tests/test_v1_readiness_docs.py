from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def assert_no_placeholders(text: str) -> None:
    lowered = text.lower()
    for marker in ("tbd", "todo", "fill in", "placeholder"):
        assert marker not in lowered


def test_v1_core_contract_documents_stable_surface():
    text = read("docs/reference/v1-core-contract.md")

    assert "# PaperGraph v1 Core Contract" in text
    for heading in (
        "## Stable Core Workflow",
        "## Stable MCP Tools",
        "## Stable CLI Commands",
        "## Evidence Status",
        "## Warning Records",
        "## CLI Error Payloads",
        "## Durable Markdown Artifacts",
        "## Evidence Boundaries",
        "## Post-v1 Scope",
    ):
        assert heading in text

    for status in ("`usable`", "`sparse`", "`limited`"):
        assert status in text
    for key in ("`kind`", "`message`", "`evidence`"):
        assert key in text
    for key in ("`status`", "`action`", "`command`", "`message`"):
        assert key in text
    for tool in (
        "workspace_get_paper_map",
        "workspace_export_paper_reading_report",
        "workspace_export_cross_paper_reading_plan",
        "workspace_plan_external_imports_for_paper",
        "workspace_plan_starter_project",
        "workspace_bootstrap_reading_project",
    ):
        assert f"`{tool}`" in text
    assert "PaperGraph does not verify proofs." in text
    assert "PaperGraph does not perform semantic theorem matching." in text
    assert_no_placeholders(text)


def test_first_workspace_walkthrough_covers_mcp_and_cli_paths():
    text = read("docs/walkthroughs/first-workspace.md")

    assert "# First PaperGraph Workspace" in text
    for heading in (
        "## MCP-Capable Agent Path",
        "## CLI-Only Path",
        "## First Paper",
        "## Workspace Starter",
        "## Single-Paper Reading Report",
        "## Cross-Paper Reading Plan",
        "## Workspace Hygiene",
    ):
        assert heading in text

    for command in (
        "papergraph-mcp doctor",
        "uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.0 papergraph-mcp doctor",
        "open_workspace",
        "workspace_add_arxiv_paper",
        "workspace_get_paper_map",
        "export-paper-reading-report",
        "export-cross-paper-reading-plan",
        "plan-starter-project",
        "bootstrap-reading-project",
        "papergraph-starter-manifest.json",
    ):
        assert command in text
    assert "outside the Git repository" in text
    assert_no_placeholders(text)


def test_workspace_starter_examples_are_compact_and_deterministic():
    summary = read("docs/examples/starter-summary-example.md")
    manifest = read("docs/examples/papergraph-starter-manifest-example.json")

    assert summary.startswith("# PaperGraph Reading Project:")
    assert "## Evidence Boundaries" in summary
    assert "papergraph-starter-manifest.json" in summary
    assert "PaperGraph does not verify proofs." in summary
    assert '"starter_schema_version": 1' in manifest
    assert '"papergraph-starter-manifest.json"' in manifest
    assert "created_at" not in manifest
    assert_no_placeholders(summary)
    assert_no_placeholders(manifest)


def test_reading_report_example_is_compact_and_evidence_scoped():
    text = read("docs/examples/reading-report-example.md")

    assert text.startswith("# Reading Report:")
    for heading in (
        "## Paper",
        "## Paper Map",
        "## Main-Result Candidates",
        "## Recommended Reading Route",
        "## External Reading Risks",
        "## Evidence Boundaries",
    ):
        assert heading in text
    assert "PaperGraph does not verify proofs." in text
    assert "example artifact" in text.lower()
    assert_no_placeholders(text)


def test_cross_paper_plan_example_is_compact_and_evidence_scoped():
    text = read("docs/examples/cross-paper-reading-plan-example.md")

    assert text.startswith("# Cross-Paper Reading Plan:")
    for heading in (
        "## Scope",
        "## Paper Set",
        "## Recommended Reading Sequence",
        "## Cross-Paper Evidence",
        "## External Reading Risks",
        "## Evidence Boundaries",
    ):
        assert heading in text
    assert "selected-paper citation evidence" in text
    assert "Citation evidence does not imply logical dependency" in text
    assert "example artifact" in text.lower()
    assert_no_placeholders(text)


def test_v1_release_checklist_is_concrete():
    text = read("docs/reference/v1-release-checklist.md")

    assert "# PaperGraph v1 Release Checklist" in text
    for heading in (
        "## Version Pins",
        "## Installation Validation",
        "## Documentation Review",
        "## Test Commands",
        "## GitHub Release",
        "## Post-v1 Scope",
    ):
        assert heading in text

    for command in (
        "uv run pytest -q -p no:cacheprovider --basetemp .pytest-tmp",
        "uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.0 papergraph-mcp --version",
        "uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.1.0 papergraph-mcp doctor",
    ):
        assert command in text
    assert_no_placeholders(text)
