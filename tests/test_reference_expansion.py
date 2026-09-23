import copy
import json
from pathlib import Path

import pytest

from papergraph.workspace import Workspace
from tests.test_workspace_reference_resolution import import_missing_reference_pdf


def candidate(arxiv="2401.12345", **changes):
    item = {"candidate_id": "candidate:" + arxiv, "confidence": "strong",
            "target": {"kind": "arxiv", "arxiv_id": arxiv, "title": "Fixed point",
                       "authors": ["Ada Author"], "year": "2020"},
            "providers": ["crossref", "arxiv"], "provider_records": [],
            "evidence": ["title_exact_match", "author_overlap:1", "year_exact_match"],
            "warnings": []}
    item.update(changes)
    return item


def test_automatic_selection_requires_identity_evidence():
    from papergraph.reference_expansion_policy import select_candidate
    query = {"title_hint": "Fixed point", "author_hints": ["Ada Author"], "year_hint": "2020"}
    c = candidate()
    assert select_candidate({"query": query, "candidates": [c]})["eligible"]
    assert not select_candidate({"query": {}, "candidates": [c]})["eligible"]
    assert not select_candidate({"query": query, "candidates": [c, candidate("2401.12346")]})["eligible"]
    assert not select_candidate({"query": query, "candidates": [c], "provider_warnings": ["timeout"]})["eligible"]
    query = {"raw_bibliography_text": "arXiv:2401.12345"}
    assert select_candidate({"query": query, "candidates": [c], "provider_warnings": ["timeout"]})["eligible"]


def test_policy_rejects_unbounded_or_unknown_options():
    from papergraph.reference_expansion_policy import validate_policy
    assert validate_policy({})["max_depth"] == 2
    for policy in ({"max_depth": 0}, {"max_new_papers": True}, {"max_edges": 10001}, {"oops": 1}):
        with pytest.raises(ValueError):
            validate_policy(policy)


@pytest.fixture
def workspace(tmp_path):
    ws = Workspace.open(tmp_path / "workspace.sqlite3")
    import_missing_reference_pdf(ws, tmp_path)
    yield ws
    ws.close()


def test_create_is_offline_and_persists_on_reopen(workspace):
    run = workspace.create_reference_expansion(["local:paper"])
    assert run["state"] == "ready"
    assert run["usage"]["new_papers"] == 0
    other = Workspace.open(workspace.path)
    try:
        assert other.get_reference_expansion(run["run_id"])["policy"]["max_depth"] == 2
    finally:
        other.close()


def test_search_failure_does_not_loop_or_consume_paper_budget(workspace, monkeypatch):
    def search(*args, **kwargs):
        raise RuntimeError("offline")
    monkeypatch.setattr(workspace, "search_external_reference", search)
    run = workspace.create_reference_expansion(["local:paper"])
    result = workspace.advance_reference_expansion(run["run_id"])
    assert result["state"] == "waiting"
    count = len(workspace.plan_external_imports_for_paper("local:paper")["blocked"])
    assert result["usage"] == {"new_papers": 0, "searches": count, "edges": count}
    assert result["edges"][0]["state"] == "retryable_failure"
    assert workspace.advance_reference_expansion(run["run_id"])["usage"] == result["usage"]


def test_manual_skip_and_cancel(workspace, monkeypatch):
    monkeypatch.setattr(workspace, "search_external_reference", lambda *a, **kw: {
        "query": {}, "candidates": [candidate(confidence="ambiguous")]})
    run = workspace.create_reference_expansion(["local:paper"])
    result = workspace.advance_reference_expansion(run["run_id"])
    edge = result["edges"][0]
    assert edge["state"] == "needs_review"
    for edge in result["edges"]:
        workspace.decide_reference_expansion(run["run_id"], edge["edge_id"], {"skip": True})
    assert workspace.advance_reference_expansion(run["run_id"])["state"] == "completed"
    assert "extracted" in workspace.export_reference_expansion(run["run_id"], format="markdown")
    workspace.cancel_reference_expansion(run["run_id"])
    with pytest.raises(ValueError, match="cancelled"):
        workspace.advance_reference_expansion(run["run_id"])


FIXTURES = Path(__file__).parent / "fixtures" / "reference_expansion"


@pytest.fixture
def chain(tmp_path, monkeypatch):
    import papergraph.workspace as module
    from papergraph.arxiv import ArxivProject
    from papergraph.project import load_project
    ws = Workspace.open(tmp_path / "chain.sqlite3")
    ws.import_project("arxiv:2401.10001", "arxiv", "2401.10001", None,
                      load_project(FIXTURES / "a" / "main.tex"))
    calls = []
    def acquire(arxiv_id, main_file, refresh):
        calls.append(arxiv_id)
        folder = {"2401.10002": "b", "2401.10003": "c"}[arxiv_id]
        root = FIXTURES / folder
        return ArxivProject(arxiv_id, root, root / "main.tex", True)
    monkeypatch.setattr(module, "prepare_arxiv_project", acquire)
    # Network access is never allowed in these reproducibility tests.
    import httpx
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **kw: pytest.fail("unexpected network"))
    yield ws, calls
    ws.close()


def drain(ws, run_id):
    for _ in range(30):
        result = ws.advance_reference_expansion(run_id, max_steps=1)
        if result["state"] != "ready":
            return result
    pytest.fail("expansion did not terminate")


def test_real_chain_deduplicates_and_terminates_cycle(chain):
    ws, calls = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"], {"max_depth": 3})
    result = drain(ws, run["run_id"])
    assert result["state"] == "completed"
    assert result["usage"]["new_papers"] == 2
    assert sorted(calls) == ["2401.10002", "2401.10003"]
    assert len(result["nodes"]) == 3
    assert len(result["edges"]) == 5
    report = ws.export_reference_expansion(run["run_id"], "markdown")
    assert "cycle" in report and "shared target" in report


def test_checked_in_golden_outputs(tmp_path):
    from scripts.reproduce_reference_expansion import ROOT, reproduce
    from papergraph.reference_expansion_report import render_expansion
    result = reproduce(tmp_path / "golden.sqlite3")
    directory = ROOT / "docs/examples"
    assert result == json.loads((directory / "reference-expansion-example.json").read_text(encoding="utf-8"))
    assert render_expansion(result) == (directory / "reference-expansion-example.md").read_text(encoding="utf-8")


def test_idle_control_is_durable_history(chain):
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    ws.cancel_reference_expansion(run["run_id"])
    result = ws.get_reference_expansion(run["run_id"])
    assert any(e.get("control") == "cancel" for e in result["events"])


def test_ordinary_exception_after_commit_reconciles(chain, monkeypatch):
    ws, calls = chain
    original = ws._import_reference_target
    def interrupted(target):
        original(target)
        raise RuntimeError("interrupted after commit")
    monkeypatch.setattr(ws, "_import_reference_target", interrupted)
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    assert drain(ws, run["run_id"])["reason"] == "import_reconciliation_required"
    monkeypatch.setattr(ws, "_import_reference_target", original)
    result = drain(ws, run["run_id"])
    assert result["usage"]["new_papers"] == 2
    assert len(calls) == 2


@pytest.mark.parametrize("limit,value,reason", [("max_new_papers", 1, "paper_limit"),
                                               ("max_edges", 1, "edge_limit")])
def test_budget_revision_continues_without_reset(chain, limit, value, reason):
    ws, calls = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"], {limit: value, "max_depth": 3})
    stopped = drain(ws, run["run_id"])
    assert stopped["state"] == "paused" and stopped["reason"] == reason
    ws.update_reference_expansion_policy(run["run_id"], {limit: 20})
    done = drain(ws, run["run_id"])
    assert done["state"] == "completed" and done["usage"]["new_papers"] == 2
    assert len(calls) == 2


def test_depth_limit_can_be_expanded(chain):
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"], {"max_depth": 1})
    stopped = drain(ws, run["run_id"])
    assert all(n["discovery"] == "depth_limit" for n in stopped["nodes"] if n["depth"] == 1)
    ws.update_reference_expansion_policy(run["run_id"], {"max_depth": 3})
    assert drain(ws, run["run_id"])["usage"]["new_papers"] == 2


def test_committed_import_is_reconciled_without_redownload(chain, monkeypatch):
    from papergraph.reference_expansion_store import Store
    ws, calls = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    ws.advance_reference_expansion(run["run_id"], max_steps=1)
    original = ws._import_reference_target
    class Crash(BaseException):
        pass
    def crash(target):
        original(target)
        raise Crash()
    monkeypatch.setattr(ws, "_import_reference_target", crash)
    with pytest.raises(Crash):
        ws.advance_reference_expansion(run["run_id"], max_steps=1)
    monkeypatch.setattr(ws, "_import_reference_target", original)
    resumed = drain(ws, run["run_id"])
    assert resumed["usage"]["new_papers"] == 2
    assert len(calls) == 2
    assert any(e["kind"] == "reconcile_import" for e in resumed["events"])


def test_workspace_lease_excludes_second_connection(chain):
    from papergraph.reference_expansion_store import Store
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    other = Workspace.open(ws.path)
    try:
        with Store(ws).lease():
            with pytest.raises(ValueError, match="lease"):
                other.advance_reference_expansion(run["run_id"])
    finally:
        other.close()


def test_schema_7_migration_is_transactional(tmp_path):
    import sqlite3
    from papergraph.workspace import _SCHEMA_SQL
    path = tmp_path / "v7.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(_SCHEMA_SQL)
    ws = Workspace.open(path)
    assert ws._connection.execute("SELECT value FROM workspace_meta WHERE key='schema_version'").fetchone()[0] == "9"
    ws.close()


def test_search_budget_and_retry_are_cumulative(workspace, monkeypatch):
    monkeypatch.setattr(workspace, "search_external_reference", lambda *a, **kw: {"query": {}, "candidates": []})
    run = workspace.create_reference_expansion(["local:paper"], {"max_searches": 1})
    stopped = drain(workspace, run["run_id"])
    assert stopped["reason"] == "search_limit"
    workspace.update_reference_expansion_policy(run["run_id"], {"max_searches": 4})
    result = drain(workspace, run["run_id"])
    assert result["usage"]["searches"] == len(result["edges"])


def test_import_failure_retry(chain, monkeypatch):
    ws, calls = chain
    original = ws._import_reference_target
    monkeypatch.setattr(ws, "_import_reference_target", lambda *a: (_ for _ in ()).throw(OSError("temporary outage")))
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    stopped = drain(ws, run["run_id"])
    assert stopped["state"] == "waiting"
    assert stopped["usage"]["new_papers"] == 0
    monkeypatch.setattr(ws, "_import_reference_target", original)
    for edge in stopped["edges"]:
        ws.decide_reference_expansion(run["run_id"], edge["edge_id"], {"retry": True})
    assert drain(ws, run["run_id"])["usage"]["new_papers"] == 2


def test_partial_provider_results_and_version_conflicts_never_autoselect():
    from papergraph.reference_expansion_policy import select_candidate
    c = candidate(arxiv="2401.12345v2")
    search = {"query": {"raw_bibliography_text": "arXiv:2401.12345v1"}, "candidates": [c]}
    assert not select_candidate(search)["eligible"]

    c["warnings"] = ["retracted"]
    search["query"]["raw_bibliography_text"] = "arXiv:2401.12345v2"
    assert not select_candidate(search)["eligible"]


def test_migration_failure_rolls_back_created_tables(tmp_path):
    import sqlite3
    from papergraph.workspace import _SCHEMA_SQL
    path = tmp_path / "bad-v7.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(_SCHEMA_SQL)
        db.execute("CREATE TABLE reference_expansion_edges (unrelated TEXT)")
    with pytest.raises(sqlite3.OperationalError):
        Workspace.open(path)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT value FROM workspace_meta WHERE key='schema_version'").fetchone()[0] == "7"
        assert db.execute("SELECT name FROM sqlite_master WHERE name='reference_expansion_runs'").fetchone() is None


def test_refreshing_same_candidates_preserves_expansion_snapshot(workspace, monkeypatch):
    records = [{"provider": name, "records": [{"kind": "arxiv", "arxiv_id": "2401.12345", "title": "Published target", "authors": ["A. Author"], "year": "2020"}], "warnings": []} for name in ("crossref", "arxiv")]
    monkeypatch.setattr(workspace, "_run_reference_search_providers", lambda *a: records)
    blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]["blocked_id"]
    first = workspace.search_external_reference("local:paper", blocked)
    second = workspace.search_external_reference("local:paper", blocked, refresh=True)
    assert first["search_run_id"] != second["search_run_id"]
    assert second["candidates"]


def test_cancel_during_last_import_is_returned_immediately(chain, monkeypatch):
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    ws.advance_reference_expansion(run["run_id"], max_steps=1)
    original = ws._import_reference_target
    def cancel(target):
        result = original(target)
        ws.cancel_reference_expansion(run["run_id"])
        return result
    monkeypatch.setattr(ws, "_import_reference_target", cancel)
    result = ws.advance_reference_expansion(run["run_id"], max_steps=1)
    assert result["state"] == "cancelled"
    assert any(e["kind"] == "control" for e in result["events"])


def test_stale_root_requires_review_not_false_completion(chain):
    from papergraph.project import load_project
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    ws.import_project("arxiv:2401.10001", "arxiv", "2401.10001", None, load_project(FIXTURES / "a" / "main.tex"))
    assert drain(ws, run["run_id"])["state"] == "waiting"


def test_manual_pdf_choice_resumes_ambiguous_reference(workspace, tmp_path, monkeypatch):
    from tests.test_workspace_reference_resolution import write_target_pdf
    monkeypatch.setattr(workspace, "search_external_reference", lambda *a, **kw: {"query": {}, "candidates": [candidate(confidence="ambiguous")]})
    run = workspace.create_reference_expansion(["local:paper"])
    waiting = drain(workspace, run["run_id"])
    pdf = tmp_path / "selected.pdf"
    write_target_pdf(pdf)
    for edge in waiting["edges"]:
        workspace.decide_reference_expansion(run["run_id"], edge["edge_id"], {"target": {"kind": "pdf", "path": str(pdf)}})
    result = drain(workspace, run["run_id"])
    assert result["usage"]["new_papers"] == 1
    assert any(e["state"] == "linked_existing" for e in result["edges"])
    assert result["state"] == "completed"


def test_mixed_branches_real_search_snapshot_and_manual_continuation(chain, monkeypatch):
    import papergraph.workspace as module
    from papergraph.arxiv import ArxivProject
    ws, _ = chain
    responses = json.loads((FIXTURES / "provider-responses.json").read_text(encoding="utf-8"))
    acquisition = module.prepare_arxiv_project
    def acquire(arxiv_id, main_file, refresh):
        if arxiv_id == "2401.10002":
            root = FIXTURES / "mixed_b"
            return ArxivProject(arxiv_id, root, root / "main.tex", True)
        return acquisition(arxiv_id, main_file, refresh)
    monkeypatch.setattr(module, "prepare_arxiv_project", acquire)
    monkeypatch.setattr(ws, "_run_reference_search_providers", lambda query, providers: responses[query["citation_keys"][0]])
    run = ws.create_reference_expansion(["arxiv:2401.10001"], {"max_depth": 3})
    waiting = drain(ws, run["run_id"])
    assert waiting["state"] == "waiting"
    assert waiting["usage"]["new_papers"] == 2  # Independent A -> C continued.
    assert any(e["state"] == "boundary" and e["reason"] == "no_importable_source" for e in waiting["edges"])
    edge = next(e for e in waiting["edges"] if e["state"] == "needs_review")
    saved = copy.deepcopy(edge["search"])
    refreshed = ws.search_external_reference(edge["source"], edge["blocked_id"], refresh=True)
    assert saved["search_run_id"] != refreshed["search_run_id"]
    saved_edge = next(e for e in ws.get_reference_expansion(run["run_id"])["edges"] if e["edge_id"] == edge["edge_id"])
    assert saved_edge["search"] == saved
    choice = next(c for c in saved["candidates"] if c["target"].get("arxiv_id") == "2401.10003")
    with pytest.raises(ValueError, match="snapshot"):
        ws.decide_reference_expansion(run["run_id"], edge["edge_id"], {"candidate_id": refreshed["candidates"][0]["candidate_id"]})
    ws.decide_reference_expansion(run["run_id"], edge["edge_id"], {"candidate_id": choice["candidate_id"]})
    done = drain(ws, run["run_id"])
    assert done["state"] == "completed" and done["usage"]["new_papers"] == 2
    resolution = ws.list_external_reference_resolutions(edge["source"])["resolutions"][0]
    assert resolution["source"]["review"]["selection"]["kind"] == "manual"


def test_decreasing_depth_does_not_execute_previously_discovered_edges(chain):
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    for _ in range(4):
        ws.advance_reference_expansion(run["run_id"], max_steps=1)
    ws.update_reference_expansion_policy(run["run_id"], {"max_depth": 1})
    done = drain(ws, run["run_id"])
    assert all(n["depth"] <= 1 for n in done["nodes"])
    assert not any(e.get("target_node") for e in done["edges"] if e["source"] != "arxiv:2401.10001")


def test_concurrent_non_expansion_import_is_not_overwritten(chain, monkeypatch):
    import papergraph.workspace as module
    from papergraph.project import load_project
    ws, _ = chain
    original = module.prepare_arxiv_project
    other = Workspace.open(ws.path)
    inserted = {}
    def acquire(arxiv_id, main_file, refresh):
        prepared = original(arxiv_id, main_file, refresh)
        pid = "arxiv:" + arxiv_id
        other.import_project(pid, "arxiv", arxiv_id, None, load_project(prepared.main_file))
        inserted[pid] = other.get_paper(pid)["imported_at"]
        return prepared
    monkeypatch.setattr(module, "prepare_arxiv_project", acquire)
    try:
        run = ws.create_reference_expansion(["arxiv:2401.10001"])
        result = drain(ws, run["run_id"])
        assert result["usage"]["new_papers"] == 0
        assert any(e.get("reason") == "existing_paper_conflict" for e in result["edges"])
        assert all(ws.get_paper(pid)["imported_at"] == stamp for pid, stamp in inserted.items())
    finally:
        other.close()


@pytest.mark.parametrize("phase", ["before_acquisition", "before_edge_completion"])
def test_process_reopen_recovers_prepared_import(chain, monkeypatch, phase):
    ws, calls = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    ws.advance_reference_expansion(run["run_id"], max_steps=1)
    class Crash(BaseException):
        pass
    method = "_import_reference_target" if phase == "before_acquisition" else "_expansion_link"
    monkeypatch.setattr(ws, method, lambda *a: (_ for _ in ()).throw(Crash()))
    with pytest.raises(Crash):
        ws.advance_reference_expansion(run["run_id"], max_steps=1)
    other = Workspace.open(ws.path)
    try:
        done = drain(other, run["run_id"])
        assert done["state"] == "completed"
        assert done["usage"]["new_papers"] == 2 and len(calls) == 2
    finally:
        other.close()


def test_rejects_budget_below_consumed_usage(chain):
    ws, _ = chain
    run = ws.create_reference_expansion(["arxiv:2401.10001"])
    done = drain(ws, run["run_id"])
    with pytest.raises(ValueError, match="consumed"):
        ws.update_reference_expansion_policy(run["run_id"], {"max_new_papers": 1})
    assert ws.get_reference_expansion(run["run_id"])["usage"] == done["usage"]


def test_schema_7_upgrade_preserves_papers_searches_and_resolutions(workspace, monkeypatch):
    records = [{"provider": "crossref", "records": [{"kind": "doi", "doi": "10.1000/example", "title": "Published target"}], "warnings": []}]
    monkeypatch.setattr(workspace, "_run_reference_search_providers", lambda *a: records)
    blocked = workspace.plan_external_imports_for_paper("local:paper")["blocked"][0]["blocked_id"]
    searched = workspace.search_external_reference("local:paper", blocked, resolver_version="legacy_v1")
    resolution = workspace.resolve_external_reference("local:paper", blocked, {"kind": "doi", "doi": "10.1000/example"}, import_target=False)
    paper = workspace.get_paper("local:paper")
    with workspace._connection:
        for suffix in ("attempts", "edges", "events", "lease", "nodes", "runs"):
            workspace._connection.execute("DROP TABLE reference_expansion_" + suffix)
        for column in ('resolver_version', 'search_schema_version', 'assessment_metadata_json'):
            workspace._connection.execute('ALTER TABLE reference_search_runs DROP COLUMN ' + column)
        for column in ('candidate_schema_version', 'assessment_json'):
            workspace._connection.execute('ALTER TABLE reference_search_candidates DROP COLUMN ' + column)
        workspace._connection.execute("UPDATE workspace_meta SET value='7' WHERE key='schema_version'")
    upgraded = Workspace.open(workspace.path)
    try:
        assert upgraded.get_paper("local:paper") == paper
        assert upgraded._reference_search_by_id(searched["search_run_id"]) == searched
        assert upgraded._reference_resolution_by_id(resolution["resolution_id"]) == resolution
    finally:
        upgraded.close()
