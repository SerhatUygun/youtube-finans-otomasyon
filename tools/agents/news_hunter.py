"""Ajan 1 — Haber/trend avcısı (saatte bir; yerel qwen3:14b).

Bloomberg HT + Google News (TR/EN konu sorguları; AA/Kitco/Reuters haberleri buradan gelir) -> yeni başlıklar ->
yerel model kanala uygunluk puanı (0-10) + kategori + Türkçe tek cümle özet -> output/_agents/news.jsonl (son 48 saat)
-> output/_agents/morning_brief.json (son 24 saatin en önemlileri + 3 video açısı önerisi).
Günlük hat (prompts/daily_video.md) brief'i girdi olarak okur; Claude'un araştırma süresini kısaltır.

  python tools/agents/news_hunter.py            # tek tur
  python tools/agents/news_hunter.py --no-llm   # yalnız topla (puansız)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from common import OUT, alert, llm_json, log, ollama_up, read_json, unload, wait_free, write_json

AGENT = "haber"
MODEL = "qwen3:14b"
NEWS = OUT / "news.jsonl"
BRIEF = OUT / "morning_brief.json"


def gn(q: str, lang: str = "tr") -> str:
    loc = "hl=tr&gl=TR&ceid=TR:tr" if lang == "tr" else "hl=en-US&gl=US&ceid=US:en"
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}+when:1d&{loc}"


FEEDS = {
    "bloomberght": "https://www.bloomberght.com/rss",
    "gn:altın": gn("altın fiyatları OR ons altın OR gram altın"),
    "gn:gümüş": gn("gümüş fiyatı"),
    "gn:fed-tr": gn("Fed faiz kararı OR Powell"),
    "gn:tcmb": gn("Merkez Bankası faiz OR TCMB"),
    "gn:kur": gn("dolar TL OR euro TL kur"),
    "gn:enflasyon": gn("enflasyon TÜFE"),
    "gn:borsa": gn("Borsa İstanbul BIST 100"),
    "gn:gold": gn("gold price", "en"),
    "gn:silver": gn("silver price", "en"),
    "gn:fed": gn("Federal Reserve rates", "en"),
    "gn:treasury": gn("Treasury yields", "en"),
    "gn:petrol": gn("Brent petrol OR akaryakıt zam"),
    "gn:maas": gn("emekli maaşı OR asgari ücret zam"),
    "gn:konut": gn("konut kredisi OR kira artışı"),
    "gn:rezerv": gn("TCMB rezerv OR swap"),
    "gn:kripto": gn("Bitcoin fiyat"),
    "gn:oil": gn("oil price OPEC", "en"),
    "gn:cbgold": gn("central bank gold buying", "en"),
}
PER_FEED = 25


def fetch() -> list[dict]:
    items = []
    for src, url in FEEDS.items():
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
            for it in ET.fromstring(raw).findall(".//item")[:PER_FEED]:
                title = (it.findtext("title") or "").strip()
                if not title:
                    continue
                try:
                    pub = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone().replace(tzinfo=None)
                except Exception:  # noqa: BLE001
                    pub = datetime.now()
                outlet = (it.findtext("source") or "").strip() or src
                items.append({"id": hashlib.md5(title.lower().encode()).hexdigest()[:12], "title": title, "link": it.findtext("link") or "",
                              "src": src, "outlet": outlet, "pub": pub.isoformat(timespec="minutes")})
        except Exception as e:  # noqa: BLE001
            log(AGENT, f"kaynak hatası {src}: {str(e)[:80]}")
    return items


SYS = ("Sen 'Finans Kanalı' adlı Türk finans YouTube kanalının haber editörüsün. Kitle: altın/gümüş birikimi yapan, Fed ve dolar/TL'yi "
       "takip eden Türk izleyici. Kanalın en çok izlenen konuları: altın/gümüş (açık ara), Fed/faiz. Borsa ve akaryakıt düşük ilgi görüyor.")


def score(batch: list[dict]) -> dict:
    lines = "\n".join(f"{i}) {x['title']} ({x['outlet']})" for i, x in enumerate(batch))
    prompt = (f"Aşağıdaki haber başlıklarını puanla. JSON döndür: {{\"items\": [{{\"i\": <no>, \"score\": <0-10 kanal için video değeri>, "
              f"\"cat\": \"altın|gümüş|fed|tcmb|kur|enflasyon|borsa|petrol|kripto|diğer\", \"ozet\": \"<başlığın TÜRKÇE çevirisi, tek cümle; İngilizceyi de çevir; yalnız başlıktaki bilgi>\"}}]}}\n"
              f"Puan rehberi: 9-10 altın/gümüşte büyük hareket ya da Fed/TCMB sürprizi; 6-8 kitleyi ilgilendiren önemli veri/gelişme; "
              f"3-5 genel ekonomi; 0-2 alakasız/reklam/tekrar fiyat listesi ('güncel altın fiyatları' sayfaları 1).\n\n{lines}")
    out = llm_json(MODEL, prompt, system=SYS)
    return {int(x["i"]): x for x in out.get("items", []) if str(x.get("i", "")).isdigit() or isinstance(x.get("i"), int)}


def angles(top: list[dict]) -> dict:
    lines = "\n".join(f"- [{x.get('score')}, {x.get('n_src', 1)} kaynak] {x['title']} || {x.get('ozet', '')}" for x in top[:15])
    prompt = ("Son 24 saatin en önemli haberleri aşağıda. Bunlardan Finans Kanalı için bugün çekilebilecek 3 uzun video AÇISI öner. "
              "Her açı kitlenin cebine/birikimine dokunmalı ve merak boşluğu içermeli (dürüst, yanıltıcı olmayan). "
              "KESİN KURAL: yalnız aşağıdaki haberlerde geçen isim ve rakamları kullan; yeni isim/rakam UYDURMA. JSON: "
              "{\"angles\": [{\"baslik_fikri\": \"...\", \"kanca\": \"ilk cümle\", \"neden_simdi\": \"...\", \"dayanak\": [\"haber özeti\", ...]}], "
              f"\"gunun_ozeti\": \"3-4 cümle\"}}\n\n{lines}")
    return llm_json(MODEL, prompt, system=SYS, temp=0.5)


def verify_angles(a: dict, top: list[dict]) -> dict:
    """Açıdaki rakamlar kaynak başlıklarda/özetlerde geçmiyorsa işaretle (yerel model rakam uydurabiliyor)."""
    import re
    src = " ".join(f"{x.get('title', '')} {x.get('ozet', '')}" for x in top).replace(".", "").replace(",", "")
    for ang in a.get("angles", []):
        txt = f"{ang.get('baslik_fikri', '')} {ang.get('kanca', '')}"
        bad = [n for n in re.findall(r"\d+(?:[.,]\d+)?", txt) if n.replace(".", "").replace(",", "") not in src]
        ang["dogrulama"] = "rakamlar haberlerde var" if not bad else f"DOĞRULANAMAYAN rakam: {', '.join(bad)} — kullanma"
    return a


def _toks(t: str) -> set[str]:
    import re
    t = re.sub(r"\s+-\s+[^-]+$", "", t.lower())  # Google News " - Kaynak" eki
    return {w for w in re.findall(r"[\wçğıöşü%']+", t) if len(w) > 2}


def dedupe(items: list[dict]) -> list[dict]:
    """Aynı olayın farklı kaynaklardaki başlıklarını birleştir (Jaccard >= 0,4); en yüksek puanlı kalır, n_src = kaynak sayısı."""
    out: list[dict] = []
    for x in sorted(items, key=lambda x: -(x.get("score") or 0)):
        tx = _toks(x["title"])
        for y in out:
            ty = y["_t"]
            if tx and ty and len(tx & ty) / len(tx | ty) >= 0.4:
                y["n_src"] += 1
                break
        else:
            out.append({**x, "_t": tx, "n_src": 1})
    for y in out:
        y.pop("_t", None)
    return out


def main(no_llm: bool = False) -> int:
    old = []
    if NEWS.exists():
        for ln in NEWS.read_text(encoding="utf-8").splitlines():
            try:
                old.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
    cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
    old = [x for x in old if x.get("pub", "") >= cutoff]
    seen = {x["id"] for x in old}
    fresh = [x for x in fetch() if x["id"] not in seen and x["pub"] >= cutoff]
    uniq = {x["id"]: x for x in fresh}
    fresh = list(uniq.values())
    log(AGENT, f"{len(fresh)} yeni başlık ({len(old)} kayıtlı)")

    llm_ok = not no_llm and ollama_up() and wait_free(AGENT)
    MAXN = 60  # tur başına puanlanacak en fazla yeni başlık (en yeniler önce); kalanlar sonraki turlarda
    fresh.sort(key=lambda x: x["pub"], reverse=True)
    if fresh and llm_ok:
        for k in range(0, min(len(fresh), MAXN), 20):
            b = fresh[k:k + 20]
            try:
                sc = score(b)
                for i, x in enumerate(b):
                    if i in sc:
                        x.update(score=sc[i].get("score"), cat=sc[i].get("cat"), ozet=sc[i].get("ozet"))
            except Exception as e:  # noqa: BLE001
                log(AGENT, f"puanlama hatası: {str(e)[:120]}")
            if not wait_free(AGENT):  # tur arasında render başladıysa bırak; puansızlar sonraki turda puanlanır
                break
    # puansız eski kayıtları da sonraki turda puanlamak için tekrar dene
    if llm_ok:
        pend = [x for x in old if x.get("score") is None and x.get("pub", "") >= (datetime.now() - timedelta(hours=24)).isoformat()][:40]
        for k in range(0, len(pend), 20):
            if not wait_free(AGENT):
                break
            try:
                sc = score(pend[k:k + 20])
                for i, x in enumerate(pend[k:k + 20]):
                    if i in sc:
                        x.update(score=sc[i].get("score"), cat=sc[i].get("cat"), ozet=sc[i].get("ozet"))
            except Exception as e:  # noqa: BLE001
                log(AGENT, f"eski puanlama hatası: {str(e)[:120]}")

    allx = old + fresh
    NEWS.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in allx), encoding="utf-8")

    day = (datetime.now() - timedelta(hours=24)).isoformat()
    top = dedupe([x for x in allx if x.get("pub", "") >= day and isinstance(x.get("score"), (int, float))])
    top = sorted(top, key=lambda x: (-x["score"], -x["n_src"]))[:25]
    brief = read_json(BRIEF, {})
    brief.update(at=datetime.now().isoformat(timespec="minutes"),
                 note="Yerel model (qwen3:14b) özetleri İPUCUDUR, doğrulanmamıştır; rakam/isim kullanmadan önce kaynağından doğrula.",
                 top=[{k: x.get(k) for k in ("score", "cat", "ozet", "title", "outlet", "n_src", "pub", "link")} for x in top])
    hot = dedupe([x for x in fresh if (x.get("score") or 0) >= 9])[:3]  # tur başına en fazla 3 uyarı, tekrarsız
    for x in hot:
        alert(AGENT, "haber", f"[{x['score']}] {x.get('ozet') or x['title']}")
    # açı önerileri: yeni önemli haber geldiyse ya da 3 saatten eskiyse yenile
    stale = brief.get("angles_at", "") < (datetime.now() - timedelta(hours=3)).isoformat()
    if llm_ok and top and (hot or stale) and wait_free(AGENT):
        try:
            a = verify_angles(angles(top), top)
            brief.update(angles=a.get("angles", []), gunun_ozeti=a.get("gunun_ozeti", ""), angles_at=datetime.now().isoformat(timespec="minutes"))
        except Exception as e:  # noqa: BLE001
            log(AGENT, f"açı önerisi hatası: {str(e)[:120]}")
    if llm_ok:
        unload(MODEL)
    write_json(BRIEF, brief)
    log(AGENT, f"brief: {len(top)} önemli haber, {len(brief.get('angles', []))} açı -> {BRIEF.name}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    raise SystemExit(main(ap.parse_args().no_llm))
