# ADR-0004: MCP layer — read-only boundary and curated tools

- **Status:** Accepted
- **Date:** 2026-07-08

## Context

Phase 5 (bonus) exposes the gold layer to an AI client via MCP. The governing plan is
explicit that this is "an AI-integration demonstration on top of the pipeline, not pipeline
machinery" (`plan.md:161-174`), and that it must be read-only and scoped to gold. Two
decisions carried real risk and are recorded here.

## Decision 1: the guardrail lives in Snowflake, not in Python

The MCP server connects as a least-privilege role **`TFL_GOLD_READONLY`**
(`mcp/setup_readonly_role.sql`): USAGE on `TFL_WH` + `TFL` + `TFL.GOLD`, `SELECT` on gold
tables/views only. It has no DML/DDL and no SILVER/RAW access. So even a buggy or
prompt-injected tool physically cannot write or reach un-curated data — the database
rejects it, not application code.

### The trap that verification caught
Connecting with `role=TFL_GOLD_READONLY` was **not enough**. The Snowflake trial account
sets `DEFAULT_SECONDARY_ROLES = ('ALL')`, so the session silently carried the user's other
roles — including ACCOUNTADMIN. First verification proved it: `INSERT` into gold and
`SELECT` on SILVER both **succeeded** when they must fail. The fix is
**`use secondary roles none`** immediately after connect (in `_query()` in
`mcp/gold_server.py`). Re-verified: SELECT gold ✓, INSERT gold denied, CREATE denied,
SELECT silver denied. Without that one statement the read-only role is defeated.

## Decision 2: curated typed tools, never free-form SQL

The server exposes four parameterized tools — `search_stations`, `top_stations`,
`daily_usage_trend`, `station_flow` — each with typed args, a docstring contract, and
**bind parameters** (no string-formatted SQL). There is deliberately **no
`run_sql(query)` tool**. The whole value of MCP-over-warehouse is that the model calls a
named, safe tool instead of guessing SQL against tables it can't see; a generic SQL
escape hatch would throw that away and reintroduce injection risk. If a needed question
isn't covered, the fix is to add a curated tool, not to open a raw SQL door.

## Consequences

- The server is safe to point any MCP client at (registered in `.mcp.json`). Read-only
  role + secondary-roles-none + curated tools are three independent layers.
- Cost stays trivial: tools hit XS `TFL_WH` (60 s auto-suspend); each call is one short
  query.
- Framed in the README as AI-adjacent demonstration; the pipeline stands alone without it.

## Addendum (2026-07-10): retargeted to the committed Parquet (durable)

The server now queries the **committed gold Parquet** (`app/gold_export/`) via DuckDB instead of
Snowflake — the same trial-independent source as the Streamlit app — so the demonstration keeps
working after the trial ends, with no credentials. The four curated tools and their contracts are
unchanged; only `_query()` swapped its backend.

The read-only guarantee now comes from **DuckDB-over-Parquet**: the connection opens the files
read-only (no write path) and the tools expose only three gold rollups as views, so an errant or
prompt-injected call cannot write or reach un-curated data — the same property the Snowflake role
gave, without a warehouse. Decision 2 (curated typed tools, no free-form SQL) stands as the primary
guardrail. The original Snowflake `TFL_GOLD_READONLY` + `use secondary roles none` design above is
**retained as history** — it records a real verification finding (the `DEFAULT_SECONDARY_ROLES=ALL`
leak) worth keeping even though the runtime no longer depends on it.
