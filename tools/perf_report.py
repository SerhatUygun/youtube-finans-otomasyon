"""Kanal performans geri bildirimi: son videoların izlenme / izlenme oranı / konu kategorisi -> output/_brain/perf.json + özet.
Günlük hat Claude'dan önce çağırır; Claude konu ve açı seçerken KİTLENİN GERÇEKTE NE İZLEDİĞİNİ görür.

30 Eyl bulgusu: uzun videolarda altın/gümüş/Fed 500–650 izlenme, borsa/benzin 64–67 (kanalın geçmişi değerli metaller);
Shorts her konuda tutuyor ama uzun videoya taşımıyor.

  python tools/perf_report.py
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "output" / "_brain" / "perf.json"

CATS = [("altın/gümüş", r"altın|gümüş|ons|gram altın|değerli metal"), ("fed/faiz", r"\bfed\b|faiz|tahvil|powell"),
        ("dolar/kur", r"dolar|kur\b|euro|rezerv"), ("borsa", r"borsa|bist|hisse|fon"), ("petrol/akaryakıt", r"petrol|brent|benzin|motorin|akaryakıt|eşel"),
        ("kripto", r"bitcoin|kripto|btc|ethereum"), ("enflasyon/ekonomi", r"enflasyon|tüfe|ekonomi|asgari|maaş")]


def cat(title: str) -> str:
    t = title.lower()
    for name, rx in CATS:
        if re.search(rx, t):
            return name
    return "diğer"


def iso_secs(d: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else 0


def main(days: int = 60):
    from googleapiclient.discovery import build
    from pipeline.stages import s09_upload
    from tools import pull_analytics
    yt = build("youtube", "v3", credentials=s09_upload._get_credentials(), cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=pull_analytics._get_credentials(), cache_discovery=False)
    up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=50).execute()["items"]
    since = (date.today() - timedelta(days=days)).isoformat()
    ids = [i["contentDetails"]["videoId"] for i in items if i["contentDetails"].get("videoPublishedAt", "")[:10] >= since]
    vids = {}
    for v in yt.videos().list(part="snippet,statistics,contentDetails,status", id=",".join(ids)).execute()["items"]:
        if v["status"]["privacyStatus"] != "public" or v["contentDetails"]["duration"] == "P0D":
            continue
        secs = iso_secs(v["contentDetails"]["duration"])
        vids[v["id"]] = {"title": v["snippet"]["title"], "date": v["snippet"]["publishedAt"][:10], "type": "shorts" if secs <= 180 else "long",
                         "views": int(v["statistics"].get("viewCount", 0)), "likes": int(v["statistics"].get("likeCount", 0)),
                         "comments": int(v["statistics"].get("commentCount", 0)), "cat": cat(v["snippet"]["title"])}
    if vids:
        r = ya.reports().query(ids="channel==MINE", startDate=since, endDate=date.today().isoformat(),
                               metrics="averageViewPercentage,averageViewDuration,subscribersGained", dimensions="video",
                               filters="video==" + ",".join(vids)).execute()
        for vid, pct, dur, subs in r.get("rows", []):
            vids[vid].update(avg_view_pct=round(pct, 1), avg_view_s=int(dur), subs=int(subs))
    summary = {}
    for t in ("long", "shorts"):
        by = {}
        for v in vids.values():
            if v["type"] == t:
                by.setdefault(v["cat"], []).append(v)
        summary[t] = {c: {"n": len(xs), "avg_views": round(sum(x["views"] for x in xs) / len(xs)),
                          "avg_view_pct": round(sum(x.get("avg_view_pct", 0) for x in xs) / len(xs), 1)} for c, xs in by.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"at": date.today().isoformat(), "summary": summary, "videos": vids}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(vids)} video -> {OUT}")
    for t, s in summary.items():
        print(t.upper(), sorted(((c, d["avg_views"], d["avg_view_pct"], d["n"]) for c, d in s.items()), key=lambda x: -x[1]))
    return summary


if __name__ == "__main__":
    main()
