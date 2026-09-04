# Reading Bridge CLI v0.6.1 Design

## Goal

PaperGraph v0.6.1 adds command-line export entry points for the Reading Bridge
workflow introduced in v0.6.0. The feature lets users and CI scripts export the
same evidence payloads that MCP clients can request, without starting an MCP
session.

## Motivation

The v0.6.0 Reading Bridge tools are useful inside an active MCP client, but the
release cannot be smoke-tested from a plain shell beyond `--version` and
`doctor`. A small CLI layer makes the bridge easier to validate, easier to
demonstrate in README examples, and easier for other local tools to consume.

## Scope

This release adds deterministic JSON CLI commands over an existing SQLite
workspace:

- `export-reading-bundle --workspace PATH --paper-id PAPER_ID`
- `export-result-reading-context --workspace PATH --result-id RESULT_ID`
- `get-source-slice --workspace PATH` with exactly one of `--span-id`,
  `--result-id`, or `--proof-id`, plus `--context 0..5`
- `get-result-reading-path --workspace PATH --result-id RESULT_ID` with
  `--direct` to disable recursive traversal

Each command prints only JSON to stdout. Successful commands exit `0`. Workspace
errors, unknown IDs, invalid selector combinations, invalid context values, and
SQLite errors produce a JSON error envelope and exit nonzero.

## Non-Goals

This release does not add new extraction logic, OCR, semantic proof
interpretation, JSON file writing, bulk export, network access, PyPI publishing,
or schema migration. It does not change MCP tool signatures or existing Reading
Bridge payload shapes.

## Interfaces

The CLI commands open a fresh `Workspace` from `--workspace`, call the
corresponding existing workspace method, print sorted pretty JSON, and close the
workspace before returning.

Error payloads use this stable shape:

```json
{
  "status": "error",
  "action": "inspect_error",
  "command": "export-reading-bundle",
  "message": "Unknown paper id: local:missing"
}
```

The `command` field is the CLI subcommand name. The `message` field is the
underlying bounded exception text. The CLI does not print tracebacks for
expected workspace/input failures.

## Data Flow

1. `argparse` parses one Reading Bridge subcommand.
2. A helper opens `Workspace.open(args.workspace)`.
3. The helper calls the matching workspace method.
4. `_print_json` serializes the payload with `indent=2` and `sort_keys=True`.
5. `finally` closes the workspace if it was opened.

## Validation

The selector command enforces the same exact-one selector rule as
`Workspace.get_source_slice`. The CLI also rejects `--context` outside `0..5`
through the existing workspace validation, so CLI and MCP behavior stay aligned.

`get-result-reading-path` defaults to recursive traversal to match the MCP tool.
Passing `--direct` sets `recursive=False`.

## Documentation

README gains a compact terminal workflow under the Reading Bridge section. The
example imports a PDF through an MCP client or other existing workflow first,
then shows CLI export commands against the resulting workspace. The docs must
make clear that CLI export reads an existing workspace; it does not import
papers by itself.

## Testing

Tests cover:

- CLI bundle export over a small PDF-backed workspace.
- CLI focused result context export.
- CLI source-slice export with `--proof-id` and bounded context.
- CLI direct reading path with `--direct`.
- CLI JSON error envelope and nonzero exit for invalid selector usage.
- README and repository release-surface expectations for `0.6.1` / `v0.6.1`.

The full suite must pass locally before PR creation. The release tag must not be
created until CI passes on the merged main branch.

## Release

The target release is `0.6.1` / `v0.6.1`. Release preparation updates
`pyproject.toml`, `uv.lock`, `README.md`, onboarding pins, diagnostics tests,
CI wheel smoke expectations, and version-sensitive tests. After merge, publish
the tag and verify:

```powershell
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp --version
```

The expected output is:

```text
papergraph-mcp 0.6.1
```
