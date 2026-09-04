import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from papergraph.evidence import (
    BibliographyEntryEvidence,
    CitationMentionEvidence,
    EvidenceDocument,
    EvidenceEdge,
    ExternalResultMentionEvidence,
    LocalResultMentionEvidence,
    ProofEvidence,
    ResultEvidence,
    SourceSpanEvidence,
)
from papergraph.workspace import SCHEMA_VERSION, Workspace


def simple_document() -> EvidenceDocument:
    span = SourceSpanEvidence(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        page=1,
        block_index=0,
        start_offset=0,
        end_offset=45,
        bbox=None,
        text="Theorem 1.1. Main. Proof. By Lemma 1.2.",
        method="pdf_text_block",
        confidence=1.0,
    )
    result = ResultEvidence(
        result_id="local:paper-a::pdf:theorem:1.1",
        paper_id="local:paper-a",
        local_id="pdf:theorem:1.1",
        kind="theorem",
        raw_kind="Theorem",
        display_kind="Theorem",
        normalized_kind="theorem",
        label=None,
        visible_number="1.1",
        title=None,
        statement="Theorem 1.1. Main.",
        span_indices=(0,),
        method="pdf_heading_regex",
        confidence=0.85,
    )
    proof = ProofEvidence(
        proof_id="local:paper-a::proof:1",
        paper_id="local:paper-a",
        result_id=result.result_id,
        text="Proof. By Lemma 1.2.",
        span_indices=(0,),
        association_basis="immediately_follows_result",
        association_confidence=0.75,
        method="pdf_proof_heading",
        confidence=0.85,
    )
    mention = LocalResultMentionEvidence(
        mention_id="local:paper-a::local-mention:1",
        paper_id="local:paper-a",
        proof_id=proof.proof_id,
        raw_text="Lemma 1.2",
        kind="lemma",
        visible_number="1.2",
        target_result_id=None,
        resolution_status="unresolved",
        method="proof_local_result_regex",
        confidence=0.8,
    )
    return EvidenceDocument(
        paper_id="local:paper-a",
        source_type="pdf",
        source_ref="paper.pdf",
        source_version=None,
        title="PDF Paper",
        authors=("Ada Lovelace",),
        main_file="paper.pdf",
        spans=(span,),
        results=(result,),
        proofs=(proof,),
        bibliography_entries=(),
        local_result_mentions=(mention,),
        citation_mentions=(),
        external_result_mentions=(),
        edges=(),
        warnings=(),
    )


def document_with_external_mentions() -> EvidenceDocument:
    base = simple_document()
    bibliography = BibliographyEntryEvidence(
        entry_id="local:paper-a::bib:target",
        paper_id="local:paper-a",
        raw_label="target",
        raw_text="@article{target, title={Target}}",
        entry_type="article",
        title="Target",
        authors=("Grace Hopper",),
        year=1960,
        arxiv_id="2401.12345",
        arxiv_version="v2",
        doi=None,
        url="https://example.test/target",
        method="pdf_bibliography",
        confidence=0.7,
    )
    citation = CitationMentionEvidence(
        mention_id="local:paper-a::citation:target",
        paper_id="local:paper-a",
        proof_id=base.proofs[0].proof_id,
        raw_text="[1]",
        raw_key="target",
        entry_id=bibliography.entry_id,
        resolution_status="resolved_candidate",
        method="proof_citation_regex",
        confidence=0.8,
    )
    external = ExternalResultMentionEvidence(
        mention_id="local:paper-a::external:target-thm",
        paper_id="local:paper-a",
        proof_id=base.proofs[0].proof_id,
        citation_mention_id=citation.mention_id,
        raw_text="Theorem A of [1]",
        external_kind="theorem",
        external_number="A",
        entry_id=bibliography.entry_id,
        target_paper_id="arxiv:2401.12345",
        resolution_status="resolved_candidate",
        method="external_result_regex",
        confidence=0.65,
    )
    edge = EvidenceEdge(
        edge_id="local:paper-a::edge:uses-external",
        paper_id="local:paper-a",
        source_id=base.results[0].result_id,
        target_id=external.mention_id,
        relation="uses",
        evidence_ids=(external.mention_id,),
        method="proof_dependency",
        confidence=0.6,
    )
    return replace(
        base,
        bibliography_entries=(bibliography,),
        citation_mentions=(citation,),
        external_result_mentions=(external,),
        edges=(edge,),
    )


def test_schema_v3_initializes_evidence_tables(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        assert SCHEMA_VERSION == 3
        tables = {
            row[0]
            for row in workspace._connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"source_spans", "results", "proofs", "local_result_mentions", "evidence_edges"} <= tables
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("3",)
    finally:
        workspace.close()


def test_import_evidence_document_and_query_result_proof_dependencies(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        result = workspace.import_evidence_document(simple_document())
        assert result.paper_id == "local:paper-a"
        assert result.theorem_count == 1

        listed = workspace.list_results()
        assert listed[0]["result_id"] == "local:paper-a::pdf:theorem:1.1"
        assert listed[0]["source_type"] == "pdf"
        assert listed[0]["first_location"]["page"] == 1

        full = workspace.get_result("local:paper-a::pdf:theorem:1.1")
        assert full["statement"] == "Theorem 1.1. Main."
        assert full["spans"][0]["page"] == 1

        proof = workspace.get_result_proof("local:paper-a::pdf:theorem:1.1")
        assert proof["known"]["proof"]["proof_id"] == "local:paper-a::proof:1"
        assert proof["inferred"][0]["basis"] == "immediately_follows_result"

        dependencies = workspace.get_proof_dependencies("local:paper-a::pdf:theorem:1.1")
        assert dependencies["known"]["resolved_local_results"] == []
        assert dependencies["unresolved"]["local_result_mentions"][0]["raw_text"] == "Lemma 1.2"
        assert dependencies["warnings"]
    finally:
        workspace.close()


def test_v2_workspace_migrates_without_losing_legacy_tables(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            '''
            CREATE TABLE workspace_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
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
            INSERT INTO workspace_meta VALUES ('schema_version', '2');
            INSERT INTO papers VALUES ('local:old', 'local', 'main.tex', NULL, NULL, '[]', 'main.tex', '2026-09-03T00:00:00+00:00', '0.4.4');
            INSERT INTO theorems VALUES ('local:old::thm:main', 'local:old', 'thm:main', 'theorem', 'theorem', 'theorem', 'theorem', NULL, 'thm:main', 'Main.', 'main.tex', 0);
            '''
        )

    workspace = Workspace.open(path)
    try:
        assert workspace._connection.execute(
            "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
        ).fetchone() == ("3",)
        assert workspace.get_paper("local:old")["paper_id"] == "local:old"
    finally:
        workspace.close()


def test_external_mentions_and_evidence_are_queryable(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_evidence_document(document_with_external_mentions())

        mentions = workspace.get_external_result_mentions(
            "local:paper-a::pdf:theorem:1.1"
        )
        assert mentions[0]["raw_text"] == "Theorem A of [1]"
        assert mentions[0]["target_paper_id"] == "arxiv:2401.12345"

        dependencies = workspace.get_proof_dependencies(
            "local:paper-a::pdf:theorem:1.1"
        )
        assert dependencies["known"]["resolved_external_results"][0]["mention_id"] == (
            "local:paper-a::external:target-thm"
        )
        assert dependencies["warnings"] == []

        evidence = workspace.get_evidence("local:paper-a::external:target-thm")
        assert evidence["metadata"]["raw_text"] == "Theorem A of [1]"
        assert evidence["spans"] == []

        edge_evidence = workspace.get_evidence("local:paper-a::edge:uses-external")
        assert edge_evidence["metadata"]["relation"] == "uses"
        assert edge_evidence["metadata"]["evidence_ids"] == [
            "local:paper-a::external:target-thm"
        ]
    finally:
        workspace.close()


def test_failed_evidence_import_preserves_previous_paper(tmp_path: Path):
    workspace = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        workspace.import_evidence_document(simple_document())
        workspace._connection.execute(
            """
            CREATE TRIGGER fail_result_replacement
            BEFORE INSERT ON results
            WHEN NEW.paper_id = 'local:paper-a'
            BEGIN
                SELECT RAISE(ABORT, 'injected evidence failure');
            END
            """
        )

        with pytest.raises(sqlite3.IntegrityError, match="injected evidence failure"):
            workspace.import_evidence_document(simple_document())

        assert workspace.get_paper("local:paper-a")["source_ref"] == "paper.pdf"
        assert [row["result_id"] for row in workspace.list_results()] == [
            "local:paper-a::pdf:theorem:1.1"
        ]
    finally:
        workspace.close()
