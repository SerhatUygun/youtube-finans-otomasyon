"""Aşama 09: YouTube taslak yükleme (YouTube Data API v3).

Girdi: output/<job_id>/video.mp4, output/<job_id>/metadata.json
Çıktı: private/unlisted YouTube videosu (yayına alma kararı insanda kalır)

İlk çalıştırmada tarayıcı açılıp Google hesabı ile OAuth onayı istenir;
token secrets/youtube_token.json içine kaydedilir ve sonraki çalıştırmalarda
yeniden kullanılır.

17 Eyl: video yüklendikten sonra iki ek adım (ikisi de best-effort, başarısız olursa
ana yükleme SONUCUNU etkilemez):
  1. tools/make_thumbnail.py ile özel kapak üretilip thumbnails().set() ile atanır.
  2. metadata.json'daki pinned_comment otomatik yorum olarak atılır (Data API'de
     programatik "sabitleme" YOK -- Studio'dan elle sabitlenmesi gerekir).
"""
import json
import os
from datetime import datetime

from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import OUTPUT_DIR, ROOT, job_path

log = get_logger("s09_upload")

# youtube.force-ssl: commentThreads().insert() (sabitlenecek yorum) için gerekli --
# youtube.upload tek başına yeterli değil. Video yükleme ilk kez bu makinede henüz
# doğrulanmadığı için (17 Eyl) scope'u BAŞTAN doğru kapsamda tanımlamak, ilk OAuth
# onayından SONRA scope genişletip yeniden yetkilendirme ihtiyacını önler.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret_file = ROOT / os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "secrets/youtube_client_secret.json")
    token_file = ROOT / os.environ.get("YOUTUBE_TOKEN_FILE", "secrets/youtube_token.json")

    if not client_secret_file.exists():
        raise RuntimeError(
            f"YouTube OAuth client secret dosyası bulunamadı: {client_secret_file}\n"
            "Google Cloud Console -> APIs & Services -> Credentials -> OAuth Client ID (Desktop app) "
            "oluşturup indirdiğin JSON'u bu yola kaydet."
        )

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.environ.get("SP_UNATTENDED"):
            # 2 Eki: otomatik günlük koşuda tarayıcı açılıp sonsuza dek beklenmesin -> net hata
            raise RuntimeError("YouTube yetkisi düşmüş (token geçersiz). Elle yenile: python tools/reauth_google.py")
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _uploads_today() -> int:
    """Bugün (yerel tarih) yapılmış YouTube yüklemelerini output/*/upload_result.json'dan sayar.
    uploaded_at alanı yoksa (24 Eyl öncesi kayıtlar) dosyanın değişme tarihine bakılır."""
    today = datetime.now().date()
    count = 0
    for f in OUTPUT_DIR.glob("*/upload_result.json"):
        try:
            stamp = json.loads(f.read_text(encoding="utf-8")).get("uploaded_at")
            day = datetime.fromisoformat(stamp).date() if stamp else datetime.fromtimestamp(f.stat().st_mtime).date()
        except Exception:
            day = datetime.fromtimestamp(f.stat().st_mtime).date()
        if day == today:
            count += 1
    return count


PENDING_COMMENTS = OUTPUT_DIR / "_brain" / "pending_comments.json"


def queue_comment(video_id: str, text: str) -> None:
    """9 Eki: yayın öncesi atılamayan yorumu sıraya ekler (tools/post_pending_comments.py saatlik dener)."""
    try:
        q = json.loads(PENDING_COMMENTS.read_text(encoding="utf-8")) if PENDING_COMMENTS.exists() else []
        if not any(x["video_id"] == video_id for x in q):
            q.append({"video_id": video_id, "text": text, "queued_at": datetime.now().isoformat(timespec="seconds")})
        PENDING_COMMENTS.parent.mkdir(parents=True, exist_ok=True)
        PENDING_COMMENTS.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning(f"Yorum sıraya alınamadı: {e}")


def _ensure_playlist(youtube, title: str, description: str = "") -> str:
    """Kanalda bu adla oynatma listesi varsa id'sini döndürür, yoksa herkese açık oluşturur."""
    req = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
    while req is not None:
        res = req.execute()
        for pl in res.get("items", []):
            if pl["snippet"]["title"] == title:
                return pl["id"]
        req = youtube.playlists().list_next(req, res)
    pl = youtube.playlists().insert(part="snippet,status", body={
        "snippet": {"title": title, "description": description, "defaultLanguage": "tr"},
        "status": {"privacyStatus": "public"}}).execute()
    return pl["id"]


def publish_time(spec: str, now: datetime | None = None, min_lead_min: int = 25) -> datetime:
    """'15:00' (bugün) ya da '+1d 10:00' (yarın) -> yerel saat. Geçmişte/çok yakınsa şimdi+min_lead_min."""
    from datetime import timedelta
    now = now or datetime.now()
    days = 0
    spec = spec.strip()
    if spec.startswith("+"):
        d, spec = spec[1:].split("d", 1)
        days = int(d)
    hh, mm = (int(x) for x in spec.strip().split(":"))
    t = (now + timedelta(days=days)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    if t < now + timedelta(minutes=min_lead_min):
        t = (now + timedelta(minutes=min_lead_min + 5)).replace(second=0, microsecond=0)
    return t


def _rfc3339(t: datetime) -> str:
    return t.astimezone().isoformat(timespec="seconds")  # yerel ofsetli (TR +03:00); YouTube kabul eder


def run(job_id: str, publish_at: datetime | None = None) -> dict:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    cfg = load_config()["youtube"]
    video_file = job_path(job_id, "video.mp4")
    metadata_file = job_path(job_id, "metadata.json")
    if not video_file.exists():
        raise RuntimeError(f"Video dosyası bulunamadı: {video_file}")

    # 24 Eyl: GÜNLÜK YÜKLEME SINIRI. YouTube "inauthentic content" (Tem 2025) politikası
    # seri üretilmiş/tekrarlayan içeriği para kazanmaya uygun saymıyor; zamanlanmış Shorts +
    # otomatik döngü aynı gün sınırsız yükleme yapabiliyordu. Sınır aşılınca yükleme HATA
    # VERMEDEN atlanır (video output klasöründe kalır) ve upload_result.json YAZILMAZ --
    # web paneli o dosyanın varlığını "yüklendi" olarak okuyor. 0 = sınırsız.
    max_per_day = int(cfg.get("max_uploads_per_day", 0) or 0)
    if max_per_day > 0:
        done_today = _uploads_today()
        if done_today >= max_per_day:
            log.warning(
                f"Günlük yükleme sınırı doldu ({done_today}/{max_per_day}); {job_id} YouTube'a "
                "yüklenmedi, video output klasöründe duruyor."
            )
            return {"skipped": True, "reason": "max_uploads_per_day", "uploads_today": done_today}

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))

    # 24 Eyl: require_manual_approval açıksa config'te public/unlisted yazsa bile video
    # private yüklenir; yayına alma yalnızca publish() (web panel 'Onay Bekleyenler') ile olur.
    privacy_status = cfg.get("privacy_status", "private")
    if cfg.get("require_manual_approval", False) and privacy_status != "private":
        log.info(f"require_manual_approval açık: privacy_status {privacy_status!r} yerine 'private' kullanılıyor.")
        privacy_status = "private"

    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": metadata["title"][:100],
            "description": metadata["description"],
            "tags": metadata.get("tags", []),
            "categoryId": cfg.get("category_id", "27"),
            "defaultLanguage": cfg.get("default_language", "tr"),
            "defaultAudioLanguage": cfg.get("default_language", "tr"),
        },
        "status": {
            "privacyStatus": privacy_status,
            # Bilinçli konumlandırma kararı: içerik %100 aile dostu ama "çocuklara
            # yönelik" (made for kids / COPPA) HEDEFLENMİYOR — genel izleyici.
            # s01 SYSTEM_PROMPT da metadata'da çocuk hedefli etiket kullanmaz.
            "selfDeclaredMadeForKids": False,
            # Şeffaf AI beyanı ("How this content was made"): anlatım TTS, görseller
            # ve video AI üretimi. İçerik stilize/karikatür olsa da ses gerçek bir
            # kişinin klonu olduğu için beyan güvenli tarafta tutuluyor (YouTube
            # inauthentic content politikası, Tem 2025 + Data API containsSyntheticMedia).
            "containsSyntheticMedia": cfg.get("contains_synthetic_media", True),
        },
    }
    # 2 Eki: otomatik yayın -> private + publishAt: YouTube belirtilen saatte kendisi herkese açar.
    # Yükleme ile yayın arasındaki sürede kanal sahibi Studio'dan durdurabilir (zamanlamayı kaldır).
    if publish_at:
        privacy_status = "private"
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = _rfc3339(publish_at)

    media = MediaFileUpload(str(video_file), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    log.info(f"Yükleme başlıyor: {metadata['title']!r} ({privacy_status})")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(f"Yükleniyor: %{int(status.progress() * 100)}")

    video_id = response["id"]
    video_url = f"https://youtu.be/{video_id}"
    log.info(f"Yüklendi: {video_url}" + (f" · yayın {publish_at:%d.%m %H:%M}" if publish_at else " (private)"))

    # 17 Eyl eklendi: özel kapak (tools/make_thumbnail.py) üretilip videoya set edilir --
    # varsayılan otomatik-seçilen YouTube kapağı genelde düşük CTR'li olur. Kapak üretimi/
    # yüklemesi BAŞARISIZ olursa (PIL/font eksik, thumbnails.set izin hatası vb.) ana yükleme
    # SONUCUNU etkilemez -- video zaten yüklendi, kapak olmadan da taslak insan onayını bekler.
    thumbnail_set = False
    try:
        from tools import make_thumbnail
        thumb_path = make_thumbnail.make(job_id, None, None)
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(str(thumb_path), mimetype="image/jpeg"),
        ).execute()
        thumbnail_set = True
        log.info("Özel kapak set edildi.")
    except Exception as e:
        log.warning(f"Özel kapak üretilemedi/set edilemedi (video yine de yüklendi): {e}")

    # 17 Eyl eklendi: metadata.json'daki pinned_comment şimdiye kadar sadece web panelinde
    # "Kopyala" butonuyla gösterilip elle yapıştırılıyordu -- artık otomatik yorum olarak
    # atılıyor. NOT: YouTube Data API v3'te bir yorumu "sabitlemek" (pin) programatik olarak
    # MÜMKÜN DEĞİL (Studio arayüzüne özel) -- bu yüzden yorum atılır ama sabitleme hâlâ elle
    # (YouTube Studio'dan) yapılmalı. Yine de elle yazma adımını ortadan kaldırır.
    comment_posted = False
    pinned_comment = (metadata.get("pinned_comment") or "").strip()
    if pinned_comment:
        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={"snippet": {"videoId": video_id, "topLevelComment": {
                    "snippet": {"textOriginal": pinned_comment}}}},
            ).execute()
            comment_posted = True
            log.info("Yorum atıldı (YouTube Studio'dan elle sabitlenmesi gerekir).")
        except Exception as e:
            # 9 Eki: gizli/zamanlanmış videoda yorumlar kapalı ("disabled comments") -> yayına girince tools/post_pending_comments.py atar
            queue_comment(video_id, pinned_comment)
            log.warning(f"Yorum şimdi atılamadı, yayın sonrası sıraya alındı: {str(e)[:120]}")

    # 30 Eyl (sadakat araştırması): her video seri oynatma listesine eklenir -> bitince sıradaki otomatik oynar
    # (oturum süresi = en güçlü büyüme sinyallerinden). Liste yoksa oluşturulur.
    playlist_id = None
    pl_title = cfg.get("playlist_title")
    if pl_title:
        try:
            playlist_id = _ensure_playlist(youtube, pl_title, cfg.get("playlist_description", ""))
            youtube.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}, "position": 0}}).execute()
            log.info(f"Oynatma listesine eklendi: {pl_title}")
        except Exception as e:
            log.warning(f"Oynatma listesine eklenemedi: {e}")

    result_payload = {
        "video_id": video_id,
        "playlist_id": playlist_id,
        "url": video_url,
        "title": metadata.get("title"),
        "pinned_comment": metadata.get("pinned_comment"),
        "comment_posted": comment_posted,
        "privacy_status": privacy_status,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "contains_synthetic_media": cfg.get("contains_synthetic_media", True),
        "thumbnail_set": thumbnail_set,
        "publish_at": publish_at.isoformat(timespec="minutes") if publish_at else None,
    }
    result_file = job_path(job_id, "upload_result.json")
    result_file.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return result_payload


def upload_short(job_id: str, idx: int, title: str, description: str, tags: list[str], publish_at: datetime | None,
                 long_url: str | None = None) -> dict:
    """2 Eki: günlük Shorts (reel_N.mp4) yüklemesi. Kapak reel karesinden üretilip set edilir (6 Eki), açıklamada uzun videoya köprü olur."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    cfg = load_config()["youtube"]
    f = job_path(job_id, f"reel_{idx}.mp4")
    if not f.exists():
        raise RuntimeError(f"Shorts dosyası yok: {f}")
    title = title.strip()
    if "#shorts" not in title.lower():
        title = (title[:91] + " #Shorts") if len(title) > 91 else title + " #Shorts"
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": cfg.get("contains_synthetic_media", True)}
    if publish_at:
        status["publishAt"] = _rfc3339(publish_at)
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:25],
                        "categoryId": cfg.get("category_id", "27"), "defaultLanguage": cfg.get("default_language", "tr"),
                        "defaultAudioLanguage": cfg.get("default_language", "tr")},  # 9 Eki: ses dili (arama/altyazı eşleşmesi)
            "status": status}
    yt = build("youtube", "v3", credentials=_get_credentials())
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(f), chunksize=-1, resumable=True, mimetype="video/mp4"))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    # 6 Eki: Shorts'a da özel kapak (kanal sayfası/arama/önerilenlerde görünür). Hata yüklemeyi bozmaz.
    thumbnail_set = False
    try:
        from tools import make_short_thumb
        tp = make_short_thumb.make(job_id, idx, title)
        yt.thumbnails().set(videoId=resp["id"], media_body=MediaFileUpload(str(tp), mimetype="image/jpeg")).execute()
        thumbnail_set = True
        log.info(f"Shorts {idx} kapağı set edildi.")
    except Exception as e:  # noqa: BLE001
        log.warning(f"Shorts {idx} kapağı set edilemedi (video yine de yüklendi): {e}")
    # 9 Eki: Shorts oynatma listesi (kanal sayfasında seri rafı) + uzun videoya köprü yorumu.
    # "İlgili video" (Shorts üstündeki uzun video bağlantısı) Data API'de YOK -> Studio'dan elle / tarayıcı otomasyonu.
    try:
        st = cfg.get("shorts_playlist_title")
        if st:
            yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": _ensure_playlist(yt, st, cfg.get("shorts_playlist_description", "")),
                                                                        "resourceId": {"kind": "youtube#video", "videoId": resp["id"]}, "position": 0}}).execute()
    except Exception as e:  # noqa: BLE001
        log.warning(f"Shorts {idx} oynatma listesine eklenemedi: {e}")
    comment_posted = False
    if long_url:
        try:
            yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": resp["id"], "topLevelComment": {"snippet": {
                "textOriginal": f"Rakamların tamamı ve seviyeler uzun analizde 👉 {long_url}"}}}}).execute()
            comment_posted = True
        except Exception as e:  # noqa: BLE001
            queue_comment(resp["id"], f"Rakamların tamamı ve seviyeler uzun analizde 👉 {long_url}")
            log.warning(f"Shorts {idx} yorumu yayın sonrası sıraya alındı: {str(e)[:120]}")
    out = {"video_id": resp["id"], "url": f"https://youtube.com/shorts/{resp['id']}", "title": title, "thumbnail_set": thumbnail_set,
           "comment_posted": comment_posted,
           "publish_at": publish_at.isoformat(timespec="minutes") if publish_at else None,
           "uploaded_at": datetime.now().isoformat(timespec="seconds")}
    job_path(job_id, f"reel_{idx}_upload.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Shorts {idx} yüklendi: {out['url']}" + (f" · yayın {publish_at:%d.%m %H:%M}" if publish_at else ""))
    return out


def publish(job_id: str) -> dict:
    """Zaten yüklenmiş bir private/unlisted taslağı public'e çeker -- yarı-otomatik
    onay akışının insan-onayı adımı (bkz. web panel 'Onay Bekleyenler'). upload_result.json'da
    kaydedilmiş video_id kullanılır, yeniden yükleme YAPILMAZ (videoUpdate, tek alan)."""
    from googleapiclient.discovery import build

    upload_result_file = job_path(job_id, "upload_result.json")
    if not upload_result_file.exists():
        raise RuntimeError(f"Bu iş henüz YouTube'a yüklenmemiş: {job_id}")
    upload_result = json.loads(upload_result_file.read_text(encoding="utf-8"))
    video_id = upload_result["video_id"]

    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    # 30 Eyl HATASI: yalnız privacyStatus gönderilince YouTube diğer status alanlarını varsayılana döndürüyor ->
    # containsSyntheticMedia (AI beyanı) SİLİNİYORDU. Mevcut yazılabilir alanlar korunur, beyan zorla açık kalır.
    cur = youtube.videos().list(part="status", id=video_id).execute()["items"][0]["status"]
    writable = {"privacyStatus", "embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia"}
    status = {k: v for k, v in cur.items() if k in writable}
    status.update(privacyStatus="public", containsSyntheticMedia=load_config()["youtube"].get("contains_synthetic_media", True))
    youtube.videos().update(part="status", body={"id": video_id, "status": status}).execute()

    upload_result["privacy_status"] = "public"
    upload_result_file.write_text(json.dumps(upload_result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Video public'e alındı: {upload_result.get('url')}")
    return upload_result


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
