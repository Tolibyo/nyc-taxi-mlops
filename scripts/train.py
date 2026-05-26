
import argparse
import yaml
from pathlib import Path

import polars as pl
import pandas as pd
import numpy as np
import joblib
import mlflow
import mlflow.sklearn

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score

from src.cleaning import clean_dataframe

PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "yellow" / "2024" / "yellow_tripdata_2024-01.parquet"
MODEL_PATH = PROJECT_ROOT / "models"

parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True, type=str)
args = parser.parse_args()

with open(args.config) as f:
    config = yaml.safe_load(f)

print(f"Running experiment: {config['experiment_name']}")

df_raw = pl.read_parquet(DATA_PATH)
df_clean = clean_dataframe(df_raw)
print(df_clean.shape)

subsample_n = config["data"]["subsample_rows"]
if subsample_n is not None:
    df_clean = df_clean.sample(n=subsample_n, seed=42)

feature_cols = ["VendorID", "passenger_count", "RatecodeID", "PULocationID", "pickup_hour", "pickup_dow"]
X = df_clean.select(feature_cols)
y = df_clean["trip_duration"]

if config["features"]["cyclical_time"]:
    X = X.with_columns(
    (2 * np.pi * pl.col("pickup_hour") / 24).sin().alias("pickup_hour_sin"),
    (2 * np.pi * pl.col("pickup_hour") / 24).cos().alias("pickup_hour_cos"),
    (2 * np.pi * pl.col("pickup_dow") / 7).sin().alias("pickup_dow_sin"),
    (2 * np.pi * pl.col("pickup_dow") / 7).cos().alias("pickup_dow_cos"),
).drop(["pickup_hour", "pickup_dow"])

print(f"Feature columns: {X.columns}")

categorical_cols = ["VendorID", "RatecodeID", "PULocationID"]
numeric_cols = [c for c in X.columns if c not in categorical_cols]

print(f"Categorical: {categorical_cols}")
print(f"Numeric: {numeric_cols}")

preprocessor = ColumnTransformer(
    transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_cols),
        ("num", "passthrough", numeric_cols),
    ]
)

X_pd = X.to_pandas()
y_pd = y.to_pandas()
X_train, X_test, y_train, y_test = train_test_split(X_pd, y_pd, test_size=0.2, random_state=42)
print(X_train.shape, X_test.shape)

model_type = config["model"]["type"]
model_params = config["model"].get("params", {}) or {}

if model_type == "LinearRegression":
    model = LinearRegression(**model_params)
elif model_type == "HistGradientBoostingRegressor":
    model = HistGradientBoostingRegressor(**model_params, random_state=42)
else:
    raise ValueError(f"Unknown model type: {model_type}")

print(f"Model: {model.__class__.__name__}")

pipeline = Pipeline(steps=[
    ("preprocess", preprocessor),
    ("model", model)
])

mlflow.set_experiment(config["experiment_name"])

with mlflow.start_run():
    # Log all config params for reproducibility
    mlflow.log_param("model_type", model_type)
    mlflow.log_param("cyclical_time", config["features"]["cyclical_time"])
    mlflow.log_param("categorical_strategy", config["features"]["categorical_strategy"])
    mlflow.log_param("subsample_rows", config["data"]["subsample_rows"])
    mlflow.log_param("n_train_rows", len(X_train))
    mlflow.log_param("n_features", X_train.shape[1])
    mlflow.log_param("data_source", "yellow_tripdata_2024-01")
    for k, v in model_params.items():
        mlflow.log_param(f"hp_{k}", v)

    # Fit
    pipeline.fit(X_train, y_train)
    print("training complete")

    # Evaluate
    y_pred = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = root_mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    mlflow.log_metric("mae", mae)
    mlflow.log_metric("rmse", rmse)
    mlflow.log_metric("r2", r2)

    print(f"MAE={mae:.2f}  RMSE={rmse:.2f}  R²={r2:.4f}")

    # Log the pipeline as MLflow artifact
    mlflow.sklearn.log_model(pipeline, name="model")

    # Also save to local models/ folder with config-named filename
    MODELS_DIR = PROJECT_ROOT / "models"
    MODELS_DIR.mkdir(exist_ok=True)
    artifact_path = MODELS_DIR / f"{config['experiment_name']}_pipeline.joblib"
    joblib.dump(pipeline, artifact_path)
    print(f"saved to {artifact_path}")