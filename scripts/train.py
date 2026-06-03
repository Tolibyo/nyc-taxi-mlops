import argparse
import yaml
from pathlib import Path

import polars as pl
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

# anchored paths so script runs from anywhere
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "yellow" / "2024"
MODEL_PATH = PROJECT_ROOT / "models"

# read which config to run from the command line
parser = argparse.ArgumentParser()
parser.add_argument("--config", required=True, type=str)
args = parser.parse_args()

# load the experiment config from yaml
with open(args.config) as f:
    config = yaml.safe_load(f)

print(f"Running experiment: {config['experiment_name']}")

months = config["data"]["months"] 

# load raw data and apply shared cleaning rules
paths = [DATA_PATH / f"yellow_tripdata_2024-{m}.parquet" for m in months]
lazy_frames = [
    pl.scan_parquet(p).with_columns(
        pl.col("tpep_pickup_datetime").cast(pl.Datetime("us")),
        pl.col("tpep_dropoff_datetime").cast(pl.Datetime("us")),
    ) 
    for p in paths
]
df_lazy = pl.concat(lazy_frames)
df_clean = clean_dataframe(df_lazy, year=2024, months=months).collect()
print(df_clean.shape)

# optionally cut data size for faster runs
subsample_n = config["data"]["subsample_rows"]
if subsample_n is not None:
    df_clean = df_clean.sample(n=subsample_n, seed=42)

# pick the base features and the target
feature_cols = ["VendorID", "passenger_count", "RatecodeID", "PULocationID", "pickup_hour", "pickup_dow"]
X = df_clean.select(feature_cols)
y = df_clean["trip_duration"]

# replace hour/dow with sin/cos when config asks for it
if config["features"]["cyclical_time"]:
    X = X.with_columns(
        (2 * np.pi * pl.col("pickup_hour") / 24).sin().alias("pickup_hour_sin"),
        (2 * np.pi * pl.col("pickup_hour") / 24).cos().alias("pickup_hour_cos"),
        (2 * np.pi * pl.col("pickup_dow") / 7).sin().alias("pickup_dow_sin"),
        (2 * np.pi * pl.col("pickup_dow") / 7).cos().alias("pickup_dow_cos"),
    ).drop(["pickup_hour", "pickup_dow"])

# weekend flag from day of week (sat=6, sun=7)
if config["features"]["add_is_weekend"]:
    X = X.with_columns(
        (pl.col("pickup_dow") >= 6).cast(pl.Int8).alias("is_weekend")
    )

# rush hour flag from pickup hour
if config["features"]["add_is_rush_hour"]:
    X = X.with_columns(
        (pl.col("pickup_hour").is_in([7,8,9,16,17,18,19])).cast(pl.Int8).alias("is_rush_hour")
    )

# join zone lookup to get district from pickup zone
if config["features"]["add_district"]:
    lookup = pl.read_csv(PROJECT_ROOT / "data" / "reference" / "taxi_zones" / "taxi_zone_lookup.csv")
    lookup = lookup.select(["LocationID", "Borough"])
    X = X.join(lookup, left_on="PULocationID", right_on="LocationID", how="left")
    X = X.rename({"Borough": "pickup_district"})

print(f"Feature columns: {X.columns}")

# split columns into categorical vs numeric after all features exist
categorical_cols = ["VendorID", "RatecodeID", "PULocationID"]
if config["features"]["add_district"]:
    categorical_cols.append("pickup_district")
numeric_cols = [c for c in X.columns if c not in categorical_cols]

print(f"Categorical: {categorical_cols}")
print(f"Numeric: {numeric_cols}")

strategy = config["features"]["categorical_strategy"]

if config["features"]["bucket_rare_zones"]:
    top_n = config["features"]["top_n_zones"]
    # find the top N zones by frequency
    top_zones = (
        X.group_by("PULocationID")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .head(top_n)
        .get_column("PULocationID")
        .to_list()
    )
    # replace zones not in top_n with -1
    X = X.with_columns(
        pl.when(pl.col("PULocationID").is_in(top_zones))
        .then(pl.col("PULocationID"))
        .otherwise(-1)
        .alias("PULocationID")
    )

# convert to pandas and split into train/test
X_pd = X.to_pandas()
y_pd = y.to_pandas()
X_train, X_test, y_train, y_test = train_test_split(X_pd, y_pd, test_size=0.2, random_state=42)

# build the model based on config
model_type = config["model"]["type"]
model_params = config["model"].get("params", {}) or {}
strategy = config["features"]["categorical_strategy"]

if model_type == "LinearRegression":
    model = LinearRegression(**model_params)
elif model_type == "HistGradientBoostingRegressor":
    if strategy == "native":
        model = HistGradientBoostingRegressor(
            **model_params,
            random_state=42,
            categorical_features="from_dtype",
        )
    else:
        model = HistGradientBoostingRegressor(**model_params, random_state=42)
else:
    raise ValueError(f"Unknown model type: {model_type}")

# linear models cannot consume raw categorical columns
if strategy == "native" and model_type == "LinearRegression":
    raise ValueError("native categorical only works with tree models")

# onehot path uses a column transformer, native path feeds the model directly
if strategy == "onehot":
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical_cols),
            ("num", "passthrough", numeric_cols),
        ]
    )
    pipeline = Pipeline([("preprocess", preprocessor), ("model", model)])

elif strategy == "native":
    # cast categoricals so histgb detects them via from_dtype
    for col in categorical_cols:
        X_train[col] = X_train[col].astype("category")
        X_test[col] = X_test[col].astype("category")
    pipeline = Pipeline([("model", model)])

# group this run under its experiment name in mlflow
mlflow.set_experiment(config["experiment_name"])

with mlflow.start_run():
    # log config so the run is reproducible later
    mlflow.log_param("model_type", model_type)
    mlflow.log_param("cyclical_time", config["features"]["cyclical_time"])
    mlflow.log_param("categorical_strategy", config["features"]["categorical_strategy"])
    mlflow.log_param("subsample_rows", config["data"]["subsample_rows"])
    mlflow.log_param("n_train_rows", len(X_train))
    mlflow.log_param("n_features", X_train.shape[1])
    mlflow.log_param("data_source", f"yellow_2024_{months[0]}-{months[-1]}")
    for k, v in model_params.items():
        mlflow.log_param(f"hp_{k}", v)

    # train on the training split
    pipeline.fit(X_train, y_train)
    print("training complete")

    # predict on test split and compute the three metrics
    y_pred = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = root_mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    # log metrics to mlflow
    mlflow.log_metric("mae", mae)
    mlflow.log_metric("rmse", rmse)
    mlflow.log_metric("r2", r2)

    print(f"MAE={mae:.2f}  RMSE={rmse:.2f}  R²={r2:.4f}")

    # store the trained pipeline as an mlflow artifact
    mlflow.sklearn.log_model(pipeline, name="model")

    # also save locally with a config named file for serve.py to load
    MODELS_DIR = PROJECT_ROOT / "models"
    MODELS_DIR.mkdir(exist_ok=True)
    artifact_path = MODELS_DIR / f"{config['experiment_name']}_pipeline.joblib"
    joblib.dump(pipeline, artifact_path)
    print(f"saved to {artifact_path}")