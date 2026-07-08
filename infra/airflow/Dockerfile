FROM apache/airflow:2.11.0

# Loader deps live in Airflow's own environment; dbt gets an ISOLATED venv —
# dbt-core and airflow famously fight over shared dependencies.
RUN pip install --no-cache-dir requests snowflake-connector-python python-dotenv

RUN python -m venv /home/airflow/dbt-venv && \
    /home/airflow/dbt-venv/bin/pip install --no-cache-dir dbt-snowflake
