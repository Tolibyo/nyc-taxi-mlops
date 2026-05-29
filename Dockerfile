
FROM python:3.11-slim


WORKDIR /app


COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e . --no-deps


COPY src/ ./src/
COPY scripts/ ./scripts/


COPY models/histgb_full_year_pipeline.joblib ./models/

EXPOSE 8000

CMD ["uvicorn", "scripts.serve:app", "--host", "0.0.0.0", "--port", "8000"]