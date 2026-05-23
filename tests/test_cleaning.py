import polars as pl
from src.cleaning import clean_dataframe

df_raw = pl.read_parquet("data/raw/yellow/2024/yellow_tripdata_2024-01.parquet")
df_clean = clean_dataframe(df_raw)
print(df_clean.shape)