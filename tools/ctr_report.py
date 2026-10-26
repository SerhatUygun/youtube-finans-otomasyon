"""Kapak gösterimi + tıklama oranı (CTR): YouTube Reporting API 'channel_reach_basic_a1' raporu.
Analytics API CTR vermiyor; Reporting API günlük CSV dosyaları üretir (ilk dosyalar iş kurulduktan ~48 saat sonra,
son 30 günü kapsar). Bu betik: işi yoksa kurar, raporları indirir, video bazında toplar -> output/_brain/ctr.json.

  python tools/ctr_report.py            # iş kur / indir / özetle
Yetki: secrets/youtube_analytics_token.json (yt-analytics.readonly yeterli). Projede 'YouTube Reporting API' açık olmalı.
"""
import csv
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import pull_analytics  # noqa: E402

OUT = ROOT / "output" / "_brain" / "ctr.json"
RAW = ROOT / "output" / "_brain" / "reach_reports"
TYPE = "channel_reach_basic_a1"


def main():
    from googleapiclient.discovery import build
    creds = pull_analytics._get_credentials()
    rep = build("youtubereporting", "v1", credentials=creds, cache_discovery=False)
    jobs = rep.jobs().list().execute().get("jobs", [])
    job = next((j for j in jobs if j["reportTypeId"] == TYPE), None)
    if not job:
        job = rep.jobs().create(body={"reportTypeId": TYPE, "name": "ytbot_reach"}).execute()
        print(f"iş kuruldu ({job['id']}) — ilk rapor ~48 saat içinde gelir")
    reports = rep.jobs().reports().list(jobId=job["id"]).execute().get("reports", [])
    RAW.mkdir(parents=True, exist_ok=True)
    from google.auth.transport.requests import AuthorizedSession
    sess = AuthorizedSession(creds)
    for r in reports:
        f = RAW / f"{r['startTime'][:10]}_{r['id']}.csv"
        if f.exists():
            continue
        resp = sess.get(r["downloadUrl"])
        resp.raise_for_status()
        f.write_bytes(resp.content)
    agg = defaultdict(lambda: {"impressions": 0, "clicks": 0.0})
    for f in sorted(RAW.glob("*.csv")):
        for row in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))):
            imp = float(row.get("video_thumbnail_impressions") or 0)
            ctr = float(row.get("video_thumbnail_impressions_ctr") or 0)
            a = agg[row.get("video_id", "?")]
            a["impressions"] += imp
            a["clicks"] += imp * ctr
    res = {v: {"impressions": int(a["impressions"]), "ctr_pct": round(100 * a["clicks"] / a["impressions"], 2) if a["impressions"] else None}
           for v, a in agg.items()}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(reports)} rapor, {len(res)} video -> {OUT}")
    for v, a in sorted(res.items(), key=lambda x: -x[1]["impressions"])[:12]:
        print(f"  {v}  gösterim {a['impressions']:>6}  CTR %{a['ctr_pct']}")


if __name__ == "__main__":
    main()
