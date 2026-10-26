"""Google yetkilerini yeniler (tarayıcı onayı gerekir; bilgisayar başında çalıştır).

  1) YouTube yükleme + yorum (youtube.upload + youtube.force-ssl) -> secrets/youtube_token.json
     Eski token yalnız upload izniyle alınmıştı: sabit yorum 403 veriyordu.
  2) YouTube Analytics (yt-analytics.readonly + youtube.readonly) -> secrets/youtube_analytics_token.json
  3) Google Drive (drive.file) -> secrets/drive_token.json   (invalid_grant: süresi dolmuş)

Her adımda tarayıcı açılır; AYNI kanal hesabıyla giriş yap, izinleri onayla. Eski token .bak olarak saklanır.
  python tools/reauth_google.py            # üçü
  python tools/reauth_google.py drive      # yalnız biri (youtube | analytics | drive)
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _backup(p: Path):
    if p.exists():
        p.rename(p.with_name(f"{p.name}.bak_{datetime.now():%Y%m%d%H%M}"))


def youtube():
    from googleapiclient.discovery import build
    from pipeline.stages import s09_upload
    _backup(ROOT / "secrets" / "youtube_token.json")
    yt = build("youtube", "v3", credentials=s09_upload._get_credentials(), cache_discovery=False)
    ch = yt.channels().list(part="snippet", mine=True).execute()["items"][0]["snippet"]["title"]
    return f"kanal: {ch} (yükleme + yorum izni)"


def analytics():
    from googleapiclient.discovery import build
    from tools import pull_analytics
    _backup(ROOT / "secrets" / "youtube_analytics_token.json")
    creds = pull_analytics._get_credentials()
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    r = ya.reports().query(ids="channel==MINE", startDate="2026-09-01", endDate=datetime.now().strftime("%Y-%m-%d"), metrics="views").execute()
    return f"analitik OK (Eylül izlenme: {r.get('rows', [[0]])[0][0]})"


def drive():
    from googleapiclient.discovery import build
    from pipeline.stages import s10_drive_upload
    _backup(ROOT / "secrets" / "drive_token.json")
    d = build("drive", "v3", credentials=s10_drive_upload._get_credentials(), cache_discovery=False)
    return f"drive OK ({d.about().get(fields='user(emailAddress)').execute()['user']['emailAddress']})"


if __name__ == "__main__":
    steps = {"youtube": youtube, "analytics": analytics, "drive": drive}
    for name in (sys.argv[1:] or list(steps)):
        print(f"== {name}: tarayıcıda onay bekleniyor…", flush=True)
        try:
            print(f"   ✓ {steps[name]()}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ {name}: {e}", flush=True)
