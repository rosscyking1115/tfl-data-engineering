"""QA assistant (app/assistant.py) — tool dispatch + BYO-key plumbing, no network.

The Anthropic client is faked, so `answer()` runs the full loop without an API call and we can
assert the bring-your-own-key is actually threaded through to the client.
"""

import assistant
import data_access as da
import pandas as pd


def test_tool_schemas_wellformed():
    names = {t["name"] for t in assistant.TOOLS}
    assert names == set(assistant.DISPATCH)  # every declared tool has an implementation
    for t in assistant.TOOLS:
        assert t["name"] and t["description"] and t["input_schema"]["type"] == "object"


def test_top_stations_tool(monkeypatch):
    df = pd.DataFrame({"station_name": ["A"], "departures": [10], "arrivals": [8]})
    monkeypatch.setattr(da, "top_stations", lambda *a, **k: df)
    out = assistant._top_stations("2024-01-01", "2024-12-31")
    assert out == [{"station_name": "A", "departures": 10, "arrivals": 8}]


def test_live_status_tool(monkeypatch):
    lines = pd.DataFrame([{"snapshot_date": "2026-07-09", "line_name": "District",
                           "status_description": "Severe Delays", "reason": "x", "is_good_service": False}])
    docks = pd.DataFrame({"n_bikes": [0, 3], "n_empty_docks": [5, 0]})
    monkeypatch.setattr(da, "live_line_status", lambda: lines)
    monkeypatch.setattr(da, "live_bikepoint", lambda: docks)
    out = assistant._live_status()
    assert out["docks_total"] == 2 and out["docks_empty"] == 1 and out["docks_full"] == 1
    assert out["not_good_service"][0]["line_name"] == "District"


class _FakeResp:
    stop_reason = "end_turn"

    class _Block:
        type = "text"
        text = "Hyde Park Corner was busiest."

    content = [_Block()]


class _FakeClient:
    last_key = None

    def __init__(self, api_key=None):
        _FakeClient.last_key = api_key
        self.messages = self

    def create(self, **kwargs):
        return _FakeResp()


def test_answer_threads_byo_key(monkeypatch):
    monkeypatch.setattr(assistant.anthropic, "Anthropic", _FakeClient)
    monkeypatch.setattr(da, "date_bounds", lambda: (pd.Timestamp("2022-01-01"), pd.Timestamp("2026-06-01")))
    monkeypatch.setattr(da, "station_names", lambda: ["A", "B", "C"])
    res = assistant.answer("who was busiest?", api_key="sk-ant-test-123")
    assert res["text"] == "Hyde Park Corner was busiest."
    assert _FakeClient.last_key == "sk-ant-test-123"  # BYO key reached the client
