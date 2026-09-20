"""Bounded, resumable reference expansion exposed by Workspace."""
from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from functools import wraps
from pathlib import Path

from papergraph.identity import normalize_paper_id, paper_id_from_arxiv
from papergraph.reference_expansion_policy import LIMITS, identifiers, importable_target, select_candidate, validate_policy
from papergraph.reference_expansion_store import Store, dumps


class ExpansionImportConflict(ValueError):
    """A concurrent edit invalidated an expansion's prepared import."""


def locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call


def fingerprint(ws, paper_id):
    if not ws._paper_exists(paper_id):
        return "missing"
    paper = ws.get_paper(paper_id)
    return hashlib.sha256(dumps({k: paper.get(k) for k in ("paper_id", "imported_at", "source_ref", "source_version", "parser_version")}).encode()).hexdigest()


def node(ws, paper_id, depth):
    return {"node_id": paper_id, "paper_id": paper_id, "aliases": [paper_id], "depth": depth,
            "fingerprint": fingerprint(ws, paper_id), "cursor": 0, "discovery": "queued", "references": None}


def pending(run):
    tasks = [(n["depth"], n["paper_id"], 0, n["node_id"], n) for n in run["nodes"]
             if n["discovery"] == "queued" and n["depth"] < run["policy"]["max_depth"]]
    depths = {n["node_id"]: n["depth"] for n in run["nodes"]}
    tasks += [(depths[e["source"]], e["source"], 1, e["edge_id"], e) for e in run["edges"]
              if e["state"] in {"queued", "selected", "searching", "importing"}
              and depths[e["source"]] < run["policy"]["max_depth"]]
    return sorted(tasks, key=lambda t: t[:4])


def summarize(run):
    counts = {s: sum(e["state"] == s for e in run["edges"]) for s in
              ("needs_review", "boundary", "retryable_failure", "imported", "linked_existing", "skipped")}
    counts["runnable"] = len(pending(run))
    counts["frontier"] = sum(n["discovery"] in {"depth_limit", "queued"} for n in run["nodes"])
    run["summary"] = counts
    run["continuation_required"] = run["state"] == "ready"
    run["next_actions"] = [{"run_id": run["run_id"], "edge_id": e["edge_id"], "action":
                            "retry" if e["state"] == "retryable_failure" else "select_target_or_skip",
                            "reason": e.get("reason")} for e in run["edges"] if e["state"] in {"needs_review", "retryable_failure", "boundary"}]
    run["next_actions"] += [{"run_id": run["run_id"], "paper_id": n["paper_id"],
                             "action": "create_new_run", "reason": "stale_source"}
                            for n in run["nodes"] if n["discovery"] == "stale_source"]
    return run


class ReferenceExpansionMixin:
    def _check_expansion_import(self, paper_id):
        guard = getattr(self, "_expansion_import_guard", None)
        if guard is None:
            return
        store, run, attempt, source = guard
        # Called inside the paper-write transaction, after acquisition/parsing.
        if not self._connection.in_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        row = self._connection.execute("SELECT owner,expires FROM reference_expansion_lease WHERE singleton=1").fetchone()
        if not row or row[0] != store.owner or row[1] <= time.time():
            raise ExpansionImportConflict("execution_lease_lost")
        if paper_id != attempt["paper_id"]:
            raise ExpansionImportConflict("imported_identity_conflict")
        if fingerprint(self, source["paper_id"]) != source["fingerprint"]:
            raise ExpansionImportConflict("stale_source")
        if self._paper_exists(paper_id):
            raise ExpansionImportConflict("existing_paper_conflict")
        event = {"event_id": -time.time_ns(), "kind": "paper_committed",
                 "timestamp": time.time(), "attempt_id": attempt["attempt_id"], "paper_id": paper_id}
        # This marker rolls back together with the paper if any insert fails.
        self._connection.execute("INSERT INTO reference_expansion_events VALUES(?,?,?)", (run["run_id"], event["event_id"], dumps(event)))

    @locked
    def create_reference_expansion(self, root_paper_ids: list[str], policy: dict | None = None) -> dict:
        policy = validate_policy(policy)
        if not isinstance(root_paper_ids, list) or not root_paper_ids:
            raise ValueError("root_paper_ids must be a nonempty list")
        roots = sorted({normalize_paper_id(p) for p in root_paper_ids})
        nodes = [node(self, p, 0) for p in roots]
        if any(n["fingerprint"] == "missing" for n in nodes):
            raise ValueError("Every root paper must exist in the workspace")
        run = {"expansion_schema_version": 1, "run_id": "expansion:" + uuid.uuid4().hex,
               "roots": roots, "policy": policy, "policy_revisions": [copy.deepcopy(policy)],
               "state": "ready", "reason": None, "created_at": time.time(),
               "usage": {"new_papers": 0, "searches": 0, "edges": 0},
               "nodes": nodes, "edges": [], "attempts": [], "events": [], "affected_paper_ids": []}
        store = Store(self)
        with store.lease():
            store.event(run, "created", policy=policy)
            store.save(summarize(run))
        return run

    @locked
    def get_reference_expansion(self, run_id: str) -> dict:
        return summarize(Store(self).load(run_id))

    @locked
    def list_reference_expansions(self, state: str | None = None) -> dict:
        runs = [self.get_reference_expansion(row[0]) for row in self._connection.execute(
            "SELECT run_id FROM reference_expansion_runs ORDER BY run_id").fetchall()]
        return {"expansion_schema_version": 1, "runs": [
            {k: r[k] for k in ("run_id", "roots", "state", "reason", "policy", "usage", "summary")}
            for r in runs if state is None or state == r["state"]]}

    @locked
    def update_reference_expansion_policy(self, run_id: str, limits: dict) -> dict:
        if not isinstance(limits, dict) or not limits or set(limits) - set(LIMITS):
            raise ValueError("Only numeric budget limits may be updated")
        store = Store(self)
        with store.lease():
            run = store.load(run_id)
            self._expansion_mutable(run)
            updated = validate_policy({**run["policy"], **limits})
            reserved = sum(a.get("reserved", False) and a["phase"] == "prepared" for a in run["attempts"])
            depths = {n["node_id"]: n["depth"] for n in run["nodes"]}
            consumed = {"max_new_papers": run["usage"]["new_papers"] + reserved, "max_searches": run["usage"]["searches"],
                        "max_edges": run["usage"]["edges"], "max_depth": max(
                            [*depths.values(), *(depths[e["source"]] + 1 for e in run["edges"] if e["state"] == "importing")])}
            if any(updated[k] < v for k, v in consumed.items()):
                raise ValueError("Budget cannot be below consumed usage")
            run["policy"] = updated
            run["policy_revisions"].append(copy.deepcopy(updated))
            for n in run["nodes"]:
                if n["discovery"] == "depth_limit" and n["depth"] < updated["max_depth"]:
                    n["discovery"] = "queued"
            run.update(state="ready", reason=None)
            store.event(run, "policy_updated", policy=updated)
            store.save(summarize(run))
        return run

    def pause_reference_expansion(self, run_id: str) -> dict:
        return self._expansion_control(run_id, "pause")

    def cancel_reference_expansion(self, run_id: str) -> dict:
        return self._expansion_control(run_id, "cancel")

    def _expansion_control(self, run_id, control):
        # Separate connection: another client can signal while a download runs.
        import sqlite3
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload,control FROM reference_expansion_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown expansion run: {run_id}")
            if row[1] == "cancel" or json.loads(row[0])["state"] == "cancelled":
                raise ValueError("Expansion run is cancelled")
            db.execute("UPDATE reference_expansion_runs SET control=? WHERE run_id=?", (control, run_id))
            event = {"event_id": -time.time_ns(), "kind": "control_requested", "control": control, "timestamp": time.time()}
            db.execute("INSERT INTO reference_expansion_events VALUES(?,?,?)", (run_id, event["event_id"], dumps(event)))
        # Avoid waiting for the worker's in-process lock.
        result = json.loads(row[0])
        result["events"].append(event)
        result.update(state="cancelled" if control == "cancel" else "paused", reason="user_" + control)
        return summarize(result)

    @staticmethod
    def _expansion_mutable(run):
        if run["state"] in {"cancelled", "failed"}:
            raise ValueError(f"Expansion run is {run['state']}")

    @locked
    def decide_reference_expansion(self, run_id: str, edge_id: str, decision: dict) -> dict:
        choices = {"candidate_id", "target", "existing_paper_id", "skip", "retry"}
        if not isinstance(decision, dict) or len(decision) != 1 or not set(decision) <= choices:
            raise ValueError("Supply exactly one expansion decision")
        store = Store(self)
        with store.lease():
            run = store.load(run_id)
            self._expansion_mutable(run)
            edge = next((e for e in run["edges"] if e["edge_id"] == edge_id), None)
            if edge is None:
                raise ValueError("Unknown expansion edge")
            if edge["state"] in {"imported", "linked_existing"}:
                raise ValueError("Completed edge cannot be replaced")
            if edge["state"] == "importing":
                raise ValueError("Advance to reconcile the prepared import before making a decision")
            source = next(n for n in run["nodes"] if n["node_id"] == edge["source"])
            if fingerprint(self, source["paper_id"]) != source["fingerprint"]:
                raise ValueError("stale_source: create a new run for replaced source evidence")
            if "skip" in decision:
                if decision["skip"] is not True:
                    raise ValueError("skip must be true")
                edge.update(state="skipped", reason="user_skipped")
            elif "retry" in decision:
                if decision["retry"] is not True or edge["state"] != "retryable_failure":
                    raise ValueError("retry requires a retryable failure")
                edge.update(state="selected" if edge.get("target") else "queued", reason=None, refresh=True)
            else:
                target = decision.get("target")
                if "candidate_id" in decision:
                    candidate = next((c for c in edge.get("search", {}).get("candidates", []) if c["candidate_id"] == decision["candidate_id"]), None)
                    if candidate is None:
                        raise ValueError("Candidate does not belong to the edge search snapshot")
                    target = candidate["target"]
                if "existing_paper_id" in decision:
                    pid = normalize_paper_id(decision["existing_paper_id"])
                    self.get_paper(pid)
                    target = {"kind": "existing", "paper_id": pid}
                if not isinstance(target, dict):
                    raise ValueError("target must be an object")
                edge.update(target=copy.deepcopy(target), state="selected", reason=None,
                            decision={"kind": "manual", "input": copy.deepcopy(decision)})
            run.update(state="ready", reason=None)
            store.event(run, "decision", edge_id=edge_id, decision=decision)
            store.save(summarize(run))
        return run

    @locked
    def advance_reference_expansion(self, run_id: str, max_steps: int = 10,
                                    time_budget_seconds: int = 20) -> dict:
        if type(max_steps) is not int or not 1 <= max_steps <= 100:
            raise ValueError("max_steps must be between 1 and 100")
        if type(time_budget_seconds) is not int or not 1 <= time_budget_seconds <= 60:
            raise ValueError("time_budget_seconds must be between 1 and 60")
        store = Store(self)
        with store.lease():
            run = store.load(run_id)
            self._expansion_mutable(run)
            with self._connection:
                self._connection.execute("UPDATE reference_expansion_runs SET control=NULL WHERE run_id=? AND control='pause'", (run_id,))
            run.update(state="running", reason=None, affected_paper_ids=[])
            store.event(run, "advance")
            deadline = time.monotonic() + time_budget_seconds
            try:
                for _ in range(max_steps):
                    control = self._connection.execute("SELECT control FROM reference_expansion_runs WHERE run_id=?", (run_id,)).fetchone()[0]
                    if control:
                        run.update(state="cancelled" if control == "cancel" else "paused", reason="user_" + control)
                        store.event(run, "control", control=control)
                        break
                    tasks = pending(run)
                    if not tasks or time.monotonic() >= deadline:
                        break
                    _, _, kind, _, item = tasks[0]
                    if kind == 0:
                        self._expansion_discover(store, run, item)
                    else:
                        self._expansion_edge(store, run, item)
                    store.save(summarize(run))
                    if run["state"] == "paused":
                        break
                control = self._connection.execute("SELECT control FROM reference_expansion_runs WHERE run_id=?", (run_id,)).fetchone()[0]
                if control and run["reason"] != "user_" + control:
                    run.update(state="cancelled" if control == "cancel" else "paused", reason="user_" + control)
                    store.event(run, "control", control=control)
                if run["state"] == "running":
                    run["state"] = "ready" if pending(run) else "waiting" if any(
                        e["state"] in {"needs_review", "retryable_failure"} for e in run["edges"]) or any(
                        n["discovery"] == "stale_source" for n in run["nodes"]) else "completed"
                store.save(summarize(run))
            except Exception as exc:
                run.update(state="failed", reason=str(exc)[:240])
                store.event(run, "run_failed", reason=run["reason"])
                store.save(summarize(run))
                raise
        return run

    def _expansion_discover(self, store, run, source):
        if fingerprint(self, source["paper_id"]) != source["fingerprint"]:
            source["discovery"] = "stale_source"
            for edge in run["edges"]:
                if edge["source"] == source["node_id"] and edge["state"] not in {"imported", "linked_existing", "skipped"}:
                    edge.update(state="needs_review", reason="stale_source")
            return
        if source["references"] is None:
            plan = self.plan_external_imports_for_paper(source["paper_id"])
            source["references"] = sorted(
                [{"key": b["blocked_id"], "blocked_id": b["blocked_id"], "evidence": b["evidence"]} for b in plan["blocked"]] +
                [{"key": c["candidate_id"], "direct": c, "evidence": c["evidence"]} for c in plan["candidates"]], key=lambda r: r["key"])
        # Discovery is paginated; the snapshot/cursor preserves truncated references.
        remaining = source["references"][source["cursor"]:]
        for ref in remaining[:25]:
            if run["usage"]["edges"] >= run["policy"]["max_edges"]:
                run.update(state="paused", reason="edge_limit")
                return
            edge_id = "expansion-edge:" + hashlib.sha256((source["node_id"] + "|" + ref["key"]).encode()).hexdigest()[:24]
            edge = {"edge_id": edge_id, "source": source["node_id"], "reference_key": ref["key"],
                    "evidence": ref["evidence"], "state": "queued", "reason": None}
            if "blocked_id" in ref:
                edge["blocked_id"] = ref["blocked_id"]
            if "direct" in ref:
                direct = ref["direct"]
                if direct.get("warnings"):
                    edge.update(state="needs_review", reason="version_conflict")
                else:
                    edge.update(state="selected", target={"kind": "arxiv", "arxiv_id": direct["source"]["arxiv_id"] + (direct["source"].get("arxiv_version") or "")},
                                decision={"kind": "policy_selected", "policy_version": "unique_strong_v1", "reason_codes": ["exact_source_identifier"]})
            run["edges"].append(edge)
            run["usage"]["edges"] += 1
            source["cursor"] += 1
        if source["cursor"] == len(source["references"]):
            source["discovery"] = "done"

    def _expansion_edge(self, store, run, edge):
        source = next(n for n in run["nodes"] if n["node_id"] == edge["source"])
        if fingerprint(self, source["paper_id"]) != source["fingerprint"]:
            edge.update(state="needs_review", reason="stale_source")
            return
        if edge["state"] in {"queued", "searching"}:
            if run["usage"]["new_papers"] >= run["policy"]["max_new_papers"]:
                run.update(state="paused", reason="paper_limit")
                return
            if edge["state"] == "searching":
                edge.update(state="retryable_failure", reason="interrupted_search")
                store.event(run, "interrupted_search", edge_id=edge["edge_id"])
                return
            cached = None if edge.get("refresh") else self._latest_reference_search(edge["source"], edge["blocked_id"])
            if cached and (sorted(cached.get("providers") or ["arxiv", "crossref", "openalex"]) != run["policy"]["providers"]
                           or cached.get("max_candidates", 10) < 100):
                cached = None
            if cached is None and run["usage"]["searches"] >= run["policy"]["max_searches"]:
                run.update(state="paused", reason="search_limit")
                return
            if cached is None:
                run["usage"]["searches"] += 1
            edge["state"] = "searching"
            attempt = self._expansion_attempt(run, edge, "search")
            store.save(run)
            try:
                search = cached or self.search_external_reference(edge["source"], edge["blocked_id"], providers=run["policy"]["providers"], max_candidates=100, refresh=True)
                edge["search"] = copy.deepcopy(search)
                choice = select_candidate(search)
                if choice["eligible"]:
                    edge.update(state="selected", target=choice["target"], identity_target=choice["identity_target"],
                                decision={"kind": "policy_selected", **choice})
                elif not search.get("candidates"):
                    edge.update(state="retryable_failure" if search.get("provider_warnings") else "boundary",
                                reason="provider_unavailable" if search.get("provider_warnings") else "no_candidates")
                else:
                    no_source = choice["reason_codes"] == ["no_importable_source"] or all(c["target"].get("kind") in {"metadata", "doi", "url"} and not c["target"].get("arxiv_id") for c in search["candidates"])
                    edge.update(state="boundary" if no_source else "needs_review", reason="no_importable_source" if no_source else choice["reason_codes"][0])
                attempt["phase"] = "completed"
            except Exception as exc:
                edge.update(state="retryable_failure", reason=str(exc)[:240])
                attempt.update(phase="failed", error=edge["reason"])
            return
        self._expansion_import(store, run, edge, source)

    @staticmethod
    def _expansion_attempt(run, edge, kind, **data):
        previous = next((a["attempt_id"] for a in reversed(run["attempts"]) if a["edge_id"] == edge["edge_id"] and a["kind"] == kind), None)
        attempt = {"attempt_id": uuid.uuid4().hex, "edge_id": edge["edge_id"], "kind": kind,
                   "phase": "prepared", "previous_attempt_id": previous, **data}
        run["attempts"].append(attempt)
        edge["attempt_id"] = attempt["attempt_id"]
        return attempt

    def _expansion_import(self, store, run, edge, source):
        target = edge["target"]
        try:
            imported = importable_target(target, manual=edge.get("decision", {}).get("kind") == "manual")
            digest = None
            if target.get("kind") == "existing":
                pid = target["paper_id"]
            elif imported and imported["kind"] == "arxiv":
                pid = paper_id_from_arxiv(imported["arxiv_id"])[0]
            elif imported and imported["kind"] == "pdf":
                path = Path(imported["path"]).expanduser().resolve()
                with path.open("rb") as stream:
                    content = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        content.update(chunk)
                digest = content.hexdigest()
                pid = normalize_paper_id(imported.get("paper_id") or "local:pdf-" + digest[:24])
                imported = {**imported, "path": str(path), "paper_id": pid}
                prior = next((a for a in run["attempts"] if a.get("digest") == digest and a.get("paper_id") and self._paper_exists(a["paper_id"])), None)
                if prior:
                    pid = prior["paper_id"]
            else:
                edge.update(state="boundary", reason="no_importable_source")
                return
        except (ValueError, OSError) as exc:
            edge.update(state="retryable_failure", reason=str(exc)[:240])
            return
        exists = self._paper_exists(pid)
        if exists and imported and imported["kind"] == "arxiv":
            requested_version = paper_id_from_arxiv(imported["arxiv_id"])[1]
            if requested_version and self.get_paper(pid).get("source_version") != requested_version:
                edge.update(state="needs_review", reason="version_conflict")
                return
        if exists and digest:
            old = self.get_paper(pid)
            old_path = Path(old.get("source_ref") or "")
            if not old_path.is_file() or hashlib.sha256(old_path.read_bytes()).hexdigest() != digest:
                edge.update(state="needs_review", reason="existing_paper_conflict")
                return
        attempt = next((a for a in run["attempts"] if a["attempt_id"] == edge.get("attempt_id") and a["kind"] == "import" and a["phase"] == "prepared"), None)
        if attempt is not None:
            if exists and not attempt["baseline_exists"] and not any(
                e.get("kind") == "paper_committed" and e.get("attempt_id") == attempt["attempt_id"]
                for e in run["events"]
            ):
                edge.update(state="needs_review", reason="existing_paper_conflict")
                attempt.update(phase="conflict", reserved=False)
                return
            store.event(run, "reconcile_import", edge_id=edge["edge_id"], paper_id=pid)
        elif not exists and run["usage"]["new_papers"] >= run["policy"]["max_new_papers"]:
            run.update(state="paused", reason="paper_limit")
            return
        if attempt is None:
            attempt = self._expansion_attempt(run, edge, "import", paper_id=pid, target=imported,
                                             digest=digest, baseline_exists=exists, reserved=not exists,
                                             decision=copy.deepcopy(edge.get("decision")))
        edge["state"] = "importing"
        store.save(run)
        try:
            resolution = None
            if edge.get("blocked_id") and imported:
                resolutions = self.list_external_reference_resolutions(edge["source"])["resolutions"]
                matches = [r for r in resolutions if r["source"]["blocked_id"] == edge["blocked_id"]]
                for r in matches:
                    prior_target = importable_target(r["target"], manual=True)
                    if prior_target != imported:
                        edge.update(state="needs_review", reason="existing_resolution_conflict")
                        attempt["phase"] = "conflict"
                        return
                resolution = matches[0] if matches else self.resolve_external_reference(edge["source"], edge["blocked_id"], imported, import_target=False)
                if not matches:
                    review = {**resolution["source"]["review"], "selection": {
                        "kind": edge.get("decision", {}).get("kind", "manual"),
                        "run_id": run["run_id"], "edge_id": edge["edge_id"],
                        "policy_version": run["policy"]["auto_select_policy"]}}
                    with self._connection:
                        self._connection.execute("UPDATE reference_resolutions SET review_json=? WHERE resolution_id=?", (dumps(review), resolution["resolution_id"]))
            if not exists:
                if target.get("kind") == "existing":
                    raise ValueError("Selected existing paper no longer exists")
                self._expansion_import_guard = (store, run, attempt, source)
                try:
                    actual = self._import_reference_target(imported)
                finally:
                    self._expansion_import_guard = None
                if actual != pid:
                    raise ValueError("Imported identity differs from reserved target")
            if resolution:
                self._update_reference_resolution_import(resolution["resolution_id"], "resolved_imported", pid, [])
                edge["resolution_id"] = resolution["resolution_id"]
            if not attempt["baseline_exists"]:
                run["usage"]["new_papers"] += 1
            attempt.update(phase="completed", reserved=False)
            edge.update(state="linked_existing" if attempt["baseline_exists"] else "imported", target_node=pid, reason=None)
            self._expansion_link(run, edge, source, pid)
            run["affected_paper_ids"] = sorted(set(run["affected_paper_ids"]) | {edge["source"], pid})
            store.event(run, "import_completed", edge_id=edge["edge_id"], paper_id=pid)
        except ExpansionImportConflict as exc:
            edge.update(state="needs_review", reason=str(exc))
            attempt.update(phase="conflict", reserved=False)
        except Exception as exc:
            # A committed paper with an incomplete resolution is reconciled on retry.
            if self._paper_exists(pid) and not attempt["baseline_exists"]:
                edge.update(state="importing", reason=str(exc)[:240])
                run.update(state="paused", reason="import_reconciliation_required")
                return
            edge.update(state="retryable_failure", reason=str(exc)[:240])
            attempt.update(phase="failed", reserved=False, error=edge["reason"])
            if resolution:
                self._update_reference_resolution_import(resolution["resolution_id"], "failed_import", None, [edge["reason"]])

    def _expansion_link(self, run, edge, source, pid):
        depth = source["depth"] + 1
        existing = next((n for n in run["nodes"] if n["node_id"] == pid), None)
        if existing is None:
            existing = node(self, pid, depth)
            run["nodes"].append(existing)
        elif depth < existing["depth"]:
            existing["depth"] = depth
            if existing["discovery"] == "depth_limit":
                existing["discovery"] = "queued"
        aliases = identifiers(edge.get("identity_target", edge["target"]))
        existing["aliases"] = sorted(set(existing["aliases"]) | aliases)
        # Relax depths through already linked edges after a shorter manual path.
        changed = True
        while changed:
            changed = False
            mapping = {n["node_id"]: n for n in run["nodes"]}
            for link in run["edges"]:
                if link.get("target_node") in mapping:
                    parent, child = mapping[link["source"]], mapping[link["target_node"]]
                    if child["depth"] > parent["depth"] + 1:
                        child["depth"] = parent["depth"] + 1
                        changed = True
                        if child["discovery"] == "depth_limit":
                            child["discovery"] = "queued"
        for n in run["nodes"]:
            if n["discovery"] == "queued" and n["depth"] >= run["policy"]["max_depth"]:
                n["discovery"] = "depth_limit"

    @locked
    def export_reference_expansion(self, run_id: str, format: str = "json"):
        run = self.get_reference_expansion(run_id)
        if format == "json":
            return run
        if format != "markdown":
            raise ValueError("format must be json or markdown")
        from papergraph.reference_expansion_report import render_expansion
        return render_expansion(run)
