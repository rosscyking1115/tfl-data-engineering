"""Journey-increment loader (ingestion/journey_increment.py) — fixtures, no network.

The forward path must aggregate correctly, dedupe, fail loudly on schema drift, and stay
idempotent at the date level.
"""

import hashlib

import journey_increment as ji
import pandas as pd
import pytest

HEADER = ('"Number","Start date","Start station number","Start station",'
          '"End date","End station number","End station","Bike number","Bike model",'
          '"Total duration (ms)"\n')


def _csv(tmp_path, rows: list[str]):
    p = tmp_path / "445JourneyDataExtract01Jun2026-15Jun2026.csv"
    p.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def _row(num, start, end, s_name="Alpha Road, Soho", e_name="Beta Square, Bank",
         model="CLASSIC", dur_ms=600000):
    return (f'"{num}","{start}","001","{s_name}","{end}","002","{e_name}",'
            f'"B1","{model}","{dur_ms}"')


BASE_ROWS = [
    _row(1, "2026-06-01 08:00", "2026-06-01 08:10"),
    _row(2, "2026-06-01 09:00", "2026-06-01 09:20", model="PBSC_EBIKE"),
    _row(3, "2026-06-02 08:00", "2026-06-02 08:30", s_name="Beta Square, Bank",
         e_name="Alpha Road, Soho"),
    _row(3, "2026-06-02 08:00", "2026-06-02 08:30"),  # duplicate Number -> must dedupe
] + [_row(100 + i, "2026-06-01 10:00", "2026-06-01 10:15") for i in range(1000)]


def test_aggregate_counts_dedupes_and_keys(tmp_path):
    flows, daily = ji.aggregate_file(_csv(tmp_path, BASE_ROWS))
    # 1003 unique journeys (dup Number dropped): 1002 on 06-01, 1 on 06-02
    assert int(daily["journeys"].sum()) == 1003
    assert daily.set_index("date_key")["journeys"].to_dict() == {20260601: 1002, 20260602: 1}
    assert int(daily["ebike_journeys"].sum()) == 1
    # departures reconcile to journeys; station_key = md5(collapsed name)
    assert int(flows["departures"].sum()) == 1003
    alpha = flows[(flows["station_name"] == "Alpha Road, Soho") & (flows["date_key"] == 20260601)]
    assert alpha["station_key"].iloc[0] == hashlib.md5(b"Alpha Road, Soho").hexdigest()
    assert int(alpha["departures"].iloc[0]) == 1002


def test_schema_gate_fails_loudly_on_drift(tmp_path):
    p = tmp_path / "446JourneyDataExtract16Jun2026-30Jun2026.csv"
    p.write_text('"Number","Start Date Renamed","Whatever"\n"1","x","y"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="schema gate"):
        ji.aggregate_file(p)


def test_quality_gate_rejects_implausible_volume(tmp_path):
    with pytest.raises(SystemExit, match="quality gate"):
        ji.aggregate_file(_csv(tmp_path, [_row(1, "2026-06-01 08:00", "2026-06-01 08:10")]))


def test_replace_dates_is_idempotent_and_corrects_partials(tmp_path):
    target = tmp_path / "daily.parquet"
    pd.DataFrame({
        "date_key": [20260531, 20260601],
        "journeys": [30000, 165],   # 06-01 is a boundary partial (the real repo case)
    }).to_parquet(target, index=False)
    fuller = pd.DataFrame({"date_key": [20260601], "journeys": [25000]})
    ji.replace_dates(target, fuller, [20260601])
    ji.replace_dates(target, fuller, [20260601])  # run twice -> identical
    out = pd.read_parquet(target).set_index("date_key")["journeys"].to_dict()
    assert out == {20260531: 30000, 20260601: 25000}


def test_parse_key():
    meta = ji.parse_key("usage-stats/445JourneyDataExtract01Jun2026-15Jun2026.csv")
    assert meta["extract"] == 445 and meta["end"] == "2026-06-15"
    assert ji.parse_key("usage-stats/readme.txt") is None
