"""Thin CLI and MCP surfaces for the shared Workspace expansion contract."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

from papergraph.reference_expansion_policy import LIMITS

COMMANDS = {prefix + "-reference-expansion" for prefix in
            ("create", "advance", "get", "decide", "pause", "cancel", "export")}
COMMANDS |= {"list-reference-expansions", "update-reference-expansion-policy"}


def register_tools(mcp, get_workspace, serialized):
    def call(method, **kwargs):
        try:
            return getattr(get_workspace(), method)(**kwargs)
        except (ValueError, KeyError, OSError, RuntimeError, sqlite3.DatabaseError) as exc:
            raise ToolError(str(exc)) from exc

    def workspace_create_reference_expansion(root_paper_ids: list[str], policy: dict | None = None) -> dict:
        """Save an approved finite expansion policy. Creation does not search or import."""
        return call("create_reference_expansion", root_paper_ids=root_paper_ids, policy=policy)

    def workspace_advance_reference_expansion(run_id: str, max_steps: int = 10, time_budget_seconds: int = 20) -> dict:
        """Execute the saved policy: search, download arXiv sources, import unique strong candidates and record resolutions without per-paper prompts, within approved budgets. Resume with the same run ID."""
        return call("advance_reference_expansion", run_id=run_id, max_steps=max_steps, time_budget_seconds=time_budget_seconds)

    def workspace_get_reference_expansion(run_id: str) -> dict:
        """Read saved graph, counts, decisions and continuation actions without network."""
        return call("get_reference_expansion", run_id=run_id)

    def workspace_list_reference_expansions(state: str | None = None) -> dict:
        """List saved expansion summaries, optionally filtered by state."""
        return call("list_reference_expansions", state=state)

    def workspace_decide_reference_expansion(run_id: str, edge_id: str, decision: dict) -> dict:
        """Record exactly one candidate_id, target, existing_paper_id, skip:true or retry:true. Advance separately to execute the approved choice."""
        return call("decide_reference_expansion", run_id=run_id, edge_id=edge_id, decision=decision)

    def workspace_update_reference_expansion_policy(run_id: str, limits: dict) -> dict:
        """Explicitly revise numeric budgets; cumulative usage is retained."""
        return call("update_reference_expansion_policy", run_id=run_id, limits=limits)

    def workspace_pause_reference_expansion(run_id: str) -> dict:
        """Pause scheduling after the active step. Advance explicitly to resume."""
        return call("pause_reference_expansion", run_id=run_id)

    def workspace_cancel_reference_expansion(run_id: str) -> dict:
        """Permanently stop this run, preserving imported papers and history."""
        return call("cancel_reference_expansion", run_id=run_id)

    def workspace_export_reference_expansion(run_id: str, format: str = "json") -> dict:
        """Return saved JSON or Markdown without writing client files or using network."""
        result = call("export_reference_expansion", run_id=run_id, format=format)
        return result if isinstance(result, dict) else {"expansion_schema_version": 1, "run_id": run_id, "format": format, "markdown": result}

    funcs = [value for key, value in list(locals().items()) if key.startswith("workspace_")]
    for function in funcs:
        # Control signals use an independent connection and must not queue behind
        # the long-running advance call's workspace-state lock.
        signal = function.__name__ in {"workspace_pause_reference_expansion", "workspace_cancel_reference_expansion"}
        mcp.tool()(function if signal else serialized(function))


def add_cli(subparsers):
    for command in sorted(COMMANDS):
        parser = subparsers.add_parser(command, help="Bounded reference expansion; advance executes approved automatic searches and imports.")
        parser.add_argument("--workspace", required=True)
        if command not in {"create-reference-expansion", "list-reference-expansions"}:
            parser.add_argument("--run-id", required=True)
        if command == "create-reference-expansion":
            parser.add_argument("--root-paper-id", action="append", required=True)
            parser.add_argument("--provider", action="append")
            parser.add_argument("--auto-select-policy", choices=("unique_strong_v1", "unique_strong_v2"), default="unique_strong_v2")
        if command in {"create-reference-expansion", "update-reference-expansion-policy"}:
            for key in LIMITS:
                parser.add_argument("--" + key.replace("_", "-"), type=int)
        if command == "advance-reference-expansion":
            parser.add_argument("--max-steps", type=int, default=10)
            parser.add_argument("--time-budget-seconds", type=int, default=20)
        if command == "decide-reference-expansion":
            parser.add_argument("--edge-id", required=True)
            parser.add_argument("--decision", required=True, help='JSON object, e.g. {"skip":true} or {"candidate_id":"..."}')
        if command == "list-reference-expansions":
            parser.add_argument("--state")
        if command == "export-reference-expansion":
            parser.add_argument("--format", choices=["json", "markdown"], default="json")
            parser.add_argument("--output")
            parser.add_argument("--overwrite", action="store_true")


def run_cli(args, workspace_class):
    ws = None
    try:
        ws = workspace_class.open(args.workspace)
        kwargs = {}
        if hasattr(args, "run_id"):
            kwargs["run_id"] = args.run_id
        if args.command in {"create-reference-expansion", "update-reference-expansion-policy"}:
            policy = {key: getattr(args, key) for key in LIMITS if getattr(args, key) is not None}
            if args.command == "create-reference-expansion":
                policy["auto_select_policy"] = args.auto_select_policy
                if args.provider:
                    policy["providers"] = args.provider
                kwargs.update(root_paper_ids=args.root_paper_id, policy=policy)
            else:
                kwargs["limits"] = policy
        if args.command == "advance-reference-expansion":
            kwargs.update(max_steps=args.max_steps, time_budget_seconds=args.time_budget_seconds)
        if args.command == "decide-reference-expansion":
            kwargs.update(edge_id=args.edge_id, decision=json.loads(args.decision))
        if args.command == "list-reference-expansions":
            kwargs["state"] = args.state
        if args.command == "export-reference-expansion":
            kwargs["format"] = args.format
        payload = getattr(ws, args.command.replace("-", "_"))(**kwargs)
        output = payload if isinstance(payload, str) else json.dumps(payload, indent=2, ensure_ascii=False)
        if getattr(args, "output", None):
            with Path(args.output).open("w" if args.overwrite else "x", encoding="utf-8") as stream:
                stream.write(output)
            print(json.dumps({"output": args.output, "run_id": args.run_id}))
        else:
            print(output)
    except (ValueError, KeyError, OSError, RuntimeError, sqlite3.DatabaseError) as exc:
        print(json.dumps({"status": "error", "command": args.command, "message": str(exc)}))
        raise SystemExit(1) from exc
    finally:
        if ws is not None:
            ws.close()
