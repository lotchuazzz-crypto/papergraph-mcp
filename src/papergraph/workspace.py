"""Persistent, versioned storage for multi-paper theorem graphs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import RLock

from papergraph.citations import build_citation_records
from papergraph.evidence import (
    EVIDENCE_EMPTY_DEPENDENCY_WARNING,
    EvidenceDocument,
    SourceSpanEvidence,
    source_span_payload,
)
from papergraph.evidence_extractors import build_pdf_evidence_document
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
from papergraph.parser import latex_project_to_evidence_document, parse_project
from papergraph.pdf import load_pdf_evidence_spans
from papergraph.project import LoadedProject


SCHEMA_VERSION = 3
_REQUIRED_TABLES = {
    "workspace_meta",
    "papers",
    "theorems",
    "theorem_refs",
    "citation_evidence",
    "source_spans",
    "results",
    "result_source_spans",
    "proofs",
    "proof_source_spans",
    "bibliography_entries",
    "local_result_mentions",
    "citation_mentions",
    "external_result_mentions",
    "evidence_edges",
    "evidence_edge_source_spans",
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
_REQUIRED_TABLE_COLUMNS = {
    "theorems": _REQUIRED_THEOREM_COLUMNS,
    "source_spans": {
        "id",
        "span_id",
        "paper_id",
        "source_type",
        "source_ref",
        "page",
        "block_index",
        "start_offset",
        "end_offset",
        "bbox_json",
        "text",
        "method",
        "confidence",
    },
    "results": {
        "result_id",
        "paper_id",
        "local_id",
        "kind",
        "raw_kind",
        "display_kind",
        "normalized_kind",
        "label",
        "visible_number",
        "title",
        "statement",
        "method",
        "confidence",
    },
    "result_source_spans": {"result_id", "span_id", "position"},
    "proofs": {
        "proof_id",
        "paper_id",
        "result_id",
        "text",
        "association_basis",
        "association_confidence",
        "method",
        "confidence",
    },
    "proof_source_spans": {"proof_id", "span_id", "position"},
    "bibliography_entries": {
        "entry_id",
        "paper_id",
        "raw_label",
        "raw_text",
        "entry_type",
        "title",
        "authors_json",
        "year",
        "arxiv_id",
        "arxiv_version",
        "doi",
        "url",
        "method",
        "confidence",
    },
    "local_result_mentions": {
        "mention_id",
        "paper_id",
        "proof_id",
        "raw_text",
        "kind",
        "visible_number",
        "target_result_id",
        "resolution_status",
        "method",
        "confidence",
    },
    "citation_mentions": {
        "mention_id",
        "paper_id",
        "proof_id",
        "raw_text",
        "raw_key",
        "entry_id",
        "resolution_status",
        "method",
        "confidence",
    },
    "external_result_mentions": {
        "mention_id",
        "paper_id",
        "proof_id",
        "citation_mention_id",
        "raw_text",
        "external_kind",
        "external_number",
        "entry_id",
        "target_paper_id",
        "resolution_status",
        "method",
        "confidence",
    },
    "evidence_edges": {
        "edge_id",
        "paper_id",
        "source_id",
        "target_id",
        "relation",
        "evidence_ids_json",
        "method",
        "confidence",
    },
    "evidence_edge_source_spans": {"edge_id", "span_id", "position"},
}

_PAPERS_TABLE_SQL = """
CREATE TABLE papers (
    paper_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (source_type IN ('local', 'arxiv', 'pdf')),
    source_ref TEXT NOT NULL,
    source_version TEXT,
    title TEXT,
    authors_json TEXT NOT NULL,
    main_file TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    parser_version TEXT NOT NULL
)
"""

_EVIDENCE_SCHEMA_SQL = """
CREATE TABLE source_spans (
    id INTEGER PRIMARY KEY,
    span_id TEXT,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('local', 'arxiv', 'pdf', 'tex')),
    source_ref TEXT NOT NULL,
    page INTEGER,
    block_index INTEGER,
    start_offset INTEGER,
    end_offset INTEGER,
    bbox_json TEXT,
    text TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL
);
CREATE TABLE results (
    result_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    local_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    raw_kind TEXT NOT NULL,
    display_kind TEXT NOT NULL,
    normalized_kind TEXT NOT NULL,
    label TEXT,
    visible_number TEXT,
    title TEXT,
    statement TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL,
    UNIQUE (paper_id, local_id)
);
CREATE TABLE result_source_spans (
    result_id TEXT NOT NULL REFERENCES results(result_id) ON DELETE CASCADE,
    span_id INTEGER NOT NULL REFERENCES source_spans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (result_id, span_id, position)
);
CREATE TABLE proofs (
    proof_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    result_id TEXT REFERENCES results(result_id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    association_basis TEXT NOT NULL,
    association_confidence REAL NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL
);
CREATE TABLE proof_source_spans (
    proof_id TEXT NOT NULL REFERENCES proofs(proof_id) ON DELETE CASCADE,
    span_id INTEGER NOT NULL REFERENCES source_spans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (proof_id, span_id, position)
);
CREATE TABLE bibliography_entries (
    entry_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    raw_label TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    title TEXT,
    authors_json TEXT NOT NULL,
    year INTEGER,
    arxiv_id TEXT,
    arxiv_version TEXT,
    doi TEXT,
    url TEXT,
    method TEXT NOT NULL,
    confidence REAL NOT NULL
);
CREATE TABLE local_result_mentions (
    mention_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    proof_id TEXT REFERENCES proofs(proof_id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    kind TEXT NOT NULL,
    visible_number TEXT,
    target_result_id TEXT REFERENCES results(result_id) ON DELETE SET NULL,
    resolution_status TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL
);
CREATE TABLE citation_mentions (
    mention_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    proof_id TEXT REFERENCES proofs(proof_id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    raw_key TEXT NOT NULL,
    entry_id TEXT REFERENCES bibliography_entries(entry_id) ON DELETE SET NULL,
    resolution_status TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL
);
CREATE TABLE external_result_mentions (
    mention_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    proof_id TEXT REFERENCES proofs(proof_id) ON DELETE CASCADE,
    citation_mention_id TEXT REFERENCES citation_mentions(mention_id) ON DELETE SET NULL,
    raw_text TEXT NOT NULL,
    external_kind TEXT NOT NULL,
    external_number TEXT,
    entry_id TEXT REFERENCES bibliography_entries(entry_id) ON DELETE SET NULL,
    target_paper_id TEXT,
    resolution_status TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL
);
CREATE TABLE evidence_edges (
    edge_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence REAL NOT NULL
);
CREATE TABLE evidence_edge_source_spans (
    edge_id TEXT NOT NULL REFERENCES evidence_edges(edge_id) ON DELETE CASCADE,
    span_id INTEGER NOT NULL REFERENCES source_spans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (edge_id, span_id, position)
);
CREATE INDEX source_spans_paper_location
    ON source_spans(paper_id, source_type, source_ref, page, block_index, id);
CREATE INDEX results_paper_kind ON results(paper_id, normalized_kind, result_id);
CREATE INDEX result_spans_result ON result_source_spans(result_id, position);
CREATE INDEX proof_result ON proofs(result_id);
CREATE INDEX proof_spans_proof ON proof_source_spans(proof_id, position);
CREATE INDEX bibliography_entries_paper ON bibliography_entries(paper_id, raw_label);
CREATE INDEX local_mentions_proof ON local_result_mentions(proof_id, mention_id);
CREATE INDEX citation_mentions_proof ON citation_mentions(proof_id, mention_id);
CREATE INDEX external_mentions_proof ON external_result_mentions(proof_id, mention_id);
CREATE INDEX evidence_edges_source ON evidence_edges(source_id, relation, edge_id);
CREATE INDEX evidence_edges_target ON evidence_edges(target_id, relation, edge_id);
"""

_SCHEMA_SQL = """
CREATE TABLE workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
""" + _PAPERS_TABLE_SQL + """;
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
""" + _EVIDENCE_SCHEMA_SQL + """
INSERT INTO workspace_meta (key, value) VALUES ('schema_version', '3');
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
        if schema_version == 2 and SCHEMA_VERSION == 3:
            Workspace._migrate_v2_to_v3(connection)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            schema_version = 3
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
        for table, required_columns in _REQUIRED_TABLE_COLUMNS.items():
            columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            missing_columns = sorted(required_columns - columns)
            if missing_columns:
                raise WorkspaceSchemaError(
                    f"Workspace schema is missing required {table} columns: "
                    + ", ".join(missing_columns)
                )

    @staticmethod
    def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
        was_enforcing_foreign_keys = connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute("BEGIN")
            connection.execute(_PAPERS_TABLE_SQL.replace("papers", "papers_new", 1))
            connection.execute(
                """
                INSERT INTO papers_new (
                    paper_id, source_type, source_ref, source_version, title,
                    authors_json, main_file, imported_at, parser_version
                )
                SELECT
                    paper_id, source_type, source_ref, source_version, title,
                    authors_json, main_file, imported_at, parser_version
                FROM papers
                """
            )
            connection.execute("DROP TABLE papers")
            connection.execute("ALTER TABLE papers_new RENAME TO papers")
            _execute_sql_script(connection, _EVIDENCE_SCHEMA_SQL)
            connection.execute(
                "UPDATE workspace_meta SET value = ? WHERE key = 'schema_version'",
                (str(SCHEMA_VERSION),),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            if was_enforcing_foreign_keys:
                connection.execute("PRAGMA foreign_keys = ON")

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise WorkspaceSchemaError(
                "Workspace schema migration left foreign key violations"
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
        evidence_document = latex_project_to_evidence_document(
            normalized_paper_id,
            source_type,
            source_ref,
            source_version,
            project,
        )
        _validate_evidence_document(evidence_document, normalized_paper_id)
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
            _insert_evidence_document(self._connection, evidence_document)
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
    def import_pdf(
        self,
        path: str | Path,
        paper_id: str,
    ) -> WorkspaceImportResult:
        """Atomically add or replace one born-digital PDF paper."""

        normalized_paper_id = normalize_paper_id(paper_id)
        if not normalized_paper_id.startswith("local:"):
            raise ValueError("PDF paper ids must use the local: prefix in v0.5")

        resolved = Path(path).expanduser().resolve()
        source_ref = str(resolved)
        spans = load_pdf_evidence_spans(resolved, normalized_paper_id)
        document = build_pdf_evidence_document(
            normalized_paper_id,
            source_ref,
            spans,
        )
        return self.import_evidence_document(
            replace(document, main_file=resolved.name)
        )

    @_synchronized
    def import_evidence_document(
        self,
        document: EvidenceDocument,
    ) -> WorkspaceImportResult:
        """Atomically add or replace one extracted evidence document."""

        normalized_paper_id = normalize_paper_id(document.paper_id)
        if document.source_type not in {"local", "arxiv", "pdf"}:
            raise ValueError(f"Invalid source type: {document.source_type!r}")
        if document.source_type == "pdf":
            if normalized_paper_id.split(":", 1)[0] != "local":
                raise ValueError("PDF evidence imports must use a local: paper id")
        elif document.source_type != normalized_paper_id.split(":", 1)[0]:
            raise ValueError(
                f"source type {document.source_type!r} does not match "
                f"paper id {normalized_paper_id!r}"
            )

        _validate_evidence_document(document, normalized_paper_id)

        imported_at = datetime.now(timezone.utc).isoformat()
        authors_json = json.dumps(list(document.authors), ensure_ascii=False)
        unresolved_count = _unresolved_evidence_mention_count(document)

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
                    document.source_type,
                    document.source_ref,
                    document.source_version,
                    document.title,
                    authors_json,
                    document.main_file,
                    imported_at,
                    _parser_version(),
                ),
            )

            _insert_evidence_document(self._connection, document)

        return WorkspaceImportResult(
            paper_id=normalized_paper_id,
            theorem_count=len(document.results),
            citation_count=len(document.citation_mentions),
            unresolved_citation_count=unresolved_count,
            result_count=len(document.results),
            proof_count=len(document.proofs),
            bibliography_entry_count=len(document.bibliography_entries),
            local_mention_count=len(document.local_result_mentions),
            external_mention_count=len(document.external_result_mentions),
            unresolved_count=unresolved_count,
            warnings=document.warnings,
        )

    @_synchronized
    def list_results(
        self,
        paper_id: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Return stored evidence results in stable order."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("Result limit must be an integer from 1 through 100")

        conditions: list[str] = []
        parameters: list[str | int] = []
        if paper_id is not None:
            conditions.append("results.paper_id = ?")
            parameters.append(normalize_paper_id(paper_id))
        if kind is not None:
            conditions.append("(results.kind = ? OR results.normalized_kind = ?)")
            parameters.extend([kind, kind])
        parameters.append(limit)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = self._connection.execute(
            f"""
            SELECT
                results.result_id, results.paper_id, results.local_id,
                results.kind, results.raw_kind, results.display_kind,
                results.normalized_kind, results.label, results.visible_number,
                results.title, results.statement, results.method,
                results.confidence, papers.source_type
            FROM results
            JOIN papers ON papers.paper_id = results.paper_id
            {where_clause}
            ORDER BY results.paper_id, results.result_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return [
            {
                **_result_from_row(row),
                "source_type": row[13],
                "first_location": self._first_result_location(row[0]),
            }
            for row in rows
        ]

    @_synchronized
    def get_result(self, result_id: str) -> dict:
        """Return one evidence result with source spans."""

        row = self._connection.execute(
            """
            SELECT
                result_id, paper_id, local_id, kind, raw_kind, display_kind,
                normalized_kind, label, visible_number, title, statement,
                method, confidence
            FROM results
            WHERE result_id = ?
            """,
            (result_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown result id: {result_id}")
        return {
            **_result_from_row(row),
            "spans": self._source_spans_for_result(result_id),
        }

    @_synchronized
    def get_result_proof(self, result_id: str) -> dict:
        """Return known and inferred proof evidence for one result."""

        self._ensure_result_exists(result_id)
        proof = self._proof_for_result(result_id)
        if proof is None:
            return {
                "known": {},
                "inferred": [],
                "unresolved": {"proof": "not_found"},
                "warnings": ["No proof evidence was found for this result."],
            }
        return {
            "known": {"proof": proof},
            "inferred": [
                {
                    "basis": proof["association_basis"],
                    "confidence": proof["association_confidence"],
                    "method": proof["method"],
                }
            ],
            "unresolved": {},
            "warnings": [],
        }

    @_synchronized
    def get_proof_dependencies(
        self,
        result_id: str,
        recursive: bool = False,
    ) -> dict:
        """Return dependency evidence extracted from the associated proof."""

        self._ensure_result_exists(result_id)
        proof = self._proof_for_result(result_id)
        if proof is None:
            return {
                "result_id": result_id,
                "recursive": recursive,
                "known": {
                    "resolved_local_results": [],
                    "resolved_external_results": [],
                    "external_result_mentions": [],
                },
                "inferred": [],
                "unresolved": {"proof": "not_found"},
                "warnings": ["No proof evidence was found for this result."],
            }

        proof_ids = [proof["proof_id"]]
        if recursive:
            proof_ids.extend(self._recursive_dependency_proof_ids(result_id))

        resolved_local_result_ids: list[str] = []
        unresolved_local = []
        unresolved_citation = []
        unresolved_external = []
        resolved_external = []
        known_external_mentions = []
        for proof_id in proof_ids:
            local_rows = self._connection.execute(
                """
                SELECT
                    mention_id, paper_id, proof_id, raw_text, kind,
                    visible_number, target_result_id, resolution_status,
                    method, confidence
                FROM local_result_mentions
                WHERE proof_id = ?
                ORDER BY mention_id
                """,
                (proof_id,),
            ).fetchall()
            for row in local_rows:
                mention = _local_result_mention_from_row(row)
                mention = self._with_evidence_trace(
                    mention,
                    mention["mention_id"],
                    "local_result_mention",
                )
                if mention["target_result_id"] and _is_resolved(
                    mention["resolution_status"]
                ):
                    if mention["target_result_id"] not in resolved_local_result_ids:
                        resolved_local_result_ids.append(mention["target_result_id"])
                else:
                    unresolved_local.append(mention)

            for row in self._connection.execute(
                """
                SELECT
                    mention_id, paper_id, proof_id, raw_text, raw_key,
                    entry_id, resolution_status, method, confidence
                FROM citation_mentions
                WHERE proof_id = ?
                ORDER BY mention_id
                """,
                (proof_id,),
            ):
                mention = _citation_mention_from_row(row)
                mention = self._with_evidence_trace(
                    mention,
                    mention["mention_id"],
                    "citation_mention",
                )
                if not mention["entry_id"] or not _is_resolved(
                    mention["resolution_status"]
                ):
                    unresolved_citation.append(mention)

            for row in self._connection.execute(
                """
                SELECT
                    mention_id, paper_id, proof_id, citation_mention_id,
                    raw_text, external_kind, external_number, entry_id,
                    target_paper_id, resolution_status, method, confidence
                FROM external_result_mentions
                WHERE proof_id = ?
                ORDER BY mention_id
                """,
                (proof_id,),
            ):
                mention = _external_result_mention_from_row(row)
                mention = self._with_evidence_trace(
                    mention,
                    mention["mention_id"],
                    "external_result_mention",
                )
                if mention["target_paper_id"] and _is_resolved(
                    mention["resolution_status"]
                ):
                    resolved_external.append(mention)
                    known_external_mentions.append(mention)
                elif _is_known_external_result_mention(mention):
                    known_external_mentions.append(mention)
                else:
                    unresolved_external.append(mention)

        warnings = []
        if not resolved_local_result_ids and not known_external_mentions:
            warnings.append(EVIDENCE_EMPTY_DEPENDENCY_WARNING)
        return {
            "result_id": result_id,
            "recursive": recursive,
            "known": {
                "resolved_local_results": [
                    self.get_result(resolved_id)
                    for resolved_id in resolved_local_result_ids
                ],
                "resolved_external_results": resolved_external,
                "external_result_mentions": known_external_mentions,
            },
            "inferred": [
                {
                    "basis": proof["association_basis"],
                    "confidence": proof["association_confidence"],
                    "method": proof["method"],
                }
            ],
            "unresolved": {
                "local_result_mentions": unresolved_local,
                "citation_mentions": unresolved_citation,
                "external_result_mentions": unresolved_external,
            },
            "warnings": warnings,
        }

    @_synchronized
    def get_external_result_mentions(self, result_id: str) -> list[dict]:
        """Return external result mentions in a result's associated proof."""

        self._ensure_result_exists(result_id)
        proof = self._proof_for_result(result_id)
        if proof is None:
            return []
        rows = self._connection.execute(
            """
            SELECT
                mention_id, paper_id, proof_id, citation_mention_id,
                raw_text, external_kind, external_number, entry_id,
                target_paper_id, resolution_status, method, confidence
            FROM external_result_mentions
            WHERE proof_id = ?
            ORDER BY mention_id
            """,
            (proof["proof_id"],),
        ).fetchall()
        return [
            self._with_evidence_trace(
                _external_result_mention_from_row(row),
                row[0],
                "external_result_mention",
            )
            for row in rows
        ]

    @_synchronized
    def get_evidence(self, node_or_edge_id: str) -> dict:
        """Return metadata and spans for a stored evidence node or edge."""

        lookups = (
            ("result", "results", "result_id", _result_from_row),
            ("proof", "proofs", "proof_id", _proof_from_row),
            (
                "bibliography_entry",
                "bibliography_entries",
                "entry_id",
                _bibliography_entry_from_row,
            ),
            (
                "local_result_mention",
                "local_result_mentions",
                "mention_id",
                _local_result_mention_from_row,
            ),
            (
                "citation_mention",
                "citation_mentions",
                "mention_id",
                _citation_mention_from_row,
            ),
            (
                "external_result_mention",
                "external_result_mentions",
                "mention_id",
                _external_result_mention_from_row,
            ),
            ("edge", "evidence_edges", "edge_id", _evidence_edge_from_row),
        )
        for evidence_type, table, key_column, serializer in lookups:
            row = self._connection.execute(
                f"SELECT * FROM {table} WHERE {key_column} = ?",
                (node_or_edge_id,),
            ).fetchone()
            if row is not None:
                metadata = serializer(row)
                spans, span_trail = self._source_spans_and_trail_for_evidence(
                    evidence_type,
                    node_or_edge_id,
                    metadata,
                )
                return {
                    "id": node_or_edge_id,
                    "type": evidence_type,
                    "metadata": metadata,
                    "spans": spans,
                    "span_trail": span_trail,
                }
        raise KeyError(f"Unknown evidence id: {node_or_edge_id}")

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
    def _ensure_result_exists(self, result_id: str) -> None:
        if self._connection.execute(
            "SELECT 1 FROM results WHERE result_id = ?",
            (result_id,),
        ).fetchone() is None:
            raise KeyError(f"Unknown result id: {result_id}")

    @_synchronized
    def _first_result_location(self, result_id: str) -> dict | None:
        spans = self._source_spans_for_result(result_id)
        if not spans:
            return None
        first = spans[0]
        return {
            "source_ref": first["source_ref"],
            "page": first["page"],
            "block_index": first["block_index"],
            "start_offset": first["start_offset"],
            "end_offset": first["end_offset"],
            "bbox": first["bbox"],
        }

    @_synchronized
    def _proof_for_result(self, result_id: str) -> dict | None:
        row = self._connection.execute(
            """
            SELECT
                proof_id, paper_id, result_id, text, association_basis,
                association_confidence, method, confidence
            FROM proofs
            WHERE result_id = ?
            ORDER BY proof_id
            LIMIT 1
            """,
            (result_id,),
        ).fetchone()
        if row is None:
            return None
        proof = _proof_from_row(row)
        proof["spans"] = self._source_spans_for_proof(proof["proof_id"])
        return proof

    @_synchronized
    def _source_spans_for_result(self, result_id: str) -> list[dict]:
        rows = self._connection.execute(
            """
            SELECT
                source_spans.span_id, source_spans.paper_id,
                source_spans.source_type, source_spans.source_ref,
                source_spans.page, source_spans.block_index,
                source_spans.start_offset, source_spans.end_offset,
                source_spans.bbox_json, source_spans.text,
                source_spans.method, source_spans.confidence
            FROM result_source_spans
            JOIN source_spans ON source_spans.id = result_source_spans.span_id
            WHERE result_source_spans.result_id = ?
            ORDER BY result_source_spans.position, source_spans.id
            """,
            (result_id,),
        ).fetchall()
        return [_source_span_from_row(row) for row in rows]

    @_synchronized
    def _source_spans_for_proof(self, proof_id: str) -> list[dict]:
        rows = self._connection.execute(
            """
            SELECT
                source_spans.span_id, source_spans.paper_id,
                source_spans.source_type, source_spans.source_ref,
                source_spans.page, source_spans.block_index,
                source_spans.start_offset, source_spans.end_offset,
                source_spans.bbox_json, source_spans.text,
                source_spans.method, source_spans.confidence
            FROM proof_source_spans
            JOIN source_spans ON source_spans.id = proof_source_spans.span_id
            WHERE proof_source_spans.proof_id = ?
            ORDER BY proof_source_spans.position, source_spans.id
            """,
            (proof_id,),
        ).fetchall()
        return [_source_span_from_row(row) for row in rows]

    @_synchronized
    def _source_spans_for_edge(self, edge_id: str) -> list[dict]:
        rows = self._connection.execute(
            """
            SELECT
                source_spans.span_id, source_spans.paper_id,
                source_spans.source_type, source_spans.source_ref,
                source_spans.page, source_spans.block_index,
                source_spans.start_offset, source_spans.end_offset,
                source_spans.bbox_json, source_spans.text,
                source_spans.method, source_spans.confidence
            FROM evidence_edge_source_spans
            JOIN source_spans ON source_spans.id = evidence_edge_source_spans.span_id
            WHERE evidence_edge_source_spans.edge_id = ?
            ORDER BY evidence_edge_source_spans.position, source_spans.id
            """,
            (edge_id,),
        ).fetchall()
        return [_source_span_from_row(row) for row in rows]

    @_synchronized
    def _source_spans_for_source_span_id(self, span_id: str) -> list[dict]:
        rows = self._connection.execute(
            """
            SELECT
                span_id, paper_id, source_type, source_ref, page,
                block_index, start_offset, end_offset, bbox_json, text,
                method, confidence
            FROM source_spans
            WHERE span_id = ?
            ORDER BY paper_id, source_type, source_ref, page, block_index, id
            """,
            (span_id,),
        ).fetchall()
        return [_source_span_from_row(row) for row in rows]

    @_synchronized
    def _with_evidence_trace(
        self,
        metadata: dict,
        evidence_id: str,
        evidence_type: str,
    ) -> dict:
        spans, span_trail = self._source_spans_and_trail_for_evidence(
            evidence_type,
            evidence_id,
            metadata,
        )
        return {
            **metadata,
            "evidence_id": evidence_id,
            "spans": spans,
            "span_trail": span_trail,
        }

    @_synchronized
    def _source_spans_and_trail_for_evidence(
        self,
        evidence_type: str,
        evidence_id: str,
        metadata: dict,
    ) -> tuple[list[dict], list[dict]]:
        if evidence_type == "result":
            return self._source_spans_for_result(evidence_id), []
        if evidence_type == "proof":
            return self._source_spans_for_proof(evidence_id), []
        if evidence_type == "local_result_mention":
            return self._source_spans_and_trail_for_parent_proof(
                metadata["proof_id"],
            )
        if evidence_type == "citation_mention":
            return self._source_spans_and_trail_for_parent_proof(
                metadata["proof_id"],
            )
        if evidence_type == "external_result_mention":
            if metadata["proof_id"]:
                return self._source_spans_and_trail_for_parent_proof(
                    metadata["proof_id"],
                )
            if metadata["citation_mention_id"]:
                return self._source_spans_and_trail_for_citation_mention(
                    metadata["citation_mention_id"],
                    relation="parent_citation_mention",
                )
            return [], []
        if evidence_type == "bibliography_entry":
            return self._source_spans_and_trail_for_bibliography_entry(evidence_id)
        if evidence_type == "edge":
            return (
                self._source_spans_for_edge(evidence_id),
                self._span_trail_for_edge(metadata["evidence_ids"]),
            )
        return [], []

    @_synchronized
    def _source_spans_and_trail_for_parent_proof(
        self,
        proof_id: str | None,
        prefix: list[dict] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        span_trail = list(prefix or [])
        if proof_id is None:
            return [], span_trail
        return (
            self._source_spans_for_proof(proof_id),
            [
                *span_trail,
                {
                    "evidence_id": proof_id,
                    "evidence_type": "proof",
                    "relation": "parent_proof",
                },
            ],
        )

    @_synchronized
    def _source_spans_and_trail_for_citation_mention(
        self,
        mention_id: str,
        relation: str,
    ) -> tuple[list[dict], list[dict]]:
        row = self._connection.execute(
            """
            SELECT proof_id
            FROM citation_mentions
            WHERE mention_id = ?
            """,
            (mention_id,),
        ).fetchone()
        if row is None:
            return [], []
        return self._source_spans_and_trail_for_parent_proof(
            row[0],
            prefix=[
                {
                    "evidence_id": mention_id,
                    "evidence_type": "citation_mention",
                    "relation": relation,
                }
            ],
        )

    @_synchronized
    def _source_spans_and_trail_for_bibliography_entry(
        self,
        entry_id: str,
    ) -> tuple[list[dict], list[dict]]:
        direct_spans = self._source_spans_for_source_span_id(entry_id)
        if direct_spans:
            return direct_spans, []

        row = self._connection.execute(
            """
            SELECT mention_id, proof_id
            FROM citation_mentions
            WHERE entry_id = ? AND proof_id IS NOT NULL
            ORDER BY mention_id
            LIMIT 1
            """,
            (entry_id,),
        ).fetchone()
        if row is not None:
            return self._source_spans_and_trail_for_parent_proof(
                row[1],
                prefix=[
                    {
                        "evidence_id": row[0],
                        "evidence_type": "citation_mention",
                        "relation": "referenced_by_citation_mention",
                    }
                ],
            )

        row = self._connection.execute(
            """
            SELECT mention_id, proof_id
            FROM external_result_mentions
            WHERE entry_id = ? AND proof_id IS NOT NULL
            ORDER BY mention_id
            LIMIT 1
            """,
            (entry_id,),
        ).fetchone()
        if row is not None:
            return self._source_spans_and_trail_for_parent_proof(
                row[1],
                prefix=[
                    {
                        "evidence_id": row[0],
                        "evidence_type": "external_result_mention",
                        "relation": "referenced_by_external_result_mention",
                    }
                ],
            )
        return [], []

    @_synchronized
    def _span_trail_for_edge(self, evidence_ids: list[str]) -> list[dict]:
        span_trail = []
        for evidence_id in evidence_ids:
            evidence = self._evidence_metadata_for_id(evidence_id)
            if evidence is None:
                continue
            evidence_type, metadata = evidence
            span_trail.append(
                {
                    "evidence_id": evidence_id,
                    "evidence_type": evidence_type,
                    "relation": "edge_evidence",
                }
            )
            if evidence_type == "edge":
                continue
            _, inherited_trail = self._source_spans_and_trail_for_evidence(
                evidence_type,
                evidence_id,
                metadata,
            )
            span_trail.extend(inherited_trail)
        return _dedupe_span_trail(span_trail)

    @_synchronized
    def _evidence_metadata_for_id(self, evidence_id: str) -> tuple[str, dict] | None:
        lookups = (
            ("result", "results", "result_id", _result_from_row),
            ("proof", "proofs", "proof_id", _proof_from_row),
            (
                "bibliography_entry",
                "bibliography_entries",
                "entry_id",
                _bibliography_entry_from_row,
            ),
            (
                "local_result_mention",
                "local_result_mentions",
                "mention_id",
                _local_result_mention_from_row,
            ),
            (
                "citation_mention",
                "citation_mentions",
                "mention_id",
                _citation_mention_from_row,
            ),
            (
                "external_result_mention",
                "external_result_mentions",
                "mention_id",
                _external_result_mention_from_row,
            ),
            ("edge", "evidence_edges", "edge_id", _evidence_edge_from_row),
        )
        for evidence_type, table, key_column, serializer in lookups:
            row = self._connection.execute(
                f"SELECT * FROM {table} WHERE {key_column} = ?",
                (evidence_id,),
            ).fetchone()
            if row is not None:
                return evidence_type, serializer(row)
        return None

    @_synchronized
    def _recursive_dependency_proof_ids(self, result_id: str) -> list[str]:
        proof_ids: list[str] = []
        visited_results = {result_id}
        queue = [result_id]
        while queue:
            current_result_id = queue.pop(0)
            rows = self._connection.execute(
                """
                SELECT DISTINCT local_result_mentions.target_result_id
                FROM proofs
                JOIN local_result_mentions
                  ON local_result_mentions.proof_id = proofs.proof_id
                WHERE proofs.result_id = ?
                  AND local_result_mentions.target_result_id IS NOT NULL
                  AND local_result_mentions.resolution_status IN (
                      'resolved',
                      'resolved_candidate'
                  )
                ORDER BY local_result_mentions.target_result_id
                """,
                (current_result_id,),
            ).fetchall()
            for (target_result_id,) in rows:
                if target_result_id in visited_results:
                    continue
                visited_results.add(target_result_id)
                queue.append(target_result_id)
                proof = self._proof_for_result(target_result_id)
                if proof is not None:
                    proof_ids.append(proof["proof_id"])
        return proof_ids

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


def _execute_sql_script(connection: sqlite3.Connection, script: str) -> None:
    for statement in script.split(";"):
        stripped = statement.strip()
        if stripped:
            connection.execute(stripped)


def _insert_evidence_document(
    connection: sqlite3.Connection,
    document: EvidenceDocument,
) -> None:
    normalized_paper_id = normalize_paper_id(document.paper_id)

    span_ids: dict[int, int] = {}
    source_span_ids_by_span_id: dict[str, list[int]] = {}
    for index, span in enumerate(document.spans):
        cursor = connection.execute(
            """
            INSERT INTO source_spans (
                span_id, paper_id, source_type, source_ref, page,
                block_index, start_offset, end_offset, bbox_json, text,
                method, confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                span.span_id,
                normalized_paper_id,
                span.source_type,
                span.source_ref,
                span.page,
                span.block_index,
                span.start_offset,
                span.end_offset,
                json.dumps(list(span.bbox)) if span.bbox is not None else None,
                span.text,
                span.method,
                span.confidence,
            ),
        )
        span_ids[index] = int(cursor.lastrowid)
        if span.span_id:
            source_span_ids_by_span_id.setdefault(span.span_id, []).append(
                span_ids[index]
            )

    connection.executemany(
        """
        INSERT INTO results (
            result_id, paper_id, local_id, kind, raw_kind,
            display_kind, normalized_kind, label, visible_number, title,
            statement, method, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                result.result_id,
                normalized_paper_id,
                result.local_id,
                result.kind,
                result.raw_kind,
                result.display_kind,
                result.normalized_kind,
                result.label,
                result.visible_number,
                result.title,
                result.statement,
                result.method,
                result.confidence,
            )
            for result in document.results
        ),
    )
    result_source_span_ids: dict[str, list[int]] = {}
    result_source_span_rows = []
    for result in document.results:
        linked_span_ids = [
            span_ids[span_index] for span_index in result.span_indices
        ]
        result_source_span_ids[result.result_id] = linked_span_ids
        result_source_span_rows.extend(
            (result.result_id, span_id, position)
            for position, span_id in enumerate(linked_span_ids)
        )
    connection.executemany(
        """
        INSERT INTO result_source_spans (result_id, span_id, position)
        VALUES (?, ?, ?)
        """,
        result_source_span_rows,
    )
    connection.executemany(
        """
        INSERT INTO proofs (
            proof_id, paper_id, result_id, text, association_basis,
            association_confidence, method, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                proof.proof_id,
                normalized_paper_id,
                proof.result_id,
                proof.text,
                proof.association_basis,
                proof.association_confidence,
                proof.method,
                proof.confidence,
            )
            for proof in document.proofs
        ),
    )
    proof_source_span_ids: dict[str, list[int]] = {}
    proof_source_span_rows = []
    for proof in document.proofs:
        linked_span_ids = [
            span_ids[span_index] for span_index in proof.span_indices
        ]
        proof_source_span_ids[proof.proof_id] = linked_span_ids
        proof_source_span_rows.extend(
            (proof.proof_id, span_id, position)
            for position, span_id in enumerate(linked_span_ids)
        )
    connection.executemany(
        """
        INSERT INTO proof_source_spans (proof_id, span_id, position)
        VALUES (?, ?, ?)
        """,
        proof_source_span_rows,
    )
    connection.executemany(
        """
        INSERT INTO bibliography_entries (
            entry_id, paper_id, raw_label, raw_text, entry_type, title,
            authors_json, year, arxiv_id, arxiv_version, doi, url,
            method, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                entry.entry_id,
                normalized_paper_id,
                entry.raw_label,
                entry.raw_text,
                entry.entry_type,
                entry.title,
                json.dumps(list(entry.authors), ensure_ascii=False),
                entry.year,
                entry.arxiv_id,
                entry.arxiv_version,
                entry.doi,
                entry.url,
                entry.method,
                entry.confidence,
            )
            for entry in document.bibliography_entries
        ),
    )
    connection.executemany(
        """
        INSERT INTO local_result_mentions (
            mention_id, paper_id, proof_id, raw_text, kind,
            visible_number, target_result_id, resolution_status,
            method, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                mention.mention_id,
                normalized_paper_id,
                mention.proof_id,
                mention.raw_text,
                mention.kind,
                mention.visible_number,
                mention.target_result_id,
                mention.resolution_status,
                mention.method,
                mention.confidence,
            )
            for mention in document.local_result_mentions
        ),
    )
    connection.executemany(
        """
        INSERT INTO citation_mentions (
            mention_id, paper_id, proof_id, raw_text, raw_key,
            entry_id, resolution_status, method, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                mention.mention_id,
                normalized_paper_id,
                mention.proof_id,
                mention.raw_text,
                mention.raw_key,
                mention.entry_id,
                mention.resolution_status,
                mention.method,
                mention.confidence,
            )
            for mention in document.citation_mentions
        ),
    )
    connection.executemany(
        """
        INSERT INTO external_result_mentions (
            mention_id, paper_id, proof_id, citation_mention_id,
            raw_text, external_kind, external_number, entry_id,
            target_paper_id, resolution_status, method, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                mention.mention_id,
                normalized_paper_id,
                mention.proof_id,
                mention.citation_mention_id,
                mention.raw_text,
                mention.external_kind,
                mention.external_number,
                mention.entry_id,
                mention.target_paper_id,
                mention.resolution_status,
                mention.method,
                mention.confidence,
            )
            for mention in document.external_result_mentions
        ),
    )
    connection.executemany(
        """
        INSERT INTO evidence_edges (
            edge_id, paper_id, source_id, target_id, relation,
            evidence_ids_json, method, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                edge.edge_id,
                normalized_paper_id,
                edge.source_id,
                edge.target_id,
                edge.relation,
                json.dumps(list(edge.evidence_ids), ensure_ascii=False),
                edge.method,
                edge.confidence,
            )
            for edge in document.edges
        ),
    )
    source_span_ids_by_evidence_id = _source_span_ids_by_evidence_id(
        document=document,
        source_span_ids_by_span_id=source_span_ids_by_span_id,
        result_source_span_ids=result_source_span_ids,
        proof_source_span_ids=proof_source_span_ids,
    )
    edge_source_span_rows = []
    for edge in document.edges:
        seen_span_ids = set()
        edge_position = 0
        for evidence_id in edge.evidence_ids:
            for span_id in source_span_ids_by_evidence_id.get(
                evidence_id,
                (),
            ):
                if span_id in seen_span_ids:
                    continue
                seen_span_ids.add(span_id)
                edge_source_span_rows.append(
                    (edge.edge_id, span_id, edge_position)
                )
                edge_position += 1
    connection.executemany(
        """
        INSERT INTO evidence_edge_source_spans (
            edge_id, span_id, position
        ) VALUES (?, ?, ?)
        """,
        edge_source_span_rows,
    )


def _source_span_ids_by_evidence_id(
    *,
    document: EvidenceDocument,
    source_span_ids_by_span_id: dict[str, list[int]],
    result_source_span_ids: dict[str, list[int]],
    proof_source_span_ids: dict[str, list[int]],
) -> dict[str, list[int]]:
    source_span_ids: dict[str, list[int]] = {}
    source_span_ids.update(source_span_ids_by_span_id)
    source_span_ids.update(result_source_span_ids)
    source_span_ids.update(proof_source_span_ids)

    for mention in document.local_result_mentions:
        source_span_ids[mention.mention_id] = _copy_source_span_ids(
            proof_source_span_ids.get(mention.proof_id or ""),
        )

    for mention in document.citation_mentions:
        source_span_ids[mention.mention_id] = _copy_source_span_ids(
            proof_source_span_ids.get(mention.proof_id or ""),
        )

    for mention in document.external_result_mentions:
        inherited_span_ids = proof_source_span_ids.get(mention.proof_id or "")
        if not inherited_span_ids and mention.citation_mention_id:
            inherited_span_ids = source_span_ids.get(mention.citation_mention_id)
        source_span_ids[mention.mention_id] = _copy_source_span_ids(
            inherited_span_ids,
        )

    for entry in document.bibliography_entries:
        source_span_ids.setdefault(entry.entry_id, [])

    for mention in document.citation_mentions:
        if mention.entry_id and not source_span_ids.get(mention.entry_id):
            source_span_ids[mention.entry_id] = _copy_source_span_ids(
                source_span_ids.get(mention.mention_id),
            )

    for mention in document.external_result_mentions:
        if mention.entry_id and not source_span_ids.get(mention.entry_id):
            source_span_ids[mention.entry_id] = _copy_source_span_ids(
                source_span_ids.get(mention.mention_id),
            )

    return source_span_ids


def _copy_source_span_ids(span_ids: list[int] | None) -> list[int]:
    return list(span_ids or [])


def _dedupe_span_trail(span_trail: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for item in span_trail:
        key = (item["evidence_id"], item["evidence_type"], item["relation"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _validate_document_paper_ids(
    document: EvidenceDocument,
    normalized_paper_id: str,
) -> None:
    for item in (
        *document.spans,
        *document.results,
        *document.proofs,
        *document.bibliography_entries,
        *document.local_result_mentions,
        *document.citation_mentions,
        *document.external_result_mentions,
        *document.edges,
    ):
        if normalize_paper_id(item.paper_id) != normalized_paper_id:
            raise ValueError(
                f"Evidence item paper id {item.paper_id!r} does not match "
                f"document paper id {normalized_paper_id!r}"
            )


def _validate_evidence_document(
    document: EvidenceDocument,
    normalized_paper_id: str,
) -> None:
    _validate_document_paper_ids(document, normalized_paper_id)
    _validate_span_indices(
        "result",
        ((result.result_id, result.span_indices) for result in document.results),
        len(document.spans),
    )
    _validate_span_indices(
        "proof",
        ((proof.proof_id, proof.span_indices) for proof in document.proofs),
        len(document.spans),
    )
    _validate_evidence_traceability(document)


def _validate_span_indices(
    item_kind: str,
    items: object,
    span_count: int,
) -> None:
    for item_id, span_indices in items:
        if not span_indices:
            raise ValueError(
                f"{item_kind} {item_id!r} must reference at least one source span"
            )
        for span_index in span_indices:
            if not isinstance(span_index, int) or not 0 <= span_index < span_count:
                raise ValueError(
                    f"{item_kind} {item_id!r} references unknown span index "
                    f"{span_index!r}"
                )


def _validate_evidence_traceability(document: EvidenceDocument) -> None:
    span_ids = {
        span.span_id
        for span in document.spans
        if span.span_id is not None
    }
    result_span_counts = {
        result.result_id: len(result.span_indices)
        for result in document.results
    }
    proof_span_counts = {
        proof.proof_id: len(proof.span_indices)
        for proof in document.proofs
    }
    bibliography_ids = {entry.entry_id for entry in document.bibliography_entries}
    citation_mention_ids = {
        mention.mention_id
        for mention in document.citation_mentions
    }

    traceable_result_ids = {
        result_id
        for result_id, span_count in result_span_counts.items()
        if span_count > 0
    }
    traceable_proof_ids = {
        proof_id
        for proof_id, span_count in proof_span_counts.items()
        if span_count > 0
    }
    traceable_mention_ids: set[str] = set()
    referenced_bibliography_ids: set[str] = set()

    def require_traceable_parent_proof(mention_id: str, proof_id: str | None) -> None:
        if proof_id is None:
            raise ValueError(
                f"mention {mention_id!r} is untraceable: missing parent proof"
            )
        if proof_id not in proof_span_counts:
            raise ValueError(
                f"mention {mention_id!r} is untraceable: unknown parent proof "
                f"{proof_id!r}"
            )
        if proof_id not in traceable_proof_ids:
            raise ValueError(
                f"mention {mention_id!r} is untraceable: parent proof "
                f"{proof_id!r} has no source spans"
            )

    for mention in document.local_result_mentions:
        require_traceable_parent_proof(mention.mention_id, mention.proof_id)
        traceable_mention_ids.add(mention.mention_id)

    for mention in document.citation_mentions:
        require_traceable_parent_proof(mention.mention_id, mention.proof_id)
        traceable_mention_ids.add(mention.mention_id)
        if mention.entry_id is not None:
            if mention.entry_id not in bibliography_ids:
                raise ValueError(
                    f"mention {mention.mention_id!r} references unknown "
                    f"bibliography entry {mention.entry_id!r}"
                )
            referenced_bibliography_ids.add(mention.entry_id)

    for mention in document.external_result_mentions:
        if mention.citation_mention_id is not None:
            if mention.citation_mention_id not in citation_mention_ids:
                raise ValueError(
                    f"mention {mention.mention_id!r} references unknown citation "
                    f"mention {mention.citation_mention_id!r}"
                )
        if mention.proof_id is not None:
            require_traceable_parent_proof(mention.mention_id, mention.proof_id)
        elif (
            mention.citation_mention_id is None
            or mention.citation_mention_id not in traceable_mention_ids
        ):
            raise ValueError(
                f"mention {mention.mention_id!r} is untraceable: missing parent "
                "proof or traceable citation mention"
            )
        traceable_mention_ids.add(mention.mention_id)
        if mention.entry_id is not None:
            if mention.entry_id not in bibliography_ids:
                raise ValueError(
                    f"mention {mention.mention_id!r} references unknown "
                    f"bibliography entry {mention.entry_id!r}"
                )
            referenced_bibliography_ids.add(mention.entry_id)

    traceable_bibliography_ids = set()
    for entry in document.bibliography_entries:
        if entry.entry_id in span_ids or entry.entry_id in referenced_bibliography_ids:
            traceable_bibliography_ids.add(entry.entry_id)
            continue
        raise ValueError(
            f"bibliography entry {entry.entry_id!r} is untraceable: no direct "
            "source span, citation mention, or external result mention references it"
        )

    known_evidence_ids = {
        *span_ids,
        *result_span_counts.keys(),
        *proof_span_counts.keys(),
        *bibliography_ids,
        *(mention.mention_id for mention in document.local_result_mentions),
        *citation_mention_ids,
        *(mention.mention_id for mention in document.external_result_mentions),
    }
    traceable_evidence_ids = {
        *span_ids,
        *traceable_result_ids,
        *traceable_proof_ids,
        *traceable_bibliography_ids,
        *traceable_mention_ids,
    }

    for edge in document.edges:
        if not edge.evidence_ids:
            raise ValueError(f"edge {edge.edge_id!r} has no evidence_ids")
        for evidence_id in edge.evidence_ids:
            if evidence_id not in known_evidence_ids:
                raise ValueError(
                    f"edge {edge.edge_id!r} references unknown evidence id "
                    f"{evidence_id!r}"
                )
            if evidence_id not in traceable_evidence_ids:
                raise ValueError(
                    f"edge {edge.edge_id!r} references untraceable evidence id "
                    f"{evidence_id!r}"
                )


def _unresolved_evidence_mention_count(document: EvidenceDocument) -> int:
    unresolved_local = sum(
        1
        for mention in document.local_result_mentions
        if not mention.target_result_id or not _is_resolved(mention.resolution_status)
    )
    unresolved_citations = sum(
        1
        for mention in document.citation_mentions
        if not mention.entry_id or not _is_resolved(mention.resolution_status)
    )
    unresolved_external = sum(
        1
        for mention in document.external_result_mentions
        if not _is_known_external_result_mention(mention)
    )
    return unresolved_local + unresolved_citations + unresolved_external


def _is_known_external_result_mention(mention) -> bool:
    target_paper_id = _mention_value(mention, "target_paper_id")
    entry_id = _mention_value(mention, "entry_id")
    resolution_status = _mention_value(mention, "resolution_status")
    return bool(
        (target_paper_id or entry_id)
        and _is_resolved(resolution_status)
    )


def _mention_value(mention, key: str):
    if isinstance(mention, dict):
        return mention[key]
    return getattr(mention, key)


def _is_resolved(resolution_status: str) -> bool:
    return resolution_status in {
        "resolved",
        "resolved_bibliography_entry",
        "resolved_candidate",
        "resolved_unique",
    }


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


def _source_span_from_row(row: tuple) -> dict:
    bbox = json.loads(row[8]) if row[8] is not None else None
    span = SourceSpanEvidence(
        span_id=row[0],
        paper_id=row[1],
        source_type=row[2],
        source_ref=row[3],
        page=row[4],
        block_index=row[5],
        start_offset=row[6],
        end_offset=row[7],
        bbox=tuple(bbox) if bbox is not None else None,
        text=row[9],
        method=row[10],
        confidence=row[11],
    )
    return source_span_payload(span)


def _result_from_row(row: tuple) -> dict:
    return {
        "result_id": row[0],
        "paper_id": row[1],
        "local_id": row[2],
        "kind": row[3],
        "raw_kind": row[4],
        "display_kind": row[5],
        "normalized_kind": row[6],
        "label": row[7],
        "visible_number": row[8],
        "title": row[9],
        "statement": row[10],
        "method": row[11],
        "confidence": row[12],
    }


def _proof_from_row(row: tuple) -> dict:
    return {
        "proof_id": row[0],
        "paper_id": row[1],
        "result_id": row[2],
        "text": row[3],
        "association_basis": row[4],
        "association_confidence": row[5],
        "method": row[6],
        "confidence": row[7],
    }


def _bibliography_entry_from_row(row: tuple) -> dict:
    return {
        "entry_id": row[0],
        "paper_id": row[1],
        "raw_label": row[2],
        "raw_text": row[3],
        "entry_type": row[4],
        "title": row[5],
        "authors": json.loads(row[6]),
        "year": row[7],
        "arxiv_id": row[8],
        "arxiv_version": row[9],
        "doi": row[10],
        "url": row[11],
        "method": row[12],
        "confidence": row[13],
    }


def _local_result_mention_from_row(row: tuple) -> dict:
    return {
        "mention_id": row[0],
        "paper_id": row[1],
        "proof_id": row[2],
        "raw_text": row[3],
        "kind": row[4],
        "visible_number": row[5],
        "target_result_id": row[6],
        "resolution_status": row[7],
        "method": row[8],
        "confidence": row[9],
    }


def _citation_mention_from_row(row: tuple) -> dict:
    return {
        "mention_id": row[0],
        "paper_id": row[1],
        "proof_id": row[2],
        "raw_text": row[3],
        "raw_key": row[4],
        "entry_id": row[5],
        "resolution_status": row[6],
        "method": row[7],
        "confidence": row[8],
    }


def _external_result_mention_from_row(row: tuple) -> dict:
    return {
        "mention_id": row[0],
        "paper_id": row[1],
        "proof_id": row[2],
        "citation_mention_id": row[3],
        "raw_text": row[4],
        "external_kind": row[5],
        "external_number": row[6],
        "entry_id": row[7],
        "target_paper_id": row[8],
        "resolution_status": row[9],
        "method": row[10],
        "confidence": row[11],
    }


def _evidence_edge_from_row(row: tuple) -> dict:
    return {
        "edge_id": row[0],
        "paper_id": row[1],
        "source_id": row[2],
        "target_id": row[3],
        "relation": row[4],
        "evidence_ids": json.loads(row[5]),
        "method": row[6],
        "confidence": row[7],
    }
