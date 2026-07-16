"""Field-level semantic result comparator."""

from typing import Any


def _indexed(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(row["schema_family"], row["rental_id"]): row for row in rows}


def compare_results(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_rows = _indexed(expected["canonical_rows"])
    actual_rows = _indexed(actual["canonical_rows"])
    missing = sorted([list(identity) for identity in expected_rows.keys() - actual_rows.keys()])
    extra = sorted([list(identity) for identity in actual_rows.keys() - expected_rows.keys()])
    field_mismatches = []
    for identity in sorted(expected_rows.keys() & actual_rows.keys()):
        left = expected_rows[identity]
        right = actual_rows[identity]
        for field in sorted(left.keys() | right.keys()):
            if left.get(field) != right.get(field):
                field_mismatches.append(
                    {
                        "identity": list(identity),
                        "field": field,
                        "expected": left.get(field),
                        "actual": right.get(field),
                    }
                )
    invariant_mismatches = []
    for field in ("reconciliation", "object_history", "state_hash"):
        if expected.get(field) != actual.get(field):
            invariant_mismatches.append(field)
    passed = not missing and not extra and not field_mismatches and not invariant_mismatches
    return {
        "result": "PASS" if passed else "FAIL",
        "missing_identities": missing,
        "extra_identities": extra,
        "field_mismatches": field_mismatches[:20],
        "invariant_mismatches": invariant_mismatches,
    }
