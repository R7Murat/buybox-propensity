"""
Leakage-safe rebuild of the modeling matrix from raw Keepa data.

Ports the FE notebook (Top_Sellers_Keepa_Home_Kitchen_FE_v5) feature
definitions FAITHFULLY but stops BEFORE the leaky steps:
  - global StandardScaler / RobustScaler  -> moved into train-fit pipeline
  - global frequency encoding (Brand/Sub)  -> moved into train-fit pipeline
  - global target-mean win_rate columns    -> dropped (baseline) / OOF later

Output: UNSCALED feature frame + raw categoricals kept for in-pipeline
encoding, deduplicated to ASIN level exactly as FE did (54,855 rows).

Determinism: pure deterministic transforms; dedup rule + RANDOM_SEED=42
fixed so the rebuild is bit-for-bit reproducible.
"""
import numpy as np
import pandas as pd

RANDOM_SEED = 42
RAW_PATH = "con_KeepaExport_merged_raw.parquet"

# Final feature groups (match feature_list.json minus the 2 leak columns)
NUMERIC_SCALE = [  # continuous -> scaled in pipeline (trees ignore scaling)
    "Reviews: Rating", "Buy Box: Stock",
    "Buy Box out of stock percentage: 90 days OOS %",
    "Package: Dimension (cm³)", "Package: Weight (g)",
    "offer_count_trend", "variation_count", "fba_competitor_count",
    "price_volatility", "review_velocity", "new_price_margin_est",
    "new_price_log", "review_count_log", "sr_log", "sr_drops_90",
    "review_x_fba",
]
PASSTHROUGH = [  # binary / ordinal int -> no scaling
    "has_sales_data", "is_negative_margin", "product_age_segment",
    "fba_flag", "is_active_seller",
]
FREQ_COLS = ["Categories: Sub", "Brand"]          # -> *_enc on train
KEEP_CAT = ["listing_seller", "Categories: Root"]  # for leaked ref / OOF only
TARGET = "is_amazon_bb"


def rebuild(raw_path: str = RAW_PATH) -> pd.DataFrame:
    df = pd.read_parquet(raw_path)

    # ---- Imputations (ported from FE; median fills, near-leak-free) ----
    df["New: Current"] = df["New: Current"].fillna(df["New: Current"].median())
    df["Reviews: Review Count"] = df["Reviews: Review Count"].fillna(0)
    df["New Offer Count: 30 days avg."] = df["New Offer Count: 30 days avg."].fillna(0)
    df["New Offer Count: Current"] = df["New Offer Count: Current"].fillna(0)
    df["Reviews: Rating"] = df["Reviews: Rating"].fillna(df["Reviews: Rating"].median())
    df["Referral Fee %"] = df["Referral Fee %"].fillna(df["Referral Fee %"].median())
    df["Buy Box: Stock"] = df["Buy Box: Stock"].fillna(df["Buy Box: Stock"].median())
    df["Buy Box out of stock percentage: 90 days OOS %"] = (
        df["Buy Box out of stock percentage: 90 days OOS %"].fillna(0)
    )

    # category-median then global-median fills
    for col in ["Sales Rank: Current", "FBA Fees:",
                "Package: Weight (g)", "Package: Dimension (cm³)"]:
        cat_med = df.groupby("Categories: Root")[col].median()
        glb_med = df[col].median()
        m = df[col].isna()
        df.loc[m, col] = df.loc[m, "Categories: Root"].map(cat_med).fillna(glb_med)

    # ---- Feature derivations (ported from FE) ----
    df["offer_count_trend"] = df["New Offer Count: Current"] - df["New Offer Count: 30 days avg."]

    df["variation_count"] = df["Variation ASINs"].str.count(",") + 1
    df["variation_count"] = df["variation_count"].fillna(0)

    bins, labels = [-1, 90, 365, 730, np.inf], [0, 1, 2, 3]
    df["product_age_segment"] = (
        pd.cut(df["product_age_days"], bins=bins, labels=labels)
        .astype(float).fillna(0).astype(int)
    )

    df["fba_flag"] = (df["Buy Box: Is FBA"] == "yes").astype(int)
    df["sr_drops_90"] = df["Sales Rank: Drops last 90 days"].clip(0, None)
    df["is_active_seller"] = (df["sr_drops_90"] >= 50).astype(int)

    df["price_volatility"] = (
        (df["Buy Box: Highest"] - df["Buy Box: Lowest"])
        / df["Buy Box: Lowest"].replace(0, np.nan)
    )
    df["price_volatility"] = df["price_volatility"].fillna(df["price_volatility"].median())

    df["review_velocity"] = np.where(
        df["product_age_days"] > 0,
        df["Reviews: Review Count"] / df["product_age_days"], 0,
    )

    df["new_price_margin_est"] = (
        df["New: Current"] - df["FBA Fees:"].fillna(0)
        - df["Referral Fee %"].fillna(0.15) * df["New: Current"]
    )

    df["new_price_log"] = np.log1p(df["New: Current"])
    df["review_count_log"] = np.log1p(df["Reviews: Review Count"])
    df["sr_log"] = np.log1p(df["Sales Rank: Current"])

    # fba_competitor_count: # FBA sellers per ASIN (computed on full df)
    fba_count = (
        df[df["fba_flag"] == 1].groupby("ASIN")["fba_flag"].sum()
        .rename("fba_competitor_count")
    )
    df = df.merge(fba_count, on="ASIN", how="left")
    df["fba_competitor_count"] = df["fba_competitor_count"].fillna(0)

    # interaction on UNSCALED review_count_log (FE did it post-scaling; this is
    # cleaner — scaler now lives in the train-fit pipeline)
    df["review_x_fba"] = df["review_count_log"] * df["fba_flag"]

    # ---- Dedup to ASIN level (FE rule, exact) ----
    df = (df.sort_values(TARGET, ascending=False)
            .drop_duplicates(subset="ASIN", keep="first")
            .reset_index(drop=True))

    cols = NUMERIC_SCALE + PASSTHROUGH + FREQ_COLS + KEEP_CAT + [TARGET]
    out = df[cols].copy()
    return out


if __name__ == "__main__":
    out = rebuild()
    print("rebuilt shape:", out.shape, "| positive rate: %.4f" % out[TARGET].mean())
    print("nulls in features:", int(out[NUMERIC_SCALE + PASSTHROUGH].isna().sum().sum()))
