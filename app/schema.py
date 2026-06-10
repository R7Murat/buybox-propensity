"""Pydantic schemas. Input fields map (via alias) to the exact column names the
trained pipeline expects. These are the model's feature contract; an upstream
step (rebuild.py logic) would derive them from raw Keepa fields."""
from typing import List
from pydantic import BaseModel, Field


class ProductFeatures(BaseModel):
    model_config = {"populate_by_name": True, "extra": "ignore"}

    # robust-scaled
    variation_count: float = Field(..., alias="variation_count")
    offer_count_trend: float = Field(..., alias="offer_count_trend")
    package_weight_g: float = Field(..., alias="Package: Weight (g)")
    # standard-scaled
    reviews_rating: float = Field(..., alias="Reviews: Rating")
    new_price_log: float = Field(..., alias="new_price_log")
    review_count_log: float = Field(..., alias="review_count_log")
    sr_log: float = Field(..., alias="sr_log")
    review_velocity: float = Field(..., alias="review_velocity")
    new_price_margin_est: float = Field(..., alias="new_price_margin_est")
    sr_drops_90: float = Field(..., alias="sr_drops_90")
    package_dimension_cm3: float = Field(..., alias="Package: Dimension (cm³)")
    # passthrough binary/ordinal
    has_sales_data: int = Field(..., alias="has_sales_data")
    is_negative_margin: int = Field(..., alias="is_negative_margin")
    product_age_segment: int = Field(..., alias="product_age_segment")
    is_active_seller: int = Field(..., alias="is_active_seller")
    # categorical
    categories_sub: str = Field(..., alias="Categories: Sub")
    brand: str = Field(..., alias="Brand")
    listing_seller: str = Field(..., alias="listing_seller")


class Reason(BaseModel):
    feature: str
    shap: float
    direction: str  # "artirir" | "azaltir"


class PredictResponse(BaseModel):
    propensity: float
    risk_band: str               # dusuk | orta | yuksek
    decision_recall_priority: bool
    threshold_used: float
    seller_known: bool           # False -> seller_rate global-mean fallback
    top_reasons: List[Reason]
    framing: str = ("cross-sectional propensity (anlik); zamansal tahmin degil. "
                    "Nedenler iliskiseldir.")
