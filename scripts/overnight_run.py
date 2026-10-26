"""Gece boyu birden çok işi SIRAYLA, oturumdan bağımsız çalıştırır.

scripts/overnight_jobs.json içindeki job_id listesini okur ve her biri için (video.mp4
yoksa) pipeline'ı s02→s07 çalıştırır (script.json önceden yazılmış olmalı — beyin/manuel
üretim). VRAM sıralı kullanıldığı için işler ard arda işlenir. Tüm çıktı
output/_logs/overnight.log'a yazılır.

Detached başlatmak için (oturum kapansa da devam eder):
    powershell Start-Process -WindowStyle Hidden -FilePath ".venv\\Scripts\\python.exe" \
        -ArgumentList "scripts/overnight_run.py"
"""
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.orchestrator import process_existing_job  # noqa: E402
from pipeline.utils.paths import OUTPUT_DIR  # noqa: E402

JOBS_FILE = ROOT / "scripts" / "overnight_jobs.json"
LOG = OUTPUT_DIR / "_logs" / "overnight.log"


def _log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


def main():
    if not JOBS_FILE.exists():
        _log(f"HATA: {JOBS_FILE} yok")
        return
    job_ids = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    _log(f"=== Gece toplu üretim başlıyor: {len(job_ids)} iş ===")

    for i, job_id in enumerate(job_ids, 1):
        d = OUTPUT_DIR / job_id
        if (d / "video.mp4").exists():
            _log(f"[{i}/{len(job_ids)}] {job_id} zaten tamam (video.mp4 var), atlanıyor")
            continue
        if not (d / "script.json").exists():
            _log(f"[{i}/{len(job_ids)}] {job_id} script.json yok, atlanıyor")
            continue
        _log(f"[{i}/{len(job_ids)}] {job_id} başlıyor...")
        try:
            process_existing_job(job_id, skip_upload=True)
            ok = (d / "video.mp4").exists()
            _log(f"[{i}/{len(job_ids)}] {job_id} bitti (video.mp4 {'VAR' if ok else 'YOK!'})")
        except Exception as e:
            _log(f"[{i}/{len(job_ids)}] {job_id} HATA: {e}")
            _log(traceback.format_exc())

    _log("=== Gece toplu üretim tamamlandı ===")


if __name__ == "__main__":
    main()
