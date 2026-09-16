"""Workspace starter planning and bootstrap artifact rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from papergraph.arxiv import (
    prepare_arxiv_project,
    validate_arxiv_request,
)
from papergraph.identity import paper_id_from_arxiv
from papergraph.project import load_project


STARTER_SCHEMA_VERSION = 1
STARTER_SUMMARY_NAME = "START_HERE.md"
STARTER_MANIFEST_NAME = "papergraph-starter-manifest.json"


def plan_starter_project(
    *,
    workspace_path: str | Path,
    artifact_dir: str | Path | None,
    papers: list[dict],
    project_title: str | None = None,
    focus: str | None = None,
    target_result_id: str | None = None,
    create_queue: bool = True,
    create_session: bool = True,
    max_candidates: int = 5,
    overwrite: bool = False,
) -> dict:
    del focus, max_candidates, overwrite
    workspace_text = _path_text(workspace_path)
    artifact_text = _path_text(artifact_dir) if artifact_dir is not None else None
    planned_papers = [_normalize_paper_input(paper) for paper in papers]
    blocking_issues = _arxiv_blocking_issues(planned_papers)
    if blocking_issues:
        return {
            "starter_schema_version": STARTER_SCHEMA_VERSION,
            "status": "blocked",
            "action": blocking_issues[0]["action"],
            "workspace_path": workspace_text,
            "artifact_dir": artifact_text,
            "project_title": _project_title(project_title),
            "paper_inputs": planned_papers,
            "planned_papers": [],
            "planned_artifacts": [],
            "planned_state_changes": [],
            "warnings": [],
            "blocking_issues": blocking_issues,
        }
    _validate_distinct_paper_ids(planned_papers)

    planned_artifacts = [
        {"kind": "starter_summary", "path": STARTER_SUMMARY_NAME},
        {"kind": "starter_manifest", "path": STARTER_MANIFEST_NAME},
    ]
    for paper in planned_papers:
        planned_artifacts.append(
            {
                "kind": "reading_report",
                "paper_id": paper["paper_id"],
                "path": _reading_report_name(paper["paper_id"]),
            }
        )
    if len(planned_papers) >= 2:
        planned_artifacts.append(
            {
                "kind": "cross_paper_reading_plan",
                "path": "cross-paper-reading-plan.md",
            }
        )

    planned_state_changes = [{"kind": "open_workspace", "path": workspace_text}]
    planned_state_changes.extend(
        {"kind": "add_paper", "paper_id": paper["paper_id"]}
        for paper in planned_papers
    )
    if create_queue and target_result_id:
        planned_state_changes.append(
            {"kind": "create_reading_queue", "target_result_id": target_result_id}
        )
    if create_session and planned_papers:
        planned_state_changes.append(
            {
                "kind": "create_reading_session",
                "paper_id": planned_papers[0]["paper_id"],
            }
        )

    return {
        "starter_schema_version": STARTER_SCHEMA_VERSION,
        "status": "ready",
        "action": "bootstrap_reading_project",
        "workspace_path": workspace_text,
        "artifact_dir": artifact_text,
        "project_title": _project_title(project_title),
        "paper_inputs": planned_papers,
        "planned_papers": planned_papers,
        "planned_artifacts": planned_artifacts,
        "planned_state_changes": planned_state_changes,
        "warnings": [],
        "blocking_issues": [],
    }


def bootstrap_reading_project(
    workspace,
    *,
    workspace_path: str | Path,
    artifact_dir: str | Path,
    papers: list[dict],
    project_title: str | None = None,
    focus: str | None = None,
    target_result_id: str | None = None,
    create_queue: bool = True,
    create_session: bool = True,
    max_candidates: int = 5,
    overwrite: bool = False,
) -> dict:
    del focus
    artifact_path = Path(artifact_dir)
    artifact_path.mkdir(parents=True, exist_ok=True)
    workspace_text = _path_text(workspace_path)
    title = _project_title(project_title)

    planned_papers = [_normalize_paper_input(paper) for paper in papers]
    _validate_distinct_paper_ids(planned_papers)
    for paper in planned_papers:
        _import_planned_paper(workspace, paper)

    existing_papers = workspace.list_papers()
    paper_ids = [paper["paper_id"] for paper in existing_papers]
    artifacts = []
    warnings = []
    paper_maps = []

    for filename in (STARTER_SUMMARY_NAME, STARTER_MANIFEST_NAME):
        _validate_output_path(artifact_path / filename, overwrite)

    report_payloads = []
    for paper_id in paper_ids:
        report = workspace.export_paper_reading_report(
            paper_id,
            max_candidates=max_candidates,
        )
        report_path = artifact_path / _reading_report_name(paper_id)
        _validate_output_path(report_path, overwrite)
        report_path.write_text(report["markdown"], encoding="utf-8")
        artifacts.append(
            _artifact_record("reading_report", report_path, artifact_path, paper_id)
        )
        report_payloads.append(report)
        paper_maps.append(report["paper_map"])
        warnings.extend(report.get("warnings", []))

    cross_plan = None
    if len(paper_ids) >= 2:
        cross_plan = workspace.export_cross_paper_reading_plan(
            paper_ids,
            max_candidates_per_paper=min(max_candidates, 20),
        )
        plan_path = artifact_path / "cross-paper-reading-plan.md"
        _validate_output_path(plan_path, overwrite)
        plan_path.write_text(cross_plan["markdown"], encoding="utf-8")
        artifacts.append(
            _artifact_record("cross_paper_reading_plan", plan_path, artifact_path)
        )
        warnings.extend(cross_plan.get("warnings", []))

    selected_target = target_result_id or _select_target_result(paper_maps)
    reading_queue = None
    reading_session = None
    if create_queue and selected_target:
        reading_queue = workspace.create_reading_queue(selected_target)
    if create_session and paper_ids:
        reading_session = workspace.create_reading_session(
            paper_ids[0],
            target_result_id=selected_target,
        )

    next_commands = _next_commands(workspace_text, paper_ids)
    summary_markdown = _render_start_here(
        title=title,
        workspace_path=workspace_text,
        papers=existing_papers,
        paper_maps=paper_maps,
        artifacts=artifacts,
        reading_queue=reading_queue,
        reading_session=reading_session,
        warnings=warnings,
        next_commands=next_commands,
    )
    summary_path = artifact_path / STARTER_SUMMARY_NAME
    summary_path.write_text(summary_markdown, encoding="utf-8")
    summary_record = _artifact_record("starter_summary", summary_path, artifact_path)

    manifest_path = artifact_path / STARTER_MANIFEST_NAME
    manifest_payload = {
        "starter_schema_version": STARTER_SCHEMA_VERSION,
        "workspace_path": workspace_text,
        "artifact_dir": str(artifact_path),
        "project_title": title,
        "paper_ids": paper_ids,
        "artifacts": [summary_record, *artifacts],
        "next_commands": next_commands,
        "warnings": warnings,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest_record = _artifact_record("starter_manifest", manifest_path, artifact_path)

    final_artifacts = [summary_record, manifest_record, *artifacts]
    return {
        "starter_schema_version": STARTER_SCHEMA_VERSION,
        "status": "written",
        "workspace": {
            "path": workspace_text,
            "schema_version": _workspace_schema_version(workspace),
            "paper_count": len(paper_ids),
        },
        "papers": existing_papers,
        "paper_maps": paper_maps,
        "artifacts": final_artifacts,
        "reading_queue": reading_queue,
        "reading_session": reading_session,
        "warnings": warnings,
        "next_commands": next_commands,
    }


def _normalize_paper_input(paper: dict) -> dict:
    kind = str(paper.get("kind", "")).strip()
    if kind not in {"arxiv", "local_tex", "pdf"}:
        raise ValueError(f"Unsupported paper input kind: {kind!r}")
    if kind == "arxiv":
        raw_input = _required_text(paper.get("input"), "input")
        validation = validate_arxiv_request(raw_input)
        selected_id = validation.get("selected_id")
        return {
            "kind": "arxiv",
            "input": raw_input,
            "main_file": paper.get("main_file"),
            "refresh": bool(paper.get("refresh", False)),
            "paper_id": f"arxiv:{selected_id or raw_input}",
            "validation": validation,
        }
    field = "paper_id"
    paper_id = _required_text(paper.get(field), f"{field} is required for {kind} inputs")
    normalized = {
        "kind": kind,
        "paper_id": paper_id,
        "path": _path_text(_required_text(paper.get("path"), "path")),
    }
    return normalized


def _arxiv_blocking_issues(papers: list[dict]) -> list[dict]:
    issues = []
    for paper in papers:
        if paper["kind"] != "arxiv":
            continue
        validation = paper["validation"]
        if validation.get("action") != "safe_to_load" or not validation.get("selected_id"):
            issues.append(
                {
                    "kind": "arxiv_conflict",
                    "action": validation.get("action", "inspect_error"),
                    "input": paper["input"],
                    "validation": validation,
                }
            )
    return issues


def _import_planned_paper(workspace, paper: dict) -> None:
    if paper["kind"] == "local_tex":
        project = load_project(paper["path"])
        workspace.import_project(
            paper["paper_id"],
            "local",
            paper["path"],
            None,
            project,
        )
        return
    if paper["kind"] == "pdf":
        workspace.import_pdf(paper["path"], paper["paper_id"])
        return
    if paper["kind"] == "arxiv":
        validation = paper["validation"]
        selected_id = validation["selected_id"]
        prepared = prepare_arxiv_project(
            selected_id,
            paper.get("main_file"),
            paper.get("refresh", False),
        )
        paper_id, source_version = paper_id_from_arxiv(prepared.arxiv_id)
        workspace.import_project(
            paper_id,
            "arxiv",
            paper_id.removeprefix("arxiv:"),
            source_version,
            load_project(prepared.main_file),
        )
        return
    raise ValueError(f"Unsupported paper input kind: {paper['kind']!r}")


def _validate_distinct_paper_ids(papers: list[dict]) -> None:
    paper_ids = [paper["paper_id"] for paper in papers]
    if len(paper_ids) != len(set(paper_ids)):
        raise ValueError("paper_ids must be distinct")


def _validate_output_path(path: Path, overwrite: bool) -> None:
    if path.exists() and path.is_dir():
        raise ValueError(f"Output path is a directory: {path}")
    if path.exists() and not overwrite:
        raise ValueError(f"Output path already exists: {path}")


def _render_start_here(
    *,
    title: str,
    workspace_path: str,
    papers: list[dict],
    paper_maps: list[dict],
    artifacts: list[dict],
    reading_queue: dict | None,
    reading_session: dict | None,
    warnings: list[dict],
    next_commands: list[str],
) -> str:
    lines = [
        f"# PaperGraph Reading Project: {title}",
        "",
        "## Project",
        "",
        f"- Workspace: `{workspace_path}`",
        f"- Papers: {len(papers)}",
        "",
        "## Papers Loaded",
        "",
    ]
    if not papers:
        lines.append("- No papers are loaded yet.")
    for paper, paper_map in zip(papers, paper_maps):
        summary = paper_map.get("summary", {})
        lines.extend(
            [
                f"- `{paper['paper_id']}`",
                f"  - Title: {paper.get('title') or 'Untitled'}",
                f"  - Source type: `{paper.get('source_type')}`",
                f"  - Evidence status: `{summary.get('evidence_status', 'limited')}`",
                f"  - Results: {paper.get('theorem_count', 0)}",
            ]
        )
    lines.extend(
        [
            "",
            "## Start Here",
            "",
            "- Open the first Reading Report, then inspect the Paper Map warnings.",
            "",
            "## Reading Artifacts",
            "",
        ]
    )
    for artifact in artifacts:
        lines.append(f"- `{artifact['kind']}`: [{artifact['path']}]({artifact['path']})")
    lines.extend(["", "## Reading Queue And Session", ""])
    if reading_queue is None and reading_session is None:
        lines.append("- No reading queue or session was created.")
    if reading_queue is not None:
        lines.append(f"- Queue: `{reading_queue['queue_id']}`")
    if reading_session is not None:
        lines.append(f"- Session: `{reading_session['session_id']}`")
    lines.extend(["", "## Evidence Quality", ""])
    if not warnings:
        lines.append("- No starter-level warnings.")
    for warning in warnings:
        lines.append(f"- `{warning.get('kind', 'warning')}`: {warning.get('message', '')}")
    lines.extend(
        [
            "",
            "## External Reading Risks",
            "",
            "- Review Paper Map and Cross-Paper Reading Plan risk sections before importing external papers.",
            "",
            "## Evidence Boundaries",
            "",
            "- PaperGraph does not verify proofs.",
            "- PaperGraph does not infer hidden mathematical prerequisites.",
            "- PaperGraph does not perform semantic theorem matching.",
            "",
            "## Next Commands",
            "",
            "```powershell",
            *next_commands,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _select_target_result(paper_maps: list[dict]) -> str | None:
    for paper_map in paper_maps:
        candidates = paper_map.get("main_result_candidates", [])
        if candidates:
            return candidates[0].get("result_id")
    return None


def _next_commands(workspace_path: str, paper_ids: list[str]) -> list[str]:
    commands = [
        f"papergraph-mcp get-paper-map --workspace {workspace_path} --paper-id {paper_id}"
        for paper_id in paper_ids
    ]
    if paper_ids:
        commands.append(
            "papergraph-mcp export-paper-reading-report "
            f"--workspace {workspace_path} --paper-id {paper_ids[0]}"
        )
    return commands


def _artifact_record(
    kind: str,
    path: Path,
    artifact_dir: Path,
    paper_id: str | None = None,
) -> dict:
    record: dict[str, Any] = {
        "kind": kind,
        "path": path.relative_to(artifact_dir).as_posix(),
        "bytes": len(path.read_bytes()),
    }
    if paper_id is not None:
        record["paper_id"] = paper_id
    return record


def _reading_report_name(paper_id: str) -> str:
    slug = paper_id.replace(":", "-").replace("/", "-").replace(".", "-")
    return f"{slug}-reading-report.md"


def _path_text(path: str | Path) -> str:
    return str(path)


def _project_title(project_title: str | None) -> str:
    if project_title is None or not str(project_title).strip():
        return "PaperGraph Reading Project"
    return str(project_title).strip()


def _required_text(value, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} cannot be empty")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _workspace_schema_version(workspace) -> int:
    row = workspace._connection.execute(
        "SELECT value FROM workspace_meta WHERE key = 'schema_version'"
    ).fetchone()
    return int(row[0])
