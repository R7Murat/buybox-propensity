"""FastAPI entrypoint — Buy Box Propensity API (thin e2e skeleton)."""
from fastapi import FastAPI
from app.schema import ProductFeatures, PredictResponse
from app.service import predict

app = FastAPI(title="Buy Box Propensity API", version="0.1.0",
              description="Cross-sectional propensity (anlik) — zamansal tahmin degil.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
def predict_endpoint(payload: ProductFeatures):
    return predict(payload.model_dump(by_alias=True))
