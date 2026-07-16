import csv
import json
from collections import Counter
from pathlib import Path

from benchmark.gate0.spike.build_inventory import classify_incident, parse_publication_period

ROOT = Path(__file__).parents[1]
EVIDENCE = ROOT / "docs" / "gate0" / "reliability-reference"


def test_parse_publication_period_supports_two_and_four_digit_years():
    assert parse_publication_period(
        "usage-stats/01aJourneyDataExtract10Jan16-23Jan16.csv"
    ) == ("2016-01-10", "2016-01-23")
    assert parse_publication_period(
        "usage-stats/444JourneyDataExtract17May2026-31May2026.csv"
    ) == ("2026-05-17", "2026-05-31")


def test_observed_incidents_are_named_without_constructed_replay_claims():
    assert classify_incident("classic_missing_end_station_id", "325JourneyData.csv") == (
        "missing_end_station_identifier"
    )
    assert classify_incident("nextgen_station_names_first", "423JourneyData.csv") == (
        "reordered_header"
    )
    assert classify_incident("nextgen_standard", "444JourneyDataExtract.csv") == (
        "partial_boundary_date"
    )
    assert classify_incident(None, "historical.zip") == "none"


def test_committed_inventory_has_complete_retained_evidence_and_unknown_nonretained_fields():
    with (EVIDENCE / "source-incident-inventory.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    retained = [row for row in rows if row["local_retained"] == "true"]
    nonretained = [row for row in rows if row["local_retained"] == "false"]

    assert len(retained) == 148
    assert all(row["content_sha256"] and row["raw_rows"] for row in retained)
    assert all(row["reconciliation_delta"] == "0" for row in retained)
    assert all(not row["content_sha256"] and not row["raw_rows"] for row in nonretained)
    assert Counter(row["header_variant_key"] for row in retained) == {
        "classic_standard": 36,
        "classic_missing_end_station_id": 1,
        "nextgen_standard": 100,
        "nextgen_station_names_first": 8,
        "nextgen_interleaved_station_order": 3,
    }
    assert sum(int(row["raw_rows"]) for row in retained) == 41_376_421


def test_listing_comparison_keeps_historical_count_and_records_new_cutoff():
    comparison = json.loads((EVIDENCE / "listing-comparison.json").read_text(encoding="utf-8"))

    assert comparison["historical_snapshot"]["object_count"] == 482
    assert comparison["historical_snapshot"]["interpretation"].startswith("retained historical")
    assert comparison["refreshed_snapshot"]["observed_at_utc"].startswith("2026-07-16T")
