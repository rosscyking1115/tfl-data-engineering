"""Gate 0: measure the real extent of the LAQN historical archive.

Two measurements that need verifying before the dataset is locked:
1. Theoretical extent: every (site, species) pair with its date range, from
   /Information/MonitoringSiteSpecies — summed as hourly rows.
2. Real availability: sample hourly pulls for long-running sites, measuring the
   fraction of hours that actually have a reading (gaps are expected and are
   part of the messiness story).

Writes docs/gate0/laqn_gate0_findings.md.
"""

from datetime import datetime
from pathlib import Path

import requests

API = "https://api.erg.ic.ac.uk/AirQuality"
OUT = Path(__file__).resolve().parents[1] / "docs" / "gate0" / "laqn_gate0_findings.md"

# (site, species, one sample year) pairs pulled to measure real availability.
SAMPLE_PULLS = [
    ("MY1", "NO2", 2005),  # Marylebone Road — famous long-running roadside site
    ("MY1", "NO2", 2020),
    ("KC1", "PM25", 2015),  # North Kensington — long-running background site
    ("TH4", "NO2", 2010),  # Tower Hamlets
]


def get_json(path: str) -> dict:
    resp = requests.get(f"{API}{path}", timeout=120, headers={"Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()


def parse_date(s: str) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.split(".")[0])


def theoretical_extent() -> tuple[list[dict], float]:
    data = get_json("/Information/MonitoringSiteSpecies/GroupName=London/Json")
    sites = data["Sites"]["Site"]
    now = datetime.now()
    rows = []
    total_hours = 0.0
    for site in sites:
        species = site.get("Species") or []
        if isinstance(species, dict):
            species = [species]
        for sp in species:
            start = parse_date(sp.get("@DateMeasurementStarted", ""))
            end = parse_date(sp.get("@DateMeasurementFinished", "")) or now
            if not start:
                continue
            hours = max((end - start).total_seconds() / 3600, 0)
            total_hours += hours
            rows.append(
                {
                    "site": site["@SiteCode"],
                    "site_name": site["@SiteName"],
                    "species": sp["@SpeciesCode"],
                    "start": start,
                    "end": end,
                    "hours": hours,
                }
            )
    return rows, total_hours


def sample_availability() -> list[dict]:
    results = []
    for site, species, year in SAMPLE_PULLS:
        start, end = f"01 Jan {year}", f"01 Jan {year + 1}"
        data = get_json(f"/Data/SiteSpecies/SiteCode={site}/SpeciesCode={species}/StartDate={start}/EndDate={end}/Json")
        readings = data["RawAQData"]["Data"]
        if isinstance(readings, dict):
            readings = [readings]
        n_slots = len(readings)
        n_values = sum(1 for r in readings if r.get("@Value") not in ("", None))
        results.append(
            {
                "site": site,
                "species": species,
                "year": year,
                "hour_slots": n_slots,
                "values_present": n_values,
                "availability": n_values / n_slots if n_slots else 0.0,
            }
        )
        print(f"  {site} {species} {year}: {n_values:,}/{n_slots:,} hours with values")
    return results


def main() -> None:
    print("pulling site x species extent ...")
    extent, total_hours = theoretical_extent()
    n_sites = len({r["site"] for r in extent})
    earliest = min(r["start"] for r in extent)
    open_pairs = sum(1 for r in extent if r["end"].date() == datetime.now().date())

    print("sampling real availability ...")
    samples = sample_availability()
    avg_avail = sum(s["availability"] for s in samples) / len(samples)

    top = sorted(extent, key=lambda r: -r["hours"])[:10]
    lines = [
        "# Gate 0 findings — Option B: LAQN air-quality archive",
        "",
        f"- Sites in London group: **{n_sites}**, site×species pairs: **{len(extent)}**",
        f"- Earliest measurement start: **{earliest:%Y-%m-%d}**",
        f"- Site×species pairs still measuring today: **{open_pairs}**",
        f"- Theoretical hourly slots across all pairs: **{total_hours/1e6:,.0f}M**",
        f"- Measured availability on sample pulls: **{avg_avail:.0%}**",
        f"- **Estimated real reading count: ~{total_hours*avg_avail/1e6:,.0f}M rows**",
        "",
        "## Longest-running site×species pairs",
        "",
        "| site | name | species | from | to | years |",
        "|---|---|---|---|---|---:|",
    ]
    for r in top:
        lines.append(
            f"| {r['site']} | {r['site_name']} | {r['species']} | {r['start']:%Y-%m} | {r['end']:%Y-%m} "
            f"| {r['hours']/8766:.1f} |"
        )
    lines += [
        "",
        "## Sample availability pulls (hourly, one year each)",
        "",
        "| site | species | year | hour slots | values | availability |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for s in samples:
        lines.append(
            f"| {s['site']} | {s['species']} | {s['year']} | {s['hour_slots']:,} | {s['values_present']:,} "
            f"| {s['availability']:.0%} |"
        )
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
