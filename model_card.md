# Model Card — Amazon Buy Box Propensity (`is_amazon_bb`)

**Status:** Faz 4 final (regularized, leakage-clean). Deploy-ready candidate.

## What this model is
A **cross-sectional propensity / risk model**: given a product profile, it estimates the
**propensity that Amazon holds the Buy Box** for that product.

## What it is NOT
- **Not a temporal forecast.** Single snapshot (Oct 2023), one row per ASIN; no time dimension.
  It does **not** predict that a seller *will lose* the Buy Box in the future.
- **Not causal.** SHAP / attributions are **associational** ("products with this profile tend
  to be Amazon-dominated"), not causal/temporal.

## Intended use & scope
New/known product profile -> Amazon Buy-Box risk score. Scope: **existing seller base**
(stratified random split; generalizes to new products of observed sellers, not unseen sellers).
Unknown seller at serving -> `seller_rate` falls back to global mean (0.146).

## Final model
- LightGBM, regularized (num_leaves=15, min_child_samples=100, lr=0.05, reg_lambda=5,
  subsample/colsample=0.8), fixed 300 trees. 18 features = 17 product-level + OOF `seller_rate`.
- **Hold-out (untouched 15%) PR-AUC = 0.673, ROC-AUC = 0.924** (base rate 0.146).
- Tuning narrative: explored untuned (0.72 holdout but train-gap 0.19), Optuna+early-stopping
  under a gap guardrail (over-regularized to 0.62), and ES-grown trees (0.71/gap 0.18). **Adopted
  the regularized fixed-tree config** as the gap-controlled, defensible operating point — trading
  ~0.03 PR-AUC for a materially smaller train/CV gap.

## Operating points (assumption A: recall-priority, FN > FP; confirmed on hold-out)
| Point | Threshold | Precision | Recall | F1 |
|---|---|---|---|---|
| OP1 recall-priority | 0.62 | 0.53 | 0.78 | 0.63 |
| OP2 max-F1 | 0.73 | 0.62 | 0.64 | 0.63 |
| top-10% screen | — | 0.69 | 0.47 | — |
Threshold is a business-policy choice along the PR curve; ship as configurable.

## Leakage handling
Removed: `seller_win_rate`/`category_amazon_win_rate` (target-derived); Tier-1 mechanical
(`fba_flag`,`fba_competitor_count`,`review_x_fba`); Tier-2 BB-snapshot
(`Buy Box: Stock`,`price_volatility`,`OOS %`). All scaling/encoding fit train-only in pipeline;
`seller_rate` via cross-fitted TargetEncoder (no in-fold leakage).

## SHAP (associational) — top drivers
`sr_drops_90` (sales velocity), `review_velocity`, `review_count_log`, `variation_count`,
`Package: Weight`. Product signals dominate; `seller_rate` is a small contributor.

## Reproducibility
seed=42; deterministic rebuild from raw (54,855 ASIN-level rows); MLflow (sqlite) logs runs.
Artifacts: `final_model.pkl`, `model_metadata.json`, `seller_rate_map.pkl` (fallback).
