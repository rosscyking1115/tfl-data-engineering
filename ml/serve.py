"""Local FastAPI serving for the demand model — batch is primary, this is the live demo.

GET /predict?station=<name>&date=<YYYY-MM-DD> returns the model's predicted departures for
that station-day plus the top contributing factors (per-row SHAP contributions), and the
actual departures when known. Loads the committed model + the feature frame once at startup;
no warehouse, no external calls. This is a local demonstration surface — not deployed.

Run from repo root:
  .venv/Scripts/python -m uvicorn serve:app --app-dir ml --port 8000
Smoke test:
  curl "http://127.0.0.1:8000/predict?station=Hyde%20Park%20Corner,%20Hyde%20Park&date=2025-06-15"
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException

from features import FEATURES, TARGET, build_dataset

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "ml" / "model" / "lgbm.txt"

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE["booster"] = lgb.Booster(model_file=str(MODEL))
    df = build_dataset()
    df["name_lc"] = df["station_name"].str.lower()
    STATE["df"] = df
    yield
    STATE.clear()


app = FastAPI(title="TfL cycle-demand model", version="1.0", lifespan=lifespan)


@app.get("/health")
def health():
    df = STATE.get("df")
    return {"status": "ok", "rows": 0 if df is None else len(df),
            "stations": 0 if df is None else int(df["station_key"].nunique())}


@app.get("/predict")
def predict(station: str, date: str):
    df: pd.DataFrame = STATE["df"]
    booster: lgb.Booster = STATE["booster"]

    try:
        dkey = int(pd.Timestamp(date).strftime("%Y%m%d"))
    except Exception:
        raise HTTPException(422, f"Unparseable date: {date!r} (use YYYY-MM-DD).")

    s = station.strip().lower()
    hit = df[(df["name_lc"] == s) & (df["date_key"] == dkey)]
    if hit.empty:  # fall back to a substring match on the station name
        hit = df[(df["name_lc"].str.contains(s, regex=False)) & (df["date_key"] == dkey)]
    if hit.empty:
        lo, hi = df["date_day"].min().date(), df["date_day"].max().date()
        raise HTTPException(
            404,
            f"No station-day for station~={station!r}, date={date}. "
            f"Dates covered: {lo}→{hi} (future dates need recursive lags — out of scope for v1).",
        )

    row = hit.iloc[[0]]
    X = row[FEATURES]
    pred = float(np.clip(booster.predict(X)[0], 0, None))

    # per-row SHAP contributions (last column is the base value)
    contrib = booster.predict(X, pred_contrib=True)[0]
    factors = sorted(
        ({"feature": f, "value": _val(row.iloc[0][f]), "contribution": round(float(c), 2)}
         for f, c in zip(FEATURES, contrib[:-1])),
        key=lambda d: abs(d["contribution"]),
        reverse=True,
    )[:5]

    actual = row.iloc[0][TARGET]
    return {
        "station": row.iloc[0]["station_name"],
        "date": date,
        "predicted_departures": round(pred, 1),
        "actual_departures": None if pd.isna(actual) else int(actual),
        "is_disruption_day": bool(row.iloc[0]["is_disruption"]),
        "base_value": round(float(contrib[-1]), 1),
        "top_factors": factors,
    }


def _val(v):
    """JSON-safe scalar for the response."""
    if pd.isna(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 2)
    return str(v)
