"""Persistent, versioned storage for multi-paper theorem graphs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from papergraph.citations import build_citation_records
from papergraph.identity import global_theorem_id, normalize_paper_id
from papergraph.models import WorkspaceImportResult
from papergraph.parser import parse_project
from papergraph.project import LoadedProject


SCHEMA_VERSION = 1
_REQUIRED_TABLES = {
    "workspace_meta",
    "papers",
    "theorems",
    "theorem_refs",
    "citation_evidence",
}

_SCHEMA_SQL = """
CREATE TABLE workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE papers (
    paper_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('local', 'arxiv')),
    source_ref TEXT NOT NULL,
    source_version TEXT,
    title TEXT,
    authors_json TEXT NOT NULL,
    main_file TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    parser_version TEXT NOT NULL
);
CREATE TABLE theorems (
    global_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    local_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT,
    label TEXT,
    content TEXT NOT NULL,
    source_file TEXT,
    position INTEGER NOT NULL,
    UNIQUE (paper_id, local_id)
);
CREATE TABLE theorem_refs (
    source_global_id TEXT NOT NULL REFERENCES theorems(global_id) ON DELETE CASCADE,
    ref_label TEXT NOT NULL,
    target_global_id TEXT REFERENCES theorems(global_id) ON DELETE CASCADE,
    PRIMARY KEY (source_global_id, ref_label)
);
CREATE TABLE citation_evidence (
    id INTEGER PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    citation_key TEXT NOT NULL,
    command TEXT NOT NULL,
    source_file TEXT NOT NULL,
    bib_file TEXT,
    bib_entry_type TEXT,
    cited_arxiv_id TEXT,
    cited_version TEXT,
    target_paper_id TEXT REFERENCES papers(paper_id) ON DELETE SET NULL,
    resolution_status TEXT NOT NULL
);
CREATE INDEX theorems_paper_kind ON theorems(paper_id, kind);
CREATE INDEX citations_source ON citation_evidence(source_paper_id);
CREATE INDEX citations_target ON citation_evidence(target_paper_id);
CREATE INDEX citations_arxiv ON citation_evidence(cited_arxiv_id);
INSERT INTO workspace_meta (key, value) VALUES ('schema_version', '1');
"""


class WorkspaceError(Exception):
    """Base class for workspace persistence errors."""


class WorkspaceSchemaError(WorkspaceError):
    """Raised when a database does not use the supported workspace schema."""


class WorkspacePathError(WorkspaceError, ValueError):
    """Raised when the requested workspace path cannot be used as a file."""


class DuplicateTheoremIdError(WorkspaceError):
    """Raised when one paper contains the same local theorem ID twice."""


class Workspace:
    """A single SQLite-backed PaperGraph workspace."""

    def __init__(self, path: Path, connection: sqlite3.Connection):
        self.path = path
        self._connection = connection

    @classmethod
    def open(cls, path: str | Path) -> Workspace:
        """Open a supported workspace, initializing an empty database."""

        resolved = Path(path).expanduser().resolve()
        if resolved.is_dir():
            raise WorkspacePathError(
                f"Workspace path is a directory, not a database file: {resolved}"
            )
        resolved.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(resolved)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            cls._initialize_or_validate_schema(connection)
        except Exception:
            connection.close()
            raise
        return cls(resolved, connection)

    @staticmethod
    def _initialize_or_validate_schema(connection: sqlite3.Connection) -> None:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not tables:
            connection.executescript(_SCHEMA_SQL)
            return
        if "workspace_meta" not in tables:
            raise WorkspaceSchemaError(
                "Database has no PaperGraph workspace schema metadata"
            )

        row = connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise WorkspaceSchemaError("Workspace schema version is missing")
        try:
            schema_version = int(row[0])
        except (TypeError, ValueError) as error:
            raise WorkspaceSchemaError(
                f"Invalid workspace schema version: {row[0]!r}"
            ) from error
        if schema_version != SCHEMA_VERSION:
            raise WorkspaceSchemaError(
                f"Unsupported workspace schema version {schema_version}; "
                f"this PaperGraph supports version {SCHEMA_VERSION}"
            )
        missing_tables = sorted(_REQUIRED_TABLES - tables)
        if missing_tables:
            raise WorkspaceSchemaError(
                "Workspace schema is missing required tables: "
                + ", ".join(missing_tables)
            )

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def import_project(
        self,
        paper_id: str,
        source_type: str,
        source_ref: str,
        source_version: str | None,
        project: LoadedProject,
    ) -> WorkspaceImportResult:
        """Atomically add or replace one parsed LaTeX project."""

        normalized_paper_id = normalize_paper_id(paper_id)
        if source_type not in {"local", "arxiv"}:
            raise ValueError(f"Invalid source type: {source_type!r}")
        expected_source_type = normalized_paper_id.split(":", 1)[0]
        if source_type != expected_source_type:
            raise ValueError(
                f"source type {source_type!r} does not match "
                f"paper id {normalized_paper_id!r}"
            )

        nodes = parse_project(project)
        citations = build_citation_records(project)

        seen_local_ids: set[str] = set()
        global_ids: dict[str, str] = {}
        for node in nodes:
            if node.id in seen_local_ids:
                raise DuplicateTheoremIdError(
                    f"Duplicate theorem id in {normalized_paper_id}: {node.id}"
                )
            seen_local_ids.add(node.id)
            global_ids[node.id] = global_theorem_id(
                normalized_paper_id,
                node.id,
            )

        labels = {
            node.label: global_ids[node.id]
            for node in nodes
            if node.label is not None
        }
        main_file = project.root_file.relative_to(project.project_root).as_posix()
        imported_at = datetime.now(timezone.utc).isoformat()
        authors_json = json.dumps(list(project.authors), ensure_ascii=False)

        with self._connection:
            self._connection.execute(
                "DELETE FROM papers WHERE paper_id = ?",
                (normalized_paper_id,),
            )
            self._connection.execute(
                """
                INSERT INTO papers (
                    paper_id, source_type, source_ref, source_version, title,
                    authors_json, main_file, imported_at, parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_paper_id,
                    source_type,
                    source_ref,
                    source_version,
                    project.title,
                    authors_json,
                    main_file,
                    imported_at,
                    _parser_version(),
                ),
            )
            self._connection.executemany(
                """
                INSERT INTO theorems (
                    global_id, paper_id, local_id, kind, title, label,
                    content, source_file, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        global_ids[node.id],
                        normalized_paper_id,
                        node.id,
                        node.kind,
                        node.title,
                        node.label,
                        node.content,
                        node.source_file,
                        node.position,
                    )
                    for node in nodes
                ),
            )
            self._connection.executemany(
                """
                INSERT INTO theorem_refs (
                    source_global_id, ref_label, target_global_id
                ) VALUES (?, ?, ?)
                """,
                (
                    (global_ids[node.id], reference, labels.get(reference))
                    for node in nodes
                    for reference in node.refs
                ),
            )
            self._connection.executemany(
                """
                INSERT INTO citation_evidence (
                    source_paper_id, citation_key, command, source_file,
                    bib_file, bib_entry_type, cited_arxiv_id, cited_version,
                    target_paper_id, resolution_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        normalized_paper_id,
                        citation.citation_key,
                        citation.command,
                        citation.source_file,
                        citation.bib_file,
                        citation.bib_entry_type,
                        citation.cited_arxiv_id,
                        citation.cited_version,
                        None,
                        citation.resolution_status,
                    )
                    for citation in citations
                ),
            )

        return WorkspaceImportResult(
            paper_id=normalized_paper_id,
            theorem_count=len(nodes),
            citation_count=len(citations),
            unresolved_citation_count=sum(
                citation.resolution_status != "resolved_candidate"
                for citation in citations
            ),
        )

    def counts(self) -> dict[str, int]:
        """Return the total paper and theorem counts."""

        paper_count = self._connection.execute(
            "SELECT COUNT(*) FROM papers"
        ).fetchone()[0]
        theorem_count = self._connection.execute(
            "SELECT COUNT(*) FROM theorems"
        ).fetchone()[0]
        return {"papers": paper_count, "theorems": theorem_count}


def _parser_version() -> str:
    try:
        return version("papergraph-mcp")
    except PackageNotFoundError:
        return "unknown"
