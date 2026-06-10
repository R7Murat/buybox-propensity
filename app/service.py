"""Model service: loads the trained pipeline once, returns propensity, an
operating-point decision, and associational top-SHAP reasons. Unknown sellers
fall back to the global-mean target encoding automatically (TargetEncoder prior)."""
import os, json
import numpy as np, pandas as pd, joblib, shap

ROOT = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(ROOT, "final_model.pkl"))
META_PATH = os.getenv("META_PATH", os.path.join(ROOT, "model_metadata.json"))

# pipeline output feature order (robust, standard, freq, pass, sellerrate)
FEAT = ["variation_count", "offer_count_trend", "Package: Weight (g)",
        "Reviews: Rating", "new_price_log", "review_count_log", "sr_log",
        "review_velocity", "new_price_margin_est", "sr_drops_90",
        "Package: Dimension (cm³)", "Categories: Sub__freq", "Brand__freq",
        "has_sales_data", "is_negative_margin", "product_age_segment",
        "is_active_seller", "listing_seller__sellerrate"]

import sys
from sklearn.base import BaseEstimator, TransformerMixin


class FrequencyEncoder(BaseEstimator, TransformerMixin):
    """Must match the class the pipeline was pickled with."""
    def __init__(self, min_count=50):
        self.min_count = min_count

    def fit(self, X, y=None):
        X = pd.DataFrame(X); self.maps_, self.rare_ = {}, {}
        for c in X.columns:
            f = X[c].value_counts(); rare = set(f[f < self.min_count].index)
            coll = X[c].where(~X[c].isin(rare), "other")
            self.maps_[c] = coll.value_counts(normalize=True).to_dict(); self.rare_[c] = rare
        return self

    def transform(self, X):
        X = pd.DataFrame(X); out = np.zeros((len(X), X.shape[1]))
        for j, c in enumerate(X.columns):
            coll = X[c].where(~X[c].isin(self.rare_[c]), "other")
            out[:, j] = coll.map(self.maps_[c]).fillna(0).values
        return out


# pipeline pickle'i __main__.FrequencyEncoder olarak kaydetti -> cozumlenebilir yap
sys.modules["__main__"].FrequencyEncoder = FrequencyEncoder

_pipe = joblib.load(MODEL_PATH)
_meta = json.load(open(META_PATH, encoding="utf-8"))
_PRE = _pipe.named_steps["pre"]
_CLF = _pipe.named_steps["clf"]
_THR = float(_meta["operating_points"]["OP1_recall_priority(A)"]["threshold"])
_explainer = shap.TreeExplainer(_CLF)
try:
    _known_sellers = set(_PRE.named_transformers_["sellerrate"].categories_[0])
except Exception:
    _known_sellers = set()


def predict(record: dict) -> dict:
    """record: dict keyed by exact pipeline column names (alias form)."""
    df = pd.DataFrame([record])
    Z = _PRE.transform(df)
    proba = float(_CLF.predict_proba(Z)[0, 1])

    sv = _explainer.shap_values(Z)
    sv = sv[1] if isinstance(sv, list) else sv
    sv = np.asarray(sv).reshape(-1)
    order = np.argsort(-np.abs(sv))[:5]
    reasons = [{"feature": FEAT[i], "shap": round(float(sv[i]), 4),
                "direction": "artirir" if sv[i] > 0 else "azaltir"} for i in order]

    band = "yuksek" if proba >= _THR else ("orta" if proba >= _THR * 0.6 else "dusuk")
    return {
        "propensity": round(proba, 4),
        "risk_band": band,
        "decision_recall_priority": bool(proba >= _THR),
        "threshold_used": round(_THR, 4),
        "seller_known": record.get("listing_seller") in _known_sellers,
        "top_reasons": reasons,
    }
