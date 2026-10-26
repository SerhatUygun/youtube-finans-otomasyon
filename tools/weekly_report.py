"""10 Eki: haftalık öğrenme raporu — son 7 günün videoları: izlenme, izlenme yüzdesi, abone kazancı, 1.000 izlenmede abone,
trafik kaynağı. Çıktı: output/_brain/weekly.json (günlük talimat okur) + weekly.md (insan için). Görev: Pazartesi 09:30.

Kullanım: .venv/Scripts/python.exe tools/weekly_report.py [--days 7]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("SP_UNATTENDED", "1")

import youtube_mcp as Y  # noqa: E402  (aynı yetki/istemciler)

BRAIN = ROOT / "output" / "_brain"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    end, start = date.today(), date.today() - timedelta(days=a.days)
    r = Y.ya().reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), dimensions="video",
                               metrics="views,averageViewPercentage,subscribersGained,subscribersLost,likes,comments,shares",
                               sort="-views", maxResults=50).execute()
    rows = r.get("rows", [])
    ids = [x[0] for x in rows]
    meta = {}
    for i in range(0, len(ids), 50):
        for v in Y.yt().videos().list(part="snippet,contentDetails", id=",".join(ids[i:i + 50])).execute().get("items", []):
            meta[v["id"]] = {"title": v["snippet"]["title"], "date": v["snippet"]["publishedAt"][:10],
                             "short": "#shorts" in v["snippet"]["title"].lower() or v["contentDetails"]["duration"].startswith("PT") and "M" not in v["contentDetails"]["duration"]}
    vids = []
    for vid, views, pct, sg, sl, lk, cm, sh in rows:
        m = meta.get(vid, {})
        vids.append({"id": vid, "title": m.get("title", vid), "date": m.get("date"), "type": "shorts" if m.get("short") else "long",
                     "views": views, "avg_pct": round(pct, 1), "subs_net": sg - sl, "subs_per_1k": round(1000 * sg / views, 2) if views else 0,
                     "likes": lk, "comments": cm, "shares": sh})
    tot = Y.ya().reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), metrics="views,subscribersGained,subscribersLost").execute()
    tv, tg, tl = (tot.get("rows") or [[0, 0, 0]])[0]
    src = Y.ya().reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), metrics="views", dimensions="insightTrafficSourceType",
                                 sort="-views").execute().get("rows", [])
    rep = {"from": str(start), "to": str(end), "views": tv, "subs_gained": tg, "subs_lost": tl, "subs_per_1k": round(1000 * tg / tv, 2) if tv else 0,
           "traffic": {k: v for k, v in src}, "videos": vids,
           "best_subs": sorted(vids, key=lambda x: -x["subs_per_1k"] if x["views"] >= 100 else 0)[:3],
           "best_retention_long": sorted([x for x in vids if x["type"] == "long"], key=lambda x: -x["avg_pct"])[:3]}
    BRAIN.mkdir(parents=True, exist_ok=True)
    (BRAIN / "weekly.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# Haftalık rapor · {start} → {end}", "",
          f"- İzlenme **{tv:,}** · abone +{tg} / −{tl} (net {tg - tl:+d}) · 1.000 izlenmede **{rep['subs_per_1k']}** abone",
          "- Trafik: " + ", ".join(f"{k} {v:,}" for k, v in list(rep["traffic"].items())[:6]), "", "| Tür | Video | İzlenme | İzlenme % | Net abone | Abone/1k |", "|---|---|---|---|---|---|"]
    md += [f"| {v['type']} | {v['title'][:60].replace('|', '/')} | {v['views']:,} | {v['avg_pct']} | {v['subs_net']:+d} | {v['subs_per_1k']} |" for v in vids[:25]]
    (BRAIN / "weekly.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:4]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
