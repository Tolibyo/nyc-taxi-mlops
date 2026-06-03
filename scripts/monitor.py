

import polars as pl
from pathlib import Path
from evidently import Report
from evidently.presets import DataDriftPreset
from src.cleaning import clean_dataframe

PROJECT_ROOT = Path(__file__).parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "yellow" / "2024" / "yellow_tripdata_2024-01.parquet"
REPORT_PATH = PROJECT_ROOT / "reports" / "drift_report.html"


df_raw = pl.read_parquet(DATA_PATH)
df_reference = clean_dataframe(df_raw, year=2024, months=["01"])
print(df_reference.shape)


df_current = df_reference.with_columns(
    ((pl.col("pickup_hour") + 10) % 24). alias("pickup_hour")
)

print(df_reference.shape, df_current.shape)
print(df_reference["pickup_hour"].value_counts().sort("pickup_hour").head(5))
print(df_current["pickup_hour"].value_counts().sort("pickup_hour").head(5))

df_reference_pd = df_reference.to_pandas()
df_current_pd = df_current.to_pandas()

report = Report(metrics=[DataDriftPreset()])
snapshot = report.run(reference_data=df_reference_pd, current_data=df_current_pd)

monitor_cols = ["VendorID", "passenger_count", "RatecodeID", "PULocationID", "pickup_hour", "pickup_dow", "trip_duration"]
df_reference_pd = df_reference.select(monitor_cols).to_pandas()
df_current_pd = df_current.select(monitor_cols).to_pandas()

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
snapshot.save_html(str(REPORT_PATH))
print(f"report saved to {REPORT_PATH}")