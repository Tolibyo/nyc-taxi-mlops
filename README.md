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
scripts/        download.py, train.py, serve.py, monitor.py
src/            cleaning.py        # shared cleaning + feature logic
tests/          test_cleaning.py, test_api.py   # unit + API tests
configs/        one YAML per experiment
data/           reference zone lookup (raw parquet is gitignored)
k8s/local/      kind manifests + cluster config (deployment, service, ingress)
k8s/eks/        cloud manifests for EKS (deployment, service, ingress)
helm/           helm chart (templated manifests + values)
terraform/      s3 model bucket + IAM, as code (LocalStack)
terraform/eks/  EKS cluster, node group, IRSA, LB controller, as code (real AWS)
models/         trained .joblib pipelines (gitignored)
Dockerfile, .github/workflows/ci.yml
pyproject.toml, uv.lock
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
clone, CI, and the Docker build all rebuild the exact same environment. There's no
`requirements.txt` — the image installs straight from the lockfile with
`uv sync --locked`, one source of truth.

**Lean serving image.** Built on the `uv` base image, installing runtime deps only
via `uv sync --locked`, not the training stack (no MLflow, Polars, Evidently,
pytest). scikit-learn is in there because the saved pipeline unpickles into sklearn
objects even though serve.py never imports it directly; boto3 is in for the optional
S3 model fetch. Deps are synced before code is copied so a code change doesn't bust
the dependency cache. Runtime-only keeps it a fraction of the ~2GB full stack.

**Validation at the door, model on first request.** `serve.py` mirrors the
cleaning rules as Pydantic field constraints, so a request the training data
would have filtered out gets a 422 instead of a silent prediction on
out-of-distribution input. The model loads lazily on the first `/predict` call
rather than at import, which keeps the app importable without the artifact and
makes the API suite runnable in CI.

**Tests.** Two suites. The cleaning tests use small synthetic DataFrames, one
rule asserted per test. The API tests run FastAPI's TestClient against the app
in process: request contract, boundary validation at the edges of every field
rule, and a rare-zone parity check that sends two bucketed zones through
`/predict` and requires identical predictions, proving the bucketing applies at
serve time. No external data, sub-second, CI runs everything plus ruff on every
push.

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

## Kubernetes

Runs on Kubernetes, verified locally on [kind](https://kind.sigs.k8s.io/). The
manifests in `k8s/local/` target kind — nginx ingress, the locally side-loaded
image (`imagePullPolicy: IfNotPresent`), model baked into the image, served behind a
Service and Ingress. The cloud variant lives in `k8s/eks/` and differs where it has
to (ALB ingress class, the ECR image); see Cloud below.

```bash
kind create cluster --name mlops --config k8s/local/kind-config.yaml
kind load docker-image nyc-taxi-serve:latest --name mlops

kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=90s

kubectl apply -f k8s/local/taxi-deployment.yaml -f k8s/local/taxi-service.yaml -f k8s/local/taxi-ingress.yaml
```

Predict through the ingress (port 80, routed to the service on 8000):

```bash
curl -X POST http://localhost/predict \
  -H "Content-Type: application/json" \
  -d '{"pickup_datetime":"2024-06-15T17:30:00","passenger_count":2,"vendor_id":2,"ratecode_id":1,"pickup_location_id":161}'
```

## Helm

The same app is packaged as a Helm chart in `helm/`, bundling the manifests with
templated values so config (image, replicas, port) is set without editing YAML.
Deploy the whole release in one command; `--set` or a per-environment values file
overrides defaults. Stateful storage is deliberately kept out of the chart so an
uninstall can't delete data.

```bash
helm install taxi ./helm
helm upgrade taxi ./helm --set replicaCount=3
helm rollback taxi 1
```

Requires the `nyc-taxi-serve` image built and loaded into the cluster (see above).

## Model storage

`serve.py` loads the model from the image by default, or fetches it from S3 when
`MODEL_BUCKET` is set. The bucket and IAM read access are provisioned as code in `terraform/`, verified locally
against [LocalStack](https://localstack.cloud/). Credentials and the S3 endpoint come
from the environment (`.env`, gitignored; `.env.example` is the template), so no secrets
live in code. Against real AWS the same `serve.py` drops the endpoint and picks up the
serving role's credentials automatically.

```bash
docker run -d -p 4566:4566 localstack/localstack:3      # local AWS
cd terraform && terraform init && terraform apply        # provision bucket + IAM
aws --endpoint-url=http://localhost:4566 s3 cp \
  models/histgb_full_year_pipeline.joblib s3://nyc-taxi-models/
```

## Cloud (EKS)

The full serving stack runs on a real EKS cluster, provisioned in Terraform under
`terraform/eks/` (separate from the LocalStack `terraform/`): one network across two
AZs from the VPC layer, an EKS control plane, and a managed node group of two
t3.medium workers in the private subnets. `aws eks update-kubeconfig` points kubectl
at the cluster.

Public traffic goes through the AWS Load Balancer Controller, which turns a
Kubernetes Ingress into a real ALB. It gets its AWS permissions through IRSA (IAM
Roles for Service Accounts): an OIDC provider, an IAM role scoped to a single service
account, and that service account annotated with the role's ARN.

The whole control layer is code — the controller (a `helm_release`), its IAM role and
policy, the OIDC provider, and the service account (a `kubernetes_service_account`)
are all in Terraform, so one `terraform apply` brings the cluster and its control
layer up from scratch.

The app itself — Deployment, Service, Ingress — lives in `k8s/eks/`, applied with
kubectl. The Ingress carries the ALB annotations: internet-facing scheme, IP target
type, and a `/health` healthcheck path.

```bash
# infrastructure (from terraform/eks/)
cd terraform/eks
terraform init && terraform plan && terraform apply
aws eks update-kubeconfig --region us-east-1 --name tripsvc

# app (from repo root)
kubectl apply -f k8s/eks/
kubectl get ingress tripsvc            # wait for the ADDRESS column to fill
```

Predict through the ALB (internet-facing, port 80 to the service on 8000):

```bash
curl -X POST http://<alb-address>/predict \
  -H "Content-Type: application/json" \
  -d '{"pickup_datetime":"2024-06-15T17:30:00","passenger_count":2,"vendor_id":2,"ratecode_id":1,"pickup_location_id":161}'
# -> {"predicted_duration_sec": 1737}
```

Tear down with `terraform destroy` — delete the Ingress first
(`kubectl delete -f k8s/eks/ingress.yaml`) so the controller removes the ALB before
the cluster goes, otherwise the load balancer is orphaned.

## Stack

Polars, scikit-learn, MLflow, FastAPI, Evidently, Docker, Kubernetes, Helm, Terraform, uv, GitHub Actions.

## Limitations and what's next

This is the foundation layer and it's honest about the edges.

There's no model registry yet. When fetched from S3 it's a fixed key, not versioned,
and it's single-node with no autoscaling, GPU, or real SLOs.

Next: fold the app manifests (Deployment, Service, Ingress) into Terraform so the
whole stack, not just the control layer, comes up from one apply; add
readiness/liveness probes and resource limits to the cloud manifests; a model
registry with the service behind autoscaling, observability and SLOs; and a PyTorch
plus ONNX path for inference optimization.

## Data

Trip records from the
[NYC Taxi & Limousine Commission](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).