"""Phase 1: download the backfill window of raw journey files into data/raw/.

Selects every JourneyDataExtract whose extract END date is >= WINDOW_START by
parsing the trailing date token in the key (e.g. ...-15Oct2024.csv). The window
deliberately starts 2022-01-01 so it straddles the Sep-2022 schema change and
the backfill job has to prove both era mappings.

Idempotent: skips files already present with the expected size. Prints the
selection and total size before downloading.
"""

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

BUCKET_URL = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"
ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "gate0" / "cycle_file_inventory.csv"
DEST = ROOT / "data" / "raw" / "usage-stats"

WINDOW_START = datetime(2022, 1, 1)
END_DATE_RE = re.compile(r"-(\d{1,2})([A-Za-z]{3})(\d{4})\.csv$")


def extract_end_date(key: str) -> datetime | None:
    m = END_DATE_RE.search(key)
    if not m:
        return None
    day, mon, year = m.groups()
    try:
        return datetime.strptime(f"{day}{mon}{year}", "%d%b%Y")
    except ValueError:
        return None


def select_files() -> list[dict]:
    with INVENTORY.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    picked = []
    for r in rows:
        end = extract_end_date(r["key"])
        if end and end >= WINDOW_START and "JourneyDataExtract" in r["key"]:
            picked.append({"key": r["key"], "size": int(r["size_bytes"]), "end": end})
    picked.sort(key=lambda r: r["end"])
    return picked


def main() -> None:
    files = select_files()
    total_mb = sum(f["size"] for f in files) / 1e6
    print(f"{len(files)} files selected ({files[0]['end']:%Y-%m-%d} -> {files[-1]['end']:%Y-%m-%d}), "
          f"{total_mb/1e3:.1f} GB total")
    if "--dry-run" in sys.argv:
        return

    DEST.mkdir(parents=True, exist_ok=True)
    done_mb = 0.0
    for i, f in enumerate(files, 1):
        target = DEST / Path(f["key"]).name
        if target.exists() and target.stat().st_size == f["size"]:
            done_mb += f["size"] / 1e6
            continue
        with requests.get(BUCKET_URL + f["key"], stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with target.open("wb") as out:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    out.write(chunk)
        done_mb += f["size"] / 1e6
        print(f"[{i}/{len(files)}] {target.name} ({done_mb/1e3:.2f}/{total_mb/1e3:.1f} GB)", flush=True)
    print("download complete")


if __name__ == "__main__":
    main()
