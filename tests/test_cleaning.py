import polars as pl
from datetime import datetime
from src.cleaning import clean_dataframe


def test_trip_duration_created_correctly():

    df = pl.DataFrame({
        "tpep_pickup_datetime": [datetime(2024, 1, 15, 10, 0)],
        "tpep_dropoff_datetime": [datetime(2024, 1, 15, 10, 10)],
        "passenger_count": [1],
        "RatecodeID": [1],
    })

    result = clean_dataframe(df, year=2024, months=["01"])

    assert result.shape[0] == 1
    assert result["trip_duration"][0] == 600

def test_clean_removes_negative_duration():
    
    df = pl.DataFrame({
        "tpep_pickup_datetime": [datetime(2024,1,1,10,0), datetime(2024,1,1,10,0)],
        "tpep_dropoff_datetime": [datetime(2024,1,1,10,10), datetime(2024,1,1,9,50)],
        "passenger_count": [1, 1],
        "RatecodeID": [1, 1],
    })

    result1 = clean_dataframe(df, year=2024, months=["01"])

    assert result1.shape[0] == 1
    

def test_long_duration_filtered():
    
    df = pl.DataFrame({
        "tpep_pickup_datetime": [datetime(2024, 1, 15, 10, 0)],
        "tpep_dropoff_datetime": [datetime(2024, 1, 16, 10, 0)],
        "passenger_count": [1],
        "RatecodeID": [1],
    }) 

    result2 =  clean_dataframe(df, year=2024, months=["01"])

    assert result2.shape[0] == 0

def test_bad_RateCodeID_filtered():

    df = pl.DataFrame({
        "tpep_pickup_datetime": [datetime(2024, 1, 15, 10, 0)] * 3,
        "tpep_dropoff_datetime": [datetime(2024, 1, 15, 10, 10)] * 3,
        "passenger_count": [1, 1, 1],
        "RatecodeID": [1, 99, 6],
    }) 

    result3 = clean_dataframe(df, year=2024, months=["01"])

    assert result3.shape[0] == 1
    assert result3["RatecodeID"][0] == 1


def test_passenger_count_range():

    df = pl.DataFrame({
        "tpep_pickup_datetime": [datetime(2024, 1, 15, 10, 0)] * 3,
        "tpep_dropoff_datetime": [datetime(2024, 1, 15, 10, 10)] * 3,
        "passenger_count": [0, 3, 8],
        "RatecodeID": [1, 1, 1],
    }) 

    result4 = clean_dataframe(df, year=2024, months=["01"])

    assert result4.shape[0] == 1
    assert result4["passenger_count"][0] == 3