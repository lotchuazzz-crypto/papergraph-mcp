import json
from collections import Counter
import pytest
from scripts.reproduce_reference_quality import CASES_PATH, evaluate, examples

CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_declared_reference_quality(case):
    evaluate(case)


def test_corpus_coverage():
    assert len(CASES) >= 40
    assert len({case["name"] for case in CASES}) == len(CASES)
    counts = Counter(case["category"] for case in CASES)
    for category, minimum in {"query_layouts": 10, "identifiers": 10, "grouping_order": 6,
                              "ranking_conflicts": 6, "provider_failures": 4, "automation_boundaries": 4}.items():
        assert counts[category] >= minimum


def test_documented_examples_are_reproducible():
    path = CASES_PATH.parents[3] / 'docs/examples/reference-search-example.json'
    assert json.loads(path.read_text(encoding='utf-8')) == examples(CASES)
