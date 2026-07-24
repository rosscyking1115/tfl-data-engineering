{{ config(materialized='view', tags=['analytics', 'certification']) }}

-- Thin lineage interface over the rigor-owned export.  This model deliberately
-- does not calculate an uplift, comparator, interval, or event count.
select
    'app/gold_export/analysis_rigor.json' as evidence_artifact,
    certificate.certificate_id,
    certificate.evidence_version,
    certificate.adr_id,
    certificate.claim_class,
    certificate.permitted_claim,
    certificate.primary_specification.comparator_family as comparator_family,
    certificate.primary_specification.strike_seed as cited_strike_seed,
    'app/gold_export/demand_deviation.parquet' as station_day_evidence,
    certificate.primary_specification.min_expected_departures as min_expected_departures,
    certificate.primary_specification.grain as grain,
    certificate.generated_at_utc,
    certificate.journey_coverage.min_date as journey_min_date,
    certificate.journey_coverage.max_date as journey_max_date,
    headline.median_ratio as headline_ratio,
    headline.ci95_lo,
    headline.ci95_hi,
    headline.n_events,
    certificate.input_sha256 as input_sha256
from read_json_auto('app/gold_export/analysis_rigor.json')
