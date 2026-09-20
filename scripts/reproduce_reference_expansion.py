"""Offline fixture runner; replaces only acquisition, never orchestration or parsing."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from papergraph.arxiv import ArxivProject
from papergraph.project import load_project
from papergraph.reference_expansion_report import render_expansion
from papergraph.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/reference_expansion"


def normalize(run):
    """Normalize IDs, times, timestamp-derived revisions and fixture-root paths."""
    replacements = {run["run_id"]: "expansion:fixture"}
    replacements.update({a["attempt_id"]: f"attempt:{i}" for i, a in enumerate(run["attempts"], 1)})
    def visit(value, key=None):
        if key in {"created_at", "timestamp"}:
            return 0
        if key == "fingerprint":
            return "fixture-source-revision"
        if key == "event_id" and value < 0:
            return -next(i for i, event in enumerate(run["events"], 1) if event["event_id"] == value)
        if isinstance(value, dict):
            return {k: visit(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [visit(v) for v in value]
        if isinstance(value, str):
            return replacements.get(value, value).replace(str(FIXTURES), "<fixtures>").replace(str(FIXTURES).replace("\\", "/"), "<fixtures>")
        return value
    return visit(run)


def reproduce(workspace_path):
    def acquire(arxiv_id, main_file, refresh):
        folder = {"2401.10002": "b", "2401.10003": "c"}[arxiv_id]
        root = FIXTURES / folder
        return ArxivProject(arxiv_id, root, root / "main.tex", True)
    with patch("papergraph.workspace.prepare_arxiv_project", acquire), patch(
        "httpx.Client.send", side_effect=AssertionError("Fixture must stay offline")
    ):
        ws = Workspace.open(workspace_path)
        try:
            ws.import_project("arxiv:2401.10001", "arxiv", "2401.10001", None,
                              load_project(FIXTURES / "a/main.tex"))
            run = ws.create_reference_expansion(["arxiv:2401.10001"], {"max_depth": 3})
            for _ in range(20):
                run = ws.advance_reference_expansion(run["run_id"], max_steps=10)
                if run["state"] != "ready":
                    break
            assert run["state"] == "completed" and run["usage"]["new_papers"] == 2
            return normalize(run)
        finally:
            ws.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true", help="Explicitly regenerate existing output artifacts")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="papergraph-fixture-") as temporary:
        run = reproduce(Path(temporary) / "workspace.sqlite3")
    for name, content in {
        "reference-expansion-example.json": json.dumps(run, indent=2, ensure_ascii=False) + "\n",
        "reference-expansion-example.md": render_expansion(run),
    }.items():
        with (args.output_dir / name).open("w" if args.overwrite else "x", encoding="utf-8") as stream:
            stream.write(content)
    print(json.dumps({"state": run["state"], "usage": run["usage"], "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
