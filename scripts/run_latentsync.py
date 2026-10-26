"""Dijital ikiz CLI: taban çekim + ses -> dudak senkronlu video (pipeline/twin.lipsync).

  python scripts/run_latentsync.py --audio ses.wav --out ikiz.mp4 [--base assets/twin/base.mp4] [--seconds 10]
  --seconds: yalnız ilk N saniye (smoke test)
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import twin  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base")
    ap.add_argument("--seconds", type=float)
    a = ap.parse_args()
    audio, out = Path(a.audio).resolve(), Path(a.out).resolve()
    work = out.parent / f"_{out.stem}_work"
    if a.seconds:
        work.mkdir(parents=True, exist_ok=True)
        cut = work / "audio_cut.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-t", str(a.seconds), str(cut)], check=True)
        audio = cut
    twin.lipsync(audio, out, work, base=Path(a.base).resolve() if a.base else None)


if __name__ == "__main__":
    main()
