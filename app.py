"""
app.py — Buy Box Propensity · Gradio UI (HuggingFace Spaces)
"""
import os, json, datetime as dt, tempfile
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import gradio as gr

import app.service as svc
from app.service import predict
from keepa_transform import transform, validate_columns, REQUIRED_RAW

C_HIGH, C_MID, C_LOW, C_NEU = "#d9534f", "#f0ad4e", "#5cb85c", "#5b9bd5"
BAND_COLOR = {"yuksek": C_HIGH, "orta": C_MID, "dusuk": C_LOW}
BAND_LABEL = {"yuksek": "YÜKSEK", "orta": "ORTA", "dusuk": "DÜŞÜK"}
FRAMING = ("Cross-sectional propensity (anlık) — zamansal tahmin değil. "
           "SHAP nedenleri ilişkiseldir, nedensel değil.")

with open(os.path.join(os.path.dirname(__file__), "ornek_istek.json"), encoding="utf-8") as _f:
    EX = json.load(_f)

SINGLE_NUM_ORDER = ["new_price_log", "new_price_margin_est",
                    "sr_log", "sr_drops_90", "review_velocity",
                    "Reviews: Rating", "review_count_log", "variation_count",
                    "offer_count_trend", "Package: Weight (g)", "Package: Dimension (cm³)"]
CONTRACT_BIN = ["has_sales_data", "is_negative_margin", "is_active_seller"]
CONTRACT_CAT = ["Categories: Sub", "Brand", "listing_seller"]
SINGLE_KEYS = SINGLE_NUM_ORDER + CONTRACT_BIN + CONTRACT_CAT

# --- geçici dosya (gr.State yerine) ---
_CONTRACT_TMP = os.path.join(tempfile.gettempdir(), "bb_contract.parquet")

def _shap_figure(reasons):
    feats = [r["feature"] for r in reasons][::-1]
    vals = [r["shap"] for r in reasons][::-1]
    cols = [C_HIGH if v > 0 else C_LOW for v in vals]
    fig, ax = plt.subplots(figsize=(6.2, 0.5 * len(feats) + 0.6))
    ax.barh(feats, vals, color=cols, alpha=0.9)
    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_xlabel("SHAP katkısı  (← azaltır | artırır →)")
    ax.set_title("En etkili nedenler"); fig.tight_layout()
    return fig

def _reasons_md(reasons):
    rows = "\n".join(f"| `{r['feature']}` | {r['shap']:+.3f} | {r['direction']} |" for r in reasons)
    return "| Feature | SHAP | Yön |\n|---|---|---|\n" + rows

def _propensity_html(out):
    band = out["risk_band"]; color = BAND_COLOR.get(band, C_NEU)
    pct = out["propensity"] * 100
    decision = ("Amazon BB tutar (recall-öncelikli)" if out["decision_recall_priority"]
                else "Amazon BB tutmaz")
    seller = "biliniyor" if out["seller_known"] else "bilinmiyor → global-mean fallback"
    return f"""
<div style="text-align:center;padding:14px;border-radius:14px;border:2px solid {color};background:{color}14">
  <div style="font-size:13px;color:#888;letter-spacing:.5px">PROPENSITY</div>
  <div style="font-size:54px;font-weight:800;color:{color};line-height:1">{out['propensity']:.4f}</div>
  <div style="font-size:15px;color:#ccc">{pct:.1f}% · risk bandı:
      <b style="color:{color}">{BAND_LABEL.get(band, band)}</b></div>
  <div style="margin-top:8px;font-size:13px;color:#999">
      Karar: <b>{decision}</b> · eşik {out['threshold_used']:.4f} · satıcı: {seller}</div>
</div>"""

def predict_single(npl,npm,srl,srd,rv,rr,rcl,vc,oct_,pw,pd_,hsd,inm,ias,sub,brand,seller,pas):
    record = dict(zip(SINGLE_KEYS,
        [npl,npm,srl,srd,rv,rr,rcl,vc,oct_,pw,pd_,hsd,inm,ias,sub,brand,seller]))
    for b in CONTRACT_BIN: record[b] = int(record[b])
    record["product_age_segment"] = int(pas)
    out = predict(record)
    return _propensity_html(out), _shap_figure(out["top_reasons"]), _reasons_md(out["top_reasons"])

def _read_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"): return pd.read_excel(path)
    if ext == ".parquet": return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)

def _score(contract_df):
    Z = svc._PRE.transform(contract_df)
    proba = svc._CLF.predict_proba(Z)[:, 1]
    thr = svc._THR
    band = np.where(proba >= thr, "yuksek", np.where(proba >= thr * 0.6, "orta", "dusuk"))
    return proba, band, thr

def predict_batch(file, as_of, listing_seller, show_unq):
    if file is None:
        return "Dosya yükleyin.", None, "", None
    try: raw = _read_any(file.name)
    except Exception as e:
        return f"⚠️ Dosya okunamadı: {e}", None, "", None
    missing = validate_columns(raw)
    if missing:
        msg = ("### ⚠️ Bu bir Keepa export'u gibi görünmüyor\n"
               f"Eksik zorunlu kolon(lar): **{', '.join(missing)}**\n\n"
               "Lütfen Keepa ürün export'u yükleyin (xlsx/csv/parquet).")
        return msg, None, "", None
    as_of = (as_of or "").strip() or None
    seller = (listing_seller or "").strip() or None
    contract = transform(raw, as_of=as_of, listing_seller=seller).reset_index(drop=True)
    # geçici dosyaya kaydet (satır SHAP için)
    contract.to_parquet(_CONTRACT_TMP, index=False)
    proba, band, thr = _score(contract)
    res = pd.DataFrame({"propensity": np.round(proba, 4), "risk_band": band,
                         "karar": np.where(proba >= thr, "Amazon BB tutar", "tutmaz")})
    if "ASIN" in raw.columns: res.insert(0, "ASIN", raw["ASIN"].values)
    if show_unq and "Buy Box: Unqualified" in raw.columns:
        res["unqualified (aktif BB yok)"] = np.where(
            raw["Buy Box: Unqualified"].astype(str).str.lower().eq("yes"), "evet", "hayır")
    res = res.sort_values("propensity", ascending=False).reset_index(drop=True)
    n = len(res); hi = int((band == "yuksek").sum()); md = int((band == "orta").sum()); lo = n - hi - md
    summary = (f"**{n}** satır · eşik {thr:.4f} · "
               f"🔴 YÜKSEK **{hi}** ({hi/n*100:.0f}%) · 🟡 ORTA **{md}** · 🟢 DÜŞÜK **{lo}**")
    out_path = "/tmp/buybox_scored.csv"; res.to_csv(out_path, index=False)
    return ("✅ Tahmin tamam. " + FRAMING, res, summary, out_path)

def row_shap(idx):
    if idx is None or idx == "": return None, ""
    try: contract = pd.read_parquet(_CONTRACT_TMP)
    except Exception: return None, "Önce Toplu Tahmin çalıştırın."
    idx = int(idx)
    if idx >= len(contract): return None, "Geçersiz satır."
    out = predict(contract.iloc[idx].to_dict())
    return _shap_figure(out["top_reasons"]), _reasons_md(out["top_reasons"])

EX_HIGH = [2.15, -0.076, 10.67, 11.0, 0.26, 4.5, 6.28, 16.0, 0.0, 90.0, 573.0,
           0, 1, 0, "Masking Tape", "Swanson", "Layger", 3]
EX_MID  = [5.2, 30.0, 6.0, 120.0, 0.005, 4.7, 1.8, 1.0, 6.0, 1500.0, 6000.0,
           1, 0, 1, "Kitchen Faucets", "Moen", "BotleyStore", 0]
EX_LOW  = [4.5, 15.0, 7.5, 90.0, 0.03, 4.5, 3.0, 2.0, 3.0, 600.0, 3000.0,
           1, 0, 1, "Shower Systems", "Delta", "GoldasKitchen", 1]

def build():
    with gr.Blocks(title="Buy Box Propensity") as demo:
        gr.Markdown(
            "# 🅰️ Amazon Buy Box Propensity\n"
            "Bir ürün profilinin **Amazon'un Buy Box'ı tuttuğu** propensity'sini tahmin eder.\n\n"
            "**Nasıl kullanılır:** Hazır senaryolardan birine tıklayın veya değerleri girin → **Tahmin Et**.\n\n"
            "*Veri burada işlenir, saklanmaz · cross-sectional (anlık).*")
        with gr.Tab("🔍 Tekil Tahmin"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("#### Ürün Profili")
                    with gr.Accordion("💰 Fiyat & Marj — Ürün kârlı mı?", open=True):
                        gr.Markdown("<small>Negatif marj Amazon hakimiyetini artırır.</small>")
                        npl = gr.Number(label="Fiyat (log scale)", info="ln(1+fiyat CAD). 2.15≈7.60, 4.5≈89 CAD", value=EX["new_price_log"])
                        npm = gr.Number(label="Tahmini Kâr Marjı (CAD)", info="Negatif = zarar", value=EX["new_price_margin_est"])
                    with gr.Accordion("📊 Satış & Talep — Ürün satılıyor mu?", open=True):
                        gr.Markdown("<small>Sales Rank düşükse popüler, rank drops yüksekse aktif.</small>")
                        srl = gr.Number(label="Sales Rank (log)", info="Düşük=popüler. 6≈top400, 10≈top22K", value=EX["sr_log"])
                        srd = gr.Number(label="Rank Düşüş (90 gün)", info="50+ = aktif satış", value=EX["sr_drops_90"])
                        rv  = gr.Number(label="Yorum Hızı (gün başı)", info="0.01=yavaş, 0.5=hızlı", value=EX["review_velocity"])
                    with gr.Accordion("📦 Ürün & Yorum", open=False):
                        rr  = gr.Number(label="Yıldız Puanı", value=EX["Reviews: Rating"])
                        rcl = gr.Number(label="Yorum Sayısı (log)", value=EX["review_count_log"])
                        vc  = gr.Number(label="Varyasyon Sayısı", value=EX["variation_count"])
                        oct_ = gr.Number(label="Teklif Trendi", value=EX["offer_count_trend"])
                        pw  = gr.Number(label="Paket Ağırlığı (g)", value=EX["Package: Weight (g)"])
                        pd_ = gr.Number(label="Paket Boyutu (cm³)", value=EX["Package: Dimension (cm³)"])
                    with gr.Accordion("🏷️ Bayraklar & Kategorik", open=False):
                        hsd = gr.Radio([0, 1], value=EX["has_sales_data"], label="Satış Verisi Var mı?")
                        inm = gr.Radio([0, 1], value=EX["is_negative_margin"], label="Negatif Marj?")
                        ias = gr.Radio([0, 1], value=EX["is_active_seller"], label="Aktif Satıcı?")
                        sub = gr.Textbox(EX["Categories: Sub"], label="Alt Kategori")
                        brand = gr.Textbox(EX["Brand"], label="Marka")
                        seller = gr.Textbox(EX["listing_seller"], label="Satıcı Adı", info="Boş→bilinmeyen")
                        pas = gr.Slider(0, 3, value=EX["product_age_segment"], step=1,
                                        label="Ürün Yaş Segmenti", info="0=0-90gün, 1=3ay-1yıl, 2=1-2yıl, 3=2+yıl")
                    btn = gr.Button("🔮 Tahmin Et", variant="primary", size="lg")
                    all_inputs = [npl,npm,srl,srd,rv,rr,rcl,vc,oct_,pw,pd_,hsd,inm,ias,sub,brand,seller,pas]
                    gr.Markdown(
                        "#### 📋 Hazır Senaryolar\n"
                        "<small>Bir senaryoya tıklayın → form otomatik dolar ve tahmin çalışır.</small>")
                    with gr.Row():
                        ex_hi = gr.Button("🔴 Yüksek Risk", size="sm")
                        ex_md = gr.Button("🟡 Orta Risk", size="sm")
                        ex_lo = gr.Button("🟢 Düşük Risk", size="sm")
                    gr.Markdown(
                        "<small>🔴 <b>Yüksek</b>: negatif marj, düşük satış → Amazon BB'yi tutar &nbsp;·&nbsp; "
                        "🟡 <b>Orta</b>: yüksek marj ama bilinmeyen pazar &nbsp;·&nbsp; "
                        "🟢 <b>Düşük</b>: aktif satış, pozitif marj → satıcı fırsatı</small>")
                with gr.Column(scale=1):
                    gr.Markdown("#### Sonuç")
                    out_html = gr.HTML(); out_plot = gr.Plot(); out_reasons = gr.Markdown()
            outputs = [out_html, out_plot, out_reasons]
            btn.click(predict_single, all_inputs, outputs)
            # Senaryo butonları: önce formu doldur, sonra tahmini çalıştır
            ex_hi.click(lambda: EX_HIGH, None, all_inputs).then(predict_single, all_inputs, outputs)
            ex_md.click(lambda: EX_MID, None, all_inputs).then(predict_single, all_inputs, outputs)
            ex_lo.click(lambda: EX_LOW, None, all_inputs).then(predict_single, all_inputs, outputs)
        with gr.Tab("📁 Ham Keepa Yükle"):
            gr.Markdown("### Toplu tahmin — Keepa export'u yükleyin\n"
                "**xlsx / csv / parquet** yükleyin. Eksik kolon varsa uyarı verir.\n\n"
                "**Adımlar:** ① Dosya sürükle ② Tarih+satıcı gir ③ Toplu Tahmin ④ Sonuçları incele/indir")
            with gr.Row():
                up = gr.File(label="Keepa export", file_types=[".xlsx",".xls",".csv",".parquet"])
                with gr.Column():
                    as_of = gr.Textbox(label="Export tarihi (YYYY-MM-DD)", value=str(dt.date.today()),
                                       info="Eğitim: 2023-10-17")
                    seller_b = gr.Textbox(label="Satıcı adı (opsiyonel)", info="Boş→bilinmeyen")
                    show_unq = gr.Checkbox(value=True, label="Unqualified sütunu göster")
            run = gr.Button("📊 Toplu Tahmin", variant="primary", size="lg")
            status = gr.Markdown(); summary = gr.Markdown()
            results = gr.Dataframe(label="Sonuçlar (propensity sıralı)", interactive=False)
            download = gr.File(label="📥 Skorlanmış CSV")
            run.click(predict_batch, [up,as_of,seller_b,show_unq], [status,results,summary,download])
            gr.Markdown("---")
            gr.Markdown("#### 🔍 Satır detayı — SHAP nedenleri")
            row_idx = gr.Number(label="Satır numarası (0'dan başlar)", value=0, precision=0)
            shap_btn = gr.Button("Nedenleri Göster")
            b_plot = gr.Plot(); b_reasons = gr.Markdown()
            shap_btn.click(row_shap, [row_idx], [b_plot, b_reasons])
        gr.Markdown(f"<sub>{FRAMING}</sub>")
    return demo

demo = build()
if __name__ == "__main__": demo.launch()
