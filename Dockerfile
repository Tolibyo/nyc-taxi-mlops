
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app


COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY models/histgb_full_year_pipeline.joblib ./models/

RUN uv sync --locked --no-editable

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "scripts.serve:app", "--host", "0.0.0.0", "--port", "8000"]