"""Dijital ikiz: kanal sahibinin kendi taban çekimi + yeni ses -> LatentSync 1.5 ile dudak senkronlu video.

Görüntü birebir gerçek çekimdir; yalnız ağız bölgesi sese göre yeniden üretilir. Taban çekim ileri-geri (ping-pong)
döngülenir ki döngü noktasında sıçrama olmasın. Ses parça parça (varsayılan 20 sn) işlenir: her parça ayrı süreç ->
RAM birikmez, s03_avatar._wait_render_process koruması her parçada RAM/VRAM'i izler.

  base  : assets/twin/base.mp4 (1-2 dk, sabit kamera, doğal konuşma)  ->  _raw/twin_base_pp.mp4 (bir kez, önbellek)
  audio : herhangi wav (ör. günlük hattın voice.wav'ı)
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from pipeline.utils.config import load_config
from pipeline.utils.paths import ROOT

REPO = ROOT / "vendor" / "LatentSync"
VPY = REPO / ".venv" / "Scripts" / "python.exe"


def _dur(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout.strip())


def _ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def pingpong_base(base: Path, cache_dir: Path, fps=25, height=1080) -> Path:
    """base + ters(base) -> kesintisiz döngü. reverse filtresi tüm kareleri RAM'e aldığı için 8 sn'lik parçalarla yapılır.
    LatentSync 25 fps ile eğitildi -> taban 25 fps'e çevrilir."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{base.stem}_pp_{int(base.stat().st_mtime)}.mp4"
    if out.exists():
        return out
    fwd = cache_dir / "base_fwd.mp4"
    _ff("-i", base, "-an", "-vf", f"scale=-2:{height},fps={fps},format=yuv420p", "-c:v", "libx264", "-crf", "15", "-preset", "medium", fwd)
    d = _dur(fwd)
    pieces, t, k = [], 0.0, 0
    while t < d - 0.05:
        seg = cache_dir / f"rev_{k:03d}.mp4"
        _ff("-ss", f"{t:.3f}", "-t", "8", "-i", fwd, "-vf", "reverse", "-an", "-c:v", "libx264", "-crf", "15", "-preset", "medium", seg)
        pieces.append(seg)
        t += 8
        k += 1
    lst = cache_dir / "pp.txt"
    lst.write_text("\n".join([f"file '{fwd.as_posix()}'"] + [f"file '{p.as_posix()}'" for p in reversed(pieces)]), encoding="utf-8")
    _ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)
    for p in pieces:
        p.unlink(missing_ok=True)
    return out


def lipsync(audio: Path, out: Path, work: Path, log=print, base: Path | None = None) -> Path:
    from pipeline.stages.s03_avatar import _wait_render_process

    cfg = load_config().get("twin", {})
    base = base or (ROOT / cfg.get("base_video", "assets/twin/base.mp4"))
    if not base.exists():
        raise RuntimeError(f"dijital ikiz taban çekimi yok: {base} (1-2 dk kendini çek, bu yola koy)")
    if not VPY.exists():
        raise RuntimeError(f"LatentSync kurulu değil: {VPY} (scripts/setup_latentsync.ps1)")
    work.mkdir(parents=True, exist_ok=True)
    pp = pingpong_base(base, ROOT / "assets" / "twin" / ".cache")
    total = _dur(audio)
    chunk = float(cfg.get("chunk_seconds", 20))
    ppd = _dur(pp)
    done_f = work / "chunks.json"
    done = json.loads(done_f.read_text(encoding="utf-8")) if done_f.exists() else {}
    outs, t, k = [], 0.0, 0
    t0 = time.time()
    while t < total - 0.02:
        ln = min(chunk, total - t)
        o = work / f"ls_{k:03d}.mp4"
        if str(k) not in done or not o.exists():
            a = work / f"a_{k:03d}.wav"
            v = work / f"v_{k:03d}.mp4"
            _ff("-ss", f"{t:.3f}", "-t", f"{ln:.3f}", "-i", audio, "-ar", "16000", "-ac", "1", a)
            # taban döngüde aynı konumdan devam: kesintisiz hareket
            _ff("-stream_loop", "-1", "-ss", f"{t % ppd:.3f}", "-i", pp, "-t", f"{ln:.3f}", "-an", "-c:v", "libx264", "-crf", "15", "-preset", "fast", v)
            cmd = [str(VPY), "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2.yaml",
                   "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", str(cfg.get("steps", 20)),
                   "--guidance_scale", str(cfg.get("guidance", 1.5)), "--enable_deepcache",
                   "--video_path", str(v), "--audio_path", str(a), "--video_out_path", str(o)]
            lg = work / f"ls_{k:03d}.log"
            with open(lg, "w", encoding="utf-8") as f:
                proc = subprocess.Popen(cmd, cwd=str(REPO), stdout=f, stderr=subprocess.STDOUT)
                _wait_render_process(proc, lg, "LatentSync", int(cfg.get("max_chunk_minutes", 15)) * 60, cfg)
            if proc.returncode != 0 or not o.exists():
                raise RuntimeError(f"LatentSync parça {k} başarısız: {lg.read_text(encoding='utf-8', errors='replace')[-1200:]}")
            done[str(k)] = round(ln, 3)
            done_f.write_text(json.dumps(done), encoding="utf-8")
            el = time.time() - t0
            log(f"  ikiz: parça {k + 1}/{int(total // chunk) + 1} bitti ({el:.0f}s)")
        outs.append(o)
        t += ln
        k += 1
    lst = work / "ls.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in outs), encoding="utf-8")
    # parçaları birleştir, sesi ORİJİNAL (48 kHz) wav'dan al; 30 fps'e çevir (Remotion)
    _ff("-f", "concat", "-safe", "0", "-i", lst, "-i", audio, "-map", "0:v", "-map", "1:a", "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-c:a", "aac", "-b:a", "256k", "-shortest", out)
    log(f"ikiz video hazır: {out.name} ({total / 60:.1f} dk, {time.time() - t0:.0f}s)")
    return out
