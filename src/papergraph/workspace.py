"""Persistent, versioned storage for multi-paper theorem graphs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import RLock

from papergraph.citations import build_citation_records
from papergraph.identity import (
    global_theorem_id,
    normalize_paper_id,
    split_global_theorem_id,
)
from papergraph.models import (
    DEPENDENCY_EXTRACTION_BASIS,
    EMPTY_DEPENDENCY_WARNING,
    WorkspaceImportResult,
)
from papergraph.parser import parse_project
from papergraph.project import LoadedProject


SCHEMA_VERSION = 2
_REQUIRED_TABLES = {
    "workspace_meta",
    "papers",
    "theorems",
    "theorem_refs",
    "citation_evidence",
}
_REQUIRED_THEOREM_COLUMNS = {
    "global_id",
    "paper_id",
    "local_id",
    "kind",
    "raw_kind",
    "display_kind",
    "normalized_kind",
    "title",
    "label",
    "content",
    "source_file",
    "position",
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
    raw_kind TEXT NOT NULL,
    display_kind TEXT NOT NULL,
    normalized_kind TEXT NOT NULL,
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
CREATE INDEX theorems_paper_kind ON theorems(paper_id, normalized_kind);
CREATE INDEX citations_source ON citation_evidence(source_paper_id);
CREATE INDEX citations_target ON citation_evidence(target_paper_id);
CREATE INDEX citations_arxiv ON citation_evidence(cited_arxiv_id);
INSERT INTO workspace_meta (key, value) VALUES ('schema_version', '2');
"""


class WorkspaceError(Exception):
    """Base class for workspace persistence errors."""


class WorkspaceSchemaError(WorkspaceError):
    """Raised when a database does not use the supported workspace schema."""


class WorkspacePathError(WorkspaceError, ValueError):
    """Raised when the requested workspace path cannot be used as a file."""


class DuplicateTheoremIdError(WorkspaceError):
    """Raised when one paper contains the same local theorem ID twice."""


def _synchronized(method):
    """Serialize access to one workspace's shared SQLite connection."""

    @wraps(method)
    def synchronized(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return synchronized


class Workspace:
    """A single SQLite-backed PaperGraph workspace."""

    def __init__(self, path: Path, connection: sqlite3.Connection):
        self.path = path
        self._connection = connection
        self._lock = RLock()

    @classmethod
    def open(cls, path: str | Path) -> Workspace:
        """Open a supported workspace, initializing an empty database."""

        resolved = Path(path).expanduser().resolve()
        if resolved.is_dir():
            raise WorkspacePathError(
                f"Workspace path is a directory, not a database file: {resolved}"
            )
        resolved.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(resolved, check_same_thread=False)
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
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(theorems)")
        }
        missing_columns = sorted(_REQUIRED_THEOREM_COLUMNS - columns)
        if missing_columns:
            raise WorkspaceSchemaError(
                "Workspace schema is missing required theorem columns: "
                + ", ".join(missing_columns)
            )

    @_synchronized
    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    @_synchronized
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
                    global_id, paper_id, local_id, kind, raw_kind,
                    display_kind, normalized_kind, title, label, content,
                    source_file, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        global_ids[node.id],
                        normalized_paper_id,
                        node.id,
                        node.kind,
                        node.raw_kind,
                        node.display_kind,
                        node.normalized_kind,
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
            self._connection.execute(
                """
                UPDATE citation_evidence
                SET target_paper_id = (
                    SELECT papers.paper_id
                    FROM papers
                    WHERE papers.paper_id =
                          'arxiv:' || citation_evidence.cited_arxiv_id
                )
                """
            )
            unresolved_citation_count = self._connection.execute(
                """
                SELECT COUNT(*)
                FROM citation_evidence
                WHERE source_paper_id = ?
                  AND target_paper_id IS NULL
                """,
                (normalized_paper_id,),
            ).fetchone()[0]

        return WorkspaceImportResult(
            paper_id=normalized_paper_id,
            theorem_count=len(nodes),
            citation_count=len(citations),
            unresolved_citation_count=unresolved_citation_count,
        )

    @_synchronized
    def counts(self) -> dict[str, int]:
        """Return the total paper and theorem counts."""

        paper_count = self._connection.execute(
            "SELECT COUNT(*) FROM papers"
        ).fetchone()[0]
        theorem_count = self._connection.execute(
            "SELECT COUNT(*) FROM theorems"
        ).fetchone()[0]
        return {"papers": paper_count, "theorems": theorem_count}

    @_synchronized
    def list_papers(self) -> list[dict]:
        """Return stored papers and graph counts in stable paper-ID order."""

        rows = self._connection.execute(
            """
            SELECT
                papers.paper_id, papers.source_type, papers.source_ref,
                papers.source_version, papers.title, papers.authors_json,
                papers.main_file, papers.imported_at, papers.parser_version,
                (SELECT COUNT(*) FROM theorems
                 WHERE theorems.paper_id = papers.paper_id),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.source_paper_id = papers.paper_id),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.source_paper_id = papers.paper_id
                   AND citation_evidence.target_paper_id IS NOT NULL),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.target_paper_id = papers.paper_id),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.source_paper_id = papers.paper_id
                   AND citation_evidence.target_paper_id IS NULL)
            FROM papers
            ORDER BY papers.paper_id
            """
        ).fetchall()
        return [_paper_from_row(row) for row in rows]

    @_synchronized
    def get_paper(self, paper_id: str) -> dict:
        """Return one stored paper with theorem-kind and citation counts."""

        normalized_paper_id = normalize_paper_id(paper_id)
        row = self._connection.execute(
            """
            SELECT
                papers.paper_id, papers.source_type, papers.source_ref,
                papers.source_version, papers.title, papers.authors_json,
                papers.main_file, papers.imported_at, papers.parser_version,
                (SELECT COUNT(*) FROM theorems
                 WHERE theorems.paper_id = papers.paper_id),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.source_paper_id = papers.paper_id),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.source_paper_id = papers.paper_id
                   AND citation_evidence.target_paper_id IS NOT NULL),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.target_paper_id = papers.paper_id),
                (SELECT COUNT(*) FROM citation_evidence
                 WHERE citation_evidence.source_paper_id = papers.paper_id
                   AND citation_evidence.target_paper_id IS NULL)
            FROM papers
            WHERE papers.paper_id = ?
            """,
            (normalized_paper_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown paper id: {normalized_paper_id}")

        result = _paper_from_row(row)
        result["kinds"] = {
            kind: count
            for kind, count in self._connection.execute(
                """
                SELECT normalized_kind, COUNT(*)
                FROM theorems
                WHERE paper_id = ?
                GROUP BY normalized_kind
                ORDER BY normalized_kind
                """,
                (normalized_paper_id,),
            )
        }
        return result

    @_synchronized
    def search_theorems(
        self,
        query: str,
        paper_id: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Find theorem titles and bodies by case-insensitive substring."""

        if not isinstance(query, str) or not query.strip():
            raise ValueError("Search query must not be empty")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("Search limit must be an integer from 1 through 100")

        conditions = [
            "instr(lower(coalesce(title, '') || char(10) || content), "
            "lower(?)) > 0"
        ]
        parameters: list[str | int] = [query.strip()]
        if paper_id is not None:
            conditions.append("paper_id = ?")
            parameters.append(normalize_paper_id(paper_id))
        if kind is not None:
            conditions.append("kind = ?")
            parameters.append(kind)
        parameters.append(limit)

        rows = self._connection.execute(
            f"""
            SELECT global_id, paper_id, local_id, kind, raw_kind,
                   display_kind, normalized_kind, title, source_file,
                   substr(content, 1, 240)
            FROM theorems
            WHERE {' AND '.join(conditions)}
            ORDER BY paper_id, global_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            {
                "global_id": global_id,
                "paper_id": stored_paper_id,
                "local_id": local_id,
                "kind": stored_kind,
                "raw_kind": raw_kind,
                "display_kind": display_kind,
                "normalized_kind": normalized_kind,
                "title": title,
                "source_file": source_file,
                "excerpt": excerpt,
            }
            for (
                global_id,
                stored_paper_id,
                local_id,
                stored_kind,
                raw_kind,
                display_kind,
                normalized_kind,
                title,
                source_file,
                excerpt,
            ) in rows
        ]

    @_synchronized
    def get_dependencies(
        self,
        global_id: str,
        recursive: bool = False,
    ) -> list[dict]:
        """Return direct or recursively reachable stored theorem references."""

        paper_id, local_id = split_global_theorem_id(global_id)
        normalized_global_id = global_theorem_id(paper_id, local_id)
        if self._connection.execute(
            "SELECT 1 FROM theorems WHERE global_id = ?",
            (normalized_global_id,),
        ).fetchone() is None:
            raise KeyError(f"Unknown theorem id: {normalized_global_id}")

        adjacency: dict[str, list[str]] = {}
        for source_global_id, target_global_id in self._connection.execute(
            """
            SELECT source_global_id, target_global_id
            FROM theorem_refs
            WHERE target_global_id IS NOT NULL
            ORDER BY source_global_id, ref_label, target_global_id
            """
        ):
            adjacency.setdefault(source_global_id, []).append(target_global_id)

        if recursive:
            dependency_ids: list[str] = []
            visited: set[str] = set()

            def visit(theorem_id: str) -> None:
                for dependency_id in adjacency.get(theorem_id, ()):
                    if dependency_id in visited:
                        continue
                    visited.add(dependency_id)
                    dependency_ids.append(dependency_id)
                    visit(dependency_id)

            visit(normalized_global_id)
        else:
            dependency_ids = adjacency.get(normalized_global_id, [])

        return [self._theorem_summary(item) for item in dependency_ids]

    @_synchronized
    def get_dependency_diagnostics(
        self,
        global_id: str,
        recursive: bool = False,
    ) -> dict:
        """Explain how dependencies were extracted for a stored theorem."""

        paper_id, local_id = split_global_theorem_id(global_id)
        normalized_global_id = global_theorem_id(paper_id, local_id)
        if self._connection.execute(
            "SELECT 1 FROM theorems WHERE global_id = ?",
            (normalized_global_id,),
        ).fetchone() is None:
            raise KeyError(f"Unknown theorem id: {normalized_global_id}")

        rows = self._connection.execute(
            """
            SELECT ref_label, target_global_id
            FROM theorem_refs
            WHERE source_global_id = ?
            ORDER BY ref_label
            """,
            (normalized_global_id,),
        ).fetchall()
        dependencies = self.get_dependencies(
            normalized_global_id,
            recursive=recursive,
        )
        dependency_ids = [
            item["global_id"]
            for item in dependencies
        ]
        warnings = []
        if not dependency_ids:
            warnings.append(EMPTY_DEPENDENCY_WARNING)
        return {
            "global_theorem_id": normalized_global_id,
            "recursive": recursive,
            "extraction_basis": DEPENDENCY_EXTRACTION_BASIS,
            "referenced_labels": [row[0] for row in rows],
            "resolved_labels": [row[0] for row in rows if row[1] is not None],
            "unresolved_labels": [row[0] for row in rows if row[1] is None],
            "dependency_ids": dependency_ids,
            "warnings": warnings,
        }

    @_synchronized
    def get_citations(
        self,
        paper_id: str,
        direction: str = "outgoing",
        include_unresolved: bool = True,
    ) -> list[dict]:
        """Return ordered incoming or outgoing citation evidence."""

        if direction not in {"incoming", "outgoing"}:
            raise ValueError("Citation direction must be 'incoming' or 'outgoing'")
        normalized_paper_id = normalize_paper_id(paper_id)
        if not self._paper_exists(normalized_paper_id):
            raise KeyError(f"Unknown paper id: {normalized_paper_id}")

        if direction == "incoming":
            condition = "target_paper_id = ?"
        else:
            condition = "source_paper_id = ?"
            if not include_unresolved:
                condition += " AND target_paper_id IS NOT NULL"

        rows = self._connection.execute(
            f"""
            SELECT source_paper_id, citation_key, command, source_file,
                   bib_file, bib_entry_type, cited_arxiv_id, cited_version,
                   target_paper_id, resolution_status
            FROM citation_evidence
            WHERE {condition}
            ORDER BY source_paper_id, citation_key, source_file, command, id
            """,
            (normalized_paper_id,),
        ).fetchall()
        keys = (
            "source_paper_id",
            "citation_key",
            "command",
            "source_file",
            "bib_file",
            "bib_entry_type",
            "cited_arxiv_id",
            "cited_version",
            "target_paper_id",
            "resolution_status",
        )
        return [dict(zip(keys, row)) for row in rows]

    @_synchronized
    def _paper_exists(self, paper_id: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM papers WHERE paper_id = ?",
            (paper_id,),
        ).fetchone() is not None

    @_synchronized
    def _theorem_summary(self, global_id: str) -> dict:
        row = self._connection.execute(
            """
            SELECT global_id, paper_id, local_id, kind, raw_kind,
                   display_kind, normalized_kind, title, label, source_file
            FROM theorems
            WHERE global_id = ?
            """,
            (global_id,),
        ).fetchone()
        assert row is not None
        references = [
            ref_label
            for (ref_label,) in self._connection.execute(
                """
                SELECT ref_label
                FROM theorem_refs
                WHERE source_global_id = ?
                ORDER BY ref_label
                """,
                (global_id,),
            )
        ]
        return {
            "global_id": row[0],
            "paper_id": row[1],
            "local_id": row[2],
            "kind": row[3],
            "raw_kind": row[4],
            "display_kind": row[5],
            "normalized_kind": row[6],
            "title": row[7],
            "label": row[8],
            "source_file": row[9],
            "refs": references,
        }


def _parser_version() -> str:
    try:
        return version("papergraph-mcp")
    except PackageNotFoundError:
        return "unknown"


def _paper_from_row(row: tuple) -> dict:
    return {
        "paper_id": row[0],
        "source_type": row[1],
        "source_ref": row[2],
        "source_version": row[3],
        "title": row[4],
        "authors": json.loads(row[5]),
        "main_file": row[6],
        "imported_at": row[7],
        "parser_version": row[8],
        "theorem_count": row[9],
        "citation_count": row[10],
        "outgoing_citation_count": row[11],
        "incoming_citation_count": row[12],
        "unresolved_citation_count": row[13],
    }
