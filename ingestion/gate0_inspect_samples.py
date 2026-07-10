"""Gate 0: measure schemas and row density of the sample files, then extrapolate
a full-history row count from the complete bucket inventory.

Outputs a markdown summary to docs/gate0/cycle_gate0_findings.md.
"""

import io
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "raw-samples"
INVENTORY = ROOT / "docs" / "gate0" / "cycle_file_inventory.csv"
OUT = ROOT / "docs" / "gate0" / "cycle_gate0_findings.md"

con = duckdb.connect()


def inspect_csv(path: Path) -> dict:
    cols = [r[0] for r in con.sql(f"describe select * from read_csv_auto('{path.as_posix()}')").fetchall()]
    rows = con.sql(f"select count(*) from read_csv_auto('{path.as_posix()}')").fetchone()[0]
    return {"file": path.name, "kind": "csv", "rows": rows, "mb": path.stat().st_size / 1e6, "columns": cols}


def inspect_xlsx(path: Path) -> dict:
    df = pd.read_excel(path)
    return {
        "file": path.name,
        "kind": "xlsx",
        "rows": len(df),
        "mb": path.stat().st_size / 1e6,
        "columns": list(df.columns),
    }


def inspect_zip(path: Path) -> dict:
    total_rows = 0
    member_cols: dict[str, list[str]] = {}
    with zipfile.ZipFile(path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        for m in members:
            with zf.open(m) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
                header = text.readline().strip()
                member_cols[m] = header.split(",")
                total_rows += sum(1 for _ in text)
    return {
        "file": path.name,
        "kind": "zip",
        "rows": total_rows,
        "mb": path.stat().st_size / 1e6,
        "columns": member_cols[members[0]],
        "members": len(members),
        "member_headers": member_cols,
    }


def main() -> None:
    results = []
    for p in sorted(SAMPLES.iterdir()):
        if p.suffix == ".csv":
            results.append(inspect_csv(p))
        elif p.suffix == ".xlsx":
            results.append(inspect_xlsx(p))
        elif p.suffix == ".zip":
            results.append(inspect_zip(p))

    # Extrapolate: apply each era's measured rows/MB to the inventory sizes.
    # CSV-era rate = mean over the CSV/xlsx samples; zip rate measured separately
    # (compressed MB -> rows).
    csv_rates = [r["rows"] / r["mb"] for r in results if r["kind"] in ("csv", "xlsx")]
    csv_rate = sum(csv_rates) / len(csv_rates)
    zip_rate = next(r["rows"] / r["mb"] for r in results if r["kind"] == "zip")

    inv = con.sql(f"select ext, sum(size_bytes)/1e6 mb from '{INVENTORY.as_posix()}' group by ext").fetchall()
    inv_mb = dict((e or "none", mb) for e, mb in inv)
    est_csv = (inv_mb.get("csv", 0) + inv_mb.get("xlsx", 0)) * csv_rate
    est_zip = inv_mb.get("zip", 0) * zip_rate
    est_total = est_csv + est_zip

    lines = [
        "# Gate 0 findings — Option A: cycle-hire journey archive",
        "",
        f"Inventory: see [cycle_file_inventory.csv](cycle_file_inventory.csv) "
        f"({int(con.sql(f'select count(*) from \"{INVENTORY.as_posix()}\"').fetchone()[0])} objects, "
        f"{sum(inv_mb.values())/1e3:.1f} GB).",
        "",
        "## Sample measurements",
        "",
        "| file | kind | rows | MB | rows/MB |",
        "|---|---|---:|---:|---:|",
    ]
    for r in results:
        lines.append(f"| {r['file']} | {r['kind']} | {r['rows']:,} | {r['mb']:.1f} | {r['rows']/r['mb']:,.0f} |")
    lines += [
        "",
        "## Schemas per era (verbatim column names)",
        "",
    ]
    for r in results:
        lines.append(f"**{r['file']}**")
        lines.append("```")
        lines.append(", ".join(str(c) for c in r["columns"]))
        lines.append("```")
        if r["kind"] == "zip":
            uniq = {tuple(v) for v in r["member_headers"].values()}
            lines.append(f"(zip: {r['members']} member CSVs, {len(uniq)} distinct header variants)")
        lines.append("")
    lines += [
        "## Full-history row estimate",
        "",
        f"- CSV/xlsx era rate: {csv_rate:,.0f} rows/MB over {inv_mb.get('csv',0)+inv_mb.get('xlsx',0):,.0f} MB "
        f"→ ~{est_csv/1e6:,.0f}M rows",
        f"- zip era rate (compressed): {zip_rate:,.0f} rows/MB over {inv_mb.get('zip',0):,.0f} MB "
        f"→ ~{est_zip/1e6:,.0f}M rows",
        f"- **Estimated total: ~{est_total/1e6:,.0f}M rows**",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
