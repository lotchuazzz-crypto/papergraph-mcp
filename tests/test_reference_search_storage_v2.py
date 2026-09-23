from contextlib import closing
import json
from pathlib import Path
import sqlite3
import pytest
from papergraph.workspace import Workspace
from tests.test_reference_search import import_search_source_pdf

FIXTURES = Path(__file__).parent / 'fixtures/reference_quality'


def test_cache_version_refresh_and_reopen(tmp_path):
    path = tmp_path / 'ws.sqlite3'
    with closing(Workspace.open(path)) as ws:
        blocker = import_search_source_pdf(ws, tmp_path)
        calls = []
        def provider(q):
            calls.append(q)
            return [{'provider':'crossref','records':[], 'warnings':[], 'outcome':'empty'}]
        ws.reference_search_provider = provider
        args = ('local:paper',blocker['blocked_id'])
        old = ws.search_external_reference(*args,resolver_version='legacy_v1')
        new = ws.search_external_reference(*args)
        assert new['search_schema_version'] == 2 and old['search_schema_version'] == 1
        assert new['search_run_id'] != old['search_run_id']
        assert ws.search_external_reference(*args) == new and len(calls)==2
        assert ws.search_external_reference(*args,resolver_version='legacy_v1') == old
        fresh = ws.search_external_reference(*args,refresh=True)
        assert fresh['search_run_id'] != new['search_run_id']
        assert len(ws.list_external_reference_searches()['searches']) == 3
    with closing(Workspace.open(path)) as ws:
        assert ws._reference_search_by_id(new['search_run_id']) == new


def test_schema8_preserves_snapshots_and_decisions(tmp_path):
    path = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript((FIXTURES/'schema8.sql').read_text(encoding='utf-8'))
    manifest = json.loads((FIXTURES/'schema8-manifest.json').read_text(encoding='utf-8'))
    with closing(Workspace.open(path)) as ws:
        assert ws._connection.execute("SELECT value FROM workspace_meta WHERE key='schema_version'").fetchone()[0] == '9'
        actual = ws._reference_search_by_id(manifest['search']['search_run_id'])
        for key,value in manifest['search'].items():
            assert actual[key] == value
        run = ws.get_reference_expansion(manifest['run']['run_id'])
        assert run['policy'] == manifest['run']['policy']
        assert run['state'] == 'paused'


def test_failed_migration_rolls_back(tmp_path):
    from papergraph.reference_search_store import migrate
    class Failing(sqlite3.Connection):
        def execute(self, sql, *args):
            if 'ADD COLUMN assessment_json' in sql:
                raise sqlite3.OperationalError('injected failure')
            return super().execute(sql,*args)
    db = sqlite3.connect(tmp_path/'fail.sqlite3',factory=Failing)
    try:
        db.executescript((FIXTURES/'schema8.sql').read_text(encoding='utf-8'))
        before = list(db.iterdump())
        with pytest.raises(sqlite3.OperationalError,match='injected'):
            migrate(db)
        assert list(db.iterdump()) == before
    finally:
        db.close()
