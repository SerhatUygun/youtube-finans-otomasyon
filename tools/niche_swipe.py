"""10 Eki: yt-viral fikrinin otomatik hali — nişteki (TR finans) videoları kanalın KENDİ medyanına göre sırala, patlayanları çıkar.
Ham izlenme kanal büyüklüğünü ölçer; medyan katı (multiple) fikri ölçer. Resmi Data API (yt-dlp/scraping yok); kota ~600-800 birim/hafta.
Çıktı: output/_brain/niche.json (günlük talimat okur). Weekly görevi çağırır; tek başına da çalışır.

Kullanım: .venv/Scripts/python.exe tools/niche_swipe.py [--days 60] [--min 2.0]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("SP_UNATTENDED", "1")

BRAIN = ROOT / "output" / "_brain"
QUERIES = ["gram altın yorum", "fed faiz kararı altın", "dolar tl tahmin", "borsa istanbul yorum", "bitcoin tl analiz", "tcmb faiz kararı"]
_FIN = re.compile(r"altın|gram|fed|faiz|dolar|euro|borsa|bist|bitcoin|btc|kripto|enflasyon|tcmb|merkez bankası|petrol|brent|fon|hisse|yatırım|ekonomi|piyasa|lira|tl", re.I)
OWN = {"Finans Kanalı", "Finans Kanalı Shorts"}


def _shape(title: str) -> list[str]:
    """Başlığın kalıbı (Türkçe, basit): soru / rakam / uyarı / karşılaştırma."""
    t = title.lower()
    out = []
    if "?" in t or re.search(r"\b(neden|nasıl|ne olacak|mı|mi|mu|mü)\b", t):
        out.append("soru")
    if re.search(r"\d", t):
        out.append("rakam")
    if re.search(r"\b(dikkat|uyarı|tuzak|kriz|çöküş|düşüyor|düşecek|kaybet\w*|son dakika)\b", t):
        out.append("risk/uyarı")
    if re.search(r"\bvs\b|\bmi\b.*\bmi\b|karşılaştır", t):
        out.append("karşılaştırma")
    return out or ["diğer"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--min", type=float, default=2.0)
    ap.add_argument("--max-channels", type=int, default=25)
    a = ap.parse_args()
    import youtube_mcp as Y  # noqa: E402

    yt = Y.yt()
    after = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    chans: dict[str, str] = {}
    for q in QUERIES:
        r = yt.search().list(part="snippet", q=q, type="video", order="viewCount", publishedAfter=after, regionCode="TR",
                             relevanceLanguage="tr", maxResults=15).execute()
        for it in r.get("items", []):
            sn = it["snippet"]
            if sn["channelTitle"] not in OWN:
                chans.setdefault(sn["channelId"], sn["channelTitle"])
    rows = []
    for cid, cname in list(chans.items())[: a.max_channels]:
        try:
            up = yt.channels().list(part="contentDetails", id=cid).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            ids = [i["contentDetails"]["videoId"] for i in yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=20).execute()["items"]]
            for v in yt.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute().get("items", []):
                dur = v["contentDetails"]["duration"]
                rows.append({"channel": cname, "title": v["snippet"]["title"], "views": int(v["statistics"].get("viewCount", 0)),
                             "published": v["snippet"]["publishedAt"][:10], "id": v["id"], "short": "M" not in dur and "H" not in dur})
        except Exception as e:  # tek kanal hatası raporu bozmasın
            print(f"[niche] {cname}: {e}", file=sys.stderr)
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["channel"], []).append(r)
    out = []
    for ch, vids in by.items():
        if len(vids) < 4:
            continue  # medyan için en az 4 video
        med = statistics.median(v["views"] for v in vids) or 1
        for v in vids:
            m = v["views"] / med
            if m >= a.min and _FIN.search(v["title"]) and v["published"] >= after[:10]:
                out.append({**v, "median": int(med), "multiple": round(m, 2), "shape": _shape(v["title"])})
    out.sort(key=lambda x: -x["multiple"])
    shapes: dict[str, int] = {}
    for o in out:
        for s in o["shape"]:
            shapes[s] = shapes.get(s, 0) + 1
    rep = {"generated": datetime.now().strftime("%Y-%m-%d"), "channels": len(by), "outliers": out[:12], "shape_counts": shapes}
    BRAIN.mkdir(parents=True, exist_ok=True)
    (BRAIN / "niche.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[niche] {len(by)} kanal, {len(out)} patlayan; kalıplar: {shapes}")
    for o in out[:5]:
        print(f"  {o['multiple']}x {o['views']:,} · {o['channel']} · {o['title'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
