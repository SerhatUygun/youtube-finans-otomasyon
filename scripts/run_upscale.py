"""Real-ESRGAN ile videoyu upscale eder (+ opsiyonel yüz restorasyonu). Bağımsız araç.

Ana venv'den çalışır; Real-ESRGAN'ın izole venv'indeki resmi video inference scriptini
subprocess ile çağırır ve sonucu --out'a taşır.

Kullanım:
  python scripts/run_upscale.py --in output/<job>/video.mp4 --out output/<job>/video_4k.mp4
      [--scale 2] [--model RealESRGAN_x2plus] [--face-enhance]
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Giriş videosu")
    ap.add_argument("--out", required=True, help="Çıkış (upscale) videosu")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--model", default="RealESRGAN_x2plus")
    ap.add_argument("--face-enhance", action="store_true", help="GFPGAN/CodeFormer ile yüz restorasyonu")
    ap.add_argument("--venv", default=str(ROOT / "vendor/Real-ESRGAN/.venv/Scripts/python.exe"))
    ap.add_argument("--repo", default=str(ROOT / "vendor/Real-ESRGAN"))
    args = ap.parse_args()

    venv = Path(args.venv)
    if not venv.exists():
        sys.exit(f"Real-ESRGAN venv yok: {venv} (scripts/setup_upscale.ps1 çalıştır)")
    inp = Path(args.inp).resolve()
    if not inp.exists():
        sys.exit(f"Giriş videosu yok: {inp}")

    with tempfile.TemporaryDirectory() as td:
        outdir = Path(td) / "up"
        outdir.mkdir(parents=True, exist_ok=True)
        # Real-ESRGAN'ın resmi video scripti: inference_realesrgan_video.py
        cmd = [
            str(venv), "inference_realesrgan_video.py",
            "-n", args.model,
            "-i", str(inp),
            "-o", str(outdir),
            "-s", str(args.scale),
        ]
        if args.face_enhance:
            cmd.append("--face_enhance")
        print("Real-ESRGAN upscale çalışıyor (kare kare; uzun sürebilir) ...")
        res = subprocess.run(cmd, cwd=args.repo)
        if res.returncode != 0:
            sys.exit("Real-ESRGAN başarısız (log yukarıda).")
        vids = glob.glob(str(outdir / "**" / "*.mp4"), recursive=True)
        if not vids:
            sys.exit(f"Upscale çıktısı bulunamadı: {outdir}")
        produced = max(vids, key=os.path.getmtime)
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(produced, out)
    print(f"DONE -> {out}")


if __name__ == "__main__":
    main()
