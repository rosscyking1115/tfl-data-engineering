"""Gate 0: download era-spanning sample files into data/raw-samples/ (gitignored).

Samples chosen from the inventory to cover each file-format era: the 2012-2014
annual zips, early weekly CSVs (2016), the stray 2017 xlsx, and weekly/biweekly
CSVs from 2019/2022/2026. Idempotent: skips files already present.
"""

from pathlib import Path

import requests

BUCKET_URL = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"
DEST = Path(__file__).resolve().parents[1] / "data" / "raw-samples"

SAMPLE_KEYS = [
    "usage-stats/cyclehireusagestats-2013.zip",
    "usage-stats/01aJourneyDataExtract10Jan16-23Jan16.csv",
    "usage-stats/49JourneyDataExtract15Mar2017-21Mar2017.xlsx",
    "usage-stats/143JourneyDataExtract02Jan2019-08Jan2019.csv",
    "usage-stats/299JourneyDataExtract05Jan2022-11Jan2022.csv",
    "usage-stats/435JourneyDataExtract01Jan2026-15Jan2026.csv",
]


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for key in SAMPLE_KEYS:
        target = DEST / Path(key).name
        if target.exists() and target.stat().st_size > 0:
            print(f"skip (exists): {target.name}")
            continue
        print(f"downloading {key} ...")
        with requests.get(BUCKET_URL + key, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with target.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        print(f"  -> {target.name} ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
