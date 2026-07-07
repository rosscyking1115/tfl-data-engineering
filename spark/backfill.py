"""Spark backfill: unify multi-era cycle-hire journey extracts into silver parquet.

Eras (verified in Gate 0, docs/gate0/cycle_gate0_findings.md):
- "classic" (2012 -> ~Sep 2022): Rental Id, Duration (s), Bike Id, dd/MM/yyyy HH:mm
  datetimes, integer station IDs.
- "nextgen" (~Sep 2022 -> present): Number, Total duration (ms), Bike number + Bike model,
  ISO datetimes, zero-padded string station numbers in new ranges.

Every raw row ends up in exactly one of silver / quarantine, so per-file
raw = silver + quarantine reconciles exactly. Duplicate rental IDs (weekly extract
overlaps) go to quarantine with reason=duplicate_rental_id.

Run via infra/run_backfill.ps1 (Dockerised spark-submit; Windows lacks winutils).
"""

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, functions as F, Window

# Era is detected from the id column present in the header; every OTHER column is
# mapped by NAME per distinct header variant. This matters: real files vary both in
# column ORDER (2025 extracts shuffle station name/number) and in PRESENCE (a 2022
# extract lacks `EndStation Id` entirely), and Spark maps multi-file CSV reads by
# position — so files are read per header-variant group, never mixed.
ERA_ID_COLUMN = {"Rental Id": "classic", "Number": "nextgen"}

# era -> mapping of unified raw (string) column -> source column
ERA_PROJECTIONS = {
    "classic": {
        "rental_id_raw": "Rental Id",
        "bike_id_raw": "Bike Id",
        "bike_model": None,  # column absent in this era
        "start_dt_raw": "Start Date",
        "end_dt_raw": "End Date",
        "duration_raw": "Duration",  # seconds
        "start_station_code": "StartStation Id",
        "start_station_name": "StartStation Name",
        "end_station_code": "EndStation Id",
        "end_station_name": "EndStation Name",
    },
    "nextgen": {
        "rental_id_raw": "Number",
        "bike_id_raw": "Bike number",
        "bike_model": "Bike model",
        "start_dt_raw": "Start date",
        "end_dt_raw": "End date",
        "duration_raw": "Total duration (ms)",  # milliseconds
        "start_station_code": "Start station number",
        "start_station_name": "Start station",
        "end_station_code": "End station number",
        "end_station_name": "End station",
    },
}
# All observed datetime formats across eras; parsing tries each in turn.
# (classic: dd/MM/yyyy; nextgen: ISO, with and without seconds)
TS_FORMATS = ["dd/MM/yyyy HH:mm", "yyyy-MM-dd HH:mm", "yyyy-MM-dd HH:mm:ss"]


def sniff_header_groups(input_dir: Path) -> dict[tuple[str, ...], list[str]]:
    """Group csv files by their exact header (name AND order). Fails loudly when a
    header has no recognizable era id column, or names an unmapped column set."""
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    unknown: dict[str, str] = {}
    for f in sorted(input_dir.glob("*.csv")):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            fields = tuple(c.strip() for c in next(csv.reader(fh)) if c.strip())
        if any(idcol in fields for idcol in ERA_ID_COLUMN):
            groups[fields].append(str(f))
        else:
            unknown[f.name] = ",".join(fields)
    if unknown:
        details = "\n".join(f"  {k}: {v}" for k, v in unknown.items())
        raise SystemExit(f"Header variant(s) with no known era id column:\n{details}")
    return dict(groups)


def era_of(fields: tuple[str, ...]) -> str:
    return next(era for idcol, era in ERA_ID_COLUMN.items() if idcol in fields)


def project_group(spark: SparkSession, fields: tuple[str, ...], files: list[str]) -> DataFrame:
    """Read one header-variant group and project to unified raw columns BY NAME.
    Columns absent from this variant become NULL (e.g. the 2022 files without
    `EndStation Id`)."""
    era = era_of(fields)
    df = spark.read.csv(files, header=True, inferSchema=False, quote='"', escape='"')
    cols = [
        (F.col(src).cast("string") if src and src in fields else F.lit(None).cast("string")).alias(dst)
        for dst, src in ERA_PROJECTIONS[era].items()
    ]
    return df.select(
        F.lit(era).alias("era"),
        *cols,
        F.element_at(F.split(F.input_file_name(), "/"), -1).alias("source_file"),
    )


def parse_ts(col: str):
    return F.coalesce(*[F.try_to_timestamp(F.col(col), F.lit(fmt)) for fmt in TS_FORMATS])


def typed(df: DataFrame) -> DataFrame:
    duration_s = F.when(
        F.col("era") == "classic", F.col("duration_raw").cast("bigint")
    ).otherwise((F.col("duration_raw").cast("bigint") / 1000).cast("bigint"))
    return (
        df.withColumn("rental_id", F.col("rental_id_raw").cast("bigint"))
        .withColumn("bike_id", F.col("bike_id_raw").cast("bigint"))
        .withColumn("start_ts", parse_ts("start_dt_raw"))
        .withColumn("end_ts", parse_ts("end_dt_raw"))
        .withColumn("duration_s", duration_s)
        .withColumn("start_station_code", F.trim("start_station_code"))
        .withColumn("end_station_code", F.trim("end_station_code"))
    )


def empty(col: str):
    return F.col(col).isNull() | (F.trim(F.col(col)) == "")


def with_quarantine_reason(df: DataFrame) -> DataFrame:
    checks = [
        ("null_rental_id", F.col("rental_id").isNull()),
        ("bad_start_ts", F.col("start_ts").isNull()),
        ("bad_end_ts", F.col("end_ts").isNull()),
        ("nonpositive_duration", F.col("duration_s").isNull() | (F.col("duration_s") <= 0)),
        # A station is only "missing" when BOTH its code and name are absent —
        # one 2022 header variant has no EndStation Id column at all, and those
        # rows are recoverable in dbt via a name -> station mapping.
        (
            "missing_station",
            (empty("start_station_code") & empty("start_station_name"))
            | (empty("end_station_code") & empty("end_station_name")),
        ),
    ]
    reason = F.concat_ws(
        ",", *[F.when(cond, F.lit(name)).otherwise(F.lit(None)) for name, cond in checks]
    )
    return df.withColumn("quarantine_reason", F.when(reason != "", reason))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/usage-stats")
    parser.add_argument("--output", default="data")
    args = parser.parse_args()

    groups = sniff_header_groups(Path(args.input))
    for fields, files in groups.items():
        print(f"header group [{era_of(fields)}] {len(fields)} cols x {len(files)} files: {fields}")

    spark = (
        SparkSession.builder.appName("cycle-backfill")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )

    unified = None
    for fields, files in groups.items():
        df = project_group(spark, fields, files)
        unified = df if unified is None else unified.unionByName(df)

    checked = with_quarantine_reason(typed(unified))

    # Duplicate rental ids across overlapping extracts: keep the first occurrence
    # (by source_file name), quarantine the rest.
    win = Window.partitionBy("era", "rental_id").orderBy("source_file")
    checked = checked.withColumn(
        "quarantine_reason",
        F.when(F.col("quarantine_reason").isNotNull(), F.col("quarantine_reason")).when(
            F.col("rental_id").isNotNull() & (F.row_number().over(win) > 1),
            F.lit("duplicate_rental_id"),
        ),
    ).cache()

    silver_cols = [
        "era", "rental_id", "bike_id", "bike_model", "start_ts", "end_ts", "duration_s",
        "start_station_code", "start_station_name", "end_station_code", "end_station_name",
        "source_file",
    ]
    silver = (
        checked.filter(F.col("quarantine_reason").isNull())
        .select(*silver_cols)
        .withColumn("ingested_at", F.lit(datetime.now(timezone.utc).isoformat()).cast("timestamp"))
        .withColumn("year", F.year("start_ts"))
        .withColumn("month", F.month("start_ts"))
    )
    quarantine = checked.filter(F.col("quarantine_reason").isNotNull()).select(
        "era", "source_file", "quarantine_reason",
        "rental_id_raw", "bike_id_raw", "bike_model", "start_dt_raw", "end_dt_raw",
        "duration_raw", "start_station_code", "start_station_name",
        "end_station_code", "end_station_name",
    )

    out = Path(args.output)
    silver.write.mode("overwrite").partitionBy("year", "month").parquet(str(out / "silver" / "journeys"))
    quarantine.write.mode("overwrite").parquet(str(out / "quarantine" / "journeys"))

    # Reconciliation: per-file raw counts vs what actually landed on disk.
    raw_counts = checked.groupBy("source_file").agg(F.count("*").alias("raw_rows"))
    silver_counts = (
        spark.read.parquet(str(out / "silver" / "journeys"))
        .groupBy("source_file").agg(F.count("*").alias("silver_rows"))
    )
    quarantine_counts = (
        spark.read.parquet(str(out / "quarantine" / "journeys"))
        .groupBy("source_file").agg(F.count("*").alias("quarantine_rows"))
    )
    recon = (
        raw_counts.join(silver_counts, "source_file", "left")
        .join(quarantine_counts, "source_file", "left")
        .fillna(0, ["silver_rows", "quarantine_rows"])
        .withColumn("delta", F.col("raw_rows") - F.col("silver_rows") - F.col("quarantine_rows"))
        .orderBy("source_file")
    )
    recon.coalesce(1).write.mode("overwrite").option("header", True).csv(str(out / "silver" / "_audit"))

    totals = recon.agg(
        F.sum("raw_rows"), F.sum("silver_rows"), F.sum("quarantine_rows"), F.sum(F.abs("delta"))
    ).first()
    reasons = (
        quarantine.withColumn("reason", F.explode(F.split("quarantine_reason", ",")))
        .groupBy("reason").count().orderBy(F.desc("count")).collect()
    )
    print(f"RAW={totals[0]:,} SILVER={totals[1]:,} QUARANTINE={totals[2]:,} ABS_DELTA={totals[3]:,}")
    for r in reasons:
        print(f"  quarantine[{r['reason']}] = {r['count']:,}")
    if totals[3] != 0:
        raise SystemExit("RECONCILIATION FAILED: raw != silver + quarantine for some file")
    print("RECONCILIATION OK")
    spark.stop()


if __name__ == "__main__":
    main()
