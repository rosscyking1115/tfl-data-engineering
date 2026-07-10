"""Train the station-level daily demand model (LightGBM) with MLflow tracking.

Temporal validation only: fit on 2022→2024, early-stop on 2025, report held-out 2026.
The model must beat two baselines on the test window or we iterate before shipping:
  - median      — expected_demand's baseline (median departures by station×dow×wet×cold),
                  computed from pre-test data only (fair, no leakage).
  - seasonal-naive — same station, same day-of-week, last week (= the dep_lag_7 feature).

Objective is L1 (predicts the conditional *median*), which is robust to the strike tail
and matches the "normal / expected demand" framing the counterfactual baseline needs.

Run from the repo root:  .venv/Scripts/python ml/train.py
Artifacts: ml/model/lgbm.txt, ml/model/feature_importance.csv; runs in ./mlruns (gitignored).
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd
from features import CATEGORICALS, FEATURES, TARGET, build_dataset, split_frames, xy

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "ml" / "model"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

PARAMS = dict(
    objective="regression_l1",   # MAE / conditional median — robust to the disruption tail
    n_estimators=3000,
    learning_rate=0.03,
    num_leaves=63,
    min_child_samples=100,
    subsample=0.8,
    subsample_freq=1,
    colsample_bytree=0.8,
    reg_lambda=1.0,
    n_jobs=-1,
    random_state=42,
    verbose=-1,
)


def _mae(a, p):
    return float(np.mean(np.abs(np.asarray(a, float) - np.asarray(p, float))))


def _rmse(a, p):
    return float(np.sqrt(np.mean((np.asarray(a, float) - np.asarray(p, float)) ** 2)))


def median_baseline(train_val: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """expected_demand's logic: median departures by station×dow×wet×cold, learned from
    pre-test data, applied to test rows. Falls back to station median, then global median."""
    keys = ["station_key", "dow", "is_wet", "is_cold"]
    grp = train_val.groupby(keys, observed=True)[TARGET].median().rename("m").reset_index()
    stn = train_val.groupby("station_key", observed=True)[TARGET].median().rename("ms").reset_index()
    glob = float(train_val[TARGET].median())
    out = test.merge(grp, on=keys, how="left").merge(stn, on="station_key", how="left")
    return out["m"].fillna(out["ms"]).fillna(glob).to_numpy()


def main() -> None:
    df = build_dataset()
    parts = split_frames(df)
    Xtr, ytr = xy(parts["train"])
    Xva, yva = xy(parts["val"])
    Xte, yte = xy(parts["test"])
    print(f"train={len(Xtr):,}  val={len(Xva):,}  test={len(Xte):,}")

    # Local SQLite backend (MLflow deprecated the bare file store). Still fully local/free;
    # mlflow.db + mlartifacts/ are gitignored. View with: mlflow ui --backend-store-uri sqlite:///mlflow.db
    mlflow.set_tracking_uri(f"sqlite:///{(ROOT / 'mlflow.db').as_posix()}")
    mlflow.set_experiment("tfl-demand-forecast")

    with mlflow.start_run(run_name="lgbm-daily-station"):
        mlflow.log_params({**PARAMS, "features": ",".join(FEATURES),
                           "train_end": 20250101, "val_end": 20260101})

        model = lgb.LGBMRegressor(**PARAMS)
        model.fit(
            Xtr, ytr,
            eval_set=[(Xva, yva)],
            eval_metric="l1",
            categorical_feature=CATEGORICALS,
            callbacks=[lgb.early_stopping(150), lgb.log_evaluation(200)],
        )
        best_iter = model.best_iteration_ or PARAMS["n_estimators"]
        mlflow.log_metric("best_iteration", best_iter)

        pred_va = model.predict(Xva)
        pred_te = model.predict(Xte)

        # baselines on the held-out test window
        base_med = median_baseline(pd.concat([parts["train"], parts["val"]]), parts["test"])
        base_sn = parts["test"]["dep_lag_7"].to_numpy()
        sn_mask = ~np.isnan(base_sn)  # seasonal-naive undefined for a station's first week

        metrics = {
            "val_mae": _mae(yva, pred_va), "val_rmse": _rmse(yva, pred_va),
            "test_mae": _mae(yte, pred_te), "test_rmse": _rmse(yte, pred_te),
            "median_test_mae": _mae(yte, base_med),
            "seasonal_naive_test_mae": _mae(yte[sn_mask], base_sn[sn_mask]),
        }
        metrics["lift_vs_median_pct"] = 100 * (
            metrics["median_test_mae"] - metrics["test_mae"]) / metrics["median_test_mae"]
        # compare model vs seasonal-naive on the same defined rows
        metrics["lift_vs_seasonal_naive_pct"] = 100 * (
            metrics["seasonal_naive_test_mae"] - _mae(yte[sn_mask], pred_te[sn_mask])
        ) / metrics["seasonal_naive_test_mae"]
        mlflow.log_metrics(metrics)

        # month-by-month backtest on test
        bt = parts["test"][["date_day", TARGET]].copy()
        bt["pred"] = pred_te
        bt["ym"] = bt["date_day"].dt.strftime("%Y-%m")
        backtest = bt.groupby("ym").apply(
            lambda g: pd.Series({"n": len(g), "mae": _mae(g[TARGET], g["pred"])}),
            include_groups=False,
        )

        # persist artifacts
        model.booster_.save_model(str(MODEL_DIR / "lgbm.txt"))
        imp = (pd.DataFrame({"feature": FEATURES, "gain": model.booster_.feature_importance("gain")})
               .sort_values("gain", ascending=False))
        imp.to_csv(MODEL_DIR / "feature_importance.csv", index=False)
        mlflow.log_artifact(str(MODEL_DIR / "lgbm.txt"))
        mlflow.log_artifact(str(MODEL_DIR / "feature_importance.csv"))

        print("\n=== held-out test metrics ===")
        for k, v in metrics.items():
            print(f"  {k:28s} {v:8.3f}")
        print(f"\nbest_iteration: {best_iter}")
        print("\n=== top features (gain) ===")
        print(imp.head(10).to_string(index=False))
        print("\n=== month-by-month backtest (test) ===")
        print(backtest.to_string())

        beats = metrics["lift_vs_median_pct"] > 0 and metrics["lift_vs_seasonal_naive_pct"] > 0
        print("\n" + ("PASS — model beats both baselines on the test window."
                       if beats else
                       "FAIL — does not beat both baselines; iterate features before shipping."))


if __name__ == "__main__":
    main()
