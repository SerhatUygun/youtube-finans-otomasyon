"""Kendi çektiğin videoya otomatik grafik kurgu (Finans Kanalı).

 1. Çekim 1920x1080/30fps'e çevrilir, ses loudnorm; (varsayılan) uzun sessizlikler/boşluklar kesilir (jump cut)
 2. faster-whisper kelime zamanlı transkript -> segmentler (pipeline/daily/timeline.from_words)
 3. Claude headless (prompts/footage_edit.md): rakam doğrulama + sahne/layout yerleşimi + başlık/açıklama/kapak
 4. pipeline/daily/build.py (çekim modu): plan -> Remotion render (kamera taban katman) -> kapak -> YouTube PRIVATE -> Drive

Kullanım:
  python tools/edit_footage.py çekim.mp4                  # tam (yükleme dahil, private)
  python tools/edit_footage.py çekim.mp4 --no-upload      # deneme
  python tools/edit_footage.py çekim.mp4 --no-cut         # boşlukları kesme
  python tools/edit_footage.py --job footage-20260929-1400 --resume   # kaldığı yerden
  python tools/edit_footage.py footage.mp4 --lang en --brand "Other Channel" --host Host --no-upload   # başka kanal (İngilizce)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.daily_run import AYLAR, DAILY, GUNLER, Log, claude_resilient  # noqa: E402
from pipeline.daily import timeline as tlmod  # noqa: E402

FPS = 30


def _dur(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout.strip())


LANG = "tr"


def face_x(media: Path, n: int = 24) -> float | None:
    """Çekimde yüzün ortalama yatay konumu (0..1). Yan panel (left/right) yüzün karşı tarafına açılsın diye."""
    try:
        import cv2
    except ImportError:
        return None
    cap = cv2.VideoCapture(str(media))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs = []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * (k + 0.5) / n))
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        faces = det.detectMultiScale(g, 1.1, 6, minSize=(g.shape[0] // 8, g.shape[0] // 8))
        if len(faces):
            x, _, w, _ = max(faces, key=lambda f: f[2] * f[3])
            xs.append((x + w / 2) / g.shape[1])
    cap.release()
    if len(xs) < 3:
        return None
    xs.sort()
    return round(xs[len(xs) // 2], 3)


def _words(model, media: Path) -> list[tuple[str, float, float]]:
    res, _ = model.transcribe(str(media), language=LANG, word_timestamps=True, beam_size=5, vad_filter=True)
    out: list[tuple[str, float, float]] = []
    for r in res:
        for w in r.words or []:
            raw = w.word
            tok = raw.strip()
            if not tok:
                continue
            # 30 Eyl: whisper segment sınırında önceki kelimeleri sıfır süreyle TEKRAR yazabiliyor (altyazıda çift görünüyordu)
            if float(w.end) - float(w.start) < 0.02 or (out and float(w.start) < out[-1][1] - 0.05):
                continue
            # whisper rakamları/ekleri ayrı token verir ("%3" ",2" / "4200" "'ün"): boşluksuz başlayan ya da ,.'’ ile
            # başlayan parçayı öncekine yapıştır -> altyazıda "%3,2", "4200'ün"
            if out and (not raw.startswith(" ") or tok[0] in ",.'’") and float(w.start) - out[-1][2] < 0.3:
                pw, ps, _ = out[-1]
                out[-1] = (pw + tok, ps, float(w.end))
            else:
                out.append((tok, float(w.start), float(w.end)))
    return out


def keep_intervals(words, dur: float, gap=0.7, pre=0.12, post=0.22) -> list[tuple[float, float]]:
    """Konuşma aralıkları: kelimeler arası boşluk > gap ise kes; her aralığa küçük pay bırak."""
    if not words:
        return [(0.0, dur)]
    out = []
    a, b = max(words[0][1] - pre, 0.0), words[0][2]
    for _, s, e in words[1:]:
        if s - b > gap:
            out.append((a, min(b + post, dur)))
            a = max(s - pre, 0.0)
        b = max(b, e)
    out.append((a, min(b + post, dur)))
    return out


def prepare(src: Path, dst: Path, cut: bool, model, raw: Path, log) -> None:
    """Çekimi normalize eder; cut=True ise boşlukları atar. Filtre uzun olabileceği için script dosyasıyla verilir."""
    vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p"
    af = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"
    if not cut:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-af", af, "-c:v", "libx264", "-crf", "17",
                        "-preset", "medium", "-c:a", "aac", "-b:a", "256k", str(dst)], check=True)
        return
    dur = _dur(src)
    iv = keep_intervals(_words(model, src), dur)
    kept = sum(b - a for a, b in iv)
    log(f"jump cut: {len(iv)} parça, {dur:.1f} sn -> {kept:.1f} sn ({dur - kept:.1f} sn boşluk atıldı)")
    parts = []
    for i, (a, b) in enumerate(iv):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}];")
    cat = "".join(f"[v{i}][a{i}]" for i in range(len(iv)))
    script = "".join(parts) + f"{cat}concat=n={len(iv)}:v=1:a=1[cv][ca];[cv]{vf}[vo];[ca]{af}[ao]"
    fs = raw / "cut_filter.txt"
    fs.write_text(script, encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex_script", str(fs), "-map", "[vo]", "-map", "[ao]",
                    "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-c:a", "aac", "-b:a", "256k", str(dst)], check=True)


def validate_scenes(video: dict) -> list[str]:
    known = set(("Intro KineticTitle Stamp StatCards Gauge Dots ReasonCards Quote Chart Normalized Compare Ladder Scenario RangeBar Vote "
                 "Bars Volatility Timeline CoinFlip Tug AssetCards Chapter Disclaimer Poll Outro DateQuestion Candles Heatmap WorldMap "
                 "YieldCurve Breaking Countdown Headline Metal3D Globe3D PumpBoard Waterfall DominoChain").split())
    errs = []
    n = len(video.get("segments", []))
    for k, sc in enumerate(video.get("scenes", [])):
        if sc.get("t") not in known:
            errs.append(f"sahne {k}: bilinmeyen şablon {sc.get('t')}")
        if sc.get("layout") not in ("cam", "split", "corner", "full", "left", "right", "pip"):
            errs.append(f"sahne {k}: layout eksik/geçersiz ({sc.get('layout')})")
        cue = str(sc.get("cue", "0"))
        if cue.split(":")[0].split("+")[0].split("-")[0].isdigit() and int(cue.split(":")[0].split("+")[0].split("-")[0]) >= n:
            errs.append(f"sahne {k}: cue {cue} segment sayısını ({n}) aşıyor")
        if sc.get("t") == "Chapter" and not isinstance(sc.get("before"), int):
            errs.append(f"sahne {k}: Chapter 'before' (int) eksik")
    if not video.get("scenes"):
        errs.append("scenes boş")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?", help="çekim dosyası (mp4/mov)")
    ap.add_argument("--job", help="iş klasörü adı (varsayılan footage-YYYYMMDD-HHMM)")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--no-cut", action="store_true", help="boşlukları kesme")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--lang", default="tr", choices=["tr", "en"], help="konuşma dili (whisper + yayın metinleri)")
    ap.add_argument("--brand", help="başka kanal adı: Finans Kanalı logosu yerine bu yazılır (ör. 'Other Channel')")
    ap.add_argument("--host", help="konuşan kişinin adı (prompt için; varsayılan sunucu)")
    a = ap.parse_args()
    global LANG
    LANG = a.lang
    if a.brand:  # başka kanalın videosu ASLA Finans Kanalı kanalına yüklenmez; dosya teslim edilir
        a.no_upload = True
    now = datetime.now()
    job_id = a.job or f"footage-{now:%Y%m%d-%H%M}"
    job = ROOT / "output" / job_id
    raw = job / "_raw"
    raw.mkdir(parents=True, exist_ok=True)
    log = Log(DAILY / f"{now:%Y-%m-%d}.log")
    status_f = raw / "status.json"
    status = json.loads(status_f.read_text(encoding="utf-8")) if status_f.exists() else {}
    pub = ROOT / "remotion" / "public" / "auto" / job_id
    pub.mkdir(parents=True, exist_ok=True)
    try:
        if "timelines" not in status:
            if not a.video:
                raise SystemExit("çekim dosyası gerekli")
            src = Path(a.video).resolve()
            log(f"== {job_id}: çekim hazırlanıyor ({src.name}, {_dur(src) / 60:.1f} dk)")
            from faster_whisper import WhisperModel
            wm = WhisperModel("large-v3", device="cuda", compute_type="int8")
            cam = pub / "cam.mp4"
            prepare(src, cam, not a.no_cut, wm, raw, log)
            d = _dur(cam)
            tl = tlmod.from_words(_words(wm, cam), d)
            del wm
            (raw / "timeline_long.json").write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
            (job / "video.json").write_text(json.dumps({"segments": [{"tts": s["text"], "text": s["text"]} for s in tl["segments"]]},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
            (job / "reels.json").write_text("[]", encoding="utf-8")
            fx = face_x(cam)
            log(f"yüz konumu (yatay): {fx}")
            meta = {"src": f"auto/{job_id}/cam.mp4", "source": str(src), "lang": a.lang, "faceX": fx,
                    "host": a.host or "sunucu"}
            if a.brand:
                meta["brand"] = {"name": a.brand}
            (raw / "footage.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            stamp = now.isoformat(timespec="seconds")
            status.update(tts={"at": stamp, "footage": True}, timelines={"at": stamp, "seconds": tl["seconds"]})
            status_f.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"transkript: {len(tl['segments'])} segment, {tl['seconds'] / 60:.2f} dk")

        video = json.loads((job / "video.json").read_text(encoding="utf-8"))
        if not video.get("scenes") or not (job / "thumb.json").exists():
            fmeta = json.loads((raw / "footage.json").read_text(encoding="utf-8"))
            pname = "footage_edit_en.md" if fmeta.get("lang") == "en" else "footage_edit.md"
            prompt = ((ROOT / "prompts" / pname).read_text(encoding="utf-8")
                      .replace("{{HOST}}", fmeta.get("host", "sunucu")).replace("{{CHANNEL}}", (fmeta.get("brand") or {}).get("name", "Finans Kanalı"))
                      .replace("{{FACE_X}}", str(fmeta.get("faceX")))
                      .replace("{{DATE_TR}}", f"{now.day} {AYLAR[now.month - 1]} {now.year}")
                      .replace("{{WEEKDAY_TR}}", GUNLER[now.weekday()]).replace("{{JOB_DIR}}", job.relative_to(ROOT).as_posix()))
            log(f"== {job_id}: Claude kurgu planı başlıyor")
            out = claude_resilient(prompt, job, log)
            video = json.loads((job / "video.json").read_text(encoding="utf-8"))
            errs = validate_scenes(video)
            if errs:
                log(f"doğrulama: {len(errs)} hata -> düzeltme turu")
                claude_resilient("video.json sahnelerinde şu hatalar var, düzelt (segments'e dokunma):\n- " + "\n- ".join(errs),
                                 job, log, out.get("session_id"))
                video = json.loads((job / "video.json").read_text(encoding="utf-8"))
        errs = validate_scenes(video)
        if errs:
            raise RuntimeError("sahne doğrulaması başarısız: " + "; ".join(errs[:5]))
        brief = json.loads((job / "brief.json").read_text(encoding="utf-8"))
        for w in brief.get("warnings", []):
            log(f"  ! UYARI (rakam): {w}")

        # Claude'un düzelttiği altyazı metinlerini (kelime sayısı aynıysa) zaman çizelgesine işle
        tlp = raw / "timeline_long.json"
        tl = json.loads(tlp.read_text(encoding="utf-8"))
        for seg, vs in zip(tl["segments"], video["segments"]):
            toks = vs["text"].split()
            if len(toks) == len(seg["words"]):
                for w, t in zip(seg["words"], toks):
                    w["w"] = t
                seg["text"] = vs["text"]
        tlp.write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")

        from pipeline.daily.build import Build
        res = Build(job, log=log).run(upload=not a.no_upload)
        log(f"== BİTTİ (çekim): {res['title']} · {res['seconds'] / 60:.2f} dk · {res.get('upload', {}).get('url', 'yüklenmedi')}")
        print(json.dumps({"job": job_id, **res}, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001
        log(f"!! HATA: {e}")
        (DAILY / f"{now:%Y-%m-%d}_{job_id}_HATA.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return 1


if __name__ == "__main__":
    sys.exit(main())
