"""'Ask the data' QA assistant — Claude answers questions about the TfL gold
layer by calling curated, typed tools over the committed Parquet (via DuckDB).

Design (ADR-0007): correctness comes from constraining the model to a fixed set
of validated tools rather than free-form SQL. The model can only return numbers a
tool produced, and refuses gracefully when a question falls outside the tools.
"""

from pathlib import Path
import json
import os

import anthropic

import data_access as da

# python-dotenv is a local-dev convenience for reading .env; it isn't in the app's
# (lean) requirements, so on Streamlit Cloud it's absent — skip it gracefully. There's
# no .env there anyway; a key, if provided, would come from the environment/secrets.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ModuleNotFoundError:
    pass

MODEL = "claude-opus-4-8"  # per the claude-api guidance; set ANTHROPIC_MODEL to override
MAX_TOOL_TURNS = 6


# --- tool implementations (all query DuckDB/Parquet via data_access) ---

def _search_stations(name_substring: str, limit: int = 20) -> list[dict]:
    names = [n for n in da.station_names() if name_substring.lower() in n.lower()]
    return [{"station_name": n} for n in names[:limit]]


def _top_stations(start_date: str, end_date: str, by: str = "departures", limit: int = 10) -> list[dict]:
    return da.top_stations(start_date, end_date, by, int(limit)).to_dict(orient="records")


def _station_flow(station_name: str, start_date: str, end_date: str) -> dict:
    s = da.station_series(station_name, start_date, end_date)
    if s.empty:
        return {"station_name": station_name, "rows": 0}
    return {
        "station_name": station_name,
        "total_departures": int(s["departures"].sum()),
        "total_arrivals": int(s["arrivals"].sum()),
        "net_inflow": int(s["net_inflow"].sum()),
        "days": int(len(s)),
    }


def _daily_usage_trend(start_date: str, end_date: str) -> dict:
    import pandas as pd

    df = da.daily_stats()
    df = df[(df["date_day"] >= pd.Timestamp(start_date)) & (df["date_day"] <= pd.Timestamp(end_date))]
    if df.empty:
        return {"days": 0}
    total = int(df["journeys"].sum())
    return {
        "days": int(len(df)),
        "total_journeys": total,
        "avg_journeys_per_day": round(df["journeys"].mean(), 1),
        "avg_duration_min": round((df["avg_duration_min"] * df["journeys"]).sum() / max(total, 1), 1),
        "ebike_share": round(df["ebike_journeys"].sum() / max(total, 1), 4),
    }


def _disruption_impact() -> dict:
    head = da.disruption_headline().to_dict(orient="records")
    dates = da.disruption_dates().to_dict(orient="records")
    return {"weather_adjusted_headline": head, "per_disruption_date": dates}


def _live_status() -> dict:
    lines = da.live_line_status()
    docks = da.live_bikepoint()
    out = {}
    if not lines.empty:
        out["snapshot_date"] = str(lines["snapshot_date"].max())
        out["not_good_service"] = lines[~lines["is_good_service"]][
            ["line_name", "status_description", "reason"]
        ].to_dict(orient="records")
    if not docks.empty:
        out["docks_total"] = int(len(docks))
        out["docks_empty"] = int((docks["n_bikes"] == 0).sum())
        out["docks_full"] = int((docks["n_empty_docks"] == 0).sum())
    return out


DISPATCH = {
    "search_stations": _search_stations,
    "top_stations": _top_stations,
    "station_flow": _station_flow,
    "daily_usage_trend": _daily_usage_trend,
    "disruption_impact": _disruption_impact,
    "live_status": _live_status,
}

TOOLS = [
    {
        "name": "search_stations",
        "description": "Find station names containing a text fragment. Use to resolve a "
        "human station name to an exact name before calling station_flow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name_substring": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["name_substring"],
        },
    },
    {
        "name": "top_stations",
        "description": "Busiest stations between two dates (YYYY-MM-DD, inclusive), ranked by "
        "'departures' or 'arrivals'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "by": {"type": "string", "enum": ["departures", "arrivals"]},
                "limit": {"type": "integer"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "station_flow",
        "description": "Total departures, arrivals and net inflow for ONE station over a date "
        "window (YYYY-MM-DD). station_name must be exact — use search_stations first if unsure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "station_name": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["station_name", "start_date", "end_date"],
        },
    },
    {
        "name": "daily_usage_trend",
        "description": "System-wide usage between two dates (YYYY-MM-DD): total journeys, "
        "average per day, average duration, and e-bike share.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "disruption_impact",
        "description": "How tube/rail strikes shifted cycling demand vs a weather-adjusted "
        "baseline: the headline (normal vs disruption day ratios) and every known disruption "
        "date with its actual/expected demand and ratio.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "live_status",
        "description": "The latest daily snapshot: which tube/rail lines are not good service "
        "right now, and current BikePoint dock occupancy (empty/full counts).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _system_prompt() -> str:
    lo, hi = da.date_bounds()
    n = len(da.station_names())
    return (
        "You answer questions about the Transport for London Santander Cycle Hire dataset, "
        f"which covers {lo.date()} to {hi.date()} across {n} docking stations, plus a daily "
        "live layer (line status + dock occupancy).\n\n"
        "Rules:\n"
        "- Answer ONLY using the provided tools. Every number in your answer must come from a "
        "tool result — never estimate, guess, or use outside knowledge for figures.\n"
        "- Briefly say which data backed the answer (e.g. 'from the demand-deviation table').\n"
        "- If a question can't be answered with these tools (weather, other cities, future "
        "predictions, individual riders, causes beyond the data), say so plainly and state what "
        "you CAN answer. Do not fabricate.\n"
        "- Journey data lags ~1-2 months, so you cannot report today's ridership — only the live "
        "line-status and dock snapshot are current.\n"
        "- Be concise."
    )


def answer(question: str, history: list | None = None) -> dict:
    """Run the tool-calling loop. Returns {text, tools_used}."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.getenv("ANTHROPIC_MODEL", MODEL)
    messages = (history or []) + [{"role": "user", "content": question}]
    tools_used = []

    for _ in range(MAX_TOOL_TURNS):
        resp = client.messages.create(
            model=model, max_tokens=1500, system=_system_prompt(),
            tools=TOOLS, messages=messages,
        )
        if resp.stop_reason != "tool_use":
            text = "".join(b.text for b in resp.content if b.type == "text")
            return {"text": text, "tools_used": tools_used}

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                tools_used.append({"name": block.name, "input": block.input})
                try:
                    out = DISPATCH[block.name](**block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(out, default=str)})
                except Exception as exc:  # surface tool errors to the model, don't crash
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": f"error: {exc}", "is_error": True})
        messages.append({"role": "user", "content": results})

    return {"text": "I couldn't complete that within the tool-call limit.", "tools_used": tools_used}
