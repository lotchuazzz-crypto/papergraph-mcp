"""Render the saved citation graph without network calls or filesystem writes."""
def render_expansion(run: dict) -> str:
    def clean(value):
        from papergraph.reading_report import _text
        return _text(value)
    lines = ["# Reference Expansion", "", f"Run: `{run['run_id']}`", "",
             f"State: {run['state']} ({run.get('reason') or 'within approved policy'})", "",
             f"Policy: depth {run['policy']['max_depth']}; new papers {run['usage']['new_papers']}/{run['policy']['max_new_papers']}; searches {run['usage']['searches']}/{run['policy']['max_searches']}; edges {run['usage']['edges']}/{run['policy']['max_edges']}.", "",
             "This report follows extracted citation evidence within the approved limits. It does not verify proofs or establish complete mathematical dependencies.", "", "## Reference tree", ""]
    seen = set()
    nodes = {n["node_id"]: n for n in run["nodes"]}

    def visit(pid, depth, ancestors):
        indent = "  " * depth
        if pid in ancestors:
            lines.append(f"{indent}- `{pid}` (cycle)")
            return
        if pid in seen:
            lines.append(f"{indent}- `{pid}` (shared target; see earlier entry)")
            return
        seen.add(pid)
        lines.append(f"{indent}- `{pid}` ({nodes[pid]['discovery']})")
        for edge in sorted((e for e in run["edges"] if e["source"] == pid), key=lambda e: e["edge_id"]):
            choice = edge.get("decision", {}).get("kind", "pending")
            reasons = ", ".join(edge.get("decision", {}).get("reason_codes", []))
            lines.append(f"{indent}  - `{edge['edge_id']}`: {edge['state']}; {choice}; {clean(edge.get('reason') or reasons)}")
            for evidence in edge["evidence"]:
                lines.append(f"{indent}    - Evidence: {clean(evidence.get('raw_text') or evidence.get('id') or evidence)} (source: {clean(evidence.get('source_file') or evidence.get('id') or 'saved evidence')})")
            search = edge.get("search") or {}
            for candidate in search.get("candidates", []):
                assessment = candidate.get("assessment")
                if assessment:
                    lines.append(f"{indent}    - Source status: {clean(assessment['source_status'])}; reason: {clean(', '.join(assessment['reason_codes']))}")
            actions = sorted({a for b in search.get("boundaries", []) for a in b.get("next_actions", [])})
            if actions:
                lines.append(f"{indent}    - Next actions: {clean(', '.join(actions))}")
            if edge.get("target_node"):
                visit(edge["target_node"], depth + 2, ancestors | {pid})
    for root in run["roots"]:
        visit(root, 0, set())
    lines.extend(["", "## Next actions", ""])
    for action in run["next_actions"]:
        lines.append(f"- `{action['run_id']}` / `{action.get('edge_id', action.get('paper_id'))}`: {action['action']} ({clean(action['reason'])})")
    if run["state"] == "ready":
        lines.append("- Advance this run to continue saved work.")
    if run["state"] == "paused":
        lines.append("- Review the stop reason; explicitly increase the exhausted budget or resume a user pause.")
    lines.extend(["", "## Attempts", ""])
    for attempt in run["attempts"]:
        lines.append(f"- `{attempt['edge_id']}`: {attempt['kind']} / {attempt['phase']}; {clean(attempt.get('error', ''))}")
    return "\n".join(line.rstrip() for line in lines).rstrip() + "\n"
