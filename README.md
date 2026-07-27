# Buy Box Propensity — MLOps

An Amazon **Buy Box propensity** model: given a product profile, it estimates the propensity
that Amazon holds the Buy Box for that product. The project demonstrates the full
**model-to-production** path — a leakage-clean LightGBM plus end-to-end serving (FastAPI),
infrastructure as code, CI/CD, and drift monitoring.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Hugging%20Face-FFD21E?logo=huggingface&logoColor=black)](https://huggingface.co/spaces/R7Murat/buybox-propensity)
[![PR-AUC](https://img.shields.io/badge/PR--AUC-0.673-blue)](#results)
[![ROC-AUC](https://img.shields.io/badge/ROC--AUC-0.924-blue)](#results)
[![Deployment](https://img.shields.io/badge/EKS%20deployment-verified%20%26%20torn%20down-success)](#deployment-evidence)

**Complete.** Model, evaluation, serving, IaC, CI/CD and monitoring are all shipped and
verified — see [Deployment evidence](#deployment-evidence).

## 🔗 Live demo

**Hugging Face Spaces:** [▶️ Live Demo](https://huggingface.co/spaces/R7Murat/buybox-propensity) — Gradio UI, always on.

---

## What this model is / is NOT

- A **cross-sectional propensity / risk** model (single snapshot, Oct 2023; one row per ASIN).
- **Not a temporal forecast** — it does not predict that a seller *will lose* the Buy Box.
- **Not causal** — SHAP attributions are associational ("products with this profile tend to be
  Amazon-dominated"), not causal or temporal.
- **Scope:** existing seller base; unknown sellers fall back to the global-mean `seller_rate` (0.146).

---

## Results

| Metric | Value |
|---|---|
| Hold-out PR-AUC | **0.673** (no-skill base rate 0.146 → ~4.6×) |
| Hold-out ROC-AUC | **0.924** |
| Model | Regularized LightGBM, 18 features, fixed 300 trees |

**Operating points** (assumption A: recall-priority, FN > FP)

| Point | Threshold | Precision | Recall | F1 |
|---|---|---|---|---|
| OP1 recall-priority | 0.62 | 0.53 | 0.78 | 0.63 |
| OP2 max-F1 | 0.73 | 0.62 | 0.64 | 0.63 |
| top-10% screen | — | 0.69 | 0.47 | — |

PR-AUC is reported alongside ROC-AUC because the positive class is rare (14.6%) — ROC-AUC alone
would overstate performance at this base rate.

### Leakage handling (the honesty note)

The ablation ladder makes the leakage effect explicit:

```
0.96   leaky baseline
0.711  CV, leak-clean
0.673  final, gap-controlled hold-out
```

**Removed:** target-derived (`seller_win_rate`, `category_amazon_win_rate`); Tier-1 mechanical
(`fba_flag`, `fba_competitor_count`, `review_x_fba`); Tier-2 Buy Box snapshot (`Buy Box: Stock`,
`price_volatility`, `OOS %`).

All scaling and encoding is fit train-only inside the pipeline; `seller_rate` uses a cross-fitted
TargetEncoder (no in-fold leakage). These fields are also absent from the serving schema
(`extra=ignore`), so they are excluded at inference time too.

Full detail: [`model_card.md`](model_card.md)

---

## Architecture (two tiers)

**Tier 1 — Hugging Face Spaces.** Always-on, clickable Gradio demo. The surface that stays live.

**Tier 2 — ephemeral EKS.** The orchestration proof: Terraform IaC, CI/CD, HPA, rolling updates,
Evidently drift. Stood up during a demo window, evidence captured, then torn down with
`terraform destroy`.

> *Note: serverless (Lambda) would be the production choice for a model this size; EKS here is a
> deliberate decision to demonstrate Kubernetes orchestration.*

Architecture diagram: [`docs/demo-evidence/architecture-diagram.html`](docs/demo-evidence/architecture-diagram.html)

---

## Deployment evidence

The EKS deployment is intentionally **not left running** — provisioning, validating and
destroying is the full cycle, and resource hygiene is part of the point. The evidence below
documents that cycle end to end.

| # | Evidence | What it shows |
|---|---|---|
| 01 | [Terraform apply complete](docs/demo-evidence/01-terraform-apply-complete.png) | IaC provisioning succeeded |
| 02 | [EKS cluster active](docs/demo-evidence/02-eks-cluster-list-active.png) | Cluster running |
| 03 | [EKS cluster detail](docs/demo-evidence/03-eks-cluster-detail.png) | Node group and config |
| 04 | [Pods & services running](docs/demo-evidence/04-kubectl-pods-svc-running.png) | Workload healthy |
| 05 | [Horizontal Pod Autoscaler](docs/demo-evidence/05-kubectl-hpa.png) | Autoscaling configured |
| 06 | [Swagger UI — request](docs/demo-evidence/06-swagger-ui-input.png) | Live API accepting input |
| 07 | [Swagger UI — prediction](docs/demo-evidence/07-swagger-ui-predict-result.png) | Model serving in cluster |
| 08 | [Swagger UI — schemas](docs/demo-evidence/08-swagger-ui-schemas.png) | Typed request/response contract |
| 09 | [GitHub Actions all green](docs/demo-evidence/09-github-actions-all-green.png) | CI/CD pipeline passing |
| 10 | [Terraform destroy](docs/demo-evidence/10-terraform-destroy.png) | Clean teardown, no orphaned resources |

---

## Repository layout

```
app/            FastAPI service (main, service, schema) — FrequencyEncoder pickle fix
app.py          Gradio UI entrypoint (Hugging Face Spaces)
src/            rebuild.py — deterministic FE rebuild (raw → 54,855 rows, seed 42)
models/         final_model.pkl (full pipeline) + model_metadata.json + seller_rate_map.pkl
notebooks/      03_ablation_3b.ipynb, 04_tuning_shap.ipynb
infra/terraform ECR + EKS + IAM/OIDC + budget
k8s/            deployment + service + hpa
monitoring/     evidently_drift.py
.github/        CI/CD workflow (OIDC keyless)
docs/           deployment evidence + architecture diagram
```

---

## Quickstart (local)

```bash
# With Docker
docker build -t buybox-propensity:local .
docker run -p 8000:8000 buybox-propensity:local
curl -X POST localhost:8000/predict \
     -H "Content-Type: application/json" \
     -d @ornek_istek.json

# Without Docker
pip install -r requirements.txt
uvicorn app.main:app --reload   # /health, /predict
```

---

## Cloud / IaC operations

- **Registry:** Amazon ECR · **Host:** EKS · **CI/CD:** GitHub Actions with keyless OIDC to AWS
  (no static credentials) · **IaC:** Terraform with S3 + DynamoDB remote state.
- **Cost-aware by design:** public subnets (no NAT gateway), small node group, AWS Budgets alert
  at 10 USD, `terraform destroy` plus an orphan-resource check after each demo window.

**Run order**

```
terraform apply           # provision ECR, EKS, IAM/OIDC, budget
git push → GitHub Actions # build image, push to ECR, deploy to EKS
kubectl get pods,svc,hpa  # validate workload
<swagger UI>              # validate serving
evidently_drift.py        # generate drift report
terraform destroy         # tear down, verify no orphans
```

## Monitoring

Evidently tracks **input and prediction drift**. Labels arrive with delay, so live accuracy is not
monitored; instead, crossing a drift threshold raises an alert and triggers retraining.

---

## Data

The raw data (Keepa export) is **not in this repository** — it is commercial/licensed and not
needed for serving. The source and schema are documented; to rebuild the features see
[`src/rebuild.py`](src/rebuild.py). The Evidently reference sample is produced from processed
features, not raw data.
