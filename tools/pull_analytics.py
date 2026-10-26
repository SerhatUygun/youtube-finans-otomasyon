"""YouTube Analytics -> BEYİN geri besleme döngüsü (küme 3). KOD HAZIR — çalıştırmadan önce
hesabı 'yt-analytics.readonly' scope'uyla yeniden yetkilendirmen gerekir (aşağıya bak).

Şu an beyin KENDİ kendini değerlendiriyor (critic). Bu araç, GERÇEK performansı (izlenme,
izlenme oranı/retention, abone kazanımı) çekip beyne öğretir: hangi açı/konu gerçekten tuttu?
Sonuç learned_guidance'a beslenir -> beyin tahminle değil, veriyle öğrenir.

ÖN KOŞUL (bir kereye mahsus):
  1. Google Cloud Console -> APIs & Services -> Library -> 'YouTube Analytics API' ETKİNLEŞTİR.
  2. Bu araç ilk çalıştığında tarayıcı açılıp yeni scope onayı ister; token
     secrets/youtube_analytics_token.json'a yazılır (upload token'ına DOKUNMAZ).

Kullanım:
  python tools/pull_analytics.py --days 28
  -> output/_brain/analytics.json (ham metrikler) + output/_brain/analytics_guidance.txt
     (beyne enjekte edilen özet). brain_learn.prompt_context() bunu otomatik okur.
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from pipeline.utils.paths import OUTPUT_DIR  # noqa: E402

# Analytics + kanal videolarını okumak için gereken scope'lar (upload scope'undan AYRI).
SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

BRAIN_DIR = OUTPUT_DIR / "_brain"
ANALYTICS_JSON = BRAIN_DIR / "analytics.json"
ANALYTICS_GUIDANCE = BRAIN_DIR / "analytics_guidance.txt"


def _get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret_file = ROOT / os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "secrets/youtube_client_secret.json")
    # AYRI token dosyası: çalışan upload token'ını (farklı scope) bozmamak için.
    token_file = ROOT / os.environ.get("YOUTUBE_ANALYTICS_TOKEN_FILE", "secrets/youtube_analytics_token.json")
    if not client_secret_file.exists():
        sys.exit(f"OAuth client secret yok: {client_secret_file} (bkz. s09_upload açıklaması)")

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _video_titles(youtube, video_ids):
    """videoId -> title eşlemesi (50'lik gruplar)."""
    titles = {}
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        resp = youtube.videos().list(part="snippet", id=",".join(chunk), maxResults=50).execute()
        for it in resp.get("items", []):
            titles[it["id"]] = it["snippet"]["title"]
    return titles


def pull(days: int = 28, max_results: int = 50) -> dict:
    from googleapiclient.discovery import build

    creds = _get_credentials()
    yta = build("youtubeAnalytics", "v2", credentials=creds)
    youtube = build("youtube", "v3", credentials=creds)

    end = date.today()
    start = end - timedelta(days=days)
    # Video başına temel performans metrikleri. (Not: gösterim/CTR public Analytics API'de
    # sınırlıdır; retention için averageViewPercentage en güçlü sinyaldir.)
    metrics = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained"
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start.isoformat(),
        endDate=end.isoformat(),
        metrics=metrics,
        dimensions="video",
        sort="-views",
        maxResults=max_results,
    ).execute()

    cols = [h["name"] for h in resp.get("columnHeaders", [])]
    rows = resp.get("rows", []) or []
    vids = [r[cols.index("video")] for r in rows]
    titles = _video_titles(youtube, vids) if vids else {}

    videos = []
    for r in rows:
        rec = dict(zip(cols, r))
        vid = rec.get("video")
        videos.append({
            "video_id": vid,
            "title": titles.get(vid, ""),
            "views": rec.get("views", 0),
            "avg_view_pct": round(float(rec.get("averageViewPercentage", 0)), 1),
            "avg_view_sec": round(float(rec.get("averageViewDuration", 0)), 0),
            "minutes_watched": rec.get("estimatedMinutesWatched", 0),
            "likes": rec.get("likes", 0),
            "subs_gained": rec.get("subscribersGained", 0),
        })

    out = {"updated": end.isoformat(), "window_days": days, "count": len(videos), "videos": videos}
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    ANALYTICS_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_guidance(videos)
    print(f"Analytics çekildi: {len(videos)} video ({days} gün) -> {ANALYTICS_JSON}")
    return out


def _write_guidance(videos: list[dict], min_videos: int = 4) -> None:
    """Retention'a (avg_view_pct) göre en iyi/en kötü videoları özetleyip beyne enjekte edilecek
    kısa bir kılavuz yazar. Yeterli veri yoksa (az video) yazmaz -> beyin davranışı değişmez."""
    scored = [v for v in videos if v.get("avg_view_pct")]
    if len(scored) < min_videos:
        log_line = f"(analytics_guidance yazılmadı: yalnızca {len(scored)} ölçülebilir video, >= {min_videos} gerekli)"
        print(log_line)
        return
    scored.sort(key=lambda v: v["avg_view_pct"], reverse=True)
    top = scored[:3]
    bottom = scored[-3:]

    def _line(v):
        return f"\"{v['title'][:70]}\" (izlenme oranı %{v['avg_view_pct']}, {v['views']} izlenme)"

    text = (
        "REAL PERFORMANCE DATA from THIS channel (last window) — optimize toward what actually "
        "retained viewers:\n"
        "- BEST retained (do MORE of this angle/topic/hook style):\n"
        + "\n".join(f"  · {_line(v)}" for v in top)
        + "\n- WORST retained (avoid this angle/pacing):\n"
        + "\n".join(f"  · {_line(v)}" for v in bottom)
        + "\nInfer WHY the best held attention (hook, topic, pacing) and lean into it; do not copy titles."
    )
    ANALYTICS_GUIDANCE.write_text(text, encoding="utf-8")
    print(f"Beyin kılavuzu güncellendi -> {ANALYTICS_GUIDANCE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=28)
    ap.add_argument("--max", type=int, default=50)
    args = ap.parse_args()
    try:
        pull(days=args.days, max_results=args.max)
    except Exception as e:
        sys.exit(
            f"Analytics çekilemedi: {type(e).__name__}: {e}\n"
            "En olası neden: 'yt-analytics.readonly' scope'u yok (yeniden yetkilendir) veya "
            "YouTube Analytics API etkin değil (Google Cloud Console)."
        )


if __name__ == "__main__":
    main()
