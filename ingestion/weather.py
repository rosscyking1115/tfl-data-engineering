"""Weather enrichment: daily London weather from Open-Meteo (free, no key).

Historical archive for the journey window feeds the weather-adjusted demand baseline
(cold/wet days suppress cycling — see the 2024-01-08 strike-day counterexample). The
same endpoint shape serves the daily-forward pull in the GitHub Actions cron.

Writes app/gold_export/weather_daily.parquet (committed — tiny, one row/day).
"""

import argparse
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "gold_export" / "weather_daily.parquet"

# central London
LAT, LON = 51.5074, -0.1278
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ["temperature_2m_mean", "temperature_2m_max", "precipitation_sum",
         "rain_sum", "wind_speed_10m_max", "weather_code"]


def fetch(start: str, end: str) -> pd.DataFrame:
    resp = requests.get(
        ARCHIVE,
        params={
            "latitude": LAT, "longitude": LON,
            "start_date": start, "end_date": end,
            "daily": ",".join(DAILY), "timezone": "Europe/London",
        },
        timeout=120,
    )
    resp.raise_for_status()
    daily = resp.json()["daily"]
    df = pd.DataFrame(daily).rename(columns={"time": "date_day"})
    df["date_day"] = pd.to_datetime(df["date_day"])
    df["date_key"] = df["date_day"].dt.strftime("%Y%m%d").astype(int)
    # simple, interpretable flags the baseline/UI can use directly
    df["is_wet"] = df["precipitation_sum"].fillna(0) >= 1.0        # >=1mm
    df["is_cold"] = df["temperature_2m_mean"] < 8.0               # sub-8C mean
    return df


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2021-12-01")
    p.add_argument("--end", default="2026-06-30")
    args = p.parse_args()
    df = fetch(args.start, args.end)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"[OK] weather_daily: {len(df):,} days "
          f"({df['date_day'].min().date()} -> {df['date_day'].max().date()}) "
          f"-> {OUT.name} ({OUT.stat().st_size/1e6:.2f} MB)")
    print(df[["date_day", "temperature_2m_mean", "precipitation_sum", "is_wet", "is_cold"]].tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
