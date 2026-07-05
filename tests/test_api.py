



from fastapi.testclient import TestClient
from scripts.serve import app


import pytest
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingRegressor
from src.transformers import RareZoneBucketer, CategoryCaster


@pytest.fixture
def trained_model():
    rng = np.random.default_rng(42)
    sample_size = 300
    training_features = pd.DataFrame({
        "VendorID": rng.integers(1, 3, sample_size),
        "passenger_count": rng.integers(1, 7, sample_size),
        "RatecodeID": rng.integers(1, 6, sample_size),
        "PULocationID": rng.integers(1, 266, sample_size),
        "pickup_hour": rng.integers(0, 24, sample_size),
        "pickup_dow": rng.integers(1, 8, sample_size),
    })
    training_target = rng.integers(60, 3600, sample_size)
    categorical_columns = ["VendorID", "RatecodeID", "PULocationID"]
    model_pipeline = Pipeline([
        ("bucket", RareZoneBucketer(top_n=20)),
        ("cast", CategoryCaster(categorical_columns)),
        ("model", HistGradientBoostingRegressor(
            random_state=42, categorical_features="from_dtype", max_iter=10)),
    ])
    model_pipeline.fit(training_features, training_target)
    return model_pipeline


client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

@pytest.mark.parametrize("passenger_count", [1, 6])
def test_predict_accepts_passenger_boundaries(passenger_count, trained_model, monkeypatch):
    monkeypatch.setattr("scripts.serve.pipeline", trained_model)
    response = client.post("/predict", json={
        "pickup_datetime": "2024-06-15T17:30:00",
        "passenger_count": passenger_count,
        "vendor_id": 2,
        "ratecode_id": 1,
        "pickup_location_id": 161,
    })
    assert response.status_code == 200
    body = response.json()
    assert "predicted_duration_sec" in body
    assert body["predicted_duration_sec"] > 0

@pytest.mark.parametrize("passenger_count", [0, 7])
def test_predict_rejects_invalid_passenger_count(passenger_count):
    response = client.post("/predict", json={
        "pickup_datetime": "2024-06-15T17:30:00",
        "passenger_count": passenger_count,
        "vendor_id": 2,
        "ratecode_id": 1,
        "pickup_location_id": 161,
    })
    assert response.status_code == 422


def test_rare_zones_predict_identically(trained_model, monkeypatch):
    monkeypatch.setattr("scripts.serve.pipeline", trained_model)
    client = TestClient(app)

    bucketer = trained_model.named_steps["bucket"]
    top_zones = list(bucketer.top_zones_)

    rare_zones = []
    for zone_id in range(1, 266):
        if zone_id not in top_zones:
            rare_zones.append(zone_id)
        if len(rare_zones) == 2:
            break

    first_response = client.post("/predict", json={
        "pickup_datetime": "2024-06-15T17:30:00",
        "passenger_count": 1,
        "vendor_id": 2,
        "ratecode_id": 1,
        "pickup_location_id": rare_zones[0]
    })

    second_response = client.post("/predict", json={
        "pickup_datetime": "2024-06-15T17:30:00",
        "passenger_count": 1,
        "vendor_id": 2,
        "ratecode_id": 1,
        "pickup_location_id": rare_zones[1]
    })

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_prediction = first_response.json()["predicted_duration_sec"]
    second_prediction = second_response.json()["predicted_duration_sec"]
    assert first_prediction == second_prediction