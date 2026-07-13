# ADR-0009: The analytical contract — claim, design, assumptions, falsifiers

- **Status:** Accepted
- **Date:** 2026-07-13

## The claim, stated precisely

> On days with a verified, source-cited London Underground strike, Santander cycle-hire demand
> runs at a **median 1.42× its weather-adjusted expectation** (95% bootstrap CI **1.24–1.61**,
> 13 events, 2022–2025). We report this as an **observed association**, not a causal effect:
> the event-study design is *consistent with* displaced Tube journeys landing on the bikes, but
> observational transport data cannot rule out every confounder, and we do not claim it can.

Scoping the claim as associational is deliberate. A causal claim would have to defend, among
other things, that strike timing is unrelated to every demand driver — and strikes are announced
in advance, seasonally clustered, and weather-correlated in their *effects*. The honest framing
is the defensible one.

## Design

- **Unit:** station × day. **Grain:** daily (the committed gold grain; an hourly rollup is
  banked in `app/gold_export/hourly/` for a future intra-day event study).
- **Treatment:** a qualifying disruption day — v1 uses the **citation-backed strike seed**
  (`dbt/seeds/disruption_dates.csv`; every row carries `source_url`). Strikes are network-wide,
  so exposure is network-wide by construction in v1 (a proximity-based exposure for line-level
  events becomes possible with the snapshot-derived event log + station coordinates).
- **Counterfactual ("expected demand"), two independent families:**
  1. **Stratified median** — median departures for the same station × ISO weekday ×
     wet (≥1 mm) × cold (<8 °C mean) bucket (`expected_demand.sql`).
  2. **LightGBM counterfactual** — the demand model predicted with the disruption flag off
     (ADR-0008), which additionally conditions on continuous weather, calendar, and each
     station's own recent demand.
  Agreement between the two (1.42× vs 1.30×) is part of the evidence; neither is hand-tuned to
  produce the headline.
- **Statistic:** median of station-day `actual / expected` ratios on treatment days, with
  small-expected station-days filtered (expected ≥ 5) to avoid ratio blow-ups.

## Uncertainty, placebo, robustness (analysis/rigor.py — seeded, reproducible)

- **CI:** cluster bootstrap resampling **event days** (the independent unit; station-days within
  a strike day are correlated), 2,000 replicates, percentile 95% interval.
- **Placebo / negative control:** the identical statistic on 1,000 random sets of 13
  **non**-disruption dates, matched to the real events' day-of-week composition. Result: null
  median 1.00, 97.5th percentile 1.089, one-sided **p < 0.001** — the pipeline does not
  manufacture the signal from ordinary days.
- **Sensitivity battery:** the headline across wet ∈ {0.5, 1, 2 mm} × cold ∈ {6, 8, 10 °C}
  stays within **1.39–1.47**; across min-expected ∈ {3, 5, 10} and both baseline families it
  remains clearly elevated. No single arbitrary choice carries the result.

## Assumptions (each is a falsifier a reviewer should probe)

1. **Baseline comparability:** same-station, same-weekday, same-weather-bucket days are a fair
   "normal". *Threat:* residual confounding (events, holidays, seasonal drift). Partially
   addressed by the ML family (richer conditioning); not eliminable in observational data.
2. **Weather control adequacy:** binary wet/cold buckets are coarse. *Mitigation:* sensitivity
   battery + the ML family's continuous weather features.
3. **Event log correctness:** a mislabeled event biases the estimate — demonstrated concretely
   by the **January 2024 correction** (below). *Mitigation:* per-row source citations.
4. **No-data ≠ zero:** absent station-days must not be read as zero demand (guarded in the
   data-quality layer).
5. **Two-horizon honesty:** deep strike history exists only because strikes are publicly
   documented; the API-derived event log (`disruption_events`) accumulates forward from
   2026-07-08 only. Analyses of non-strike disruption types are limited to that window.

## Correction log

- **2026-07-13:** citation audit found the planned January 2024 tube strikes (8 & 10 Jan) were
  **called off on 7 Jan** (RMT: "Tube strike averted after progress made in dispute"). Both rows
  removed from the seed; headline moved 1.33× → 1.42×; the former "cold strikes stay below
  baseline" narrative was retired (those were ordinary cold days). The near-baseline events that
  remain are explained by **severity** (a stations-only partial action, 0.95×; a knock-on day,
  1.00×), not weather.

## Out of scope (v1)

Causal identification; intra-day dynamics (hourly rollup banked, not analysed); station-level
spatial exposure for line-level events (coordinates land in the rigor pass; radius sensitivity
planned); forecasting future strikes' demand (the ML model deliberately cannot anticipate strike
magnitude — that residual *is* the measured association).
