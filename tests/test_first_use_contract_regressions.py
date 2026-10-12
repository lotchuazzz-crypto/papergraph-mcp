from pathlib import Path

import pytest

import papergraph.server as server
from papergraph.cli_commands import cli_command
from papergraph.starter import plan_starter_project
from papergraph.workspace import Workspace
from papergraph.project import load_project


@pytest.mark.parametrize('kind,filename', [('local_tex', 'main.tex'), ('pdf', 'paper.pdf')])
@pytest.mark.parametrize('state', ['missing', 'directory', 'unreadable', 'wrong_type', 'file'])
def test_starter_preflight_is_honest_and_does_not_write(tmp_path, monkeypatch, kind, filename, state):
    source = tmp_path / (filename if state != 'wrong_type' else 'wrong.txt')
    if state == 'directory':
        source.mkdir()
    elif state != 'missing':
        source.write_bytes(b'fixture')
    if state == 'unreadable':
        original = Path.open
        def fail_open(path, *args, **kwargs):
            if path == source:
                raise PermissionError('synthetic permission denial')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', fail_open)
    planned = tmp_path / 'fresh parent'
    result = server.workspace_plan_starter_project(
        str(planned / 'workspace.sqlite3'), str(planned / 'artifacts'),
        [{'kind': kind, 'path': str(source), 'paper_id': 'local:fixture'}])
    assert result['status'] == ('ready' if state == 'file' else 'blocked')
    assert not planned.exists()
    if state != 'file':
        assert result['planned_state_changes'] == []
        assert result['blocking_issues'][0]['kind'] == 'invalid_local_input'


def test_starter_plan_does_not_touch_existing_database(tmp_path):
    db = tmp_path / 'existing.sqlite3'
    db.write_bytes(b'not a database; planner must not open or migrate it')
    before = db.read_bytes()
    assert server.workspace_plan_starter_project(str(db), None, [])['status'] == 'ready'
    assert db.read_bytes() == before


def test_cli_plan_creates_no_workspace(tmp_path, capsys):
    target = tmp_path / 'new parent'
    server.main(['plan-starter-project', '--workspace', str(target / 'ws.sqlite3'),
                 '--artifact-dir', str(target / 'artifacts')])
    assert '"ready"' in capsys.readouterr().out
    assert not target.exists()


def test_result_pages_are_stable_complete_only_when_paged(tmp_path):
    tex = tmp_path / 'main.tex'
    tex.write_text(''.join(r'\begin{lemma}\label{l:' + str(i) + r'}Synthetic.\end{lemma}' for i in range(105)))
    ws = Workspace.open(tmp_path / 'ws.sqlite3')
    try:
        ws.import_project('local:pages', 'local', str(tex), None, load_project(tex))
        first = ws.list_results(limit=100)
        last = ws.list_results(limit=100, offset=100)
        assert (len(first), len(last)) == (100, 5)
        assert len({r['result_id'] for r in first + last}) == 105
        assert ws.list_results(limit=100, offset=105) == []
        for offset in (-1, True, 1.5):
            with pytest.raises(ValueError, match='offset'):
                ws.list_results(offset=offset)
    finally:
        ws.close()


def test_quoting_distinguishes_shells():
    value = "C:/Users/O'Brien/$research `file`.sqlite3"
    assert "'C:/Users/O''Brien/$research `file`.sqlite3'" in cli_command('get-paper-map', workspace=value, paper_id='local:fixture')
    import shlex
    command = cli_command('get-paper-map', shell='posix', workspace=value, paper_id='local:fixture')
    assert shlex.split(command) == ['papergraph-mcp', 'get-paper-map', '--workspace', value, '--paper-id', 'local:fixture']
