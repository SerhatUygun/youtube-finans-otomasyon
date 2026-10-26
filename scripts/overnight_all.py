"""Gece boyu HER ŞEYİ tek bağımsız süreçte yapar (oturumdan tamamen kopuk çalışır):
  1) Beyinle 3 temellendirilmiş Türkçe script üretir (make_examples),
  2) Ollama modelini VRAM'den boşaltır,
  3) Her işi sırayla videoya çevirir (overnight_run).

PowerShell Start-Process -WindowStyle Hidden ile detached başlatılır; Claude oturumu
kapansa bile devam eder. Tüm ilerleme output/_logs/overnight.log'a yazılır.
"""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline.utils.paths import OUTPUT_DIR  # noqa: E402

LOG = OUTPUT_DIR / "_logs" / "overnight.log"


def _log(msg: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} | MASTER | {msg}\n")


def main():
    _log("################ GECE TOPLU ÜRETİM BAŞLADI ################")
    try:
        import make_examples
        _log("Adım 1: beyinle Türkçe scriptler üretiliyor...")
        make_examples.main()
    except Exception as e:
        _log(f"Adım 1 HATA (script üretimi): {e}")
        import traceback
        _log(traceback.format_exc())

    try:
        import overnight_run
        _log("Adım 2: videolar sırayla render ediliyor...")
        overnight_run.main()
    except Exception as e:
        _log(f"Adım 2 HATA (video render): {e}")
        import traceback
        _log(traceback.format_exc())

    _log("################ GECE TOPLU ÜRETİM BİTTİ ################")


if __name__ == "__main__":
    main()
