"""Consumer lineage and local-Airflow guards for the certified evidence path."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_streamlit_shows_certificate_lineage_without_a_second_calculation():
    page = _text("app/app_pages/disruption_impact.py")
    access = _text("app/data_access.py")
    assert "da.certified_evidence()" in page
    assert "Evidence lineage" in page
    assert "Source-cited strike seed" in page
    assert "def certified_evidence_lineage" in access
    assert "median(deviation_ratio)" not in page


def test_powerbi_and_dbt_expose_the_same_rigor_lineage():
    query = _text("powerbi/queries.pq")
    model = _text("powerbi/model.tmdl")
    dbt_model = _text("dbt/models/analytics/certified_adr0009_evidence.sql")
    exposures = _text("dbt/models/analytics/exposures.yml")
    assert "analysis_rigor.json" in query
    assert "evidence_artifact" in query
    assert "cited_strike_seed" in query
    assert "evidence_artifact" in model
    assert "cited_strike_seed" in model
    assert "evidence_artifact" in dbt_model
    assert "cited_strike_seed" in dbt_model
    assert "streamlit_certified_adr0009" in exposures
    assert "powerbi_certified_adr0009" in exposures
    assert "ref('certified_adr0009_evidence')" in exposures


def test_local_airflow_dags_parse_and_guard_delivery_order():
    dags_dir = ROOT / "infra" / "airflow" / "dags"
    for path in dags_dir.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    defaults = _text("infra/airflow/dags/alert_utils.py")
    ingest = _text("infra/airflow/dags/daily_api_ingest.py")
    dbt = _text("infra/airflow/dags/dbt_build_and_test.py")
    monthly = _text("infra/airflow/dags/monthly_history_check.py")
    assert not (dags_dir / "failure_alert_demo.py").exists()
    assert '"retries": 2' in defaults
    assert '"on_failure_callback": notify_failure' in defaults
    assert "default_args=DEFAULT_ARGS" in ingest
    assert "default_args=DEFAULT_ARGS" in dbt
    assert "default_args=DEFAULT_ARGS" in monthly
    assert "wait_for_completion=True" in ingest
    assert "allowed_states=[\"success\"]" in ingest
    assert "failed_states=[\"failed\"]" in ingest
    assert "{{ ds }}" in ingest
    assert "max_active_runs=1" in ingest
    assert "schedule=None" in dbt
    assert "max_active_runs=1" in dbt
    assert "local-demo" in ingest and "local-demo" in dbt


def test_documentation_leads_with_the_decision_and_two_horizon_boundary():
    readme = _text("README.md")
    note = _text("docs/certified_evidence.md")
    assert "## Analyst investigation" in readme
    assert "observed association, not\ncausation" in readme
    assert "GitHub Actions + committed\nParquet/DuckDB" in readme
    assert "Airflow is a local portfolio demonstration" in readme
    assert "## Analyst investigation" in note
    assert "observed\nassociation, not causation" in note
    assert "Two data horizons" in note
