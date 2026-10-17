from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

import pytest

import papergraph.server as server
from papergraph.workspace import Workspace
from tests.doc_contracts import linked_document


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "workspace"


@pytest.fixture(autouse=True)
def reset_server_state():
    server._reset_server_state()
    yield
    server._reset_server_state()


def test_readme_local_fixture_walkthrough_reports_unresolved_local_targets(
    tmp_path: Path,
):
    """The documented local sequence must not imply local citation resolution."""

    server.open_workspace(str(tmp_path / "papergraph-demo.sqlite3"))
    for directory, paper_id in (
        ("paper_a", "local:paper-a"),
        ("paper_b", "local:paper-b"),
        ("paper_c", "local:paper-c"),
    ):
        server.workspace_add_local_paper(
            str(FIXTURE_ROOT / directory / "main.tex"), paper_id
        )

    assert [paper["paper_id"] for paper in server.workspace_list_papers()] == [
        "local:paper-a",
        "local:paper-b",
        "local:paper-c",
    ]
    assert [result["global_id"] for result in server.workspace_search_theorems(
        "fixed point", limit=10
    )] == [
        "local:paper-a::thm:main",
        "local:paper-b::thm:main",
        "local:paper-c::thm:main",
    ]

    outgoing = server.workspace_get_citations(
        "local:paper-a", direction="outgoing", include_unresolved=True
    )
    assert [row["citation_key"] for row in outgoing] == [
        "absent",
        "missing",
        "paper-b",
    ]
    assert outgoing[2]["cited_arxiv_id"] == "2401.12346"
    assert outgoing[2]["target_paper_id"] is None
    assert outgoing[2]["resolution_status"] == "resolved_candidate"
    assert server.workspace_get_citations(
        "local:paper-b", direction="incoming"
    ) == []

    readme = linked_document(ROOT / "README.md", "docs/walkthroughs/first-workspace.md")
    assert "does not resolve to `local:paper-b`" in readme
    assert "`target_paper_id: null`" in readme
    assert "`workspace_add_arxiv_paper`" in readme
    assert "cited arXiv ID is imported" in readme


def test_walkthrough_cli_examples_keep_the_pinned_launcher():
    guide = linked_document(ROOT / 'README.md', 'docs/walkthroughs/first-workspace.md')
    blocks = re.findall(r'```powershell\n(.*?)```', guide, re.S)
    commands = [line for block in blocks for line in block.splitlines()
                if 'papergraph-mcp ' in line]
    assert len(commands) >= 25
    for line in commands:
        assert re.match(r'^(?:\$\w+ = )?uvx --from ', line), line
        assert ('--from papergraph-mcp==1.2.2 papergraph-mcp ' in line
                or '--from git+https://github.com/lotchuazzz-crypto/'
                   'papergraph-mcp.git@v1.2.2 papergraph-mcp ' in line), line


def test_linked_offline_tutorial_runs_plan_bootstrap_and_reading_state(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if shell is None:
        pytest.skip('PowerShell not available; server contract is tested separately')
    guide = linked_document(ROOT / 'README.md', 'docs/walkthroughs/first-workspace.md')
    section = guide.split('## Local Three-Paper Walkthrough\n', 1)[1].split('## First Paper', 1)[0]
    plan_block, reading_block = re.findall(r'```powershell\n(.*?)```', section, re.S)
    demo = tmp_path / "reading data O'Brien $literal `tick`"

    def literal(path):
        return "'" + str(path).replace("'", "''") + "'"

    plan_block = re.sub(r'^\$PaperGraphCheckout = .*$',
                        lambda _: '$PaperGraphCheckout = ' + literal(ROOT), plan_block, flags=re.M)
    plan_block = re.sub(r'^\$demo = .*$', lambda _: '$demo = ' + literal(demo), plan_block, flags=re.M)
    prefix = 'uvx --from papergraph-mcp==1.2.2 papergraph-mcp'

    def run(block):
        # Deterministic source-contract test: replace only the package launcher.
        # A separate manual acceptance runs the actual public uvx pin.
        block = block.replace(prefix, '& ' + literal(sys.executable) + ' -m papergraph.server')
        lines = ["$ErrorActionPreference = 'Stop'"]
        for line in block.splitlines():
            lines.append(line)
            if '-m papergraph.server ' in line:
                lines.append('if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }')
        executed = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', '\n'.join(lines)],
                                  capture_output=True, text=True, timeout=120)
        assert executed.returncode == 0, (executed.stderr, executed.stdout)
        return executed.stdout

    plan_json = run(plan_block.replace('$plan\n', '$plan | ConvertTo-Json -Depth 30\n'))
    assert json.loads(plan_json)['status'] == 'ready'
    assert not demo.exists(), 'planning must not create workspace parents or artifacts'
    bindings = plan_block.split('$plan = ', 1)[0]
    run(bindings + reading_block)
    workspace = Workspace.open(demo / 'papergraph.sqlite3')
    try:
        assert [paper['paper_id'] for paper in workspace.list_papers()] == [
            'local:paper-a', 'local:paper-b', 'local:paper-c']
        sessions = workspace.list_reading_sessions()
        assert len(sessions) == 1
        state = workspace.get_reading_session(sessions[0]['session_id'])
        assert any(row['target_id'] == 'local:paper-a::thm:main'
                   and row['status'] == 'reviewed' for row in state['checkpoints'])
        assert state['notes'][0]['text'] == 'Check the cited fixed point theorem.'
    finally:
        workspace.close()
    assert 'Evidence Triage' in (demo / 'starter/START_HERE.md').read_text(encoding='utf-8')
    assert '# Reading Report:' in (demo / 'reading-report.md').read_text(encoding='utf-8')
    assert '# Cross-Paper Reading Plan' in (demo / 'cross-paper-plan.md').read_text(encoding='utf-8')
