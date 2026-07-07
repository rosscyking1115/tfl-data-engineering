"""Gate 0: enumerate the TfL cycling open-data bucket and write a file inventory.

https://cycling.data.tfl.gov.uk/ itself serves an HTML browser (Cloudflare), but
the underlying bucket answers ListObjectsV2 at the regional S3 endpoint. This
script paginates the usage-stats/ prefix there and writes
docs/gate0/cycle_file_inventory.csv (key, size_bytes, last_modified, ext).
Idempotent; re-run any time. This inventory is also the Phase 1 backfill input.
"""

from pathlib import Path
import csv
import xml.etree.ElementTree as ET

import requests

BUCKET_URL = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"
PREFIX = "usage-stats/"
NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
OUT = Path(__file__).resolve().parents[1] / "docs" / "gate0" / "cycle_file_inventory.csv"


def list_bucket(prefix: str) -> list[dict]:
    rows, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        resp = requests.get(BUCKET_URL, params=params, timeout=60)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for obj in root.findall("s3:Contents", NS):
            key = obj.findtext("s3:Key", "", NS)
            rows.append(
                {
                    "key": key,
                    "size_bytes": int(obj.findtext("s3:Size", "0", NS)),
                    "last_modified": obj.findtext("s3:LastModified", "", NS),
                    "ext": Path(key).suffix.lower().lstrip("."),
                }
            )
        token = root.findtext("s3:NextContinuationToken", None, NS)
        if not token:
            break
    return rows


def main() -> None:
    rows = list_bucket(PREFIX)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["key", "size_bytes", "last_modified", "ext"])
        writer.writeheader()
        writer.writerows(rows)

    total_gb = sum(r["size_bytes"] for r in rows) / 1e9
    by_ext: dict[str, int] = {}
    for r in rows:
        by_ext[r["ext"]] = by_ext.get(r["ext"], 0) + 1
    print(f"{len(rows)} objects under {PREFIX}, {total_gb:.2f} GB total")
    print("by extension:", dict(sorted(by_ext.items(), key=lambda kv: -kv[1])))
    print(f"inventory -> {OUT}")


if __name__ == "__main__":
    main()
