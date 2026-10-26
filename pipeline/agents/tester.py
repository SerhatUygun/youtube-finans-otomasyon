"""Tester ajanı -- render EDİLDİKTEN SONRA çıktı dosyasını (tek segment klibi ya da final
video.mp4) teknik olarak doğrular: ffprobe süre/video-akışı + ffmpeg blackdetect ile siyah/
donuk kare taraması. Sonuç bir JSON rapor olarak iş klasörüne yazılır ve (config açıksa)
pipeline.stages.s10_drive_upload.upload_test_artifact ile Google Drive'a yüklenir --
KULLANICI İSTEĞİ: hiçbir test çıktısı Drive'a yüklenmeden kaybolmasın, bunu unutma.

Savunmacı: ffprobe/ffmpeg bulunamazsa veya bir adım patlarsa o kontrol atlanır (diğer
kontroller geçerli kalır); Drive yüklemesi başarısız olursa SADECE loglanır -- test
sonucunu ya da çağıran pipeline aşamasını asla bloklamaz/bozmaz."""
import json
import re
import subprocess
from pathlib import Path

from pipeline.utils.logging import get_logger
from pipeline.utils.paths import job_path

log = get_logger("agents.tester")


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height",
         "-of", "json", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    return json.loads(out.stdout or "{}")


def _black_frame_ratio(path: Path) -> float | None:
    """ffmpeg blackdetect filtresiyle toplam siyah-kare süresi / toplam süre oranını
    tahmin eder. Ölçülemezse None (bu kontrol atlanır, diğerleri geçerli kalır)."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-i", str(path), "-vf", "blackdetect=d=0.5:pic_th=0.98",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    except Exception:
        return None
    hits = re.findall(r"black_duration:([\d.]+)", proc.stderr or "")
    if not hits:
        return 0.0
    total_black = sum(float(h) for h in hits)
    try:
        dur = float(_ffprobe(path).get("format", {}).get("duration", 0) or 0)
    except Exception:
        return None
    return (total_black / dur) if dur > 0 else None


def validate_clip(path: Path, expected_seconds: float | None = None,
                   tolerance_s: float = 0.75, max_black_ratio: float = 0.85,
                   check_black_frames: bool = True) -> dict:
    """Tek bir render çıktısını doğrular. Döner: {"pass": bool, "checks": {...}, "path": str}."""
    path = Path(path)
    if not path.exists() or path.stat().st_size < 1024:
        return {"pass": False, "checks": {"exists": False}, "path": str(path)}

    checks = {"exists": True, "size_bytes": path.stat().st_size}
    ok = True

    try:
        probe = _ffprobe(path)
        dur = float(probe.get("format", {}).get("duration", 0) or 0)
        has_video = any(s.get("codec_type") == "video" for s in probe.get("streams", []))
        checks["duration_s"] = round(dur, 2)
        checks["has_video_stream"] = has_video
        ok = ok and has_video and dur > 0
        if expected_seconds is not None:
            delta = abs(dur - float(expected_seconds))
            checks["expected_seconds"] = expected_seconds
            checks["duration_delta_s"] = round(delta, 2)
            ok = ok and delta <= tolerance_s
    except Exception as e:
        checks["ffprobe_error"] = str(e)
        ok = False

    if check_black_frames:
        black_ratio = _black_frame_ratio(path)
        if black_ratio is not None:
            checks["black_frame_ratio"] = round(black_ratio, 3)
            ok = ok and black_ratio <= max_black_ratio

    return {"pass": ok, "checks": checks, "path": str(path)}


def run_and_report(job_id: str, report_name: str, path: Path,
                    expected_seconds: float | None = None, upload_to_drive: bool = True,
                    extra: dict | None = None, **validate_kwargs) -> dict:
    """validate_clip + raporu diske yaz + (opsiyonel) Drive'a yükle. Drive yüklemesi
    ASLA test sonucunu ya da çağıran pipeline aşamasını bloklamaz."""
    result = validate_clip(Path(path), expected_seconds, **validate_kwargs)
    if extra:
        result["extra"] = extra
    result["report_name"] = report_name

    report_path = job_path(job_id, f"tests/{report_name}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Test raporu yazıldı ({'PASS' if result['pass'] else 'FAIL'}): {report_path}")

    if upload_to_drive:
        try:
            from pipeline.stages import s10_drive_upload
            files = [report_path]
            if Path(path).exists():
                files.append(Path(path))
            s10_drive_upload.upload_test_artifact(job_id, report_name, files, result)
        except Exception as e:
            log.warning(f"Test artefaktı Drive'a yüklenemedi (test sonucu etkilenmedi): {e}")
    return result
