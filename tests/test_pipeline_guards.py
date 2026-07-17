"""Pipeline guards (rigor-pass Area 4): idempotency + injected errors, on fixtures.

A reliable pipeline KNOWS when it's wrong: re-running must not double-load,
and corrupt input must fail loudly instead of silently passing through.
"""

import live_snapshot as ls
import pandas as pd
import pytest


def _snap(day: str, values: list[int]) -> pd.DataFrame:
    return pd.DataFrame({
        "snapshot_date": [day] * len(values),
        "line_id": [f"l{i}" for i in range(len(values))],
        "status_severity": values,
    })


# ------------------------------------------------------------------ idempotency

def test_upsert_run_twice_is_identical(tmp_path):
    """The daily job re-run on the same input must produce byte-identical state."""
    path = tmp_path / "snap.parquet"
    df = _snap("2026-07-13", [10, 9, 6])
    ls.upsert(path, df.copy(), "snapshot_date", "2026-07-13")
    once = pd.read_parquet(path)
    ls.upsert(path, df.copy(), "snapshot_date", "2026-07-13")
    twice = pd.read_parquet(path)
    pd.testing.assert_frame_equal(once, twice)
    assert len(twice) == 3  # no double-load


def test_upsert_injected_duplicate_day_replaces_not_appends(tmp_path):
    """Injected error: a re-collected day with different content must REPLACE the old
    rows (last write wins), never accumulate duplicates."""
    path = tmp_path / "snap.parquet"
    ls.upsert(path, _snap("2026-07-13", [10, 10, 10]), "snapshot_date", "2026-07-13")
    ls.upsert(path, _snap("2026-07-13", [6, 9]), "snapshot_date", "2026-07-13")
    out = pd.read_parquet(path)
    assert len(out) == 2
    assert sorted(out["status_severity"]) == [6, 9]


def test_upsert_preserves_other_days(tmp_path):
    path = tmp_path / "snap.parquet"
    ls.upsert(path, _snap("2026-07-12", [10]), "snapshot_date", "2026-07-12")
    ls.upsert(path, _snap("2026-07-13", [9]), "snapshot_date", "2026-07-13")
    out = pd.read_parquet(path)
    assert sorted(out["snapshot_date"].unique()) == ["2026-07-12", "2026-07-13"]


# --------------------------------------------------------------- injected errors

def test_quality_gate_fails_loudly_on_short_payload():
    """A truncated/partial API response must halt the run, not commit a bad snapshot."""
    with pytest.raises(SystemExit, match="quality gate"):
        ls.check_quality(100, 20)   # bikepoints far too few
    with pytest.raises(SystemExit, match="quality gate"):
        ls.check_quality(800, 3)    # lines far too few


def test_quality_gate_passes_normal_payload():
    ls.check_quality(798, 20)  # current production magnitudes


def test_fill_rate_survives_missing_dock_counts():
    """Regression for the 2026-07-11..13 cron outage: a bikepoint with a missing/corrupt
    dock count must produce NaN fill_rate, not crash .round() with object-dtype NA."""
    bp_df = pd.DataFrame({
        "n_bikes": [10, None, 5, 0],
        "n_docks": [20, 30, None, 0],   # None -> object dtype (the crash trigger); 0 docks
    })
    fill = ls.compute_fill_rate(bp_df)
    assert fill.iloc[0] == 0.5
    assert pd.isna(fill.iloc[1]) and pd.isna(fill.iloc[2]) and pd.isna(fill.iloc[3])


def test_malformed_bikepoint_payload_degrades_to_nulls_not_garbage():
    """A place with missing/corrupt additionalProperties must yield None counts (missing),
    never a fabricated number — the 'no data ≠ zero' principle at the parser level."""
    broken = {"id": "BikePoints_1", "commonName": "X", "additionalProperties": [
        {"key": "NbBikes", "value": "not-a-number"},
    ]}
    assert ls.as_int(ls.prop(broken, "NbBikes")) is None      # corrupt -> None
    assert ls.as_int(ls.prop(broken, "NbDocks")) is None      # absent  -> None
    assert ls.as_int(ls.prop({"id": "x"}, "NbBikes")) is None  # no properties at all
