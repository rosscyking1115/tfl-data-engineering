# Certified ADR-0009 evidence

## Analyst investigation

**Decision supported:** determine whether a verified, source-cited London Underground strike is
associated with an unusual change in cycle-hire demand before using disruption as an explanatory
factor in analyst investigation. The certified answer is deliberately narrow: **observed
association, not causation**. It does not predict a future journey, attribute a causal effect, or
turn the forward-collected disruption log into historical coverage.

The authoritative result is
[`app/gold_export/analysis_rigor.json`](../app/gold_export/analysis_rigor.json). Its certificate
locks ADR-0009, the station × day grain, primary stratified-median comparator, the LightGBM
counterfactual family, eligibility (expected departures at least five), uncertainty evidence and
the source-cited strike seed. dbt, Streamlit and Power BI expose that artifact; none recalculates
the uplift.

## Evidence to consumers

| Stage | Artifact | Role |
|---|---|---|
| Strike provenance | [`dbt/seeds/disruption_dates.csv`](../dbt/seeds/disruption_dates.csv) | Source-cited historical strike seed. |
| Station-day measurement | [`app/gold_export/demand_deviation.parquet`](../app/gold_export/demand_deviation.parquet) | Historical actual-versus-expected evidence at station × day. |
| Certified result | [`app/gold_export/analysis_rigor.json`](../app/gold_export/analysis_rigor.json) | Sole owner of the headline, comparator, eligibility, uncertainty and permitted language. |
| dbt interface | [`certified_adr0009_evidence.sql`](../dbt/models/analytics/certified_adr0009_evidence.sql) | Thin, reviewable lineage interface; it contains no uplift calculation. |
| Streamlit | [`app/app_pages/disruption_impact.py`](../app/app_pages/disruption_impact.py) | Reads the certificate and shows its provenance; raw event/station views are diagnostic. |
| Power BI | [`powerbi/queries.pq`](../powerbi/queries.pq) | Imports a disconnected certificate table from the same JSON artifact. |

The dbt exposures `streamlit_certified_adr0009` and `powerbi_certified_adr0009` make those two
consumer paths visible in generated dbt documentation.

## Two data horizons

Historical quantification relies on source-cited strike dates and journey data, which is published
in bulk with a lag. The live Line Status and BikePoint feeds have no supplied historical archive;
the repository only has the disruption events it has collected since 2026-07-08. Therefore
`disruption_events` is a forward-only, line × start-date operational log. It can support monitoring
and diagnostic views, but it must not be presented as deep historical disruption coverage.

## Operations boundary

GitHub Actions rebuilds, validates and commits the durable Parquet/DuckDB runtime. Airflow is kept
as a local portfolio demonstration: it retries bounded failures, serialises local runs, and awaits
the triggered dbt result. It is not the durable scheduler and does not alter the certified claim.
