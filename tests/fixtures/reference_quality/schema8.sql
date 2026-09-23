BEGIN TRANSACTION;
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
INSERT INTO "citation_evidence" VALUES(1,'arxiv:2401.10001','ambiguous','cite','main.tex','refs.bib','article',NULL,NULL,NULL,'unsupported_identifier');
INSERT INTO "citation_evidence" VALUES(2,'arxiv:2401.10001','metadata','cite','main.tex','refs.bib','article',NULL,NULL,NULL,'unsupported_identifier');
INSERT INTO "citation_evidence" VALUES(3,'arxiv:2401.10001','a','cite','main.tex','refs.bib','article','2401.10001',NULL,'arxiv:2401.10001','resolved_candidate');
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
CREATE TABLE evidence_edge_source_spans (
    edge_id TEXT NOT NULL REFERENCES evidence_edges(edge_id) ON DELETE CASCADE,
    span_id INTEGER NOT NULL REFERENCES source_spans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (edge_id, span_id, position)
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
);
INSERT INTO "papers" VALUES('arxiv:2401.10001','arxiv','2401.10001',NULL,'Expansion Fixture B','["Bert Author"]','main.tex','2026-09-23T14:09:57.701756+00:00','1.1.4');
CREATE TABLE proof_source_spans (
    proof_id TEXT NOT NULL REFERENCES proofs(proof_id) ON DELETE CASCADE,
    span_id INTEGER NOT NULL REFERENCES source_spans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (proof_id, span_id, position)
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
CREATE TABLE reading_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES reading_sessions(session_id)
        ON DELETE CASCADE,
    target_kind TEXT NOT NULL CHECK (
        target_kind IN (
            'result_id',
            'proof_id',
            'span_id',
            'external_stop',
            'unresolved_stop'
        )
    ),
    target_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'reviewed', 'blocked', 'skipped')
    ),
    summary TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (session_id, target_kind, target_id)
);
CREATE TABLE reading_notes (
    note_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES reading_sessions(session_id)
        ON DELETE CASCADE,
    target_kind TEXT CHECK (
        target_kind IS NULL OR target_kind IN (
            'result_id',
            'proof_id',
            'span_id',
            'external_stop',
            'unresolved_stop',
            'session'
        )
    ),
    target_id TEXT,
    note_type TEXT NOT NULL CHECK (
        note_type IN ('note', 'question', 'warning', 'decision')
    ),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE reading_queue_items (
    item_id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL REFERENCES reading_queues(queue_id)
        ON DELETE CASCADE,
    position INTEGER NOT NULL,
    target_kind TEXT NOT NULL CHECK (
        target_kind IN (
            'result_id',
            'proof_id',
            'span_id',
            'external_stop',
            'unresolved_stop'
        )
    ),
    target_id TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (
        priority IN ('required', 'recommended', 'caution')
    ),
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (queue_id, target_kind, target_id)
);
CREATE TABLE reading_queues (
    queue_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    target_result_id TEXT REFERENCES results(result_id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE reading_sessions (
    session_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    target_result_id TEXT REFERENCES results(result_id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'paused', 'completed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE reference_expansion_attempts (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 attempt_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,attempt_id));
CREATE TABLE reference_expansion_edges (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 edge_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,edge_id));
CREATE TABLE reference_expansion_events (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 event_id INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,event_id));
INSERT INTO "reference_expansion_events" VALUES('expansion:940fd0364c6c40c2b2f45dceee08161c',1,'{"event_id": 1, "kind": "created", "policy": {"auto_select_policy": "unique_strong_v1", "max_depth": 2, "max_edges": 500, "max_new_papers": 10, "max_searches": 100, "providers": ["arxiv", "crossref", "openalex"]}, "timestamp": 1790172597.7264233}');
INSERT INTO "reference_expansion_events" VALUES('expansion:940fd0364c6c40c2b2f45dceee08161c',-1790172597738242300,'{"control": "pause", "event_id": -1790172597738242300, "kind": "control_requested", "timestamp": 1790172597.7382443}');
CREATE TABLE reference_expansion_lease (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), owner TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE reference_expansion_nodes (
 run_id TEXT NOT NULL REFERENCES reference_expansion_runs(run_id),
 node_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,node_id));
INSERT INTO "reference_expansion_nodes" VALUES('expansion:940fd0364c6c40c2b2f45dceee08161c','arxiv:2401.10001','{"aliases": ["arxiv:2401.10001"], "cursor": 0, "depth": 0, "discovery": "queued", "fingerprint": "015df842c0bd6de43b8a21a7e9f7ab87c91377880abec19079bff64403fc9979", "node_id": "arxiv:2401.10001", "paper_id": "arxiv:2401.10001", "references": null}');
CREATE TABLE reference_expansion_runs (
 run_id TEXT PRIMARY KEY, payload TEXT NOT NULL, control TEXT);
INSERT INTO "reference_expansion_runs" VALUES('expansion:940fd0364c6c40c2b2f45dceee08161c','{"affected_paper_ids": [], "attempts": [], "continuation_required": true, "created_at": 1790172597.720996, "edges": [], "events": [{"event_id": 1, "kind": "created", "policy": {"auto_select_policy": "unique_strong_v1", "max_depth": 2, "max_edges": 500, "max_new_papers": 10, "max_searches": 100, "providers": ["arxiv", "crossref", "openalex"]}, "timestamp": 1790172597.7264233}], "expansion_schema_version": 1, "next_actions": [], "nodes": [{"aliases": ["arxiv:2401.10001"], "cursor": 0, "depth": 0, "discovery": "queued", "fingerprint": "015df842c0bd6de43b8a21a7e9f7ab87c91377880abec19079bff64403fc9979", "node_id": "arxiv:2401.10001", "paper_id": "arxiv:2401.10001", "references": null}], "policy": {"auto_select_policy": "unique_strong_v1", "max_depth": 2, "max_edges": 500, "max_new_papers": 10, "max_searches": 100, "providers": ["arxiv", "crossref", "openalex"]}, "policy_revisions": [{"auto_select_policy": "unique_strong_v1", "max_depth": 2, "max_edges": 500, "max_new_papers": 10, "max_searches": 100, "providers": ["arxiv", "crossref", "openalex"]}], "reason": null, "roots": ["arxiv:2401.10001"], "run_id": "expansion:940fd0364c6c40c2b2f45dceee08161c", "state": "ready", "summary": {"boundary": 0, "frontier": 1, "imported": 0, "linked_existing": 0, "needs_review": 0, "retryable_failure": 0, "runnable": 1, "skipped": 0}, "usage": {"edges": 0, "new_papers": 0, "searches": 0}}','pause');
CREATE TABLE reference_resolutions (
    resolution_id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    blocked_id TEXT NOT NULL,
    target_kind TEXT NOT NULL CHECK (
        target_kind IN ('arxiv', 'pdf', 'doi', 'url', 'metadata')
    ),
    target_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('resolved_imported', 'resolved_not_imported', 'failed_import')
    ),
    imported_paper_id TEXT REFERENCES papers(paper_id) ON DELETE SET NULL,
    evidence_json TEXT NOT NULL,
    review_json TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    warning_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source_paper_id, blocked_id, target_kind, target_json)
);
INSERT INTO "reference_resolutions" VALUES('reference-resolution:arxiv-2401.10001-external-import-blocked-citation_record-arxiv-2401.10001-cite-main.tex-ambiguous-doi-doi-10.1000-maps-kind-doi-title-maps','arxiv:2401.10001','external-import:blocked:citation_record-arxiv-2401.10001-cite-main.tex-ambiguous','doi','{"doi": "10.1000/maps", "kind": "doi", "title": "Maps"}','resolved_not_imported',NULL,'[{"bib_file": "refs.bib", "citation_key": "ambiguous", "id": "arxiv:2401.10001:cite:main.tex:ambiguous", "kind": "citation_record", "paper_id": "arxiv:2401.10001", "proof_id": null, "raw_text": "\\cite{ambiguous}", "result_id": null, "source": "paper.citation_evidence", "source_file": "main.tex"}]','{"citation_keys": ["ambiguous"], "evidence_summary": "Needed by 0 local results through 0 proofs; citation keys: ambiguous; cited result evidence: \\cite{ambiguous}", "local_result_ids": [], "proof_ids": [], "raw_texts": ["\\cite{ambiguous}"]}','[]','[]','2026-09-23T14:09:57.715920+00:00','2026-09-23T14:09:57.715920+00:00');
CREATE TABLE reference_search_candidates (
    candidate_id TEXT PRIMARY KEY,
    search_run_id TEXT NOT NULL REFERENCES reference_search_runs(search_run_id)
        ON DELETE CASCADE,
    source_paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    blocked_id TEXT NOT NULL,
    target_json TEXT NOT NULL,
    score REAL NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    provider_record_json TEXT NOT NULL,
    warning_json TEXT NOT NULL,
    rank INTEGER NOT NULL
);
INSERT INTO "reference_search_candidates" VALUES('reference-candidate:arxiv-2401.10001-external-import-blocked-citation_record-arxiv-2401.10001-cite-main.tex-ambiguous-doi-10.1000-maps-kind-doi-title-maps:arxiv-2401.10001-external-import-blocked-citation_record-arxiv-2401.10001-cite-main.tex-ambiguous-1-author_hints-citation_keys-ambiguous-raw_bibliography_text-raw_citation_texts-cite-ambiguous-title_hint-null-year_hint-null','reference-search:arxiv-2401.10001-external-import-blocked-citation_record-arxiv-2401.10001-cite-main.tex-ambiguous-1-author_hints-citation_keys-ambiguous-raw_bibliography_text-raw_citation_texts-cite-ambiguous-title_hint-null-year_hint-null','arxiv:2401.10001','external-import:blocked:citation_record-arxiv-2401.10001-cite-main.tex-ambiguous','{"doi": "10.1000/maps", "kind": "doi", "title": "Maps"}',1.5,'weak','["doi_present"]','[{"provider": "crossref", "record": {"doi": "10.1000/maps", "title": "Maps"}}]','[]',1);
CREATE TABLE reference_search_runs (
    search_run_id TEXT PRIMARY KEY,
    source_paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    blocked_id TEXT NOT NULL,
    query_json TEXT NOT NULL,
    provider_json TEXT NOT NULL,
    boundary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
INSERT INTO "reference_search_runs" VALUES('reference-search:arxiv-2401.10001-external-import-blocked-citation_record-arxiv-2401.10001-cite-main.tex-ambiguous-1-author_hints-citation_keys-ambiguous-raw_bibliography_text-raw_citation_texts-cite-ambiguous-title_hint-null-year_hint-null','arxiv:2401.10001','external-import:blocked:citation_record-arxiv-2401.10001-cite-main.tex-ambiguous','{"author_hints": [], "citation_keys": ["ambiguous"], "raw_bibliography_text": "", "raw_citation_texts": ["\\cite{ambiguous}"], "title_hint": null, "year_hint": null}','{"max_candidates": 10, "provider_warnings": [], "providers": null}','[]','2026-09-23T14:09:57.710788+00:00');
CREATE TABLE result_source_spans (
    result_id TEXT NOT NULL REFERENCES results(result_id) ON DELETE CASCADE,
    span_id INTEGER NOT NULL REFERENCES source_spans(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (result_id, span_id, position)
);
INSERT INTO "result_source_spans" VALUES('arxiv:2401.10001::main',1,0);
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
INSERT INTO "results" VALUES('arxiv:2401.10001::main','arxiv:2401.10001','main','lemma','lemma','lemma','lemma','main','1',NULL,'\label{main}Some references need review.','latex_environment',1.0);
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
INSERT INTO "source_spans" VALUES(1,NULL,'arxiv:2401.10001','tex','main.tex',NULL,NULL,48,88,NULL,'\label{main}Some references need review.','latex_environment',1.0);
CREATE TABLE theorem_refs (
    source_global_id TEXT NOT NULL REFERENCES theorems(global_id) ON DELETE CASCADE,
    ref_label TEXT NOT NULL,
    target_global_id TEXT REFERENCES theorems(global_id) ON DELETE CASCADE,
    PRIMARY KEY (source_global_id, ref_label)
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
INSERT INTO "theorems" VALUES('arxiv:2401.10001::main','arxiv:2401.10001','main','lemma','lemma','lemma','lemma',NULL,'main','\label{main}Some references need review.','main.tex',48);
CREATE TABLE workspace_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO "workspace_meta" VALUES('schema_version','8');
CREATE INDEX theorems_paper_kind ON theorems(paper_id, normalized_kind);
CREATE INDEX citations_source ON citation_evidence(source_paper_id);
CREATE INDEX citations_target ON citation_evidence(target_paper_id);
CREATE INDEX citations_arxiv ON citation_evidence(cited_arxiv_id);
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
CREATE INDEX reading_sessions_paper_status
    ON reading_sessions(paper_id, status, updated_at, session_id);
CREATE INDEX reading_checkpoints_session
    ON reading_checkpoints(session_id, updated_at, checkpoint_id);
CREATE INDEX reading_notes_session
    ON reading_notes(session_id, created_at, note_id);
CREATE INDEX reading_queues_paper_status
    ON reading_queues(paper_id, status, updated_at, queue_id);
CREATE INDEX reading_queue_items_queue
    ON reading_queue_items(queue_id, position, item_id);
CREATE INDEX reference_resolutions_source
    ON reference_resolutions(source_paper_id, blocked_id, target_kind, resolution_id);
CREATE INDEX reference_search_runs_source
    ON reference_search_runs(source_paper_id, blocked_id, created_at, search_run_id);
CREATE INDEX reference_search_candidates_run
    ON reference_search_candidates(search_run_id, rank, candidate_id);
COMMIT;
