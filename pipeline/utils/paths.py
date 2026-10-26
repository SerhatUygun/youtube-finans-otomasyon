import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
SECRETS_DIR = ROOT / "secrets"

# 17 Eyl: iş klasörü sadeleştirme -- kullanıcı için asıl "sonuç" olan bu dosyalar kökte
# kalır; script.json/audio.wav/visuals//altyazı kaynağı/log gibi ham-üretim dosyalarının
# HEPSİ _raw/ alt klasörüne gider (bkz. job_path). Klasörü açan biri direkt video/short/
# metadata'yı görsün, üretim artıklarıyla boğulmasın.
_JOB_TOP_LEVEL_FILES = {
    "video.mp4", "short.mp4", "metadata.json",
    "critic.json", "factcheck.json", "upload_result.json", "drive_upload_result.json",
}
_JOB_RAW_SUBDIR = "_raw"

# Türkçe harflerin ASCII'ye düşerken sessizce kaybolmasını önler -- NFKD ayrıştırması
# ı/İ için (aksan içermedikleri için) çalışmıyordu ("altın" -> "altn" gibi kırık slug'lara
# yol açıyordu). Geri kalanlar (ş/ğ/ü/ö/ç) NFKD ile zaten doğru düşüyor, yine de netlik için
# hepsi burada açıkça eşleniyor.
_TR_MAP = str.maketrans({
    "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
    "ü": "u", "Ü": "U", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
})


def slugify(text: str) -> str:
    text = text.translate(_TR_MAP)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:40] or "job"


def make_job_id(text: str) -> str:
    """Okunabilir iş klasörü adı: 2026-09-17_00-10-13-fed-petrol-altin-krizi.
    (Eski format YYYYMMDD-HHMMSS-slug idi -- tire/alt çizgi ile bölünmediği için tek
    bir uzun rakam bloğu gibi görünüyordu.)"""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    return f"{ts}-{slugify(text)}"


def job_dir(job_id: str) -> Path:
    d = OUTPUT_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_raw_dir(job_id: str) -> Path:
    d = job_dir(job_id) / _JOB_RAW_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_path(job_id: str, filename: str) -> Path:
    """İş klasöründeki bir dosyanın yolu. video.mp4/short.mp4/metadata.json/critic.json/
    factcheck.json/upload_result.json kökte kalır (web arayüzü ve kullanıcı bunlara bakar);
    geri kalan HER ŞEY (script.json, audio.wav, subtitles.srt, visuals/, video_broll/,
    segments_timing.json, *_manifest.json, *.log, avatar*, vb.) _raw/ alt klasörüne gider.
    Tüm aşamalar dosya yollarını bu fonksiyon üzerinden aldığı için değişiklik tek noktada.

    Geriye dönük uyumluluk: bu değişiklikten ÖNCE üretilmiş işlerde bu dosyalar hâlâ iş
    klasörünün kökünde duruyor. Kökte zaten varsa (eski iş) oradan okumaya devam edilir;
    yoksa (yeni iş) _raw/ altına yazılır -- eski işlerin web arayüzünde bozulmaması için."""
    top_component = filename.split("/")[0]
    if top_component in _JOB_TOP_LEVEL_FILES:
        return job_dir(job_id) / filename
    legacy_path = job_dir(job_id) / filename
    if legacy_path.exists():
        return legacy_path
    return job_raw_dir(job_id) / filename
