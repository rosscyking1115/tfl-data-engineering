# Phase 1 findings — Spark backfill (2022 → May 2026)

Run: 2026-07-07, `apache/spark:4.0.1-java21-python3` container, `local[10]`,
10 GB driver heap, **~30 min wall clock** over 148 CSVs / 6.5 GB raw
→ 1.64 GB parquet, partitioned by year/month.

## Reconciliation (raw = silver + quarantine, per file — see backfill_reconciliation.csv)

| | rows |
|---|---:|
| RAW | 41,376,421 |
| SILVER | 41,376,181 |
| QUARANTINE | 240 |
| per-file delta | **0 everywhere** |

Quarantine breakdown (reasons overlap): 240 `nonpositive_duration` rows, of which 184 also have
`missing_station` and `bad_end_ts`, consistent with hires that never docked. There were **zero
duplicate rental IDs**: the weekly/biweekly extracts do not overlap, so the dedupe
guard did not fire in this window. It remains in place because it costs one window and protects re-runs
and the older eras).

## Silver shape (verified independently with DuckDB, not Spark's own counters)

| year | rows | note |
|---|---:|---|
| 2021 | 56,013 | boundary days from the first extract window |
| 2022 | 11,419,289 | era transition inside the year: 8.87M classic + 2.55M nextgen |
| 2023 | 8,514,447 | |
| 2024 | 8,755,141 | |
| 2025 | 9,068,040 | |
| 2026 | 3,563,251 | through May |

- 312,144 rows have NULL `end_station_code` — exactly the one 8-column 2022 file
  (`325JourneyDataExtract06Jul2022-12Jul2022.csv`); names survive, id repair happens
  in dbt via a name→station map.
- Durations: minimum 1 s, maximum **209 days** (an unreturned bike), mean 23.2 min. The
  accepted-range dbt test should flag, not fail, the long tail.

## Snowflake load (Phase 1b, 2026-07-07)

Internal stage + `COPY INTO` via [load_silver_to_snowflake.py](../../ingestion/load_silver_to_snowflake.py):
**41,376,181 rows in `TFL.SILVER.JOURNEYS` — exact match with local silver.**
Era boundary confirmed in-warehouse: classic ends 2022-09-11 23:58, nextgen starts
2022-09-12 05:02 (the switchover gap is real, not an artifact).

Cost: **0.105 credits (~$0.21 at Standard $2/credit)** for the entire 1.6 GB / 41M-row load on the XS
warehouse; auto-suspend (60 s) activated immediately afterwards. The trial's default
`COMPUTE_WH` was also set to a 60 s auto-suspend.

Issue recorded for Phase 2: Spark wrote **10,803 small Parquet files** (default
200 shuffle partitions fanned out across 54 year/month partitions). Harmless at this
scale, but inefficient. Add a `.repartition("year","month")` (or coalesce per partition)
before the write and re-measure PUT/COPY time.

## Findings beyond Gate 0

Five header variants, not two eras (ADR-0002): a column deleted mid-2022, and two
2025 column-order shuffles that positional CSV reading would have silently corrupted.
Nextgen raw timestamps carry no seconds (`2026-01-15 23:59`). Gate 0's DuckDB
display had normalized this away; the job now tries all observed formats.
