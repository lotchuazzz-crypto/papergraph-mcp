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


def test_snapshot_assessment_reopens_and_report_is_offline(tmp_path, monkeypatch):
    path = tmp_path / 'persist.sqlite3'
    with closing(Workspace.open(path)) as ws:
        blocked = import_search_source_pdf(ws, tmp_path)['blocked_id']
        ws.reference_search_provider = lambda q: [{'provider':'crossref','records':[{'doi':'10.1000/a','title':'Published target'}]}]
        snapshot = ws.search_external_reference('local:paper',blocked,providers=['crossref'])
    with closing(Workspace.open(path)) as ws:
        ws.reference_search_provider = lambda q: pytest.fail('Unexpected provider call')
        monkeypatch.setattr(ws, '_import_reference_target', lambda *a,**k: pytest.fail('Unexpected import'))
        assert ws.search_external_reference('local:paper',blocked,providers=['crossref']) == snapshot
        report = ws.export_paper_reading_report('local:paper')
        assert 'Source status:' in report['markdown']
        assert ws.list_external_reference_resolutions('local:paper')['resolutions'] == []


def test_conflicted_candidate_overwrite_does_not_mutate(tmp_path):
    with closing(Workspace.open(tmp_path/'conflict.sqlite3')) as ws:
        blocked = import_search_source_pdf(ws, tmp_path)['blocked_id']
        ws.reference_search_provider = lambda q: [{'provider':'crossref','records':[
            {'doi':'10.1000/a','arxiv_id':'2401.12345'}, {'doi':'10.1000/b','arxiv_id':'2401.12345'}]}]
        snapshot = ws.search_external_reference('local:paper',blocked)
        ws.resolve_external_reference('local:paper',blocked,{'kind':'doi','doi':'10.1000/original'})
        before = list(ws._connection.iterdump())
        with pytest.raises(ValueError,match='(?i)conflict'):
            ws.resolve_external_reference_candidate('local:paper',blocked,snapshot['candidates'][0]['candidate_id'],overwrite=True)
        assert list(ws._connection.iterdump()) == before


def test_cache_requires_providers_limit_and_valid_arguments(tmp_path):
    with closing(Workspace.open(tmp_path/'cache.sqlite3')) as ws:
        blocked = import_search_source_pdf(ws, tmp_path)['blocked_id']
        calls = []
        ws.reference_search_provider = lambda q: calls.append(q) or []
        args = ('local:paper', blocked)
        first = ws.search_external_reference(*args,providers=['crossref'],max_candidates=2)
        ws.search_external_reference(*args,providers=['openalex'],max_candidates=2)
        ws.search_external_reference(*args,providers=['crossref'],max_candidates=3)
        assert ws.search_external_reference(*args,providers=['crossref'],max_candidates=2) == first
        assert len(calls) == 3
        for options in ({'resolver_version':'future'}, {'max_candidates':True}, {'max_candidates':0}, {'providers':['unknown']}):
            with pytest.raises(ValueError):
                ws.search_external_reference(*args,**options)
        assert len(calls) == 3


def test_failed_candidate_write_rolls_back_whole_snapshot(tmp_path):
    from papergraph.reference_assessment import rank_candidates_v2
    from papergraph.reference_search_store import save_search
    with closing(Workspace.open(tmp_path/'atomic.sqlite3')) as ws:
        blocked = import_search_source_pdf(ws,tmp_path)['blocked_id']
        class FailSecondCandidate:
            count = 0
            def execute(self, sql, *args):
                if 'INSERT INTO reference_search_candidates' in sql:
                    self.count += 1
                    if self.count == 2:
                        raise sqlite3.OperationalError('injected candidate write failure')
                return ws._connection.execute(sql,*args)
        before = list(ws._connection.iterdump())
        ranked = rank_candidates_v2({},[{'provider':'crossref','records':[{'doi':'10.1000/a'},{'doi':'10.1000/b'}]}])
        with pytest.raises(sqlite3.OperationalError,match='injected'):
            save_search(FailSecondCandidate(), run_id='reference-search:atomic',paper_id='local:paper',
                        blocked_id=blocked,ranked=ranked,providers=['crossref'],max_candidates=10,
                        resolver_version='deterministic_v2',timestamp='2026-09-23T00:00:00Z')
        assert list(ws._connection.iterdump()) == before
