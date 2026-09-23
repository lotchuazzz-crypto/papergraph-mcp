"""Offline, literal-expectation resolver acceptance; never contacts providers."""
from __future__ import annotations

import copy
import argparse
import json
from collections import Counter
from pathlib import Path

from papergraph.reference_assessment import rank_candidates_v2, select_v2
from papergraph.reference_identity import group_reference_records, normalize_identifier
from papergraph.reference_query import build_query_v2

CASES_PATH = Path(__file__).resolve().parents[1] / "tests/fixtures/reference_quality/cases.json"


def canonical(items):
    return sorted(items, key=lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False))


def evaluate(case):
    query = build_query_v2(case["blocked"])
    for key, expected in case["expected_query"].items():
        assert query[key] == expected, (key, query[key], expected)
    if "normalization" in case:
        item = case["normalization"]
        actual = normalize_identifier(item["raw"], item["kind"])
        for key, expected in case["expected_normalization"].items():
            assert actual[key] == expected, (key, actual[key], expected)
    providers = case["provider_results"]
    groups = group_reference_records(providers)
    projection = [{"identifiers": g["identifiers"], "conflict_codes": sorted({c["code"] for c in g["conflicts"]})} for g in groups]
    assert canonical(projection) == canonical(case["expected_groups"]), projection
    result = rank_candidates_v2(query, providers, case["max_candidates"])
    candidates = [{"confidence": c["confidence"], "reason_codes": c["assessment"]["reason_codes"],
                   "eligible": c["assessment"]["auto_selection"]["eligible"]} for c in result["candidates"]]
    assert candidates == case["expected_candidates"], candidates
    eligible = select_v2(result)["eligible"]
    assert eligible == case["expected_eligible"], result
    if case["safety_negative"]:
        assert not eligible, "Unsafe automatic selection"
    if "expected_boundaries" in case:
        assert [b["kind"] for b in result["boundaries"]] == case["expected_boundaries"]
    # Reverse providers, records, and both independently; compare the full payload.
    for reverse_providers, reverse_records in [(True, False), (False, True), (True, True)]:
        permuted = copy.deepcopy(providers)
        if reverse_providers:
            permuted.reverse()
        if reverse_records:
            for provider in permuted:
                provider["records"].reverse()
        assert group_reference_records(permuted) == groups
        assert rank_candidates_v2(query, permuted, case["max_candidates"]) == result
    return eligible


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--examples-output', type=Path)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures, unsafe = [], 0
    for case in cases:
        # Count unsafe outcomes independently of expectation assertions.
        eligible = select_v2(rank_candidates_v2(build_query_v2(case["blocked"]), case["provider_results"], case["max_candidates"]))["eligible"]
        unsafe += bool(case["safety_negative"] and eligible)
        try:
            evaluate(case)
        except (AssertionError, ValueError, TypeError, KeyError) as error:
            failures.append({"name": case["name"], "detail": str(error)})
    print(json.dumps({"total": len(cases), "passed": len(cases)-len(failures),
        "categories": dict(Counter(c["category"] for c in cases)),
        "safety_negative_total": sum(c["safety_negative"] for c in cases),
        "false_selections": unsafe, "failures": failures}, indent=2, ensure_ascii=False))
    if args.examples_output and not failures and not unsafe:
        with args.examples_output.open('w' if args.overwrite else 'x', encoding='utf-8') as stream:
            stream.write(json.dumps(examples(cases), indent=2, ensure_ascii=False) + '\n')
    return int(bool(failures or unsafe))


def examples(cases):
    return {case['name']: rank_candidates_v2(build_query_v2(case['blocked']), case['provider_results'], case['max_candidates'])
            for case in cases if case['name'] in {'exact_arxiv', 'contradictory_bridge', 'doi_only'}}


if __name__ == "__main__":
    raise SystemExit(main())
