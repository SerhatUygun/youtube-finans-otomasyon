"""Ajan 4 — Gece Editörü (15 Eki 2026; yerel gpt-oss:20b, kapak için isteğe bağlı qwen2.5vl).

Günün üretimi YÜKLENDİKTEN sonra, ertesi koşu başlamadan önce çalışır (ağır iş varsa BEKLER; model işi bitince bellekten atılır).
Girdi (hepsi mevcut dosyalar; veri yoksa iddia da yok):
  son daily-* klasörü (metadata/packaging_audit/video.json/reels.json/thumb.json), output/_brain/{perf,retention,ctr,
  yt_suggest,trends_tr,ref_brief,daily_history}, output/_agents/{morning_brief,perf_notes}, output/_brain/thumb_layouts.json
Çıktı:
  output/_agents/editor_notes/<tarih>.md   -> ayrıntılı editör notu (insan okur)
  output/_brain/editor_brief.md            -> kısa özet; günlük prompt İLHAM olarak okur (kopya yok)
Kodu/videoları DEĞİŞTİRMEZ; kanala hiçbir şey YAZMAZ. Modelin "algoritma" bilgisi doğrulanmış sayılmaz: öneriler yalnız
kanalın kendi verisine ve toplanan gerçek kaynaklara dayanmalı; dayanağı olmayan satır "VARSAYIM" diye işaretlenir.

  python tools/agents/night_editor.py             # tek tur
  python tools/agents/night_editor.py --no-ref    # referans kanal taramasını atla
"""
from __future__ import annotations

import argparse
import base64
import subprocess
import sys
from datetime import datetime

from common import OUT, ROOT, alert, llm_json, log, ollama_up, read_json, unload, wait_free, write_json  # noqa: F401

AGENT = "editor"
MODEL = "gpt-oss:20b"
VL_MODEL = "qwen2.5vl:7b"
NOTES_DIR = OUT / "editor_notes"
BRAIN = ROOT / "output" / "_brain"

SYSTEM = (
    "Sen deneyimli bir YouTube finans kanalı editörü, kurgucusu ve hareketli grafik (motion) tasarımcısısın. Kanal: Finans Kanalı "
    "(Türkçe; altın, gümüş, Fed, TL, BIST). Türkçe yaz. Kısa, somut, uygulanabilir ol. KURALLAR: (1) Yalnız sana verilen verilere dayan; "
    "veride olmayan rakam/izlenme/CTR UYDURMA. (2) YouTube algoritması hakkında genel bilgi verirsen satırı 'VARSAYIM:' ile başlat. "
    "(3) Kopya/çeviri önerme; rakip kanallardan yalnız konu, tez ve yapı ilhamı. (4) Yanıltıcı/abartılı iddia ve yatırım tavsiyesi önerme. "
    "(5) Kapakta gerçek insan yüzü ve kendini tanıtma önerme. (6) Kapaklar BİLİNÇLİ olarak her gün farklı yerleşim/renkle üretilir; "
    "'aynı font/palet/büyüklük kullan' ASLA önerme, benzerlik varsa çeşitlendirmeyi öner. (7) Verilerde olmayan şeyleri (ses kalitesi, müzik, "
    "kapak içeriği) değerlendirme; yalnız verilen alanlar hakkında yaz. (8) Sadece verideki rakamlarla somut öner; belirsizse o maddeyi YAZMA. "
    "(10) 'yarin_icin' açıları bugünkü başlıkların TEKRARI olamaz; gündem/arama verisinden YENİ konu öner. "
    "(11) Başlıkta yalnız noktalama/tek kelime değiştiren öneri yazma. (9) Boş doldurma yapma: en fazla 4 'gelistir' maddesi, her birinin 'dayanak' alanı verideki gerçek bir alanı/rakamı göstermeli."
)


def latest_job():
    jobs = sorted((ROOT / "output").glob("daily-2*"), key=lambda p: p.stat().st_mtime)
    for j in reversed(jobs):
        if (j / "metadata.json").exists() or (j / "reels.json").exists():
            return j
    return None


def clip(x, n=1800):
    s = x if isinstance(x, str) else str(x)
    return s[:n]


def vl_thumb_review(job) -> str:
    """Kapağı GÖREREK değerlendir (VL model kuruluysa); yoksa boş döner."""
    import requests
    img = job / "thumbnail.jpg"
    if not img.exists():
        img = job / "_raw" / "reel_1_thumb.jpg"
    if not img.exists():
        return ""
    try:
        tags = requests.get("http://localhost:11434/api/tags", timeout=5).json().get("models", [])
        if not any(m["name"].startswith("qwen2.5vl") for m in tags):
            return ""
        b64 = base64.b64encode(img.read_bytes()).decode()
        r = requests.post("http://localhost:11434/api/chat", timeout=600, json={
            "model": VL_MODEL, "stream": False, "keep_alive": 0,
            "messages": [{"role": "user", "content": "Bu bir YouTube kapağı. Türkçe, 4 kısa madde: (1) küçük boyutta okunur mu, (2) odak noktası net mi, "
                          "(3) renk/kontrast, (4) tıklatır mı ve neden. Kapaktaki yazıyı yalnız NET okuyabildiğin kadarıyla yaz; emin olmadığın kelimeyi [?] ile işaretle, tahmin etme.", "images": [b64]}]})
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        log(AGENT, f"VL kapak incelemesi atlandı: {str(e)[:120]}")
        return ""


def collect(job) -> dict:
    ctx: dict = {"job": job.name}
    ctx["metadata"] = {k: v for k, v in read_json(job / "metadata.json", {}).items() if k in ("title", "title_variants", "seconds", "tags")}
    ctx["paketleme_denetimi"] = read_json(job / "_raw" / "packaging_audit.json", {})
    vj = read_json(job / "video.json", {})
    segs = vj.get("segments", [])
    ctx["video"] = {"baslik": vj.get("title"), "segment_sayisi": len(segs),
                    "acilis_30sn_metni": " ".join(s.get("tts", "") for s in segs[:3])[:900],
                    "sahneler": [s.get("t") for s in vj.get("scenes", [])][:60]}
    ctx["reels"] = [{"baslik": r.get("title"), "tam_metin": " ".join(s.get("tts", "") for s in r.get("segments") or [])[:900]}
                    for r in read_json(job / "reels.json", [])]
    ctx["gun_tipi"] = "uzun+shorts" if segs else "YALNIZ SHORTS GÜNÜ (uzun video, video.json ve uzun kapak YOK — bunları 'eksik' diye eleştirme)"
    ctx["shorts_kapaklari_var"] = sorted(p.name for p in (job / "_raw").glob("reel_*_thumb.jpg"))
    ctx["kapaklar"] = read_json(job / "thumb.json", {})
    ctx["kapak_yerlesimleri"] = {k: v for k, v in list(read_json(BRAIN / "thumb_layouts.json", {}).items())[-5:]}
    ctx["son_basliklar"] = [h for h in [__import__("json").loads(x).get("title") for x in
                                         (BRAIN / "daily_history.jsonl").read_text(encoding="utf-8").splitlines()[-10:]] if h] \
        if (BRAIN / "daily_history.jsonl").exists() else []
    perf = read_json(BRAIN / "perf.json", {})
    ctx["performans_ozeti"] = perf.get("summary")
    ctx["son_videolar_izlenme"] = [{"baslik": v.get("title"), "tip": v.get("type"), "izlenme": v.get("views"), "tarih": v.get("date")}
                                   for v in list(perf.get("videos", {}).values())[-14:]]
    ret = read_json(BRAIN / "retention.json", {})
    ctx["tutma_verisi"] = [{"job": v.get("job"), "ilk30sn_kayip": v.get("first30_loss"), "bitis_orani": v.get("end_ratio"),
                             "ucurumlar": [{"sn": c.get("at_sec"), "dusus": c.get("drop")} for c in v.get("cliffs", [])[:3]]}
                            for v in ret.get("videos", [])[-4:]]
    ctx["ctr"] = clip(read_json(BRAIN / "ctr.json", {}), 700)
    ctx["arama_onerileri"] = clip(read_json(BRAIN / "yt_suggest.json", {}), 900)
    ctx["trendler_tr"] = clip(read_json(BRAIN / "trends_tr.json", {}), 700)
    ctx["gundem"] = clip(read_json(OUT / "morning_brief.json", {}), 1400)
    ref = BRAIN / "ref_brief.md"
    ctx["referans_kanal"] = clip(ref.read_text(encoding="utf-8"), 2200) if ref.exists() else ""
    return ctx


REQUIRED = ("ozet", "guclu", "gelistir", "editor_fikirleri", "izleyici_ilgisi", "yarin_icin", "kapak_cesitliligi")


def _strip(s: str) -> str:
    import re
    return re.sub(r'[\s"\'”“\],\[}{]+$', "", s.strip())  # model artığı: ”], vb.


def clean(res: dict) -> dict:
    out = {}
    for k, v in (res or {}).items():
        if isinstance(v, str):
            out[k] = _strip(v)
        elif isinstance(v, list):
            out[k] = [(_strip(x) if isinstance(x, str) else x) for x in v if x not in ("", None, {})]
        else:
            out[k] = v
    return out


def missing(res: dict) -> list[str]:
    return [k for k in REQUIRED if not res.get(k)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ref", action="store_true")
    a = ap.parse_args()
    if not ollama_up():
        log(AGENT, "Ollama kapalı — atlandı")
        return 1
    job = latest_job()
    if not job:
        log(AGENT, "denetlenecek günlük klasör yok")
        return 0
    if not a.no_ref:  # internetten toplama (GPU'suz): referans kanal + arama önerileri
        for t in ("tools/ref_watch.py", "tools/yt_suggest.py"):
            try:
                subprocess.run([sys.executable, "-X", "utf8", str(ROOT / t)], cwd=str(ROOT), timeout=300, capture_output=True)
            except Exception as e:  # noqa: BLE001
                log(AGENT, f"{t} atlandı: {str(e)[:100]}")
    if not wait_free(AGENT, max_wait_s=3 * 3600):
        return 0
    ctx = collect(job)
    vl = vl_thumb_review(job)
    if vl:
        ctx["kapak_gorsel_inceleme"] = vl
    prompt = (
        "Aşağıda bugünkü üretimin ve kanalın verileri var (JSON). Editör notunu hazırla.\n"
        "ÇIKTI: tek JSON nesnesi:\n"
        '{"ozet":"2 cümle genel değerlendirme",'
        '"guclu":["en çok 3 madde"],'
        '"gelistir":[{"konu":"başlık|kapak|açılış|tempo|grafik|ses|shorts","sorun":"veriye dayalı","oneri":"somut düzeltme","dayanak":"hangi veri / VARSAYIM"}],'
        '"editor_fikirleri":["kurgu/animasyon: ör. şu sahneyi böl, şu geçişi ekle, şu rakamı büyüt (en çok 5)"],'
        '"izleyici_ilgisi":["son veri/arama/trendlerden izleyicinin neyi merak ettiği (en çok 4)"],'
        '"yarin_icin":[{"aci":"video açısı","neden":"veri dayanağı","baslik_ornegi":"merak+rakam"}],'
        '"kapak_cesitliligi":"son kapaklar birbirine benziyor mu, ne önerirsin"}\n\nVERİ:\n'
        + __import__("json").dumps(ctx, ensure_ascii=False)[:24000]
    )
    log(AGENT, f"{job.name} denetleniyor ({MODEL})")
    res, eksik = {}, []
    try:
        for deneme in range(3):  # boş bölüm / bozuk JSON -> eksikleri söyleyip yeniden iste
            p = prompt if not eksik else prompt + f"\n\nÖNCEKİ YANITTA BOŞ/EKSİK ALANLAR: {', '.join(eksik)}. HER ALANI DOLDUR; listeler en az 2 madde."
            try:
                res = clean(llm_json(MODEL, p, system=SYSTEM, ctx=16384, temp=0.3 + 0.1 * deneme, timeout=1500, keep="5m"))
            except Exception as e:  # noqa: BLE001
                log(AGENT, f"deneme {deneme + 1} hata: {str(e)[:120]}")
                res = {}
            eksik = missing(res)
            if not eksik:
                break
            log(AGENT, f"deneme {deneme + 1}: eksik {eksik}")
    finally:
        unload(MODEL)
    if len(eksik) > 2:
        alert(AGENT, "hata", f"editör notu eksik kaldı ({', '.join(eksik)}); not yazılmadı, eski brief korunuyor")
        return 1
    import json as _j
    import re as _re
    src = _j.dumps(ctx, ensure_ascii=False).replace(".", "").replace(",", "")

    def _bad(t: str) -> list[str]:  # veride geçmeyen rakam = uydurma şüphesi
        return [n for n in _re.findall(r"\d+(?:[.,]\d+)?", t) if len(n) > 1 and n.replace(".", "").replace(",", "") not in src]
    for y in res.get("yarin_icin", []) if isinstance(res.get("yarin_icin"), list) else []:
        if isinstance(y, dict) and (b := _bad(f"{y.get('aci', '')} {y.get('baslik_ornegi', '')}")):
            y["neden"] = f"{y.get('neden', '')} ⚠ DOĞRULANAMAYAN rakam: {', '.join(b)}"
    for g in res.get("gelistir", []) if isinstance(res.get("gelistir"), list) else []:
        if isinstance(g, dict) and (b := _bad(str(g.get("oneri", "")))):
            g["dayanak"] = f"{g.get('dayanak', '')} ⚠ doğrulanamayan: {', '.join(b)}"
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    md = [f"# Editör notu — {day} ({job.name})", "", res.get("ozet", ""), ""]
    md += ["## Güçlü"] + [f"- {x}" for x in res.get("guclu", [])]
    md += ["", "## Geliştir"] + [f"- **{g.get('konu')}**: {g.get('sorun')} → {g.get('oneri')} _(dayanak: {g.get('dayanak')})_" for g in res.get("gelistir", [])]
    md += ["", "## Editör/animasyon fikirleri"] + [f"- {x}" for x in res.get("editor_fikirleri", [])]
    md += ["", "## İzleyici neyle ilgileniyor"] + [f"- {x}" for x in res.get("izleyici_ilgisi", [])]
    md += ["", "## Yarın için açılar"] + [f"- **{y.get('aci')}** — {y.get('neden')} (örnek başlık: {y.get('baslik_ornegi')})" for y in res.get("yarin_icin", [])]
    md += ["", "## Kapak çeşitliliği", str(res.get("kapak_cesitliligi", ""))]
    if vl:
        md += ["", "## Kapak (görsel model incelemesi)", vl]
    (NOTES_DIR / f"{day}.md").write_text("\n".join(md), encoding="utf-8")
    brief = ["# Gece editörü özeti (yerel model; İLHAM — doğrula, kopyalama)", f"Tarih: {day} · {job.name}", "",
             "Düzeltilecekler:"] + [f"- {g.get('konu')}: {g.get('oneri')}" for g in res.get("gelistir", [])[:4]] \
        + ["", "Yarın için açılar:"] + [f"- {y.get('aci')} ({y.get('baslik_ornegi')})" for y in res.get("yarin_icin", [])[:3]] \
        + ["", "İzleyici ilgisi:"] + [f"- {x}" for x in res.get("izleyici_ilgisi", [])[:3]]
    BRAIN.mkdir(parents=True, exist_ok=True)
    (BRAIN / "editor_brief.md").write_text("\n".join(brief), encoding="utf-8")
    log(AGENT, f"not yazıldı: {NOTES_DIR / (day + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
