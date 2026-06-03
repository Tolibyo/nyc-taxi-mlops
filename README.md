# NYC Taxi — Trip Duration MLOps Pipeline

Predicts how long an NYC yellow-taxi trip will take, in seconds, using only what's
known at pickup time. The point of this project isn't the model. It's the pipeline
around it: reproducible training, experiment tracking, a serving API, drift
checks, tests, and CI. Where accuracy and clean engineering trade off, this leans
toward clean engineering.

## The problem

Predict `trip_duration` using only features available the moment a passenger is
picked up. That constraint is the whole design. It throws out the single most
predictive column, `trip_distance`, because you don't know distance until the trip
ends. Same for dropoff location, fare, and tips. The model works with what a
dispatcher actually has at pickup:

`VendorID`, `passenger_count`, `RatecodeID`, `PULocationID`, and `pickup_hour` /
`pickup_dow` derived from the pickup timestamp.

Target: `trip_duration` = dropoff minus pickup, in seconds.

## Layout

```
scripts/    download.py, train.py, serve.py, monitor.py
src/        cleaning.py        # shared cleaning + feature logic
tests/      test_cleaning.py   # fixture-based unit tests
configs/    one YAML per experiment
data/       reference zone lookup (raw parquet is gitignored)
models/     trained .joblib pipelines (gitignored)
Dockerfile, .github/workflows/ci.yml
pyproject.toml, uv.lock, requirements.txt
```

## How it's built

A few decisions worth pointing at.

**Config-driven training.** `train.py` is one runner. Every experiment is a YAML
file that sets the model, the feature flags, and which months to load. Running one
is `python scripts/train.py --config configs/<name>.yaml`. New experiments are new
config files, not new code.

**One cleaning module everywhere.** `src/cleaning.py` is the single source of truth
for turning raw data into model input. Training imports it directly. The
day-of-week feature uses the same convention on both sides (Polars `.dt.weekday()`
and Python `.isoweekday()` are both Monday=1..Sunday=7), so there's no off-by-one
between training and serving.

**Lazy multi-month loading.** Months are read with `pl.scan_parquet` and
concatenated lazily, so the cleaning filters run before anything is pulled into
memory. A full year, around 36M rows, fits on a laptop. The monthly TLC files mix
nanosecond and microsecond timestamps, which breaks a plain concat, so the loader
casts both to microseconds first.

**Categorical strategy is a config switch.** Linear models get one-hot encoding.
Tree models use native categorical support, which is much faster since it skips the
one-hot blowup. The full year has 262 pickup zones, over HistGradientBoosting's
255-category cap, so that config buckets rare zones into a sentinel and keeps the
top 250.

**Manifest vs lockfile.** `pyproject.toml` declares top-level deps, split into a
runtime set and a dev group. `uv.lock` pins the full tree and is committed, so a
clone or CI rebuilds the exact same environment. `requirements.txt` is generated
from the lockfile and exists only for the Docker build.

**Lean serving image.** The image installs runtime deps only, not the training
stack (no MLflow, Polars, Evidently, pytest). scikit-learn is in there because the
saved pipeline unpickles into sklearn objects even though serve.py never imports it
directly. Deps are installed before code is copied so a code change doesn't bust the
dependency cache. Ends up around 740MB instead of 2GB.

**Tests.** Small synthetic DataFrames, one cleaning rule asserted per test, no
external data, sub-second. CI runs them plus ruff on every push.

## Results

January 2024, about 2.7M rows after cleaning:

| Model | MAE (s) | RMSE (s) | R² |
|---|---|---|---|
| LinearRegression (baseline) | 384 | 531 | 0.378 |
| HistGradientBoosting | 362 | 499 | 0.450 |

Full year, about 36M rows:

| Model | MAE (s) | RMSE (s) | R² |
|---|---|---|---|
| HistGradientBoosting | 416 | 575 | 0.492 |

What the numbers say:

The tree beats the linear baseline, so the gap was real signal, not noise.

Engineered features that just re-state existing info did nothing. Cyclical time
encoding, weekend and rush-hour flags, borough rollup, all landed at R² around
0.450, inside the noise. A boosted tree already pulls those patterns out of the raw
hour, day, and zone columns. Negative result, but a real one.

Full-year R² is higher while the raw error is worse, and that's consistent. More
months means more seasonal structure to explain, so R² goes up. But the full-year
trip durations spread wider, so error in seconds goes up too. R² and absolute error
can move opposite ways across datasets with different spread. R² is the fair
cross-dataset comparison, MAE and RMSE aren't.

The ceiling is about missing information, not the model. R² sits around 0.45 to
0.49 because the most predictive things, distance and live traffic, aren't
available at pickup by design. No other model breaks that. Only new data would.
Knowing why the number is what it is beats chasing a bigger number against a fixed
information budget.

## Quick start

Needs Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
uv pip install -e .

python scripts/download.py                                # fetch the data
python scripts/train.py --config configs/histgb_default.yaml
uv run pytest tests/ -v
```

Serve a trained model:

```bash
uvicorn scripts.serve:app --host 0.0.0.0 --port 8000
```

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"pickup_datetime":"2024-06-15T17:30:00","passenger_count":2,"vendor_id":2,"ratecode_id":1,"pickup_location_id":161}'
# -> {"predicted_duration_sec": 941.8}
```

Docker:

```bash
docker build -t nyc-taxi-serve .
docker run --rm -p 8000:8000 nyc-taxi-serve
```

## Stack

Polars, scikit-learn, MLflow, FastAPI, Evidently, Docker, uv, GitHub Actions.

## Limitations and what's next

This is the foundation layer and it's honest about the edges.

Serve-time zone bucketing isn't wired up yet. The full-year model trains with rare
zones bucketed, but serve.py passes the raw zone through, so requests for rare zones
are served a bit out of distribution. The fix is to save the bucketing from training
and apply the same thing at serve time.

There's no model registry, the served model is a fixed file baked into the image,
and it's single-node with no autoscaling, GPU, or real SLOs.

Next: Kubernetes deployment (local kind, then cloud), infrastructure as code with
Terraform, a model registry with the service behind autoscaling, observability and
SLOs, and a PyTorch plus ONNX path for inference optimization.

## Data

Trip records from the
[NYC Taxi & Limousine Commission](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).
