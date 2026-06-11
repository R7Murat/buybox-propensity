# Buy Box Propensity — MLOps

An Amazon **Buy Box propensity** model: given a product profile, it estimates the
propensity that Amazon holds the Buy Box for that product. The project demonstrates the
full **model-to-production** path — a leakage-clean LightGBM plus end-to-end serving
(FastAPI), IaC, CI/CD, and monitoring.

> **Status:** Phase 6 complete — HF Spaces live demo deployed. Full pipeline: EDA → FE → Model → FastAPI → IaC/CI-CD → Monitoring → Gradio UI. Sections marked `TODO`
> are filled in as the pipeline is built.

## 🔗 Live demo
- **HuggingFace Spaces:** [▶️ Live Demo](https://huggingface.co/spaces/R7Murat/buybox-propensity) — Gradio UI (always-on, clickable)

## What this model is / is NOT
- A **cross-sectional propensity / risk** model (single snapshot, Oct 2023; one row per ASIN).
- **Not a temporal forecast** — it does not predict that a seller *will lose* the Buy Box.
- **Not causal** — SHAP attributions are associational ("products with this profile tend to be
  Amazon-dominated"), not causal/temporal.
- **Scope:** existing seller base; unknown sellers fall back to the global-mean `seller_rate` (0.146).

## Results
| Metric | Value |
|---|---|
| Hold-out PR-AUC | **0.673** (no-skill base rate 0.146 → ~4.6×) |
| Hold-out ROC-AUC | **0.924** |
| Model | Regularized LightGBM, 18 features, fixed 300 trees |

**Operating points** (assumption A: recall-priority, FN > FP):

| Point | Threshold | Precision | Recall | F1 |
|---|---|---|---|---|
| OP1 recall-priority | 0.62 | 0.53 | 0.78 | 0.63 |
| OP2 max-F1 | 0.73 | 0.62 | 0.64 | 0.63 |
| top-10% screen | — | 0.69 | 0.47 | — |

### Leakage handling (the honesty note)
The ablation ladder makes the leakage effect explicit: **0.96 (leaky) → 0.711 (CV leak-clean)
→ 0.673 (final, gap-controlled hold-out)**. Removed: target-derived
(`seller_win_rate`, `category_amazon_win_rate`); Tier-1 mechanical (`fba_flag`,
`fba_competitor_count`, `review_x_fba`); Tier-2 BB-snapshot (`Buy Box: Stock`,
`price_volatility`, `OOS %`). All scaling/encoding is fit train-only inside the pipeline;
`seller_rate` uses a cross-fitted TargetEncoder (no in-fold leakage). These fields are also
absent from the serving schema (`extra=ignore`), so they are excluded at serving time too.

See [`model_card.md`](model_card.md).

## Architecture (two tiers)
- **Tier 1 — HuggingFace Spaces:** an always-on, clickable Gradio demo (recruiter-facing).
- **Tier 2 — ephemeral EKS:** the orchestration proof (Terraform IaC + CI/CD + HPA + rolling
  + Evidently drift). Stood up during the demo window, evidence captured
  (recording / screenshots / Evidently report), then torn down with `terraform destroy`.

> _Note: serverless (Lambda) would be the production choice; EKS here is a deliberate choice
> to demonstrate Kubernetes orchestration._

_TODO — architecture diagram_

## Repository layout
```
app/            FastAPI service (main, service, schema) — FrequencyEncoder pickle fix
src/            rebuild.py — deterministic FE rebuild (raw → 54,855 rows, seed 42)
models/         final_model.pkl (full pipeline) + model_metadata.json + seller_rate_map.pkl
notebooks/      03_ablation_3b.ipynb, 04_tuning_shap.ipynb
infra/          Terraform (ECR + EKS + IAM/OIDC + budget)        # TODO Phase 5
k8s/            deployment + service + hpa                        # TODO Phase 5
monitoring/     evidently_drift.py + reference sample            # TODO Phase 5
.github/        CI/CD workflow (OIDC keyless)                     # TODO Phase 5
```

## Quickstart (local)
```bash
# With Docker
docker build -t buybox-propensity:local .
docker run -p 8000:8000 buybox-propensity:local
curl -X POST localhost:8000/predict -H "Content-Type: application/json" -d @ornek_istek.json

# Without Docker (local Python)
pip install -r requirements.txt
uvicorn app.main:app --reload   # /health, /predict
```

## Cloud / IaC operations (Phase 5)
- **Registry:** Amazon ECR · **Host:** EKS · **CI/CD:** GitHub Actions with keyless OIDC to AWS
  (no static keys) · **IaC:** Terraform with S3 + DynamoDB remote state.
- **Cost-aware:** public subnets (no NAT), small node group, AWS Budgets alert at 10 USD,
  `terraform destroy` + orphan-resource check after the demo.

_TODO — run order (terraform apply → CI/CD → Evidently → destroy) + cost runbook_

## Monitoring
Evidently tracks **input + prediction drift**. Labels are delayed, so live accuracy is not
monitored; when a drift threshold is exceeded → alert → retrain trigger. _TODO — details._

## Data
The raw data (Keepa export) is **NOT in this repository** — it is commercial/licensed and not
needed for serving. The source/schema are documented; to rebuild the features see
[`src/rebuild.py`](src/rebuild.py). The Evidently reference sample is produced from processed
features (not raw).
