
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "yellow" / "2024" / "yellow_tripdata_2024-01.parquet"
MODEL_PATH = PROJECT_ROOT / "models" / "baseline_pipeline.joblib"


import polars as pl
from src.cleaning import clean_dataframe
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from sklearn.metrics import root_mean_squared_error
from sklearn.metrics import mean_absolute_error
import joblib


df_raw = pl.read_parquet(DATA_PATH)
df_clean = clean_dataframe(df_raw)
print(df_clean.shape)

feature_cols = ["VendorID", "passenger_count", "RatecodeID", "PULocationID", "pickup_hour", "pickup_dow"]
X = df_clean.select(feature_cols)
y = df_clean["trip_duration"]

print(X.describe())
print(y.shape)

X_pd = X.to_pandas()
y_pd = y.to_pandas()

X_train, X_test, y_train, y_test = train_test_split(X_pd, y_pd, test_size=0.2, random_state=42)

print(X_train.shape, X_test.shape, y_train.shape, y_test.shape)

categorical_cols = ["VendorID", "RatecodeID", "PULocationID"]
numeric_cols = ["passenger_count", "pickup_hour", "pickup_dow"]

preprocessor = ColumnTransformer(
    transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
        ("num", "passthrough", numeric_cols),
    ]
)


pipeline = Pipeline(steps=[
    ("preprocess", preprocessor),
    ("model", LinearRegression())
])

pipeline.fit(X_train, y_train)
print('done')


y_pred = pipeline.predict(X_test)
rmse = root_mean_squared_error(y_test, y_pred)
mae = mean_absolute_error(y_test, y_pred)
r2 = r2_score(y_test, y_pred)

print(rmse)
print(mae)
print(r2)

joblib.dump(pipeline, MODEL_PATH)
print("model saved")
loaded = joblib.load(MODEL_PATH)
print(loaded.named_steps["model"].coef_.shape)