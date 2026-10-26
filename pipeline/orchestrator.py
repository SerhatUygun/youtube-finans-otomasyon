"""Uçtan uca pipeline çalıştırıcı.

topics.json kuyruğundaki 'pending' konuları sırayla işler:
  01 script -> 02 tts -> 03 avatar -> 04 visuals -> 06 subtitles -> 07 edit -> 09 youtube upload

Her aşama kendi ağır modelini (varsa) yükler; VRAM paylaşımlı ve sıralı kullanılır.
Güvenlik: YouTube'a yükleme VARSAYILAN OLARAK KAPALI — video output/ klasöründe insan
onayı bekler. Otomatik yüklemeyi açmak bilinçli bir tercih olmalı (--auto-upload).

Kullanım:
    python -m pipeline.orchestrator                     # tüm 'pending' konuları işler, yüklemez
    python -m pipeline.orchestrator --topic-id test-001  # tek bir konu
    python -m pipeline.orchestrator --auto-upload        # video hazır olunca YouTube'a da yükle
    python -m pipeline.orchestrator --auto-drive-upload  # video hazır olunca Drive'a da yükle
"""
import argparse
import json
import traceback
from pathlib import Path

from dotenv import load_dotenv

from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, make_job_id
from pipeline.utils.paths import slugify as _slugify  # geriye uyumluluk (app.py bunu import ediyor)

log = get_logger("orchestrator")


def _load_topics(topics_file):
    return json.loads(topics_file.read_text(encoding="utf-8"))


def _save_topics(topics_file, topics):
    topics_file.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")


def _free_vram(where: str = ""):
    """Aşamalar arası bellek temizliği (16GB VRAM darboğazı için). gc.collect() +
    torch.cuda.empty_cache() — bir sonraki GPU aşaması temiz başlasın, ardışık
    yüklemelerde spill/OOM olmasın. Alt-süreç aşamaları (s02/s03/s05) zaten kendi
    venv'lerinde çalışıp çıkışta boşaltır; bu, ana-süreç (s04 SDXL) artığını süpürür."""
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
            if where:
                free, total = torch.cuda.mem_get_info()
                log.info(f"VRAM temizlendi ({where}): {free / 1e9:.1f}/{total / 1e9:.1f} GB boş")
    except Exception:
        pass


def _run_stages_from_tts(job_id: str, skip_upload: bool, drive_upload: bool = False) -> dict:
    """script.json (+metadata.json) HAZIR olan bir iş için s02→s07 aşamalarını çalıştırır.
    Hem otomatik (s01 Claude) hem manuel (kullanıcı metni) akışı bunu paylaşır."""
    from pipeline.stages import (
        s02_tts, s03_avatar, s04_visuals, s05_video_broll, s05b_motion_graphics,
        s06_subtitles, s07_edit,
    )
    from pipeline.utils.config import load_config as _load_config
    from pipeline.utils.paths import ROOT as _ROOT

    s02_tts.run(job_id)
    _free_vram("s02 sonrası")

    avatar_cfg = _load_config().get("avatar", {})
    if not avatar_cfg.get("enabled", True):
        log.info("avatar.enabled=false, aşama atlanıyor")
    elif (_ROOT / avatar_cfg.get("photo", "")).exists() and (_ROOT / avatar_cfg.get("venv_python", "")).exists():
        try:
            s03_avatar.run(job_id)
        except Exception as e:
            log.error(f"Avatar aşaması başarısız oldu, avatarsız devam ediliyor: {e}")
    else:
        log.info("Avatar fotoğrafı/venv bulunamadı, avatar aşaması atlanıyor")

    _free_vram("s03 sonrası")
    try:
        s04_visuals.run(job_id)
    except Exception as e:
        log.error(f"Görsel üretimi başarısız oldu, sabit görsellere düşülüyor: {e}")

    # KRİTİK: s04 (SDXL, ana-süreç) VRAM'i s05 (b-roll, ayrı süreç, tüm VRAM'e ihtiyaç
    # duyar) başlamadan ÖNCE boşaltılmalı — yoksa 16GB'de spill/OOM.
    _free_vram("s04 sonrası")
    try:
        s05_video_broll.run(job_id)
    except Exception as e:
        log.error(f"Video b-roll aşaması başarısız oldu, statik görsellere düşülüyor: {e}")

    # Animasyonlu piyasa grafiği (Remotion, opsiyonel/additive) — GPU'suz, s05_video_broll'un
    # VRAM baskısından bağımsız; kapalıysa veya başarısız olursa statik grafik PNG korunur.
    try:
        s05b_motion_graphics.run(job_id)
    except Exception as e:
        log.error(f"Animasyonlu grafik aşaması başarısız oldu, statik grafik korunuyor: {e}")

    _free_vram("s05 sonrası")
    s06_subtitles.run(job_id)
    s07_edit.run(job_id)

    # Post-processing: MMAudio ve Upscale (eğer aktiflerse)
    cfg = _load_config()
    enh = cfg.get("enhancements", {})
    video_path = _ROOT / "output" / job_id / "video.mp4"
    
    # NOT: sys.executable/mutlak yol kullanılır -> orchestrator hangi cwd'den çağrılırsa
    # çağrılsın (Task Scheduler vb.) doğru python/script bulunur (eskiden ".venv\\..." gibi
    # cwd'ye göreli yollardı, farklı cwd'den sessizce hiçbir şey yapmadan geçiyordu).
    if enh.get("mmaudio", {}).get("enabled"):
        import shutil
        import subprocess
        import sys
        log.info("MMAudio çalıştırılıyor...")
        out_audio = str(video_path).replace(".mp4", "_audio.mp4")
        proc = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "run_mmaudio.py"),
             "--video", str(video_path), "--out", out_audio],
            cwd=str(_ROOT), check=False, capture_output=True, text=True,
        )
        if Path(out_audio).exists():
            shutil.move(out_audio, str(video_path))
        else:
            log.warning(f"MMAudio çıktı üretmedi (kod {proc.returncode}): {(proc.stderr or '')[-800:]}")

    if enh.get("upscale", {}).get("enabled"):
        import shutil
        import subprocess
        import sys
        log.info("Upscale (Real-ESRGAN) çalıştırılıyor...")
        out_upscaled = str(video_path).replace(".mp4", "_upscaled.mp4")
        proc = subprocess.run(
            [sys.executable, str(_ROOT / "scripts" / "run_upscale.py"),
             "--in", str(video_path), "--out", out_upscaled, "--scale", "2"],
            cwd=str(_ROOT), check=False, capture_output=True, text=True,
        )
        if Path(out_upscaled).exists():
            shutil.move(out_upscaled, str(video_path))
        else:
            log.warning(f"Upscale çıktı üretmedi (kod {proc.returncode}): {(proc.stderr or '')[-800:]}")

    result = {"job_id": job_id}

    # Otomatik Shorts Üretimi (eğer aktifse)
    shorts_cfg = cfg.get("shorts", {})
    if shorts_cfg.get("auto_generate", True) and video_path.exists():
        try:
            from tools import make_shorts
            dur = float(shorts_cfg.get("target_duration", 45))
            log.info(f"Dikey Shorts üretiliyor ({dur}s)...")
            short_file = make_shorts.generate_short_for_job(job_id, duration=dur)
            if short_file:
                log.info(f"Shorts başarıyla oluşturuldu: {short_file}")
                result["short_video"] = short_file
        except Exception as e:
            log.warning(f"Shorts üretimi başarısız oldu (ana video etkilenmedi): {e}")

    if skip_upload:
        log.info("--skip-upload: YouTube yüklemesi atlandı, video output klasöründe.")
    else:
        from pipeline.stages import s09_upload
        result["upload"] = s09_upload.run(job_id)

    # 17 Eyl: kullanıcı isteği -- tam otomatik Drive yüklemesi. config.yaml drive.enabled: true
    # ise --auto-drive-upload bayrağı verilmese bile HER işten sonra otomatik tetiklenir
    # (mmaudio/upscale enhancements ile aynı "config zaten açıksa CLI bayrağına gerek yok"
    # deseni). Bayrak yine de tek seferlik zorlamak için kullanılabilir.
    if drive_upload or cfg.get("drive", {}).get("enabled", False):
        from pipeline.stages import s10_drive_upload
        try:
            result["drive_upload"] = s10_drive_upload.run(job_id)
        except Exception as e:
            log.error(f"Drive yüklemesi başarısız oldu (video yerelde duruyor): {e}")

    log.info(f"=== İş tamamlandı: {job_id} ===")
    return result


def process_existing_job(job_id: str, skip_upload: bool = True, drive_upload: bool = False) -> dict:
    """s01'i ATLAR — script.json'ı önceden yazılmış (manuel metin) işler için."""
    from pipeline.utils.logging import attach_job_log_file
    from pipeline.utils.paths import job_path as _job_path
    attach_job_log_file(job_id)
    if not _job_path(job_id, "script.json").exists():
        raise RuntimeError(f"script.json bulunamadı, manuel iş çalıştırılamaz: {job_id}")
    log.info(f"=== Manuel iş başlıyor (s01 atlanıyor): {job_id} ===")
    return _run_stages_from_tts(job_id, skip_upload, drive_upload)


def process_topic(entry: dict, skip_upload: bool = True, drive_upload: bool = False) -> dict:
    from pipeline.stages import s01_script
    from pipeline.utils.config import load_config as _load_config  # noqa: F401
    from pipeline.utils.logging import attach_job_log_file
    from pipeline.utils.paths import ROOT as _ROOT  # noqa: F401

    topic = entry["topic"]
    job_id = make_job_id(topic)
    attach_job_log_file(job_id)
    log.info(f"=== İş başlıyor: {job_id} ===")
    log.info(f"Konu: {topic}")

    s01_script.run(job_id, topic)
    return _run_stages_from_tts(job_id, skip_upload, drive_upload)


def main():
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="YouTube içerik pipeline'ı")
    parser.add_argument("--topic-id", help="Sadece bu id'ye sahip konuyu işle")
    parser.add_argument(
        "--existing-job-id",
        help="script.json'ı hazır (manuel metin) bir işi s01'i atlayarak s02→s07 çalıştır",
    )
    parser.add_argument(
        "--auto-upload", action="store_true",
        help="Video hazır olunca insan onayı beklemeden YouTube'a otomatik yükle "
             "(varsayılan: yüklenmez, video output/ klasöründe bırakılır)",
    )
    parser.add_argument(
        "--auto-drive-upload", action="store_true",
        help="Video hazır olunca Google Drive'a da yükle (--auto-upload'dan BAĞIMSIZ bir "
             "bayrak; varsayılan: yüklenmez). Bkz. config.yaml drive: bloğu.",
    )
    args = parser.parse_args()

    if args.existing_job_id:
        try:
            process_existing_job(args.existing_job_id, skip_upload=not args.auto_upload,
                                  drive_upload=args.auto_drive_upload)
        except Exception:
            log.error(traceback.format_exc())
        return

    cfg = load_config()
    topics_file = ROOT / cfg["paths"]["topics_file"]
    topics = _load_topics(topics_file)

    pending = [t for t in topics if t.get("status") == "pending"]
    if args.topic_id:
        pending = [t for t in pending if t.get("id") == args.topic_id]
        if not pending:
            log.error(f"'{args.topic_id}' id'li bekleyen konu bulunamadı")
            return

    if not pending:
        log.info("İşlenecek bekleyen konu yok.")
        return

    for entry in pending:
        entry["status"] = "processing"
        _save_topics(topics_file, topics)
        try:
            result = process_topic(entry, skip_upload=not args.auto_upload,
                                    drive_upload=args.auto_drive_upload)
            entry["status"] = "done"
            entry["result"] = result
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)
            log.error(f"Konu başarısız oldu: {entry['topic']}")
            log.error(traceback.format_exc())
        finally:
            _save_topics(topics_file, topics)


if __name__ == "__main__":
    main()
