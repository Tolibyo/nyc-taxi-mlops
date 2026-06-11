
from pathlib import Path
import joblib
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import pandas as pd
import os
import boto3
from dotenv import load_dotenv; load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent

S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL")
MODEL_BUCKET = os.environ.get("MODEL_BUCKET", "nyc-taxi-models")
MODEL_KEY = os.environ.get("MODEL_KEY", "histgb_full_year_pipeline.joblib")

s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT)
s3.download_file(MODEL_BUCKET, MODEL_KEY, "/tmp/model.joblib")
pipeline = joblib.load("/tmp/model.joblib")


class TripRequest(BaseModel):
    pickup_datetime: datetime
    passenger_count: int
    vendor_id: int
    ratecode_id: int
    pickup_location_id: int



def request_to_features(request: TripRequest) -> pd.DataFrame:
    return pd.DataFrame([{    
    "VendorID": request.vendor_id,
    "passenger_count": request.passenger_count,
    "RatecodeID": request.ratecode_id,
    "PULocationID": request.pickup_location_id,
    "pickup_hour": request.pickup_datetime.hour,
    "pickup_dow": request.pickup_datetime.isoweekday()
    }])


app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/predict")
def predict(request: TripRequest):
    features = request_to_features(request)
    prediction = pipeline.predict(features)[0]
    return {"predicted_duration_sec": float(prediction)}