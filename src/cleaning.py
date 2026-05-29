
# Mission: Predict trip_duration in seconds for NYC yellow taxi trips
# using only features known at pickup time.


import polars as pl
from datetime import datetime


def clean_dataframe(df, year: int, months: list[str]):

    min_month = min(int(m) for m in months)
    max_month = max(int(m) for m in months)
    
    start = datetime(year, min_month, 1)

    if max_month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, max_month + 1, 1)

    df = df.with_columns(
        (pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime"))
        .dt.total_seconds()
        .alias("trip_duration")
    )

    df = df.filter(
        (pl.col("tpep_pickup_datetime") >= start)
        & (pl.col("tpep_pickup_datetime") < end)
        & (pl.col("trip_duration") >= 30)
        & (pl.col("trip_duration") <= 14400)
    )

    df = df.drop_nulls(subset=["passenger_count", "RatecodeID"])
    df = df.with_columns(
        pl.col("tpep_pickup_datetime").dt.hour().alias("pickup_hour"),
        pl.col("tpep_pickup_datetime").dt.weekday().alias("pickup_dow")
    )

    df = df.filter(
    (pl.col("RatecodeID") != 99)
    & (pl.col("RatecodeID") != 6)
    )

    df = df.filter(
    (pl.col("passenger_count") >= 1)
    & (pl.col("passenger_count") <= 6)
    )

    return df

