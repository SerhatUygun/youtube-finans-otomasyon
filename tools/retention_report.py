"""10 Eki: izleyici tutma eğrisi raporu — son uzun videoların ilk 30 sn kaybı ve "uçurum" anları, o anda söylenen cümleyle.
Analytics API: elapsedVideoTimeRatio x audienceWatchRatio (filters video==ID). Zaman eşlemesi: output/daily-*/_raw/props_long.json
(plan.segments, 30 fps) + upload_result.json (video_id). Çıktı: output/_brain/retention.json (weekly_report ve günlük talimat okur).

Kullanım: .venv/Scripts/python.exe tools/retention_report.py [--max 4] [--cliff 0.04]
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

BRAIN = ROOT / "output" / "_brain"


def _jobs(limit: int) -> list[dict]:
    """video_id'si olan, uzun video timeline'ı bulunan son işler (yeniden eskiye)."""
    out = []
    for d in sorted((ROOT / "output").glob("daily-*"), reverse=True):
        up, pr = d / "upload_result.json", d / "_raw" / "props_long.json"
        if not (up.exists() and pr.exists()):
            continue
        try:
            vid = json.loads(up.read_text(encoding="utf-8"))["video_id"]
            plan = json.loads(pr.read_text(encoding="utf-8"))["plan"]
        except Exception:
            continue
        out.append({"job": d.name, "video_id": vid, "fps": plan.get("fps", 30), "total": plan.get("total", 0), "segments": plan.get("segments", [])})
        if len(out) >= limit:
            break
    return out


def _said_at(job: dict, ratio: float) -> str:
    t = ratio * job["total"]
    for s in job["segments"]:
        if s["s"] <= t <= s["e"]:
            return s["text"][:140]
    return ""


def _curve(Y, vid: str, start: date, end: date) -> list[tuple[float, float]]:
    r = Y.ya().reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), dimensions="elapsedVideoTimeRatio",
                               metrics="audienceWatchRatio", filters=f"video=={vid}").execute()
    return sorted((float(a), float(b)) for a, b in r.get("rows", []))


def analyze(job: dict, pts: list[tuple[float, float]], cliff: float) -> dict:
    dur = job["total"] / job["fps"]
    at = lambda sec: next((w for x, w in pts if x * dur >= sec), pts[-1][1])  # noqa: E731
    first30 = max(0.0, 1 - at(30) / max(pts[0][1], 1e-9)) if pts else 0.0
    cliffs = []
    for (x0, w0), (x1, w1) in zip(pts, pts[1:]):
        if w0 - w1 >= cliff and x1 * dur > 30:
            cliffs.append({"at_sec": round(x1 * dur), "drop": round(w0 - w1, 3), "said": _said_at(job, x1)})
    cliffs.sort(key=lambda c: -c["drop"])
    return {"job": job["job"], "video_id": job["video_id"], "duration_sec": round(dur), "first30_loss": round(first30, 3),
            "end_ratio": round(pts[-1][1], 3) if pts else None, "cliffs": cliffs[:4]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=4)
    ap.add_argument("--cliff", type=float, default=0.04, help="iki nokta arası en az bu kadar izleyici kaybı = uçurum")
    a = ap.parse_args()
    import youtube_mcp as Y  # noqa: E402

    end, start = date.today(), date.today() - timedelta(days=90)
    res = []
    for job in _jobs(a.max):
        try:
            pts = _curve(Y, job["video_id"], start, end)
        except Exception as e:  # yetki/kota: rapor asla bozulmasın
            print(f"[retention] {job['job']}: {e}", file=sys.stderr)
            continue
        if len(pts) >= 10:
            res.append(analyze(job, pts, a.cliff))
    BRAIN.mkdir(parents=True, exist_ok=True)
    rep = {"generated": str(end), "videos": res,
           "avg_first30_loss": round(sum(r["first30_loss"] for r in res) / len(res), 3) if res else None}
    (BRAIN / "retention.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False)[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
