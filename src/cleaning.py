
# Mission: Predict trip_duration in seconds for NYC yellow taxi trips
# using only features known at pickup time.


import polars as pl
from datetime import datetime


def clean_dataframe(df):

    df = df.with_columns(
        (pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime"))
        .dt.total_seconds()
        .alias("trip_duration")
    )

    df = df.filter(
        (pl.col("tpep_pickup_datetime") >= datetime(2024, 1, 1))
        & (pl.col("tpep_pickup_datetime") < datetime(2024, 2, 1))
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

