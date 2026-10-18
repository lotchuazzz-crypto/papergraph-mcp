import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from papergraph.project import load_project
from papergraph.workspace import Workspace


def test_all_generated_followups_run_in_powershell(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if shell is None:
        pytest.skip('PowerShell not available; POSIX quoting is covered separately')
    path = tmp_path / "reading data O'Brien $literal `tick`" / 'ws.sqlite3'
    ws = Workspace.open(path)
    try:
        fixture = Path(__file__).parent / 'fixtures' / 'workspace'
        for name in ('a', 'b', 'c'):
            main = fixture / f'paper_{name}' / 'main.tex'
            ws.import_project(f'local:paper-{name}', 'local', str(main), None, load_project(main))
        starter = ws.bootstrap_reading_project(
            workspace_path=path, artifact_dir=tmp_path / 'artifacts', papers=[],
            create_queue=False, create_session=False)
        session_id = ws.create_reading_session('local:paper-a')['session_id']
        markdowns = [(tmp_path / 'artifacts' / 'START_HERE.md').read_text(encoding='utf-8'),
                     ws.export_paper_reading_report('local:paper-a')['markdown'],
                     ws.export_cross_paper_reading_plan(['local:paper-a', 'local:paper-b', 'local:paper-c'])['markdown']]
    finally:
        ws.close()
    commands = set(starter['next_commands'])
    from tests.doc_contracts import linked_document
    tutorial = linked_document(Path(__file__).parents[1] / 'README.md', 'docs/walkthroughs/first-workspace.md')
    launcher = 'uvx --from papergraph-mcp==1.2.3 '
    checkpoint = next(line.removeprefix(launcher) for line in tutorial.splitlines()
                      if line.startswith(launcher + 'papergraph-mcp record-reading-checkpoint '))
    for markdown in markdowns:
        for block in re.findall(r'```powershell\n(.*?)```', markdown, re.S):
            commands.update(line for line in block.splitlines() if line.startswith('papergraph-mcp '))
        for block in re.findall(r'```sh\n(.*?)```', markdown, re.S):
            import shlex
            for line in block.splitlines():
                args = shlex.split(line)
                assert args[0] == 'papergraph-mcp' and args[2] == '--workspace'
                assert '--paper-id' in args or '--result-id' in args
    # Replace only the quoted placeholder with the exact PowerShell literal.
    quoted_path = "'" + str(path).replace("'", "''") + "'"
    commands.add(checkpoint.replace('$env:PAPERGRAPH_WORKSPACE', quoted_path).replace('$session.session_id', session_id))
    env = dict(os.environ)
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env['PATH']
    outputs = []
    for command in sorted(commands):
        command = command.replace("'<WORKSPACE>'", quoted_path)
        executed = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command + '; exit $LASTEXITCODE'],
                                  capture_output=True, text=True, env=env, timeout=30)
        assert executed.returncode == 0, (command, executed.stderr, executed.stdout)
        if command.startswith('papergraph-mcp export-paper-reading-report '):
            assert '# Reading Report:' in executed.stdout
        else:
            json.loads(executed.stdout)
        outputs.append({'command': command, 'exit_code': executed.returncode})
    (tmp_path / 'generated-command-evidence.json').write_text(json.dumps(outputs, indent=2), encoding='utf-8')


def test_readme_linked_static_example_commands_run_in_powershell(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if shell is None:
        pytest.skip('PowerShell not available')
    path = tmp_path / "example data O'Brien" / 'ws.sqlite3'
    ws = Workspace.open(path)
    try:
        main = Path(__file__).parent / 'fixtures/workspace/paper_a/main.tex'
        for pid in ('local:example-a', 'arxiv:2401.12345'):
            ws.import_project(pid, pid.split(':')[0], str(main), None, load_project(main))
    finally:
        ws.close()
    env = dict(os.environ)
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env['PATH']
    quoted_path = "'" + str(path).replace("'", "''") + "'"
    outputs = []
    for name in ('reading-report-example.md', 'cross-paper-reading-plan-example.md'):
        markdown = (Path(__file__).parents[1] / 'docs/examples' / name).read_text(encoding='utf-8')
        commands = re.findall(r'^papergraph-mcp .*$', markdown, re.M)
        assert commands
        for command in commands:
            command = command.replace("'<WORKSPACE>'", quoted_path)
            executed = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command + '; exit $LASTEXITCODE'],
                                      capture_output=True, text=True, env=env, timeout=30)
            assert executed.returncode == 0, (command, executed.stderr, executed.stdout)
            outputs.append({'document': name, 'command': command, 'exit_code': executed.returncode})
    (tmp_path / 'static-command-evidence.json').write_text(json.dumps(outputs, indent=2), encoding='utf-8')
