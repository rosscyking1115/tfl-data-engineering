# ADR-0001: Dataset and stack selection

- **Status:** Accepted
- **Date:** 2026-07-07
- **Context:** Gate 0 required verifying
  both dataset candidates with real downloads before locking anything. Both were measured
  on 2026-07-07; raw evidence in [docs/gate0/](../gate0/).

## Decision

**Option A — Santander Cycle Hire journey history — is the Spark-justifying backbone.**
LAQN (Option B) is **cut from scope**, not kept as enrichment. The optional cross-source
join slot stays reserved for daily weather (Open-Meteo), per the original plan.

## Measured facts (not claims)

### Option A: cycle hire (winner)

| Fact | Claimed in plan | Measured |
|---|---|---|
| Full-history rows | ~80–100M | **~189M** (143M CSV/xlsx era + 47M zip era, extrapolated from 6 samples × full 16.4 GB inventory) |
| Files | "hundreds" | **482 objects**, 16.4 GB, spanning **2012 → May 2026** (still updated) |
| Formats | CSV/XML/XLS mix | zip (2012–2015 annuals), CSV (weekly/biweekly), one stray `.xlsx` (2017) |
| Schema drift | claimed | **confirmed**: 9-column schema (`Rental Id, Duration, Bike Id, …`) 2012→~2022, then full rename to 11 columns (`Number, Start date, …, Bike model, Total duration (ms)`) |
| Value drift | claimed | **confirmed**: `dd/mm/yyyy HH:MM` strings → ISO timestamps; integer station IDs (`197`) → zero-padded strings in new ranges (`001211`, `300050`); duration seconds → `"7m 20s"` + ms; new `CLASSIC`/`PBSC_EBIKE` bike models |
| Naming mess | claimed | **confirmed**: duplicate keys with/without spaces, `07Fe16` typo, 2- vs 4-digit years, inconsistent numbering |

### Option B: LAQN air quality (cut)

| Fact | Measured |
|---|---|
| Extent | 251 London sites, 646 site×species pairs, earliest 1987, 195 pairs still live |
| Real rows | **~53M** (55M theoretical hourly slots × 96% measured availability) |
| Delivery | JSON API only (`api.erg.ic.ac.uk/AirQuality`), one request per site×species×date-range — no bulk file archive |
| Messiness | mild: 4–7% hourly gaps in sampled years; schema itself is stable |

## Rationale

1. **Scale:** 189M vs 53M. Only Option A is unambiguously past single-machine comfort at
   full grain; it exceeds the plan's own claim by ~2×.
2. **Shape of the mess matches the Spark story:** Option A is exactly the "unify a decade
   of inconsistent bulk files" problem (per-era schema mapping, format handling, quarantine).
   LAQN's mess is availability gaps in a *stable* schema — a data-quality footnote, not a
   distributed-processing justification.
3. **Backfillability:** Option A is pre-accumulated bulk files on S3 (download-bound).
   LAQN's 53M rows sit behind a per-site×species JSON API — thousands of long requests to
   backfill, which is the exact live-feed trap §1 of the plan warns about.
4. **Why cut LAQN rather than keep it as enrichment:** the plan flags two-genre dilution.
   An air-quality join onto journey data adds a second ingestion genre (API scraping) for
   one dashboard tile; weather (Open-Meteo, single clean daily pull) fills the same
   cross-source-join slot at a fraction of the complexity.
5. **Personal relevance** favored Option B, but it was one criterion of four and the only
   one Option B won.

## Consequences

- §2 onward of the build plan proceeds exactly as its Option A placeholder describes:
  Spark backfill → Snowflake medallion → dbt star schema (`fact_journey`, `dim_station`,
  `dim_date`) → Airflow → Power BI.
- The live/incremental layer is BikePoint + Line Status from the TfL Unified API.
- The backfill must handle **three eras**, not two formats: annual zips (2012–2015),
  9-column CSVs (2016–2022), 11-column CSVs (2022–present) — plus the xlsx straggler.
- Row-count target for "DONE": ≥3 recent years end-to-end (~30–40M rows); full history
  (~189M) only if Snowflake credits and weekend time allow.

## Evidence

- [cycle_file_inventory.csv](../gate0/cycle_file_inventory.csv) — full bucket listing
  (regenerate: `python ingestion/gate0_cycle_inventory.py`)
- [cycle_gate0_findings.md](../gate0/cycle_gate0_findings.md) — sample measurements,
  per-era schemas, extrapolation
- [laqn_gate0_findings.md](../gate0/laqn_gate0_findings.md) — LAQN extent + availability
