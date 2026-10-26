"""Eski iş çıktılarını arşivler — output/'taki tüm iş dizinlerini output/_archive/'e taşır.

Çalışma alanını temizler ama SİLMEZ (geri dönülebilir). Alt çizgi (_) ile başlayan özel
dizinler KORUNUR: _archive, _brain, _dataset, _logs, _preview, _videos.

Kullanım:
  python tools/archive_outputs.py            # taşı
  python tools/archive_outputs.py --dry-run  # sadece listele
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
ARCHIVE = OUTPUT / "_archive"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="sadece taşınacakları listele")
    args = ap.parse_args()

    if not OUTPUT.exists():
        print("output/ yok, yapılacak bir şey yok.")
        return
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    jobs = [d for d in OUTPUT.iterdir() if d.is_dir() and not d.name.startswith("_")]
    if not jobs:
        print("Arşivlenecek iş dizini yok.")
        return

    print(f"{len(jobs)} iş dizini {'listelenecek (dry-run)' if args.dry_run else 'arşivlenecek'}:")
    moved = 0
    for d in sorted(jobs):
        dst = ARCHIVE / d.name
        print(f"  {d.name} -> _archive/{d.name}")
        if args.dry_run:
            continue
        if dst.exists():
            shutil.rmtree(dst)  # aynı isim varsa üzerine (idempotent yeniden çalıştırma)
        shutil.move(str(d), str(dst))
        moved += 1
    if not args.dry_run:
        print(f"DONE — {moved} dizin arşivlendi -> {ARCHIVE}")


if __name__ == "__main__":
    main()
