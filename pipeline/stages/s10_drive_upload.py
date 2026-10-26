"""Aşama 10: Google Drive'a bitmiş video yüklemesi (opsiyonel, insan/talep tetiklemeli).

Girdi: output/<job_id>/video.mp4, output/<job_id>/metadata.json
Çıktı: Drive'da "<tarih> — <başlık>" adlı klasör + içine yüklenen video; drive_upload_result.json

s09_upload.py (YouTube) ile AYNI OAuth client'ı (secrets/youtube_client_secret.json) paylaşır
ama AYRI bir token dosyası kullanır (secrets/drive_token.json) -- tools/pull_analytics.py'nin
"çalışan upload token'ını bozma" deseni burada da tekrarlanır. İlk çalıştırmada tarayıcı açılıp
Drive izni istenir (scope: drive.file -- sadece bu uygulamanın oluşturduğu dosyalara erişir).

KAPALI/OTOMATİK-DEĞİL VARSAYILAN: config.yaml drive.enabled=false ve orchestrator'da
--auto-drive-upload verilmeden hiçbir zaman kendiliğinden tetiklenmez (youtube.privacy_status:
private ile aynı "insan onay kapısı" felsefesi) -- web panelden veya CLI'dan elle çağrılır.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("s10_drive_upload")

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_credentials(interactive: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    # Aynı Google Cloud OAuth client (YouTube upload ile paylaşılır -- tek proje, iki scope).
    client_secret_file = ROOT / os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "secrets/youtube_client_secret.json")
    token_file = ROOT / os.environ.get("DRIVE_TOKEN_FILE", "secrets/drive_token.json")

    if not client_secret_file.exists():
        raise RuntimeError(
            f"Google OAuth client secret dosyası bulunamadı: {client_secret_file}\n"
            "Google Cloud Console -> APIs & Services -> Credentials -> OAuth Client ID (Desktop app) "
            "oluşturup indirdiğin JSON'u bu yola kaydet (YouTube yüklemesiyle paylaşılan aynı dosya)."
        )

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not interactive:
                raise RuntimeError("Drive token yok/geçersiz — tools/reauth_google.py drive çalıştır (otomatik koşuda tarayıcı açılmaz)")
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _folder_name(metadata: dict, job_id: str) -> str:
    """'2026-09-17 — Fed Faiz Kararı ve Piyasalara Etkisi' gibi bir Drive klasör adı üretir.
    job_id formatı YYYY-MM-DD_HH-MM-SS-slug (bkz. pipeline/utils/paths.py::make_job_id) --
    ilk 10 karakter tarih. Eski (yeniden biçimlendirmeden önceki) iş klasörleri için tarih
    kısmı garip görünebilir, o durumda sadece başlık kullanılır."""
    date_part = job_id[:10]
    title = (metadata.get("title") or job_id).strip()
    if len(date_part) == 10 and date_part[4] == "-" and date_part[7] == "-":
        name = f"{date_part} — {title}"
    else:
        name = title
    return name[:150]


def _escape_drive_query_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _get_or_create_folder(drive, name: str, parent_id: str | None) -> str:
    """Aynı isimli (ve aynı üst klasördeki) bir Drive klasörü varsa onu kullanır -- tekrar
    tekrar çalıştırıldığında klasör çoğalmaz."""
    safe_name = _escape_drive_query_value(name)
    q = (
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        f"and name='{safe_name}'"
    )
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = drive.files().list(q=q, spaces="drive", fields="files(id,name)", pageSize=1).execute()
    files = res.get("files") or []
    if files:
        return files[0]["id"]

    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    folder = drive.files().create(body=body, fields="id").execute()
    return folder["id"]


def upload_test_artifact(job_id: str, report_name: str, files: list, report: dict) -> dict | None:
    """17 Eyl eklendi -- kullanıcı isteği: Editor/Denetleyici/Tester döngüsünün ürettiği
    HER test raporu (ve varsa test render dosyası) Google Drive'a yüklensin, hiçbiri
    yerelde kaybolmasın. s10 (bitmiş video) ile AYNI OAuth kimlik bilgilerini kullanır
    ama farklı bir klasöre yazar: "<üst klasör>/Tests/<job_id>/<report_name>.*".

    Çağıran taraf (pipeline/agents/tester.py) bu fonksiyonu zaten try/except içinde
    çağırır -- burada patlayan bir hata SADECE üst tarafa loglanıp yutulur, hiçbir
    render/test sonucunu etkilemez. drive.enabled=false ise hemen None döner (istek
    yapılmaz)."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from pipeline.utils.config import load_config

    cfg = (load_config().get("drive") or {})
    if not cfg.get("enabled", False):
        return None

    creds = _get_credentials()
    drive = build("drive", "v3", credentials=creds)

    parent_folder_id = (cfg.get("parent_folder_id") or "").strip() or None
    tests_folder_id = _get_or_create_folder(drive, "Tests", parent_folder_id)
    job_folder_id = _get_or_create_folder(drive, job_id, tests_folder_id)

    uploaded = []
    for f in files:
        f = Path(f)
        if not f.exists():
            continue
        mimetype = "application/json" if f.suffix == ".json" else "video/mp4"
        media = MediaFileUpload(str(f), mimetype=mimetype, resumable=False)
        body = {"name": f"{report_name}_{f.name}", "parents": [job_folder_id]}
        resp = drive.files().create(body=body, media_body=media, fields="id,webViewLink").execute()
        uploaded.append({"name": f.name, "file_id": resp["id"], "web_view_link": resp.get("webViewLink", "")})

    log.info(f"Test artefaktı Drive'a yüklendi (job={job_id}, report={report_name}, "
             f"pass={report.get('pass')}): {len(uploaded)} dosya")
    return {"job_folder_id": job_folder_id, "uploaded": uploaded}


def run(job_id: str) -> dict:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from pipeline.utils.config import load_config

    cfg = (load_config().get("drive") or {})
    video_file = job_path(job_id, "video.mp4")
    metadata_file = job_path(job_id, "metadata.json")
    if not video_file.exists():
        raise RuntimeError(f"Video dosyası bulunamadı: {video_file}")

    metadata = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else {}
    folder_name = _folder_name(metadata, job_id)
    parent_folder_id = (cfg.get("parent_folder_id") or "").strip() or None

    creds = _get_credentials()
    drive = build("drive", "v3", credentials=creds)

    log.info(f"Drive klasörü hazırlanıyor: {folder_name!r}")
    folder_id = _get_or_create_folder(drive, folder_name, parent_folder_id)

    media = MediaFileUpload(str(video_file), resumable=True, mimetype="video/mp4")
    body = {"name": f"{folder_name}.mp4", "parents": [folder_id]}

    log.info(f"Drive'a yükleme başlıyor: {metadata.get('title', job_id)!r}")
    request = drive.files().create(body=body, media_body=media, fields="id,webViewLink")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(f"Yükleniyor: %{int(status.progress() * 100)}")

    web_view_link = response.get("webViewLink", "")
    log.info(f"Drive'a yüklendi: {web_view_link}")

    result_payload = {
        "file_id": response["id"],
        "folder_id": folder_id,
        "folder_name": folder_name,
        "web_view_link": web_view_link,
        "title": metadata.get("title"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    result_file = job_path(job_id, "drive_upload_result.json")
    result_file.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return result_payload


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    print(json.dumps(run(job), ensure_ascii=False, indent=2))
