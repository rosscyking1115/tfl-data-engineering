"""Batch prediction — the learned counterfactual "normal demand" baseline.

Predicts daily departures for every station-day with **is_disruption forced to 0**, so
strike uplift never leaks into the baseline (ADR-0008). This replaces expected_demand's
coarse median with a model-learned expectation; the demand_deviation_ml dbt model then
measures actual-vs-this to isolate the disruption effect.

Writes app/gold_export/predicted_demand.parquet (committed, so dbt/app/API need no model
at runtime). Run from repo root:  .venv/Scripts/python ml/predict.py
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
from features import FEATURES, build_dataset

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "ml" / "model" / "lgbm.txt"
OUT = ROOT / "app" / "gold_export" / "predicted_demand.parquet"


def main() -> None:
    booster = lgb.Booster(model_file=str(MODEL))
    df = build_dataset()

    Xcf = df[FEATURES].copy()
    Xcf["is_disruption"] = np.int8(0)  # counterfactual: what "normal" looks like
    pred = booster.predict(Xcf)

    out = df[["date_key", "date_day", "station_key", "station_name"]].copy()
    out["predicted_departures"] = np.clip(pred, 0, None).round(2)
    out.to_parquet(OUT, index=False)

    print(f"wrote {OUT.relative_to(ROOT).as_posix()}  rows={len(out):,}  "
          f"stations={out['station_key'].nunique()}  "
          f"dates {out['date_day'].min().date()}→{out['date_day'].max().date()}")
    print(out["predicted_departures"].describe().round(2).to_string())


if __name__ == "__main__":
    main()
