
# "Predict trip_duration in seconds for NYC yellow taxi trips using only features known at pickup time."

import polars as pl
from datetime import datetime

df = pl.read_parquet("data/raw/yellow/2024/yellow_tripdata_2024-01.parquet")
print(df.shape)
print(df.columns)

print(df.dtypes)

print(df['tpep_pickup_datetime'].sort().head(5))

df = df.with_columns(
    (pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime"))
    .dt.total_seconds()
    .alias("trip_duration")
)


# print(df.describe())

with pl.Config(tbl_cols=-1):
    print(df.describe())
pl.Config.set_tbl_rows(-1)

df_filter = df.filter(
    (pl.col("tpep_pickup_datetime") >= datetime(2024, 1, 1)) 
    & (pl.col("tpep_pickup_datetime") < datetime(2024, 2, 1))
    & (pl.col("trip_duration") >= 30) 
    & (pl.col("trip_duration") <= 14400)
)

print(df.shape)
print(df_filter.shape)
print(df_filter.select("trip_duration").describe())


df_filter_null = df_filter.select([
    "VendorID",
    "tpep_pickup_datetime",
    "passenger_count",
    "RatecodeID",
    "PULocationID",
    "trip_duration",
]).null_count()

print(df_filter_null)


df_filter = df_filter.drop_nulls(subset=["passenger_count", "RatecodeID"])
print(df_filter.shape)


df_filter = df_filter.with_columns(
    pl.col("tpep_pickup_datetime").dt.hour().alias("pickup_hour"),
    pl.col("tpep_pickup_datetime").dt.weekday().alias("pickup_dow")
)

hourly = df_filter.group_by("pickup_hour").agg(
    pl.len().alias("trip_count"),
    pl.col("trip_duration").mean().alias("avg_duration_sec"),
).sort("pickup_hour")

dow = df_filter.group_by("pickup_dow").agg(
    pl.len().alias("trip_count"),
    pl.col("trip_duration").mean().alias("avg_duration_sec"),
).sort("pickup_dow")


print(hourly)
print(dow)


cardinality = df_filter.select([
    pl.col('VendorID').n_unique().alias("vendor_unique"),
    pl.col("RatecodeID").n_unique().alias("ratecode_unique"),
    pl.col("PULocationID").n_unique().alias("pulocation_unique")
])
print(cardinality)

df_filter_vendor = df_filter["VendorID"].value_counts().sort("VendorID")
df_filter_ratecode = df_filter["RatecodeID"].value_counts().sort("RatecodeID")

print(df_filter_vendor)
print(df_filter_ratecode)


df_filter = df_filter.filter(
    (pl.col("RatecodeID") != 99)
    & (pl.col("RatecodeID") != 6)
)

print(df_filter.shape)
print(df_filter["RatecodeID"].value_counts().sort("RatecodeID"))

# Returns size in Bytes (default)
print(df.estimated_size()) 

# Returns size in Kilobytes, Megabytes, or Gigabytes
print(f"Memory: {df.estimated_size('mb'):.2f} MB")
print(f"Memory: {df.estimated_size('gb'):.2f} GB")

print(df_filter.select(["trip_distance", "passenger_count"]).describe())
print(df_filter["passenger_count"].value_counts().sort("passenger_count"))

df_filter = df_filter.filter(
    (pl.col("passenger_count") >= 1)
    & (pl.col("passenger_count") <= 6)
)

print(df_filter["passenger_count"].value_counts().sort("passenger_count"))
print(df_filter.select(["trip_distance", "passenger_count"]).describe())

print(df_filter.columns)
print(df_filter.shape)
