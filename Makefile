# One-command entry points (sh-compatible; on Windows run via Git Bash, or use the
# PowerShell equivalents shown in each target's comment).
PY := .venv/Scripts/python

setup:            ## create venv + install app/test deps  (PS: python -m venv .venv; .venv\Scripts\pip install ...)
	python -m venv .venv
	$(PY) -m pip install -r app/requirements.txt -r ml/requirements.txt pytest ruff dbt-duckdb

test:             ## lint + unit tests                     (PS: .venv\Scripts\python -m pytest)
	$(PY) -m ruff check app ml tests ingestion analysis
	$(PY) -m pytest

build:            ## full dbt DAG on DuckDB, warehouse-free (needs local silver from the backfill)
	$(PY) -m dbt.cli.main deps --project-dir dbt --profiles-dir dbt
	$(PY) -m dbt.cli.main build --target duckdb --project-dir dbt --profiles-dir dbt

daily:            ## the same steps the GitHub Actions cron runs
	$(PY) ingestion/live_snapshot.py
	$(PY) ingestion/journey_increment.py
	$(PY) -m dbt.cli.main build --target duckdb --select +tag:analytics --project-dir dbt --profiles-dir dbt

analysis:         ## regenerate the rigour battery (CIs, placebo, sensitivity)
	$(PY) analysis/rigor.py

app:              ## run the Streamlit app on the committed Parquet
	$(PY) -m streamlit run app/streamlit_app.py

sample-run:       ## end-to-end taste in seconds: parse+aggregate the committed sample extract
	$(PY) scripts/sample_run.py

.PHONY: setup test build daily analysis app sample-run
