# Buy Box Propensity — MLOps

Amazon **Buy Box propensity** modeli: bir ürün profili verildiğinde, Amazon'un o ürün
için Buy Box'ı tutma olasılığını tahmin eder. Leakage'a karşı titiz kurulmuş bir
LightGBM + uçtan uca serving (FastAPI) + IaC/CI/CD/monitoring ile **modelden production'a**
tüm hattı gösterir.

> **Durum:** Faz 5 (IaC + CI/CD + Monitoring) — devam ediyor. Aşağıda `TODO` ile işaretli
> bölümler hat kuruldukça doldurulacak.

## 🔗 Canlı demo
- **HuggingFace Spaces:** _TODO — Gradio arayüzü (her zaman açık, tıklanabilir)_

## Bu model nedir / ne DEĞİLDİR
- **Cross-sectional propensity / risk** modeli (tek snapshot, Ekim 2023; ASIN başına tek satır).
- **Zamansal tahmin DEĞİL** — "satıcı Buy Box'ı kaybedecek mi" demez.
- **Nedensel DEĞİL** — SHAP atıfları ilişkiseldir ("bu profildeki ürünler Amazon-baskın olma
  eğilimindedir"), nedensel/zamansal değil.
- **Kapsam:** mevcut satıcı tabanı; bilinmeyen satıcıda `seller_rate` global ortalamaya (0.146) düşer.

## Sonuçlar
| Metrik | Değer |
|---|---|
| Hold-out PR-AUC | **0.673** (no-skill base rate 0.146 → ~4.6×) |
| Hold-out ROC-AUC | **0.924** |
| Model | Regularize LightGBM, 18 feature, sabit 300 ağaç |

**Operating points** (varsayım A: recall-öncelikli, FN > FP):

| Nokta | Eşik | Precision | Recall | F1 |
|---|---|---|---|---|
| OP1 recall-priority | 0.62 | 0.53 | 0.78 | 0.63 |
| OP2 max-F1 | 0.73 | 0.62 | 0.64 | 0.63 |
| top-10% tarama | — | 0.69 | 0.47 | — |

### Leakage handling (dürüstlük notu)
Ablation merdiveni leak'in etkisini açıkça gösterir: **0.96 (leak'li) → 0.711 (CV leak-clean)
→ 0.673 (final, gap-kontrollü holdout)**. Çıkarılanlar: target-türevli
(`seller_win_rate`, `category_amazon_win_rate`); Tier-1 mekanik (`fba_flag`,
`fba_competitor_count`, `review_x_fba`); Tier-2 BB-snapshot (`Buy Box: Stock`,
`price_volatility`, `OOS %`). Tüm scaling/encoding pipeline içinde train-only fit;
`seller_rate` cross-fitted TargetEncoder (in-fold leakage yok). Bu alanlar serving
şemasında da yer almaz (`extra=ignore`) — yani servis anında da dışlanır.

Ayrıntı: [`model_card.md`](model_card.md)

## Mimari (iki katmanlı)
- **Katman 1 — HuggingFace Spaces:** her zaman açık, tıklanabilir Gradio demo (recruiter-facing).
- **Katman 2 — ephemeral EKS:** orchestration kanıtı (Terraform IaC + CI/CD + HPA + rolling +
  Evidently drift). Demo penceresinde ayağa kalkar, kanıt (kayıt/ekran görüntüsü/Evidently raporu)
  alınır, `terraform destroy` ile yıkılır.

> _Not: production'da serverless (Lambda) daha uygun olurdu; burada EKS, K8s orchestration
> becerisini göstermek için bilinçli bir tercih._

_TODO — mimari diyagramı_

## Repo yapısı
```
app/            FastAPI servis (main, service, schema) — FrequencyEncoder pickle fix
src/            rebuild.py — deterministik FE rebuild (raw → 54.855 satır, seed 42)
models/         final_model.pkl (tam pipeline) + model_metadata.json + seller_rate_map.pkl
notebooks/      03_ablation_3b.ipynb, 04_tuning_shap.ipynb
infra/          Terraform (ECR + EKS + IAM/OIDC + budget)        # TODO Faz 5
k8s/            deployment + service + hpa                        # TODO Faz 5
monitoring/     evidently_drift.py + reference_sample            # TODO Faz 5
.github/        CI/CD workflow (OIDC keyless)                     # TODO Faz 5
```

## Hızlı başlangıç (lokal)
```bash
# Docker ile
docker build -t buybox-propensity:local .
docker run -p 8000:8000 buybox-propensity:local
curl -X POST localhost:8000/predict -H "Content-Type: application/json" -d @ornek_istek.json

# Docker'sız (lokal Python)
pip install -r requirements.txt
uvicorn app.main:app --reload   # /health, /predict
```

## Cloud / IaC operasyonu (Faz 5)
- **Registry:** Amazon ECR · **Host:** EKS · **CI/CD:** GitHub Actions, AWS'ye OIDC keyless
  (statik anahtar yok) · **IaC:** Terraform, S3+DynamoDB remote state.
- **Cost-aware:** public subnet (NAT yok), küçük node group, AWS Budget alert 10 USD,
  demo sonrası `terraform destroy` + yetim kaynak kontrolü.

_TODO — çalıştırma sırası (terraform apply → CI/CD → Evidently → destroy) + cost runbook_

## Monitoring
Evidently ile **girdi + tahmin drift** takibi. Etiket gecikmeli olduğu için canlı accuracy
izlenmez; drift eşiği aşılınca alert → retrain tetiği. _TODO — detay._

## Veri
Ham veri (Keepa export) **bu repoda YOKTUR** — ticari/lisanslı ve serving için gereksiz.
Kaynak/şema dokümante; FE'yi yeniden üretmek için [`src/rebuild.py`](src/rebuild.py).
Evidently reference örneği işlenmiş feature'lardan üretilir (ham değil).
