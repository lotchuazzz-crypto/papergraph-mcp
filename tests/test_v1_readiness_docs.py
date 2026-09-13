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
        "## Single-Paper Reading Report",
        "## Cross-Paper Reading Plan",
        "## Workspace Hygiene",
    ):
        assert heading in text

    for command in (
        "papergraph-mcp doctor",
        "open_workspace",
        "workspace_add_arxiv_paper",
        "workspace_get_paper_map",
        "export-paper-reading-report",
        "export-cross-paper-reading-plan",
    ):
        assert command in text
    assert "outside the Git repository" in text
    assert_no_placeholders(text)


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
