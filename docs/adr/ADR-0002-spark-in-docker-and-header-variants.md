# ADR-0002: Spark runs in Docker; files are mapped by header variant, not era

- **Status:** Accepted
- **Date:** 2026-07-07

## Decision 1: spark-submit inside the official Apache Spark container

Native PySpark on this Windows host failed two ways (both reproduced, not assumed):

1. **Java 25** (system default): Hadoop's `UserGroupInformation` calls
   `Subject.getSubject`, removed by JEP 486 → `UnsupportedOperationException:
   getSubject is not supported` on any write. No flag re-enables it on 24+.
2. **JDK 21** (also installed): parquet commit path requires `winutils.exe` /
   `hadoop.dll` Windows natives that Apache doesn't ship; the community binaries lag
   Hadoop 3.4.x and are a third-party supply-chain risk.

So the backfill runs via `docker run apache/spark:4.0.1-java21-python3 spark-submit`
([infra/run_backfill.ps1](../../infra/run_backfill.ps1)) with the repo bind-mounted.
This is also closer to how Spark runs in production than a bare-metal Windows install.
**Why not** a full cluster/compose setup: `--master local[*]` on 20 cores is the honest
match for a 6.5 GB single-node workload; distributing it would be theatre.

Operational gotcha worth remembering: the first full run died with exit 137
(`OOMKilled=true`) because `.wslconfig` capped the Docker/WSL2 VM at 2 GB — the
requested 10 GB driver heap can't exist inside a 2 GB cgroup, and Spark's own logs
never see the kill coming. Raised to 16 GB / 12 CPUs for the backfill.

## Decision 2: header-variant grouping with by-name projection

Gate 0 found two schema eras. The first full run found **five distinct header
variants** — the fail-loudly sniffer in [spark/backfill.py](../../spark/backfill.py)
refused to guess, which is exactly why it exists:

| era | cols | files | drift |
|---|---:|---:|---|
| classic | 9 | 36 | baseline 2022 schema |
| classic | 8 | 1 | **`EndStation Id` column missing entirely** (Jul 2022) |
| nextgen | 11 | 100 | baseline post-Sep-2022 schema |
| nextgen | 11 | 8 | same columns, **station name/number order swapped** |
| nextgen | 11 | 3 | same columns, **a third ordering** (2025) |

The trap: Spark maps multi-file CSV reads **by position**, so reading all "nextgen"
files together would have silently written station names into station-number columns
for 11 of 111 files. Files are therefore read per exact-header group and projected to
the unified schema **by column name**; a column absent from a variant becomes NULL
(the 8-col classic rows keep their end-station *names* and are repairable in dbt via a
name→station mapping, so they are NOT quarantined).

Consequences: any future sixth variant stops the job with the offending header printed,
rather than corrupting silver. Timestamps are parsed by trying all observed formats
(`dd/MM/yyyy HH:mm`, ISO with/without seconds) — the nextgen raw files carry no seconds,
which DuckDB's display had masked during Gate 0.
