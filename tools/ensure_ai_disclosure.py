"""Son yüklenen videolarda YouTube "yapay/değiştirilmiş içerik" beyanını (containsSyntheticMedia) garanti eder.

30 Eyl: kanalın 47 AI sesli videosunda beyan kapalıydı (Studio'da yayınlarken soru varsayılan "Hayır" geliyor; eski publish()
de alanı sıfırlıyordu). Kullanıcı onayıyla hepsi açıldı. Bu betik günlük hatta her koşuda son N gündeki yüklemeleri kontrol
eder, kapalı olanı açar (yalnız AI dönemi: 2025-12-01 sonrası; canlı yayın kayıtları hariç).

  python tools/ensure_ai_disclosure.py [gün=10]
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

AI_ERA = "2025-12-01"
WRITABLE = {"privacyStatus", "embeddable", "license", "publicStatsViewable", "publishAt", "selfDeclaredMadeForKids", "containsSyntheticMedia"}


def main(days: int = 2, log=print) -> list[str]:
    from googleapiclient.discovery import build
    from pipeline.stages import s09_upload
    yt = build("youtube", "v3", credentials=s09_upload._get_credentials(), cache_discovery=False)
    up = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items = yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=25).execute()["items"]
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    ids = [i["contentDetails"]["videoId"] for i in items if i["contentDetails"].get("videoPublishedAt", "9") >= max(since, AI_ERA)]
    fixed = []
    if not ids:
        return fixed
    for v in yt.videos().list(part="status,contentDetails,snippet", id=",".join(ids)).execute()["items"]:
        # NOT (30 Eyl, doğrulandı): API containsSyntheticMedia'yı OKUMADA HİÇ DÖNDÜRMÜYOR (yalnız yazılabilir) -> mevcut
        # durum bilinemez; son günlerin yüklemelerine idempotent olarak "açık" yazılır. Gerçek durum yalnız Studio'da görünür.
        if v["contentDetails"].get("duration") == "P0D":
            continue
        st = {k: x for k, x in v["status"].items() if k in WRITABLE}
        st["containsSyntheticMedia"] = True
        yt.videos().update(part="status", body={"id": v["id"], "status": st}).execute()
        fixed.append(v["id"])
        log(f"AI beyanı yazıldı (açık): {v['id']} · {v['snippet']['title'][:60]}")
    return fixed


if __name__ == "__main__":
    print(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2))
