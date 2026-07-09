# Local serving image for the demand model. Batch prediction is the primary path;
# this packages the FastAPI /predict endpoint for a runnable demo. Not deployed anywhere.
# Build from the repo root:  docker build -f ml/Dockerfile -t tfl-demand-api .
# Run:                       docker run -p 8000:8000 tfl-demand-api
FROM python:3.13-slim

WORKDIR /srv
COPY ml/requirements.txt ml/requirements.txt
RUN pip install --no-cache-dir -r ml/requirements.txt

# Only what serving needs: the model, feature code, gold Parquet, and the disruption seed.
COPY ml/ ml/
COPY app/gold_export/ app/gold_export/
COPY dbt/seeds/disruption_dates.csv dbt/seeds/disruption_dates.csv

EXPOSE 8000
CMD ["uvicorn", "serve:app", "--app-dir", "ml", "--host", "0.0.0.0", "--port", "8000"]
