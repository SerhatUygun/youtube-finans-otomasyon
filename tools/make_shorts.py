"""Uzun videodan otomatik dikey (9:16) SHORTS klibi üretir — en büyük erişim kaldıracı.

Uzun-form bir videoyu alır, en vurucu pencereyi seçer, 1080x1920 dikey formata (bulanık
arka plan pad) çevirir, altyazıyı BÜYÜK dikey stille yakar. Shorts izleyiciyi ana kanala huniler.

Pencere seçimi:
  - segments_timing.json varsa: SAYISAL/veri içeren (fiyat, %, rakam) segmentlerin yoğunlaştığı
    en iyi ~<duration>s pencereyi seçer (finans Shorts'unda "rakamlı" an en çok tutar).
  - yoksa: hook (ilk <duration> sn) — açılış genelde en güçlü kısımdır.

Kullanım:
  python tools/make_shorts.py --job output/<job_id>                 # otomatik pencere + altyazı
  python tools/make_shorts.py --video x.mp4 --srt x.srt --start 12 --duration 40 --out short.mp4
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # `python tools/make_shorts.py` çalıştırınca pipeline import edilebilsin

from pipeline.stages.s07_edit import _has_nvenc  # noqa: E402 -- NVENC varsa Shorts encode'u da GPU'ya taşır

_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _run_ffmpeg_encode(build_cmd, capture: bool = True):
    """NVENC (varsa) ile dener; donanım/sürücü kaynaklı hata olursa libx264 (CPU) ile
    tek seferlik yeniden dener -- Shorts render'ı NVENC yokluğunda/arızasında asla
    tamamen başarısız kalmasın (bkz. s07_edit._video_encoder_args aynı gerekçe)."""
    use_nvenc = _has_nvenc()
    kwargs = dict(capture_output=True, text=True, encoding="utf-8", errors="replace") if capture else {}
    res = subprocess.run(build_cmd(use_nvenc), **kwargs)
    if use_nvenc and res.returncode != 0:
        print("NVENC Shorts encode başarısız, libx264 (CPU) ile yeniden deneniyor...")
        res = subprocess.run(build_cmd(False), **kwargs)
    return res


def _short_venc_args(nvenc: bool) -> list[str]:
    if nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _parse_ts(s):
    m = _TS.match(s.strip())
    h, mi, se, ms = map(int, m.groups())
    return h * 3600 + mi * 60 + se + ms / 1000.0


def _fmt_ts(t):
    if t < 0:
        t = 0
    h = int(t // 3600); t -= h * 3600
    m = int(t // 60); t -= m * 60
    s = int(t); ms = int(round((t - s) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(path):
    """[(start, end, text)] döner."""
    cues = []
    blocks = re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8").strip())
    for b in blocks:
        lines = [ln for ln in b.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        tl = next((ln for ln in lines if "-->" in ln), None)
        if not tl:
            continue
        a, bb = tl.split("-->")
        text = " ".join(lines[lines.index(tl) + 1:]).strip()
        cues.append((_parse_ts(a), _parse_ts(bb), text))
    return cues


def shift_srt(cues, start, end, out_path):
    """Pencereye düşen cue'ları alır, zamanı start'a göre kaydırıp yeni SRT yazar."""
    lines, i = [], 1
    for a, b, text in cues:
        if b <= start or a >= end:
            continue
        na, nb = max(a, start) - start, min(b, end) - start
        lines += [str(i), f"{_fmt_ts(na)} --> {_fmt_ts(nb)}", text, ""]
        i += 1
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return i - 1


def pick_window(timing, duration):
    """Sayısal/veri içeren segmentlerin en yoğun olduğu ~duration'lık pencereyi seçer."""
    if not timing:
        return 0.0
    segs = sorted(timing, key=lambda t: t.get("start_ms", 0))
    num_re = re.compile(r"\d|%|\$|₺|dolar|yüzde|percent", re.I)
    best_start, best_score = 0.0, -1
    for s in segs:
        w_start = s.get("start_ms", 0) / 1000.0
        w_end = w_start + duration
        score = sum(1 for x in segs
                    if w_start <= x.get("start_ms", 0) / 1000.0 < w_end
                    and num_re.search(x.get("text", "")))
        if score > best_score:
            best_score, best_start = score, w_start
    return best_start


# Dikey Shorts altyazı stili — büyük, ortada, okunaklı (küçük ekran + sessiz izleme için).
_SHORT_SUB_STYLE = (
    "FontName=Segoe UI,Fontsize=16,Bold=1,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=340"
)


def generate_short_for_job(job_id_or_path: str | Path, duration: float = 45.0, burn_subs: bool = True) -> str | None:
    """Belirtilen iş klasöründen otomatik dikey Shorts üretir."""
    p = Path(job_id_or_path)
    job_dir = p if p.is_dir() else ROOT / "output" / str(job_id_or_path)
    video = job_dir / "video.mp4"
    if not video.exists():
        print(f"Shorts için video bulunamadı: {video}")
        return None

    srt = job_dir / "subtitles.srt"
    timing_file = job_dir / "segments_timing.json"
    out = job_dir / "short.mp4"

    duration = min(float(duration), 60.0)

    # Pencere seç
    if timing_file.exists():
        try:
            start = pick_window(json.loads(timing_file.read_text(encoding="utf-8")), duration)
        except Exception:
            start = 0.0
    else:
        start = 0.0

    try:
        total = ffprobe_duration(video)
    except Exception:
        total = 60.0

    start = max(0.0, min(start, max(total - duration, 0.0)))

    vf = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "gblur=sigma=28[bgb];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]"
    )

    tmp_srt = None
    use_subs = burn_subs and srt.exists() and srt.stat().st_size > 0
    if use_subs:
        tmp_srt = out.parent / (out.stem + "_subs.srt")
        try:
            n = shift_srt(parse_srt(srt), start, start + duration, tmp_srt)
            sp = str(tmp_srt.resolve()).replace("\\", "/").replace(":", "\\:")
            vf = vf.replace("[v]", "[vv]") + f";[vv]subtitles='{sp}':force_style='{_SHORT_SUB_STYLE}'[v]"
        except Exception as e:
            print(f"Shorts altyazı kaydırma hatası (altyazısız devam edilecek): {e}")

    def _build_cmd(nvenc: bool) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(video),
            "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
            *_short_venc_args(nvenc),
            "-c:a", "aac", "-b:a", "160k", str(out),
        ]

    res = _run_ffmpeg_encode(_build_cmd, capture=True)
    if tmp_srt and tmp_srt.exists():
        tmp_srt.unlink()

    if res.returncode != 0 or not out.exists():
        print(f"Shorts ffmpeg hatası: {res.stderr[-500:]}")
        return None

    # Galeriye kopyala
    try:
        videos_dir = ROOT / "output" / "_videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        dst = videos_dir / f"{job_dir.name}_short.mp4"
        import shutil
        shutil.copy2(out, dst)
    except Exception:
        pass

    return str(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="İş dizini (output/<job_id>) — video.mp4/subtitles.srt/timing otomatik")
    ap.add_argument("--video")
    ap.add_argument("--srt")
    ap.add_argument("--start", type=float, default=None, help="Başlangıç sn (yoksa otomatik seçilir)")
    ap.add_argument("--duration", type=float, default=45.0, help="Shorts süresi (<=60)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-subs", action="store_true", help="Altyazı yakma")
    args = ap.parse_args()

    if args.job:
        job = Path(args.job)
        video = job / "video.mp4"
        srt = job / "subtitles.srt"
        timing_file = job / "segments_timing.json"
        out = Path(args.out) if args.out else job / "short.mp4"
    else:
        if not args.video:
            sys.exit("--job veya --video gerekli")
        video = Path(args.video)
        srt = Path(args.srt) if args.srt else None
        timing_file = None
        out = Path(args.out) if args.out else video.with_name(video.stem + "_short.mp4")

    if not video.exists():
        sys.exit(f"Video yok: {video}")
    duration = min(args.duration, 60.0)

    # Pencere başlangıcı
    if args.start is not None:
        start = args.start
    elif timing_file and timing_file.exists():
        import json
        start = pick_window(json.loads(timing_file.read_text(encoding="utf-8")), duration)
    else:
        start = 0.0
    total = ffprobe_duration(video)
    start = max(0.0, min(start, max(total - duration, 0.0)))
    print(f"Pencere: {start:.1f}s - {start + duration:.1f}s (toplam {total:.0f}s)")

    # Video filtresi: 1080x1920 bulanık-arka-plan pad (yanları kırpmadan; grafik/metin korunur).
    # Ölçek: içeriği 1080 genişliğe sığdır (üst-alt bar); arka plan aynı kareyi büyütüp bulanıklaştır.
    vf = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "gblur=sigma=28[bgb];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgs];"
        "[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]"
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_srt = None
    use_subs = (not args.no_subs) and srt and Path(srt).exists()
    if use_subs:
        tmp_srt = out.parent / (out.stem + "_subs.srt")
        n = shift_srt(parse_srt(srt), start, start + duration, tmp_srt)
        print(f"Altyazı: {n} blok pencereye kaydırıldı")
        # ffmpeg subtitles filtresi POSIX yollu ve kaçışlı ister
        sp = str(tmp_srt.resolve()).replace("\\", "/").replace(":", "\\:")
        vf = vf.replace("[v]", "[vv]") + f";[vv]subtitles='{sp}':force_style='{_SHORT_SUB_STYLE}'[v]"

    def _build_cmd(nvenc: bool) -> list[str]:
        return [
            "ffmpeg", "-y",
            "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(video),
            "-filter_complex", vf, "-map", "[v]", "-map", "0:a?",
            *_short_venc_args(nvenc),
            "-c:a", "aac", "-b:a", "160k", str(out),
        ]
    print("Shorts render ediliyor (dikey 1080x1920, bulanık bg) ...")
    res = _run_ffmpeg_encode(_build_cmd, capture=False)
    if tmp_srt and tmp_srt.exists():
        tmp_srt.unlink()
    if res.returncode != 0 or not out.exists():
        sys.exit("ffmpeg Shorts render başarısız.")
    print(f"DONE -> {out}")


if __name__ == "__main__":
    main()
