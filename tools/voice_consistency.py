"""TTS segmentlerinin ses tutarlılığını ölçer (bölümden bölüme "farklı kişi" hissi).

Segment başına: medyan perde (F0, Hz), perde yarıton sapması (medyana göre), spektral merkez
(tını parlaklığı, Hz), konuşma hızı (hece/sn, sesli harf sayısından), RMS seviyesi (dBFS).
Çıktı: tablo + özet (varyasyon katsayısı) + aykırı segmentler (|z| > 2).

Kullanım: python tools/voice_consistency.py <segment_klasörü> [--json out.json]
"""
import json
import re
import sys
from pathlib import Path

import librosa
import numpy as np

VOWELS = re.compile(r"[aeıioöuüâîûAEIİOÖUÜ]")


def analyze(wav_path: Path, text: str | None = None) -> dict:
    y, sr = librosa.load(str(wav_path), sr=24000, mono=True)
    yt, _ = librosa.effects.trim(y, top_db=35)
    if len(yt) < sr * 0.3:
        yt = y
    f0, vflag, _ = librosa.pyin(yt, fmin=60, fmax=300, sr=sr, frame_length=1024)
    f0v = f0[vflag & ~np.isnan(f0)] if f0 is not None else np.array([])
    med = float(np.median(f0v)) if len(f0v) else float("nan")
    cent = float(np.median(librosa.feature.spectral_centroid(y=yt, sr=sr)))
    rms = float(20 * np.log10(np.sqrt(np.mean(yt ** 2)) + 1e-9))
    dur = len(yt) / sr
    rate = len(VOWELS.findall(text)) / dur if text else float("nan")
    return {"f0": med, "centroid": cent, "rms_db": rms, "dur": dur, "syl_per_s": rate}


def summarize(rows: list[dict]) -> dict:
    out = {}
    for k in ("f0", "centroid", "rms_db", "syl_per_s"):
        v = np.array([r[k] for r in rows if not np.isnan(r[k])])
        if not len(v):
            continue
        out[k] = {"median": float(np.median(v)), "std": float(np.std(v)),
                  "cv_pct": float(np.std(v) / abs(np.mean(v)) * 100), "min": float(v.min()), "max": float(v.max())}
    # perde sapması yarıton cinsinden (kulak bunu duyar)
    f0s = np.array([r["f0"] for r in rows if not np.isnan(r["f0"])])
    if len(f0s):
        st = 12 * np.log2(f0s / np.median(f0s))
        out["f0_semitone_spread"] = {"std": float(np.std(st)), "max_abs": float(np.max(np.abs(st)))}
    return out


def outliers(rows: list[dict], keys=("f0", "centroid", "syl_per_s"), z=2.0) -> list[int]:
    bad = set()
    for k in keys:
        v = np.array([r[k] for r in rows], dtype=float)
        m, s = np.nanmedian(v), np.nanstd(v)
        if s == 0 or np.isnan(s):
            continue
        for i, x in enumerate(v):
            if not np.isnan(x) and abs(x - m) / s > z:
                bad.add(i)
    return sorted(bad)


def main():
    seg_dir = Path(sys.argv[1])
    texts = {}
    sj = seg_dir.parent / "script.json"
    if sj.exists():
        segs = json.loads(sj.read_text(encoding="utf-8"))["segments"]
        texts = {i: t for i, t in enumerate(segs)}
    files = sorted(seg_dir.glob("seg_*.wav"))
    rows = []
    for f in files:
        i = int(f.stem.split("_")[1])
        r = analyze(f, texts.get(i))
        r["i"] = i
        rows.append(r)
    s = summarize(rows)
    bad = outliers(rows)
    print(json.dumps({"n": len(rows), "summary": s, "outliers": bad}, indent=1))
    for i in bad:
        r = rows[i]
        print(f"  aykırı seg {r['i']:03d}: f0={r['f0']:.0f}Hz centroid={r['centroid']:.0f} hız={r['syl_per_s']:.2f}")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps({"rows": rows, "summary": s, "outliers": bad}), encoding="utf-8")


if __name__ == "__main__":
    main()
