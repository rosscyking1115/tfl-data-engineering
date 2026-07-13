# ADR-0006: Pivot from batch pipeline to a live disruption-aware demand workflow

- **Status:** Accepted
- **Date:** 2026-07-08
- **Supersedes:** the "time-boxed, stack-locked, no-web-app" framing of the original plan
  (`docs/tfl-data-engineering-plan.md`), which remains as history.

## Context

The batch pipeline (backfill → Snowflake → dbt → Airflow) was complete but read as a
*documented exercise*, not a working system — "nothing to show." A production-pivot grilling
session + research agents settled the direction: make it a **genuinely-running workflow** that
answers a real question, durable on free tiers, still non-commercial.

## Decision

**Headline capability:** disruption-aware demand deviation — quantify and monitor how
tube/rail disruptions shift cycling demand per station vs a **weather-adjusted** baseline.
Chosen over pure demand forecasting (saturated) and dock-availability nowcasting
(cold-start-blocked — no historical occupancy archive exists).

**Three sub-decisions:**

1. **The journey-lag honesty split.** Journey data is published in bulk with a ~1–2 month
   lag, so "today's cycling demand" is *not* observable live. The workflow therefore splits:
   **historical quantification** (strong — 41M journeys on known strike dates, weather-adjusted)
   + a **live monitoring layer** (current Line Status + dock occupancy) that accumulates
   forward. It never claims real-time trip prediction. This constraint *is* the design.

2. **Snowflake demoted to a documented past phase.** The 30-day trial can't be a durable
   backbone. The durable runtime is **GitHub Actions (public repo) → committed Parquet →
   dbt-duckdb → Streamlit** — no warehouse, no server, near-zero upkeep. Snowflake's batch
   build and credit story stay in the docs as "how the heavy lift was done."

3. **Airflow stays as a local showcase, not the runtime.** Hosting Airflow 24/7 for one daily
   job is pointless; GitHub Actions is the honest free scheduler. Airflow demonstrates "how
   I'd orchestrate at scale."

## Consequences

- The charter in `CLAUDE.md` is rewritten: added tools (DuckDB, Streamlit, GitHub Actions,
  Open-Meteo, dbt-duckdb, MCP) that the old "stack is locked / no web app" rules forbade —
  justified because this is now a living workflow, not the original time-boxed slice.
- Evidence the premise holds: weather-adjusted, disruption days run **1.33× median** demand
  vs **1.00×** normal; warm-weather strikes hit 1.4–2.3×, cold-January strikes correctly stay
  ~0.8× — the weather control keeps it honest.
  *(2026-07-13 correction, rigor-pass citation audit: the January 2024 "strikes" were in fact
  called off on 7 Jan — per the RMT's own announcement — so those two dates were removed from
  the seed. Across the 13 verified, source-cited events the headline is **1.42× median**, and
  the near-baseline cases are explained by event severity (a stations-only partial action and a
  knock-on day), not cold weather. The correction itself is the honesty mechanism working.)*
- The ML **demand-forecasting** deep-dive remains a *separate future project* (breadth belongs
  across projects); this workflow uses a baseline, not a trained model.
- A daily bot commit refreshes the live Parquet — authored as the repo owner to keep the
  contributor list clean.
