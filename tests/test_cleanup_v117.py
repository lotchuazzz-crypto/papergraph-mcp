"""Guard the intentionally narrow v1.1.7 cleanup."""

import ast
import importlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_report_format_preserves_existing_values():
    assert importlib.util.find_spec("papergraph.report_format") is not None
    formatting = importlib.import_module("papergraph.report_format")

    assert formatting.source_position(None) == (0, 0, 0, "")
    assert formatting.source_position(
        {"page": "2", "block_index": 3, "start_offset": "4", "span_id": "s"}
    ) == (2, 3, 4, "s")
    assert formatting.compact_json(None) == "`None`"
    assert formatting.compact_json({"b": 2, "a": 1}) == '`{"a": 1, "b": 2}`'
    assert formatting.code_or_none(None) == "`None`"
    assert formatting.code_or_none("result-1") == "`result-1`"


def test_providers_share_optional_text_cleaning():
    base = importlib.import_module("papergraph.reference_providers.base")
    assert hasattr(base, "clean_text")
    assert base.clean_text(None) is None
    assert base.clean_text("  DOI  ") == "DOI"
    assert base.clean_text(" \t ") is None


def test_confirmed_dead_helpers_are_removed():
    expected_absent = {
        "workspace.py": {"_latest_reference_search"},
    }
    for filename, absent in expected_absent.items():
        tree = ast.parse((ROOT / "src" / "papergraph" / filename).read_text(encoding="utf-8"))
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        names.update(
            target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        )
        assert not (names & absent), f"{filename}: {names & absent}"


def test_public_schema_marker_remains_available():
    reference_search = importlib.import_module("papergraph.reference_search")
    assert reference_search.SEARCH_SCHEMA_VERSION == 2
