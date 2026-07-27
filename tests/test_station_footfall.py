"""Station footfall ingestion guards (ADR-0013).

The non-obvious parts of this source are the ones worth testing: the header-case drift
across eras, the BOM in the older files, the overlapping published files, and the
idempotency of the weekly upsert.
"""

import io

import pandas as pd
import pytest
import station_footfall as sf

# 2019-2022 spell it DayOFWeek and carry a UTF-8 BOM; 2023 onward use DayOfWeek.
OLD_ERA = "﻿TravelDate,DayOFWeek,Station,EntryTapCount,ExitTapCount\n20220103,Monday,Bank,10,9\n"
NEW_ERA = "TravelDate,DayOfWeek,Station,EntryTapCount,ExitTapCount\n20240103,Wednesday,Bank,20,19\n"


def _parse(csv_text: str) -> pd.DataFrame:
    """Exercise the same normalisation fetch() applies, without the network."""
    raw = pd.read_csv(io.BytesIO(csv_text.encode("utf-8")), encoding="utf-8-sig")
    lookup = {c.strip().lower(): c for c in raw.columns}
    missing = [w for w in sf.REQUIRED_COLUMNS if w not in lookup]
    assert not missing, f"schema gate would fire on {missing}"
    df = raw[[lookup[w] for w in sf.REQUIRED_COLUMNS]]
    df.columns = list(sf.REQUIRED_COLUMNS.values())
    return df


# ------------------------------------------------------------------ schema drift

@pytest.mark.parametrize(("csv_text", "expected_day"), [(OLD_ERA, "Monday"), (NEW_ERA, "Wednesday")])
def test_both_header_eras_normalise_to_one_shape(csv_text, expected_day):
    """DayOFWeek and DayOfWeek must land in the same column; the BOM must not leak."""
    df = _parse(csv_text)
    assert list(df.columns) == ["date_key", "day_of_week", "rail_station", "entry_taps", "exit_taps"]
    assert df["day_of_week"].iloc[0] == expected_day
    assert df["rail_station"].iloc[0] == "Bank"


def test_renamed_column_is_a_loud_failure_not_a_guess():
    """A drifted source must fail the schema gate rather than be read positionally."""
    drifted = "TravelDate,DayOfWeek,StationName,EntryTapCount,ExitTapCount\n20240103,Wednesday,Bank,20,19\n"
    with pytest.raises(AssertionError):
        _parse(drifted)


def test_backfill_keys_exclude_the_overlapping_file():
    """StationFootfall_2024_2025 spans 20240101-20251227 and would double-count two years."""
    assert not any("2024_2025" in k for k in sf.BACKFILL_KEYS)
    assert sf.CURRENT_KEY in sf.BACKFILL_KEYS


# ------------------------------------------------------------------ quality gates

def _rows(date_keys, stations, entries=1, exits=1) -> pd.DataFrame:
    return pd.DataFrame({
        "date_key": date_keys,
        "day_of_week": ["Monday"] * len(date_keys),
        "rail_station": stations,
        "entry_taps": [entries] * len(date_keys),
        "exit_taps": [exits] * len(date_keys),
    })


def test_quality_gate_rejects_duplicate_keys():
    dupes = _rows([20240103, 20240103], ["Bank", "Bank"])
    with pytest.raises(SystemExit, match="duplicate"):
        sf.check_quality(dupes)


def test_quality_gate_rejects_negative_taps():
    with pytest.raises(SystemExit, match="negative"):
        sf.check_quality(_rows([20240103], ["Bank"], entries=-1))


def test_quality_gate_rejects_empty_series():
    with pytest.raises(SystemExit, match="no footfall rows"):
        sf.check_quality(_rows([], []))


# ------------------------------------------------------------------ idempotency

def test_upsert_run_twice_is_identical(tmp_path, monkeypatch):
    """The weekly refresh re-run on the same input must not double-count."""
    monkeypatch.setattr(sf, "OUT", tmp_path / "footfall.parquet")
    new = _rows([20240103, 20240104], ["Bank", "Bank"])
    sf.upsert(new).to_parquet(sf.OUT, index=False)
    once = sf.upsert(new)
    once.to_parquet(sf.OUT, index=False)
    twice = sf.upsert(new)
    assert len(once) == len(twice) == 2


def test_upsert_replaces_a_revised_day_and_keeps_history(tmp_path, monkeypatch):
    """A re-published day must REPLACE its rows, leaving untouched dates alone."""
    monkeypatch.setattr(sf, "OUT", tmp_path / "footfall.parquet")
    _rows([20240103, 20240104], ["Bank", "Bank"]).to_parquet(sf.OUT, index=False)
    revised = _rows([20240104], ["Bank"], entries=999)
    out = sf.upsert(revised).sort_values("date_key").reset_index(drop=True)
    assert len(out) == 2                                     # no accumulation
    assert out.loc[out.date_key == 20240103, "entry_taps"].iloc[0] == 1    # history intact
    assert out.loc[out.date_key == 20240104, "entry_taps"].iloc[0] == 999  # revision applied
