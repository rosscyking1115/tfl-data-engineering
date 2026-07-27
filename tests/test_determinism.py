"""Byte-reproducibility guards for the certified evidence chain (ADR-0014).

The ADR-0009 certificate pins the SHA-256 of its input Parquet. That is only a meaningful
contract if rebuilding those inputs produces the same bytes. It did not: DuckDB writes
external Parquet in nondeterministic row order, so a local `dbt build` reordered rows
without changing a single value and turned the certificate red. A reader could not then
tell a real regression from reordering noise.

These tests keep the two halves of the fix honest:
  * every external export must impose a TOTAL order, over a key a dbt test proves unique;
  * the analysis must not depend on input row order in the first place.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rigor
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "dbt" / "models"

# The order-by key each external export must use. Each must also be a tested unique key,
# otherwise ties break arbitrarily and the "total order" is a fiction.
EXPECTED_ORDER_KEYS = {
    "demand_deviation": ["date_key", "station_key"],
    "demand_deviation_ml": ["date_key", "station_key"],
    "disruption_events": ["line_id", "start_date"],
    "expected_demand": ["station_key", "dow", "is_wet", "is_cold"],
}


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def external_models() -> dict[str, str]:
    """Every dbt model materialised as an external Parquet file."""
    found = {}
    for path in MODEL_DIR.rglob("*.sql"):
        text = path.read_text(encoding="utf-8")
        if "materialized='external'" in text or 'materialized="external"' in text:
            found[path.stem] = text
    return found


def test_the_external_export_set_is_what_we_think_it_is():
    """A new external export must be added here deliberately, with an order key chosen."""
    assert set(external_models()) == set(EXPECTED_ORDER_KEYS)


@pytest.mark.parametrize("model", sorted(EXPECTED_ORDER_KEYS))
def test_every_external_model_ends_with_a_top_level_order_by(model):
    """Without a trailing ORDER BY, DuckDB's row order — and so the file's bytes — vary."""
    sql = _strip_sql_comments(external_models()[model])
    tail = re.search(r"\border\s+by\b(?P<cols>[^)]*)$", sql, re.IGNORECASE | re.DOTALL)
    assert tail, f"{model}.sql has no top-level ORDER BY; its Parquet bytes are not reproducible"
    ordered = [c.strip() for c in tail.group("cols").replace("\n", " ").split(",") if c.strip()]
    assert ordered == EXPECTED_ORDER_KEYS[model], (
        f"{model}.sql orders by {ordered}, expected {EXPECTED_ORDER_KEYS[model]}"
    )


@pytest.mark.parametrize("model", sorted(EXPECTED_ORDER_KEYS))
def test_each_order_key_is_proven_unique_by_a_dbt_test(model):
    """An ORDER BY only yields a TOTAL order if the key is unique — so prove it, don't assume."""
    schema = yaml.safe_load((MODEL_DIR / "analytics" / "schema.yml").read_text(encoding="utf-8"))
    entry = next(m for m in schema["models"] if m["name"] == model)
    combos = [
        (t["dbt_utils.unique_combination_of_columns"].get("arguments")
         or t["dbt_utils.unique_combination_of_columns"])["combination_of_columns"]
        for t in entry.get("tests", [])
        if "dbt_utils.unique_combination_of_columns" in t
    ]
    assert EXPECTED_ORDER_KEYS[model] in combos, (
        f"{model} orders by {EXPECTED_ORDER_KEYS[model]} but no dbt test proves that unique"
    )


# ------------------------------------------------------- analysis order-independence

def _synthetic_station_days() -> pd.DataFrame:
    """Two disruption days, enough stations per day for a bootstrap to have variance."""
    rows = []
    for day in ("2024-03-01", "2024-03-02"):
        for i in range(40):
            rows.append({
                "date_key": int(day.replace("-", "")),
                "date_day": pd.Timestamp(day),
                "station_key": f"s{i:03d}",
                "departures": 10 + i,
                "expected_departures": 10.0,
                "deviation_ratio": (10 + i) / 10.0,
                "is_disruption": True,
            })
    return pd.DataFrame(rows)


def test_per_event_diagnostics_are_invariant_to_input_row_order():
    """Position-based resampling makes the per-event CIs depend on the order rows arrive in.

    demand_deviation.parquet's row order is an artefact of the query plan, so a diagnostic
    that moves when it changes is reporting noise as uncertainty.
    """
    df = _synthetic_station_days()
    shuffled = df.sample(frac=1.0, random_state=11).reset_index(drop=True)
    assert not df.equals(shuffled)

    first = rigor.per_event_cis(df, np.random.default_rng(42))
    second = rigor.per_event_cis(shuffled, np.random.default_rng(42))
    assert first == second, "per-event CIs changed under a pure row reordering"


def test_headline_bootstrap_is_invariant_to_input_row_order():
    """The certified headline CI must not move when only row order changes."""
    df = _synthetic_station_days()
    shuffled = df.sample(frac=1.0, random_state=13).reset_index(drop=True)

    first = rigor.bootstrap_headline_ci(df, np.random.default_rng(42))
    second = rigor.bootstrap_headline_ci(shuffled, np.random.default_rng(42))
    assert first == second
