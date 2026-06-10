"""
monitoring/evidently_drift.py
Input + prediction drift detection using Evidently.

Usage:
    python monitoring/evidently_drift.py \
        --reference monitoring/reference_sample.parquet \
        --current   monitoring/current_batch.parquet \
        --output    monitoring/drift_report.html

Design decisions:
- Labels are delayed → NO live accuracy monitoring; only input + prediction drift.
- When drift exceeds threshold → alert → retrain trigger (manual or automated).
- Reference sample is a small, processed (not raw) feature subset from training data.
  It does NOT contain raw Keepa data (commercial/licensed).

Workflow:
1. Periodically collect inference requests + predictions into current_batch.parquet.
2. Run this script to compare current vs reference distribution.
3. If drift detected → flag for investigation / retrain.
"""

import argparse
from pathlib import Path

import pandas as pd

try:
    from evidently import ColumnMapping
    from evidently.report import Report
    from evidently.metric_preset import DataDriftPreset
except ImportError:
    raise SystemExit(
        "Evidently not installed. Run: pip install evidently\n"
        "It is intentionally not in requirements.txt (serving vs monitoring deps are separate)."
    )

# The 18 features the model actually uses (leak-clean contract).
MODEL_FEATURES = [
    "Reviews: Rating",
    "Package: Dimension (cm³)",
    "Package: Weight (g)",
    "offer_count_trend",
    "variation_count",
    "review_velocity",
    "new_price_margin_est",
    "new_price_log",
    "review_count_log",
    "sr_log",
    "sr_drops_90",
    "has_sales_data",
    "is_negative_margin",
    "product_age_segment",
    "is_active_seller",
    "Categories: Sub",
    "Brand",
    "seller_rate",
]

PREDICTION_COL = "propensity"


def build_report(
    reference: pd.DataFrame,
    current: pd.DataFrame,
) -> Report:
    """Build an Evidently data-drift report over model features + prediction."""
    column_mapping = ColumnMapping(
        prediction=PREDICTION_COL,
        numerical_features=[f for f in MODEL_FEATURES if reference[f].dtype != "object"],
        categorical_features=[f for f in MODEL_FEATURES if reference[f].dtype == "object"],
    )

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference, current_data=current, column_mapping=column_mapping)
    return report


def main():
    parser = argparse.ArgumentParser(description="Evidently input + prediction drift check")
    parser.add_argument("--reference", required=True, help="Path to reference parquet")
    parser.add_argument("--current", required=True, help="Path to current-batch parquet")
    parser.add_argument("--output", default="monitoring/drift_report.html", help="HTML report path")
    args = parser.parse_args()

    ref = pd.read_parquet(args.reference)
    cur = pd.read_parquet(args.current)

    # Validate columns
    required = set(MODEL_FEATURES + [PREDICTION_COL])
    for label, df in [("reference", ref), ("current", cur)]:
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"{label} is missing columns: {missing}")

    report = build_report(ref, cur)
    report.save_html(args.output)
    print(f"Drift report saved to {args.output}")

    # Simple threshold check — drift detected?
    report_dict = report.as_dict()
    drift_detected = report_dict["metrics"][0]["result"]["dataset_drift"]
    if drift_detected:
        print("⚠️  DRIFT DETECTED — consider retraining.")
    else:
        print("✅ No significant drift detected.")

    return drift_detected


if __name__ == "__main__":
    main()
