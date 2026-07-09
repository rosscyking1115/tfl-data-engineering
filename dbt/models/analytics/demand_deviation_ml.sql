{{ config(materialized='external', location='app/gold_export/demand_deviation_ml.parquet') }}

-- Model-based counterpart to demand_deviation: actual departures vs the LightGBM
-- counterfactual baseline (predicted with the disruption flag forced off, ml/predict.py).
-- Because the baseline is learned per station from calendar + weather + recent-demand
-- lags, "normal" is far sharper than the median-by-bucket in expected_demand — so the
-- disruption uplift stands out more cleanly. Both tables are kept for A/B comparison.

with actual as (
    select
        f.date_key,
        cast(strptime(cast(f.date_key as varchar), '%Y%m%d') as date) as date_day,
        f.station_key,
        s.station_name,
        f.departures
    from {{ source('gold_export', 'station_daily_flows') }} f
    join {{ source('gold_export', 'dim_station') }} s on f.station_key = s.station_key
)

select
    a.date_key,
    a.date_day,
    a.station_key,
    a.station_name,
    a.departures,
    p.predicted_departures                                            as expected_departures,
    a.departures - p.predicted_departures                            as deviation,
    round(a.departures / nullif(p.predicted_departures, 0), 3)       as deviation_ratio,
    (dd.date is not null)                                            as is_disruption,
    dd.severity                                                       as disruption_severity
from actual a
left join {{ source('gold_export', 'predicted_demand') }} p
    on a.station_key = p.station_key
   and a.date_key = p.date_key
left join {{ ref('disruption_dates') }} dd
    on a.date_day = cast(dd.date as date)
