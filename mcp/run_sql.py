"""Tiny runner: execute a .sql file (semicolon-split) against Snowflake using .env creds.
Used for one-off setup like the read-only role. Not part of the pipeline."""

import sys
from pathlib import Path

from dotenv import dotenv_values
import snowflake.connector

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sql_path = Path(sys.argv[1])
    v = dotenv_values(ROOT / ".env")
    conn = snowflake.connector.connect(
        account=v["SNOWFLAKE_ACCOUNT"], user=v["SNOWFLAKE_USER"], password=v["SNOWFLAKE_PASSWORD"]
    )
    cur = conn.cursor()
    for raw in sql_path.read_text(encoding="utf-8").split(";"):
        # drop comment-only / blank chunks (e.g. trailing note after the last ';')
        code = "\n".join(l for l in raw.splitlines() if l.strip() and not l.strip().startswith("--"))
        if not code.strip():
            continue
        cur.execute(code)
        print(f"ok: {code.splitlines()[0][:70]}")
    conn.close()


if __name__ == "__main__":
    main()
