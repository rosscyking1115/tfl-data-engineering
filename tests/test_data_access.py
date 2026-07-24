"""data_access (app/data_access.py) — the date-key helper and a real loader over committed Parquet."""

import data_access as da
import pandas as pd


def test_key_converts_date_to_yyyymmdd():
    assert da._key("2024-01-02") == 20240102
    assert da._key(pd.Timestamp("2026-06-09")) == 20260609


def test_station_names_loads_committed_parquet():
    names = da.station_names()
    assert isinstance(names, list) and len(names) > 100
    assert all(isinstance(n, str) for n in names[:20])


def test_date_bounds_returns_ordered_pair():
    lo, hi = da.date_bounds()
    assert pd.Timestamp(lo) <= pd.Timestamp(hi)


def test_certified_evidence_has_locked_adr0009_envelope():
    evidence = da.certified_evidence()
    certificate = evidence["certificate"]
    assert certificate["adr_id"] == "ADR-0009"
    assert certificate["claim_class"] == "observed_association"
    assert certificate["primary_specification"]["grain"] == "station × day"
    assert certificate["primary_specification"]["min_expected_departures"] == 5
    assert evidence["headline"]["median_ratio"] == 1.423
