# Reading Queue Planner v0.8 Design

## Goal

PaperGraph v0.8.0 adds a persistent Reading Queue Planner that turns existing
Reading Bridge evidence and v0.7 Reading Session State into a concrete,
ordered list of targets an agent can review next.

The planner must stay evidence-first. It may say that a target is queued
because it is the selected result, a local proof dependency, a proof block, an
external stop, an unresolved stop, or a warning-backed caution. It must not
claim that a proof is correct, fill proof gaps, rank mathematical importance
semantically, or invent missing dependencies.

## User Workflow

An agent opens a workspace, imports a paper, selects a target result, and asks
PaperGraph for a reading queue. PaperGraph stores the queue in SQLite so the
agent can reopen, inspect, and reuse it later.

The expected workflow is:

```text
open_workspace(path="C:/Temp/papergraph-reading.sqlite3")
workspace_add_pdf_paper(path="C:/Papers/example.pdf", paper_id="local:example")
workspace_create_reading_queue(result_id="local:example::pdf:theorem:1.1", label="Main theorem queue")
workspace_get_reading_queue(queue_id="queue:...")
workspace_create_reading_session(paper_id="local:example", target_result_id="local:example::pdf:theorem:1.1")
workspace_apply_reading_queue_to_session(queue_id="queue:...", session_id="session:...")
workspace_export_reading_session_summary(session_id="session:...")
```

The same workflow must be available from the JSON CLI against an existing
workspace.

## Data Model

The workspace schema advances from version 4 to version 5.

Two tables are added:

- `reading_queues`
- `reading_queue_items`

`reading_queues` stores queue metadata:

- `queue_id`
- `paper_id`
- `target_result_id`
- `label`
- `status`
- `created_at`
- `updated_at`

The only supported queue statuses for v0.8 are `active` and `archived`.

`reading_queue_items` stores deterministic plan items:

- `item_id`
- `queue_id`
- `position`
- `target_kind`
- `target_id`
- `priority`
- `reason`
- `evidence_json`
- `created_at`

Supported target kinds match v0.7 session checkpoints:

- `result_id`
- `proof_id`
- `span_id`
- `external_stop`
- `unresolved_stop`

Supported priorities are:

- `required`
- `recommended`
- `caution`

Queue rows cascade when a paper is deleted. Queue items cascade when a queue is
deleted.

## Planner Semantics

`create_reading_queue(result_id, label=None, recursive=True)` builds one queue
from the selected result and its existing evidence.

The queue order is deterministic:

1. The selected `result_id` as `required`.
2. The selected result's proof, if present, as `required`.
3. Local result dependencies from `get_result_reading_path(result_id, recursive)`
   in `top_down` order, excluding the selected result, as `recommended`.
4. Proofs for those local dependency results, when present, immediately after
   their result, as `recommended`.
5. External stops from the reading path as `caution`.
6. Unresolved stops from the reading path as `caution`.

Duplicate `(target_kind, target_id)` pairs are omitted after their first
occurrence.

Each item includes a short deterministic `reason` and an `evidence` object. The
evidence object includes enough provenance to recover the original bridge
payload source without embedding generated explanation text.

## Public Workspace API

Add these methods to `Workspace`:

```python
def create_reading_queue(
    self,
    result_id: str,
    label: str | None = None,
    recursive: bool = True,
) -> dict: ...

def list_reading_queues(
    self,
    paper_id: str | None = None,
    status: str | None = None,
) -> list[dict]: ...

def get_reading_queue(self, queue_id: str) -> dict: ...

def apply_reading_queue_to_session(
    self,
    queue_id: str,
    session_id: str,
    status: str = "queued",
) -> dict: ...
```

`create_reading_queue` returns the stored queue metadata plus item count.
`get_reading_queue` returns `{"queue": ..., "items": [...]}`.
`apply_reading_queue_to_session` validates that the queue and session belong to
the same paper, records one reading checkpoint for each queue item with the
requested status, and returns:

```python
{
    "queue": queue_payload,
    "session": session_payload,
    "applied": [checkpoint_payload, ...],
}
```

The apply status is restricted to v0.7 checkpoint statuses:

- `queued`
- `reviewed`
- `blocked`
- `skipped`

The default is `queued`.

## MCP Tools

Expose these MCP tools:

- `workspace_create_reading_queue(result_id: str, label: str | None = None, recursive: bool = True) -> dict`
- `workspace_list_reading_queues(paper_id: str | None = None, status: str | None = None) -> list[dict]`
- `workspace_get_reading_queue(queue_id: str) -> dict`
- `workspace_apply_reading_queue_to_session(queue_id: str, session_id: str, status: str = "queued") -> dict`

They must follow the existing `require_workspace()` and `_workspace_call`
patterns so missing workspaces and validation errors surface as `ToolError`.

## CLI

Add JSON CLI commands:

```powershell
papergraph-mcp create-reading-queue --workspace C:/Temp/papergraph.sqlite3 --result-id local:example::pdf:theorem:1.1 --label "Main theorem queue"
papergraph-mcp list-reading-queues --workspace C:/Temp/papergraph.sqlite3 --paper-id local:example
papergraph-mcp get-reading-queue --workspace C:/Temp/papergraph.sqlite3 --queue-id queue:...
papergraph-mcp apply-reading-queue-to-session --workspace C:/Temp/papergraph.sqlite3 --queue-id queue:... --session-id session:...
```

All commands print JSON using the existing CLI helper path and return the same
error envelope style used by v0.6 and v0.7.

## Documentation And Release

The README should describe v0.8.0 as the release that adds persistent Reading
Queue Planner support. The quick-start and MCP configuration pins should move
from `v0.7.0` to `v0.8.0`, while historical v0.7.0 text remains as release
history.

The active version should become `0.8.0`.

## Testing

Tests must cover:

- Schema v5 creates and migrates queue tables.
- `create_reading_queue` emits deterministic ordered items from a PDF fixture
  with a target result, proof, dependency, external stop, and unresolved stop.
- Duplicate queue targets are omitted.
- `list_reading_queues` and `get_reading_queue` are deterministic.
- `apply_reading_queue_to_session` writes queued checkpoints using v0.7 session
  state and rejects cross-paper queue/session combinations.
- MCP wrappers return payloads and convert missing-workspace/errors.
- CLI commands round-trip through JSON.
- Repository metadata and README list the new tools and v0.8.0 pins.

The full suite must pass locally before publishing. The GitHub Actions matrix
on `main` must pass before creating the `v0.8.0` tag and release.

## Non-Goals

- No semantic theorem ranking.
- No automatic arXiv citation import.
- No proof verification.
- No generated plain-language theorem or proof explanations.
- No mutation of checkpoint status from queue state after apply; v0.7 reading
  sessions remain the source of reading progress.
