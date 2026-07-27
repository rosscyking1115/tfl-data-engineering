# Directions not taken

A product scan on **2026-07-27** examined four directions out of this repo and killed all
four, at roughly 85% confidence. This file records why, so they are not revisited without
new evidence. It is a record of a scan's conclusions, not a claim this repo tested them.

The scan also confirmed that Tube-relevant published history totals **under 2GB**. Nothing
here justifies cloud infrastructure, and the DuckDB / committed-Parquet / GitHub Actions
runtime stays as it is.

## Killed

**Disruption alerting and reliability history.** Tube Alerter already ships per-line
reliability with full-year windows and hourly heatmaps, free. The premise that "TfL keeps
no history" is a nine-year constant, not a recent change — a standing gap with no new
opening is not a reason to build.

**Step-free and accessible routing.** TfL Go ships four step-free tiers with per-platform
gap measurements. Citymapper has matched that for years, and Sociability is funded and
converging on the same ground.

**B2B footfall analytics.** The underlying data is free. The panel vendors in this market
sell mobile-device data, which is a different product; they are not competing on this.

**Archiving what TfL discards.** This is the manufactured-gap pattern: every live feed
discards history, so the pattern generates an unlimited supply of "gaps" without any
evidence that anyone wants them filled. Absence of an archive is not demand for one.

## Open question the scan could not close

Whether TfL Go distinguishes **which** lift is out at a multi-line station. The Stop
Structure API (March 2026) models station interiors as a graph with typed walkways,
stairs, escalators and lifts carrying walking durations, which newly makes that
computable. Recorded because it is genuinely unresolved — not proposed as a project.

## What the scan did produce

One data upgrade, taken: daily station footfall as a live-layer context series
([ADR-0013](adr/ADR-0013-station-footfall-context-series.md)). It narrows the journey
publishing lag that ADR-0006 documents. It is not a product and makes no new claim about
what this repo proves.
