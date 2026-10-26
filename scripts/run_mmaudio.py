"""MMAudio ile videoya arka plan müziği/ambiyans bed'i ekler (bağımsız araç).

Ana venv'den çalışır; ses ÜRETİMİ için MMAudio'nun izole venv'ini subprocess ile çağırır,
sonra üretilen ambiyansı ffmpeg ile mevcut anlatım sesinin ALTINA (kısık) mikser.

Akış:
  1) MMAudio venv -> demo.py (metinden ses, --prompt --duration) ile ambiyans klibi üretir
  2) ffprobe ile video süresini alır, ambiyansı o süreye döngüler
  3) ffmpeg amix: video(sesli) + ambiyans(music_volume_db kısık) -> --out mp4

Kullanım:
  python scripts/run_mmaudio.py --video output/<job>/video.mp4 --out output/<job>/video_scored.mp4
      [--prompt "calm ambient"] [--duration 8] [--volume-db -22]
"""
import argparse
import glob
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="Sesli giriş videosu (video.mp4)")
    ap.add_argument("--out", required=True, help="Çıkış mp4 (ambiyans mikslenmiş)")
    ap.add_argument("--prompt", default="calm subtle ambient background music, professional, unobtrusive")
    ap.add_argument("--duration", type=int, default=8, help="Üretilecek ambiyans klip süresi (sn)")
    ap.add_argument("--volume-db", type=float, default=-22.0, help="Ambiyans bed'i sesi (negatif=kısık)")
    ap.add_argument("--venv", default=str(ROOT / "vendor/MMAudio/.venv/Scripts/python.exe"))
    ap.add_argument("--repo", default=str(ROOT / "vendor/MMAudio"))
    args = ap.parse_args()

    venv = Path(args.venv)
    if not venv.exists():
        sys.exit(f"MMAudio venv yok: {venv} (scripts/setup_mmaudio.ps1 çalıştır)")
    video = Path(args.video).resolve()
    if not video.exists():
        sys.exit(f"Video yok: {video}")

    with tempfile.TemporaryDirectory() as td:
        gen_dir = Path(td) / "mmaudio_out"
        gen_dir.mkdir(parents=True, exist_ok=True)
        # 1) Ambiyans üret (metinden ses modu — video koşulu YOK; finans b-roll'ünde görsel
        #    koşulu anlamlı ambiyans vermez, temiz bir müzik bed'i için prompt yeterli).
        cmd = [
            str(venv), "demo.py",
            f"--duration={args.duration}",
            "--prompt", args.prompt,
            "--output", str(gen_dir),
        ]
        print("MMAudio ambiyans üretiliyor ...")
        res = subprocess.run(cmd, cwd=args.repo)
        if res.returncode != 0:
            sys.exit("MMAudio üretimi başarısız (log yukarıda).")
        # Üretilen ses dosyasını bul (demo.py flac/wav yazar; adı sürüme göre değişir)
        auds = []
        for ext in ("*.flac", "*.wav", "*.mp3"):
            auds += glob.glob(str(gen_dir / "**" / ext), recursive=True)
        if not auds:
            sys.exit(f"MMAudio çıktı sesi bulunamadı: {gen_dir}")
        ambience = max(auds, key=os.path.getmtime)

        # 2+3) Ambiyansı video süresine döngüle + anlatımın altına mikser
        dur = ffprobe_duration(video)
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        mix = [
            "ffmpeg", "-y",
            "-i", str(video),
            "-stream_loop", "-1", "-i", str(ambience),
            "-filter_complex",
            f"[1:a]volume={args.volume_db}dB,atrim=0:{dur:.3f}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out),
        ]
        print("Ambiyans anlatımın altına mikseleniyor ...")
        res = subprocess.run(mix)
        if res.returncode != 0 or not out.exists():
            sys.exit("ffmpeg miks başarısız.")
    print(f"DONE -> {out}")


if __name__ == "__main__":
    main()
