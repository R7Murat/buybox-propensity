"""
keepa_transform.py
==================
Leak-safe inference feature engineering: ham Keepa satir(lar)i -> modelin
18-alan sozlesmesi (predict() bunu bekler).

Tasarim ilkesi: train/serve skew YOK.
  - Tum imputasyonlar fe_constants.json'daki DONMUS egitim medyanlarindan gelir.
  - Satir-bazli calisir; batch istatistigi (yuklenen dosyanin medyani) KULLANILMAZ.
  - EDA (eda_v7) + rebuild.py turetmeleri BIREBIR portlanmistir.

Kaynak tanimlar:
  has_sales_data        = 'Bought in past month'.notna()            (EDA)
  is_negative_margin    = (gross_margin_est < 0); gross = Buy Box: Current
                          - FBA Fees:(0) - Referral Fee based on BB price(0)  (EDA)
  new_price_margin_est  = New: Current - FBA Fees: - Referral Fee % * New: Current  (rebuild)
  product_age_*         = (as_of - Tracking since).days, clip>=0       (EDA)
  listing_seller        = kullanici girisi; bos -> bilinmeyen -> global-mean fallback
"""
import os
import json
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONST_PATH = os.getenv(
    "FE_CONSTANTS", os.path.join(_HERE, "models", "fe_constants.json"))

with open(_CONST_PATH, encoding="utf-8") as _f:
    _C = json.load(_f)

GLB = _C["global_median"]
CATM = _C["cat_median"]
REF_FALLBACK = _C.get("referral_fee_pct_fallback", 0.15)
SNAPSHOT_TRAIN = _C.get("snapshot_date_train", "2023-10-17")
CAT_KEY = "Categories: Root"

UNKNOWN_SELLER = "__unknown__"

# inference icin gereken ham Keepa kolonlari (zorunlu sozlesme)
REQUIRED_RAW = [
    "Tracking since", "Variation ASINs",
    "New Offer Count: Current", "New Offer Count: 30 days avg.",
    "Package: Weight (g)", "Package: Dimension (cm³)",
    "Reviews: Rating", "Reviews: Review Count",
    "New: Current", "Sales Rank: Current", "Sales Rank: Drops last 90 days",
    "Bought in past month", "Buy Box: Current",
    "FBA Fees:", "Referral Fee %",
    "Referral Fee based on current Buy Box price",
    "Categories: Sub", "Brand", "Categories: Root",
]

# predict()'in bekledigi 18 sozlesme alani (alias formu)
CONTRACT = [
    "variation_count", "offer_count_trend", "Package: Weight (g)",
    "Reviews: Rating", "new_price_log", "review_count_log", "sr_log",
    "review_velocity", "new_price_margin_est", "sr_drops_90",
    "Package: Dimension (cm³)", "Categories: Sub", "Brand",
    "has_sales_data", "is_negative_margin", "product_age_segment",
    "is_active_seller", "listing_seller",
]


def validate_columns(df: pd.DataFrame):
    """Eksik zorunlu kolonlari dondurur (bos liste = sozlesme tam)."""
    return [c for c in REQUIRED_RAW if c not in df.columns]


def _cat_fill(df: pd.DataFrame, col: str) -> pd.Series:
    """cat-median (Categories: Root) sonra global-median ile doldur (rebuild.py birebir)."""
    glb = GLB[col]
    cmap = CATM.get(col, {})
    fill = df[CAT_KEY].astype(str).map(cmap).fillna(glb)
    return df[col].fillna(fill)


def transform(df: pd.DataFrame, as_of=None, listing_seller=None) -> pd.DataFrame:
    """
    df            : ham Keepa satirlari (DataFrame)
    as_of         : 'YYYY-MM-DD' (None -> egitim snapshot 2023-10-17)
    listing_seller: tek string (tum satirlara) veya None (-> bilinmeyen)
    Donus         : 18 sozlesme kolonlu DataFrame
    """
    df = df.copy()
    as_of_ts = pd.Timestamp(as_of) if as_of else pd.Timestamp(SNAPSHOT_TRAIN)
    out = pd.DataFrame(index=df.index)

    # --- impute edilen surekli alanlar (donmus medyanlar) ---
    rating = df["Reviews: Rating"].fillna(GLB["Reviews: Rating"])
    new_cur = df["New: Current"].fillna(GLB["New: Current"])
    sr_cur = _cat_fill(df, "Sales Rank: Current")
    fba_fee = _cat_fill(df, "FBA Fees:")
    pkg_w = _cat_fill(df, "Package: Weight (g)")
    pkg_d = _cat_fill(df, "Package: Dimension (cm³)")
    ref_pct = df["Referral Fee %"].fillna(GLB["Referral Fee %"]).fillna(REF_FALLBACK)

    review_cnt = df["Reviews: Review Count"].fillna(0)
    age_days = (as_of_ts - pd.to_datetime(df["Tracking since"], errors="coerce")
                ).dt.days.clip(lower=0)

    # --- turetmeler ---
    var = df["Variation ASINs"].astype("string").str.count(",") + 1
    out["variation_count"] = var.fillna(0).astype(float)

    out["offer_count_trend"] = (df["New Offer Count: Current"].fillna(0)
                                - df["New Offer Count: 30 days avg."].fillna(0))
    out["Package: Weight (g)"] = pkg_w
    out["Reviews: Rating"] = rating
    out["new_price_log"] = np.log1p(new_cur)
    out["review_count_log"] = np.log1p(review_cnt)
    out["sr_log"] = np.log1p(sr_cur)
    out["review_velocity"] = np.where(age_days > 0, review_cnt / age_days, 0.0)
    out["new_price_margin_est"] = new_cur - fba_fee - ref_pct * new_cur
    out["sr_drops_90"] = df["Sales Rank: Drops last 90 days"].clip(lower=0).fillna(0)
    out["Package: Dimension (cm³)"] = pkg_d
    out["Categories: Sub"] = df["Categories: Sub"].astype(str)
    out["Brand"] = df["Brand"].astype(str)
    out["has_sales_data"] = df["Bought in past month"].notna().astype(int)

    gross = (df["Buy Box: Current"]
             - df["FBA Fees:"].fillna(0)
             - df["Referral Fee based on current Buy Box price"].fillna(0))
    out["is_negative_margin"] = (gross < 0).fillna(False).astype(int)

    seg = pd.cut(age_days, bins=[-1, 90, 365, 730, np.inf], labels=[0, 1, 2, 3])
    out["product_age_segment"] = seg.astype("float").fillna(0).astype(int)
    out["is_active_seller"] = (out["sr_drops_90"] >= 50).astype(int)

    # listing_seller: acik parametre > df'deki kolon > bilinmeyen (-> global-mean fallback)
    if listing_seller is not None:
        out["listing_seller"] = listing_seller
    elif "listing_seller" in df.columns:
        out["listing_seller"] = df["listing_seller"].astype(str)
    else:
        out["listing_seller"] = UNKNOWN_SELLER

    return out[CONTRACT]


def transform_record(record: dict, as_of=None, listing_seller=None) -> dict:
    """Tek ham satir (dict) -> tek sozlesme dict'i (predict() icin)."""
    ls = listing_seller or record.get("listing_seller")
    return transform(pd.DataFrame([record]), as_of=as_of,
                     listing_seller=ls).iloc[0].to_dict()
