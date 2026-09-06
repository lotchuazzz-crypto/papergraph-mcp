# Reading Session State v0.7 Design

## Goal

PaperGraph v0.7 adds persistent reading-session state to the existing SQLite
workspace. A consumer can create a session for a paper or target result, record
which evidence-backed results and source slices have been reviewed, capture
open questions, and export a compact recovery summary for the next agent run.

## Motivation

PaperGraph v0.6 and v0.6.1 expose evidence-grounded Reading Bridge payloads,
but the workflow remains stateless. An agent can ask for a result context,
source slice, or reading path, yet PaperGraph cannot remember whether that
source slice was checked, which dependency blocked the reader, or what question
should be resumed later.

The next product step is a minimal state layer, not a natural-language reading
agent. PaperGraph should persist durable checkpoints and user/agent notes while
continuing to treat mathematical interpretation as consumer-owned.

## Recommended Approach

Add a small schema-v4 migration and a focused reading-session API on
`Workspace`. The state layer stores explicit records only:

- sessions;
- reviewed checkpoints for results, proofs, source spans, and external or
  unresolved stops;
- notes and questions attached to sessions and optional evidence targets.

The API should be available through MCP tools and JSON CLI commands, mirroring
the v0.6.1 Reading Bridge CLI pattern. This gives interactive clients and
terminal workflows the same deterministic state contract.

## Alternatives Considered

### Consumer-Only Session Files

The reading skill could write Markdown or JSON files next to its own logs. This
would avoid a database migration, but the state would drift from the evidence
workspace and would be hard to query through MCP. It also makes recovery depend
on each agent's private conventions.

### Full Human Notebook

PaperGraph could become a research notebook with rich Markdown pages, backlinks,
tags, and rendered reading plans. That is attractive, but too broad for v0.7 and
would blur the line between evidence storage and interpretation.

### Minimal Workspace Session State

The selected approach keeps state close to the evidence IDs it refers to. It is
small enough to test thoroughly and useful enough to support resumable AI4Math
reading workflows.

## Non-Goals

- Do not generate theorem explanations, proof strategies, symbol tables, or
  proof-gap fillings.
- Do not rank main results.
- Do not resolve external dependencies automatically.
- Do not add collaborative or multi-user access control.
- Do not store full free-form notebooks; notes are short records with explicit
  provenance and target IDs.
- Do not change Reading Bridge payload shapes except by adding optional session
  references where explicitly requested by session APIs.

## Schema

Increment `SCHEMA_VERSION` from `3` to `4`.

### `reading_sessions`

```sql
CREATE TABLE reading_sessions (
    session_id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    target_result_id TEXT REFERENCES results(result_id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'paused', 'completed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

`session_id` is deterministic enough for tests and safe for users:
`session:<slug-label-or-paper>:<YYYYMMDDHHMMSS>`. If a collision occurs, append
`-2`, `-3`, and so on.

### `reading_checkpoints`

```sql
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
    evidence JSON NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (session_id, target_kind, target_id)
)
```

`evidence` is JSON text. It may hold source handles, dependency stop payloads,
or consumer provenance. PaperGraph stores it as supplied after verifying that it
is JSON-serializable; PaperGraph does not interpret mathematical claims inside
it.

### `reading_notes`

```sql
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
)
```

The database should validate required columns on open just as earlier schema
versions do. Existing schema v3 workspaces migrate in place without losing
tables or evidence records.

## Workspace API

### `create_reading_session`

```python
Workspace.create_reading_session(
    paper_id: str,
    label: str | None = None,
    target_result_id: str | None = None,
) -> dict
```

Creates an active session for a stored paper. If `target_result_id` is provided,
it must belong to the same paper. The returned payload includes:

- `session_id`
- `paper_id`
- `target_result_id`
- `label`
- `status`
- `created_at`
- `updated_at`
- `counts` with `checkpoints` and `notes`

Default `label` is the target result ID when present, otherwise the paper ID.

### `list_reading_sessions`

```python
Workspace.list_reading_sessions(
    paper_id: str | None = None,
    status: str | None = None,
) -> list[dict]
```

Lists sessions ordered by most recently updated first, then `session_id`. Filters
must use known paper IDs and statuses.

### `get_reading_session`

```python
Workspace.get_reading_session(session_id: str) -> dict
```

Returns the session plus its checkpoints and notes in deterministic order.
Checkpoints sort by `updated_at`, then `checkpoint_id`; notes sort by
`created_at`, then `note_id`.

### `record_reading_checkpoint`

```python
Workspace.record_reading_checkpoint(
    session_id: str,
    target_kind: str,
    target_id: str,
    status: str,
    summary: str = "",
    evidence: dict | None = None,
) -> dict
```

Creates or updates one checkpoint for a target. The exact target ID is preserved.
For local IDs that PaperGraph can verify, unknown targets fail:

- `result_id` must exist in `results`;
- `proof_id` must exist in `proofs`;
- `span_id` may match either public `source_spans.span_id` or internal
  generated span ID strings used by source handles.

`external_stop` and `unresolved_stop` are intentionally opaque because they may
come from Reading Bridge path payloads.

### `add_reading_note`

```python
Workspace.add_reading_note(
    session_id: str,
    text: str,
    note_type: str = "note",
    target_kind: str | None = None,
    target_id: str | None = None,
) -> dict
```

Adds a short note or question. Empty text fails. If a target kind is supplied, a
target ID is required.

### `export_reading_session_summary`

```python
Workspace.export_reading_session_summary(session_id: str) -> dict
```

Returns a recovery payload:

```json
{
  "session": {},
  "paper": {},
  "target_result": {},
  "progress": {
    "total_checkpoints": 0,
    "reviewed": 0,
    "blocked": 0,
    "queued": 0,
    "skipped": 0
  },
  "reviewed_targets": [],
  "blocked_targets": [],
  "open_questions": [],
  "latest_notes": [],
  "next_actions": [],
  "source_policy": {
    "facts_from": "papergraph_evidence_graph",
    "interpretation_from": "consumer",
    "proof_verification": false,
    "semantic_matching": false
  }
}
```

`next_actions` are deterministic status hints, not mathematical advice:

- If there are blocked checkpoints, emit `review_blocked_targets`.
- If there are queued checkpoints, emit `continue_queued_targets`.
- If the session has a target result and no checkpoint for it, emit
  `review_target_result`.
- If there are open questions, emit `answer_or_retire_open_questions`.

## MCP Tools

Add thin wrappers that mirror workspace methods and translate expected errors
to `ToolError`:

- `workspace_create_reading_session(paper_id, label=None, target_result_id=None)`
- `workspace_list_reading_sessions(paper_id=None, status=None)`
- `workspace_get_reading_session(session_id)`
- `workspace_record_reading_checkpoint(session_id, target_kind, target_id, status, summary="", evidence=None)`
- `workspace_add_reading_note(session_id, text, note_type="note", target_kind=None, target_id=None)`
- `workspace_export_reading_session_summary(session_id)`

These tools require an active workspace and do not mutate the active single-paper
graph.

## CLI Commands

Add JSON CLI commands over an existing workspace:

- `create-reading-session --workspace PATH --paper-id PAPER_ID [--label LABEL] [--target-result-id RESULT_ID]`
- `list-reading-sessions --workspace PATH [--paper-id PAPER_ID] [--status STATUS]`
- `get-reading-session --workspace PATH --session-id SESSION_ID`
- `record-reading-checkpoint --workspace PATH --session-id SESSION_ID --target-kind KIND --target-id ID --status STATUS [--summary TEXT] [--evidence-json JSON]`
- `add-reading-note --workspace PATH --session-id SESSION_ID --text TEXT [--note-type TYPE] [--target-kind KIND --target-id ID]`
- `export-reading-session-summary --workspace PATH --session-id SESSION_ID`

Commands print only JSON to stdout. Expected workspace and input errors use the
existing CLI JSON error envelope and nonzero exit behavior.

## Error Handling

- Unknown paper, result, proof, span, or session IDs fail with clear messages.
- Invalid session status, checkpoint status, target kind, or note type fails
  before writing.
- Empty label, summary-only notes, and malformed `--evidence-json` fail.
- Updating a checkpoint is atomic and refreshes both checkpoint and session
  `updated_at`.
- Adding a note refreshes session `updated_at`.
- A failed migration or schema validation must close the attempted connection
  and leave existing database contents untouched.

## Documentation

README should add a compact "Reading session workflow" section after the Reading
Bridge workflow. It should show:

1. create a session;
2. record that a source slice or result was reviewed;
3. add an open question;
4. export the recovery summary.

The copy must preserve the evidence-first boundary: PaperGraph stores reading
state and provenance, not generated mathematical explanations.

## Validation Plan

Tests should cover:

1. Schema v4 initializes the three session tables.
2. Schema v3 migrates to v4 without losing existing evidence tables.
3. Creating a session validates paper and target-result ownership.
4. Listing sessions filters by paper and status in deterministic order.
5. Recording a checkpoint creates and updates a unique target record.
6. Checkpoint validation rejects invalid statuses, target kinds, and unknown
   verifiable targets.
7. Adding notes validates note type, text, and target fields.
8. Exported summaries report progress counts, blocked targets, open questions,
   latest notes, and deterministic next actions.
9. MCP wrappers expose the same payloads and convert workspace errors to
   `ToolError`.
10. CLI commands print JSON for session create/list/get/checkpoint/note/summary
    and JSON error envelopes for invalid inputs.
11. README examples and release surfaces mention `0.7.0` / `v0.7.0`.

## Release Criteria

v0.7.0 is ready when:

- all existing v0.6.1 tests pass;
- new workspace, MCP, CLI, migration, and README tests pass;
- a fresh workspace reports schema version `4`;
- a v3 fixture database opens and reports schema version `4`;
- command-line session workflows can be smoke-tested from an existing workspace;
- the release tag `v0.7.0` installs with `uvx` and prints
  `papergraph-mcp 0.7.0`.
