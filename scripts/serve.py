
from pathlib import Path
import joblib
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "histgb_full_year_pipeline.joblib"
pipeline = joblib.load(MODEL_PATH)


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