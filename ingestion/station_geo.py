"""Station + line geography for proximity-based disruption exposure (rigor-pass Area 6).

Two committed geo assets, both additive (the journey dims are untouched evidence):

1.  station_geo.parquet — lat/lon per docking station, from the live BikePoint feed matched to
    dim_station by whitespace-collapsed name. Match rate is reported honestly (historical
    stations that no longer exist have no live coords).
2.  line_stops.parquet — lat/lon of every station served by each rail line in the snapshot log
    (TfL /Line/{id}/StopPoints), fetched once. This is what makes "docking stations within R km
    of the disrupted line" computable.

Scope honesty: proximity exposure applies to LINE-level events from the forward snapshot log
(collection began 2026-07-08). Journey extracts currently end 2026-05-31, so the line-level
event-study has no overlap window yet — the machinery ships tested, and activates as soon as
TfL publishes journey data covering the collection period (ADR-0009).

Run once (and re-run any time):  .venv/Scripts/python ingestion/station_geo.py
"""

from pathlib import Path
import re

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "app" / "gold_export"
API = "https://api.tfl.gov.uk"


def collapse(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def build_station_geo() -> pd.DataFrame:
    q = f"""
    with bp as (
        select regexp_replace(trim(common_name), '\\s+', ' ', 'g') as name,
               avg(lat) as lat, avg(lon) as lon
        from read_parquet('{(EXPORT / "live_bikepoint.parquet").as_posix()}')
        group by 1
    )
    select d.station_key, d.station_name, bp.lat, bp.lon
    from read_parquet('{(EXPORT / "dim_station.parquet").as_posix()}') d
    left join bp on d.station_name = bp.name
    """
    return duckdb.sql(q).df()


def fetch_line_stops(line_ids: list[str]) -> pd.DataFrame:
    rows = []
    s = requests.Session()
    for lid in line_ids:
        r = s.get(f"{API}/Line/{lid}/StopPoints", timeout=60)
        r.raise_for_status()
        for sp in r.json():
            if sp.get("lat") and sp.get("lon"):
                rows.append({"line_id": lid, "stop_name": sp.get("commonName"),
                             "lat": sp["lat"], "lon": sp["lon"]})
        print(f"  {lid}: {sum(1 for x in rows if x['line_id'] == lid)} stops")
    return pd.DataFrame(rows)


def main() -> None:
    geo = build_station_geo()
    matched = int(geo["lat"].notna().sum())
    geo.to_parquet(EXPORT / "station_geo.parquet", index=False)
    print(f"[OK] station_geo: {matched}/{len(geo)} stations matched to live coords "
          f"({matched / len(geo):.0%}; unmatched are historical/renamed docks — kept as NaN)")

    line_ids = duckdb.sql(
        f"select distinct line_id from read_parquet('{(EXPORT / 'live_line_status.parquet').as_posix()}')"
    ).df()["line_id"].tolist()
    stops = fetch_line_stops(sorted(line_ids))
    stops.to_parquet(EXPORT / "line_stops.parquet", index=False)
    print(f"[OK] line_stops: {len(stops)} stops across {stops['line_id'].nunique()} lines")


if __name__ == "__main__":
    main()
