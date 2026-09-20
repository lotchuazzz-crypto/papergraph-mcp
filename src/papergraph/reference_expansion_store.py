"""Transactional expansion snapshots, history and cross-process execution lease."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from threading import Event, Thread

TABLES = {"reference_expansion_" + name for name in ("runs", "nodes", "edges", "attempts", "events", "lease")}
COLUMNS = {
    "reference_expansion_runs": {"run_id", "payload", "control"},
    "reference_expansion_lease": {"singleton", "owner", "expires"},
    **{"reference_expansion_" + group: {"run_id", key, "payload"}
       for group, key in (("nodes", "node_id"), ("edges", "edge_id"),
                          ("attempts", "attempt_id"), ("events", "event_id"))},
}
SCHEMA_SQL = """
CREATE TABLE reference_expansion_runs (
 run_id TEXT PRIMARY KEY, payload TEXT NOT NULL, control TEXT);
CREATE TABLE reference_expansion_nodes (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 node_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,node_id));
CREATE TABLE reference_expansion_edges (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 edge_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,edge_id));
CREATE TABLE reference_expansion_attempts (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 attempt_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,attempt_id));
CREATE TABLE reference_expansion_events (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 event_id INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,event_id));
CREATE TABLE reference_expansion_lease (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), owner TEXT NOT NULL, expires REAL NOT NULL);
"""


def dumps(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def migrate(connection):
    connection.execute("SAVEPOINT expansion_migration")
    try:
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip():
                connection.execute(statement)
        connection.execute("UPDATE workspace_meta SET value='8' WHERE key='schema_version'")
    except Exception:
        connection.execute("ROLLBACK TO expansion_migration")
        raise
    finally:
        connection.execute("RELEASE expansion_migration")


class Store:
    def __init__(self, workspace):
        self.ws = workspace
        self.db = workspace._connection
        self.owner = None

    def load(self, run_id):
        row = self.db.execute("SELECT payload, control FROM reference_expansion_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown expansion run: {run_id}")
        run = json.loads(row[0])
        self.merge_control_events(run)
        if row[1]:
            run["state"] = "cancelled" if row[1] == "cancel" else "paused"
            run["reason"] = "user_" + row[1]
        return run

    def merge_control_events(self, run):
        known = {event["event_id"] for event in run["events"]}
        for event_id, payload in self.db.execute("SELECT event_id,payload FROM reference_expansion_events WHERE run_id=? AND event_id<0 ORDER BY event_id DESC", (run["run_id"],)):
            if event_id not in known:
                run["events"].append(json.loads(payload))

    def save(self, run):
        with self.db:
            if not self.db.in_transaction:
                self.db.execute("BEGIN IMMEDIATE")
            self.merge_control_events(run)
            if self.owner:
                row = self.db.execute("SELECT owner, expires FROM reference_expansion_lease WHERE singleton=1").fetchone()
                if not row or row[0] != self.owner or row[1] <= time.time():
                    raise RuntimeError("Expansion execution lease lost")
            self.db.execute("INSERT INTO reference_expansion_runs(run_id,payload) VALUES (?,?) ON CONFLICT(run_id) DO UPDATE SET payload=excluded.payload", (run["run_id"], dumps(run)))
            for group, key in (("nodes", "node_id"), ("edges", "edge_id"), ("attempts", "attempt_id"), ("events", "event_id")):
                for item in run[group]:
                    self.db.execute(f"INSERT INTO reference_expansion_{group}(run_id,{key},payload) VALUES (?,?,?) ON CONFLICT(run_id,{key}) DO UPDATE SET payload=excluded.payload", (run["run_id"], item[key], dumps(item)))

    def event(self, run, kind, **data):
        run["events"].append({"event_id": len(run["events"]) + 1, "kind": kind, "timestamp": time.time(), **data})

    @contextmanager
    def lease(self):
        owner = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO reference_expansion_lease VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET owner=excluded.owner, expires=excluded.expires WHERE reference_expansion_lease.expires <= ?", (owner, time.time() + 120, time.time()))
            row = self.db.execute("SELECT owner FROM reference_expansion_lease WHERE singleton=1").fetchone()
            if row[0] != owner:
                raise ValueError("Another expansion holds the workspace execution lease")
        self.owner = owner
        stop = Event()

        def renew():
            db = sqlite3.connect(self.ws.path, timeout=10)
            try:
                while not stop.wait(10):
                    try:
                        with db:
                            db.execute("UPDATE reference_expansion_lease SET expires=? WHERE singleton=1 AND owner=?", (time.time() + 120, owner))
                    except sqlite3.Error:
                        # save() fences stale owners if renewal cannot recover.
                        continue
            finally:
                db.close()

        thread = Thread(target=renew, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=15)
            with self.db:
                self.db.execute("DELETE FROM reference_expansion_lease WHERE owner=?", (owner,))
            self.owner = None
