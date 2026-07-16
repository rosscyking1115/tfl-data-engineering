# One-command entry points (sh-compatible; on Windows run via Git Bash, or use the
# PowerShell equivalents shown in each target's comment).
PY := .venv/Scripts/python

setup:            ## create venv + install app/test deps  (PS: python -m venv .venv; .venv\Scripts\pip install ...)
	python -m venv .venv
	$(PY) -m pip install -r app/requirements.txt -r ml/requirements.txt pytest ruff dbt-duckdb

test:             ## lint + unit tests                     (PS: .venv\Scripts\python -m pytest)
	$(PY) -m ruff check app ml tests ingestion analysis benchmark
	$(PY) -m pytest

benchmark-validate: ## validate contracts, fixture hashes, and scenarios
	$(PY) -m benchmark.reliability_reference validate

benchmark-duckdb: benchmark-validate ## run the complete DuckDB conformance suite
	mkdir -p .benchmark-output/duckdb
	$(PY) -m benchmark.reliability_reference run --engine duckdb --scenario all --output .benchmark-output/duckdb

benchmark-spark: benchmark-validate ## run Spark 4.0.1 by immutable container digest
	mkdir -p .benchmark-output/spark
	docker run --rm -v "$(CURDIR):/repo:ro" -v "$(CURDIR)/.benchmark-output/spark:/out" apache/spark:4.0.1-java21-python3@sha256:fb5c5e61e7bb1be94b7f3a31afe1f73c5b4d20b6008f4ffa7278fc085da08a9e /opt/spark/bin/spark-submit /repo/tests/spark_reference_check.py /out

benchmark-compare: ## compare decoded DuckDB and Spark semantics
	$(PY) -m benchmark.reliability_reference compare --duckdb .benchmark-output/duckdb --spark .benchmark-output/spark --output .benchmark-output/comparison

benchmark: benchmark-duckdb benchmark-spark benchmark-compare ## complete portable conformance run

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

.PHONY: setup test benchmark-validate benchmark-duckdb benchmark-spark benchmark-compare benchmark build daily analysis app sample-run
