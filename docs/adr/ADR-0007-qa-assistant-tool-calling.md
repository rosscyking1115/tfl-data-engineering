# ADR-0007: "Ask the data" QA assistant — curated tool-calling over text-to-SQL

- **Status:** Accepted
- **Date:** 2026-07-09

## Context

The workflow needed a natural-language QA layer. The hard part of any data-QA assistant is
**correctness** — not fabricating numbers. Research (2026) is consistent: raw text-to-SQL
hits an "accuracy cliff" on real schemas (on the enterprise Spider 2.0 benchmark GPT-4o
scored ~10%; on truly private warehouse data ~0–2%) and fails by *silent wrongness* — a
plausible but wrong figure. Constraining the model's output space (curated typed tools, or a
semantic layer) is the reliability-first pattern, and the project already had a curated
read-only MCP as a hand-built semantic surface.

## Decision

Build the assistant as a **Claude tool-calling loop over a fixed set of curated, typed tools**
(`app/assistant.py`), not text-to-SQL and not a heavy framework.

- **Tools, not SQL.** Six read-only tools (`search_stations`, `top_stations`, `station_flow`,
  `daily_usage_trend`, `disruption_impact`, `live_status`) wrap the existing
  `app/data_access.py` queries over the committed gold **Parquet via DuckDB** — trial-independent,
  same as the app. The model can only surface numbers a tool returned.
- **Plain Anthropic SDK, `claude-opus-4-8`, manual loop.** No LangChain/LlamaIndex — a
  six-tool agent doesn't need the weight; the manual loop is easy to explain and audit.
  (`ANTHROPIC_MODEL` overrides the model, e.g. Haiku 4.5 for cost.)
- **Refusal is the guardrail.** The system prompt forbids un-tool-backed figures and instructs
  the model to decline out-of-scope questions (weather, other cities, real-time prediction,
  individual riders) rather than guess — the honest counterpart to the journey-lag constraint
  (ADR-0006).
- **Evaluated, not asserted.** `eval/` holds a golden Q&A set (incl. deliberately out-of-scope
  questions) and a harness that grades tool choice + answer content and reports a confusion
  table whose target is **zero confidently-wrong** answers.

## Consequences

- Coverage is intentionally capped by the tool set; the assistant refuses beyond it (the
  reliability feature, not a bug). New questions → add a tool, never open raw SQL.
- **Cost/abuse note:** each question spends Anthropic API credits. A public Streamlit deploy
  wired to the owner's key lets anonymous visitors spend it — so the Ask page stays **inert
  unless a key is present**, and the key should be kept out of public Streamlit secrets (demo
  the assistant locally or via screenshot). The rest of the app needs no key.
- The separate MCP server (`mcp/`) remains the "AI clients connect directly" demonstration;
  this assistant is the in-app chat. Both share the curated-tools philosophy.
