"""Ajan 7 — Boşluk analisti (17 Eki; sayım koddan, yorum yerel qwen3:14b).

Bizim son 14 günlük konu/başlıklarımızı; haber gündemi (morning_brief), rakip/trend videoları (trend_brief.json) ve
YouTube arama önerileri (yt_suggest.json) ile KARŞILAŞTIRIR:
  - aşırı tekrar ettiğimiz konular (ör. üst üste altın),
  - gündemde/rakipte çok konuşulup bizde HİÇ olmayan konular,
  - bizim kitlenin en çok izlediği konular (perf.json varsa).
Sayımlar deterministik (anahtar kelime sözlüğü); model yalnız "ne yapmalı" yorumunu yazar, rakam üretmez.
Çıktı: output/_agents/gap.json + output/_brain/gap_brief.md (günlük prompt İLHAM olarak okuyabilir).

  python tools/agents/gap_analyst.py [--no-llm]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from common import OUT, ROOT, llm_json, log, ollama_up, read_json, unload, wait_free, write_json

AGENT = "bosluk"
MODEL = "qwen3:14b"
BRAIN = ROOT / "output" / "_brain"
TOPICS = {
    "altın": ["altın", "gold", "ons", "gram"], "gümüş": ["gümüş", "silver"], "fed": ["fed", "powell", "warsh", "federal reserve"],
    "tcmb/faiz": ["tcmb", "merkez bankası", "faiz", "baz puan"], "dolar/kur": ["dolar", "kur", "euro", "dollar", "usd"],
    "enflasyon": ["enflasyon", "tüfe", "inflation", "cpi"], "borsa": ["borsa", "bist", "hisse", "stock", "msci"],
    "petrol/enerji": ["petrol", "brent", "akaryakıt", "oil", "opec", "hürmüz", "hormuz"], "kripto": ["bitcoin", "kripto", "crypto"],
    "maaş/emekli": ["emekli", "maaş", "asgari", "pension"], "konut/kira": ["konut", "kira", "ev fiyat", "housing"],
    "resesyon/kriz": ["resesyon", "kriz", "recession", "crash", "çöküş", "balon", "bubble"],
    "merkez bankası altın alımı": ["central bank gold", "merkez bankaları altın", "rezerv"],
}


PROMPT = ("Finans Kanalı (TR finans kanalı) için konu dengesi verisi (sayımlar KODDAN, doğru)."
          " Eksik konular: {eksik}. Aşırı tekrar edilenler: {asiri}. Rakiplerde en çok izlenen konular: {rakip}."
          " Bu konulardan GERÇEK konu adlarıyla en çok 4 öneri yaz. Örnek biçim: "
          '{{"teshis":"Son videoların hepsi altın içeriyor; rakiplerde resesyon/kriz en çok izleniyor.",'
          '"oneriler":[{{"konu":"resesyon/kriz","ne_yap":"Kriz gelirse 100 bin TL birikim ne olur — uzun video",'
          '"dayanak":"rakip izlenme/gün ağırlığında 1. sırada, bizde 0"}}]}} '
          " Yer tutucu metin YAZMA, yeni rakam UYDURMA. VERİ: ")


def tags(text: str) -> set[str]:
    t = text.lower()
    return {k for k, ws in TOPICS.items() if any(w in t for w in ws)}


def count(texts: list[str]) -> dict[str, int]:
    c: dict[str, int] = {}
    for x in texts:
        for k in tags(x):
            c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def main(no_llm: bool) -> int:
    ours = []
    hp = BRAIN / "daily_history.jsonl"
    if hp.exists():
        for ln in hp.read_text(encoding="utf-8").splitlines()[-14:]:
            try:
                d = json.loads(ln)
                ours.append(f"{d.get('title', '')} {d.get('topic', '')}")
            except ValueError:
                pass
    news = [f"{x.get('title', '')} {x.get('ozet', '')}" for x in (read_json(OUT / "morning_brief.json", {}).get("top") or [])]
    tv = (read_json(OUT / "trend_brief.json", {}).get("ham") or {}).get("videos", [])
    rivals = [v.get("title", "") for v in tv]
    rival_w: dict[str, int] = {}  # izlenme/gün ağırlıklı
    for v in tv:
        for k in tags(v.get("title", "")):
            rival_w[k] = rival_w.get(k, 0) + int(v.get("views_per_day") or 0)
    sug = json.dumps(read_json(BRAIN / "yt_suggest.json", {}), ensure_ascii=False)
    c_ours, c_news, c_riv = count(ours), count(news), count(rivals)
    c_sug = {k: n for k in TOPICS if (n := sum(sug.lower().count(w) for w in TOPICS[k]))}
    n = max(len(ours), 1)
    eksik = [k for k in set(c_news) | set(c_riv) if c_ours.get(k, 0) == 0 and (c_news.get(k, 0) >= 2 or c_riv.get(k, 0) >= 2)]
    eksik.sort(key=lambda k: -(c_news.get(k, 0) * 2 + c_riv.get(k, 0) * 3))
    asiri = [k for k, v in c_ours.items() if v / n >= 0.6]
    data = {"bizim_video_sayisi": len(ours), "bizim_konular": c_ours, "gundem_konulari": c_news, "rakip_konulari": c_riv,
            "rakip_izlenme_gun_agirlik": dict(sorted(rival_w.items(), key=lambda kv: -kv[1])), "arama_onerisi_konulari": c_sug,
            "bizde_eksik": eksik, "asiri_tekrar": asiri}
    yorum: dict = {}
    if not no_llm and ollama_up() and wait_free(AGENT, max_wait_s=1800):
        try:
            yorum = llm_json(MODEL, PROMPT.format(eksik=eksik or "yok", asiri=asiri or "yok", rakip=list(data["rakip_izlenme_gun_agirlik"])[:4]) + json.dumps(data, ensure_ascii=False),
                             temp=0.3, timeout=600, keep="1m")
        except Exception as e:  # noqa: BLE001
            log(AGENT, f"yorum üretilemedi: {str(e)[:120]}")
        finally:
            unload(MODEL)
    import re
    sira = list(data["rakip_izlenme_gun_agirlik"])
    for o in (yorum.get("oneriler", []) if isinstance(yorum, dict) else []):
        k = o.get("konu", "")
        o["ne_yap"] = re.sub(r"\s*\b20\d\d(['’]?[a-zçğıöşü]*)?\b:?", "", str(o.get("ne_yap", ""))).strip()  # model yıl uyduruyor
        o["dayanak"] = (f"bizde {c_ours.get(k, 0)}/{len(ours)} video · gündemde {c_news.get(k, 0)} haber · rakip ağırlık sırası "
                        f"{sira.index(k) + 1 if k in sira else '-'}")  # dayanak koddan, model değil
    now = datetime.now().isoformat(timespec="minutes")
    write_json(OUT / "gap.json", {"at": now, **data, "yorum": yorum})
    fmt = lambda d: ", ".join(f"{k} {v}" for k, v in list(d.items())[:8]) or "-"  # noqa: E731
    md = [f"# Konu boşluk analizi — {now} (sayımlar koddan; yorum yerel model, İLHAM)", "",
          f"- Bizim son {len(ours)} video: {fmt(c_ours)}", f"- Gündem (haber): {fmt(c_news)}", f"- Rakip/trend video: {fmt(c_riv)}",
          f"- Rakipte izlenme/gün ağırlığı: {fmt(data['rakip_izlenme_gun_agirlik'])}", "",
          f"**Bizde hiç yok ama gündemde/rakipte var:** {', '.join(eksik) or '-'}",
          f"**Aşırı tekrar (son videoların %60+):** {', '.join(asiri) or '-'}", ""]
    if yorum:
        md += [yorum.get("teshis", ""), ""] + [f"- **{o.get('konu')}**: {o.get('ne_yap')} _(dayanak: {o.get('dayanak')})_"
                                              for o in yorum.get("oneriler", [])]
    (BRAIN / "gap_brief.md").write_text("\n".join(md), encoding="utf-8")
    log(AGENT, f"boşluk: eksik={eksik[:4]} aşırı={asiri}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    raise SystemExit(main(ap.parse_args().no_llm))
