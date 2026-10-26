"""Segment wav'larından ses + kelime zamanlı zaman çizelgesi (Remotion plan'ının Timeline kısmı).

scripts/fed_motion/build_timeline.py'nin genelleştirilmiş hali: segment başı/sonu sessizlik kırpma, segment başına
seviye eşitleme (seviye sıçramaları "farklı kayıt" hissi veriyordu), cümle/bölüm duraklamaları, ffmpeg loudnorm,
faster-whisper kelime zamanı (initial_prompt YOK — halüsinasyon üretiyordu) + ekran metnine difflib hizalama.
"""
from __future__ import annotations

import difflib
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000
FPS = 30


def _mono(path: Path) -> np.ndarray:
    wav, sr = sf.read(str(path), dtype="float32")
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    if sr != SR:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(sr, SR)
        wav = resample_poly(wav, SR // g, sr // g).astype(np.float32)
    return wav


def trim(wav: np.ndarray, thr_db=-42.0, pad=0.04) -> np.ndarray:
    win = int(SR * 0.01)
    n = len(wav) // win
    if n == 0:
        return wav
    rms = np.sqrt(np.mean(wav[: n * win].reshape(n, win) ** 2, axis=1) + 1e-12)
    loud = np.where(20 * np.log10(rms) > thr_db)[0]
    if not len(loud):
        return wav
    a = max(loud[0] * win - int(pad * SR), 0)
    b = min((loud[-1] + 1) * win + int(pad * 1.5 * SR), len(wav))
    return wav[a:b]


def level_match(wav: np.ndarray, target_db=-20.0) -> np.ndarray:
    """Konuşma bölgelerinin RMS'ini hedefe çeker (segmentler arası seviye farkını kaldırır)."""
    win = int(SR * 0.02)
    n = len(wav) // win
    if n == 0:
        return wav
    fr = wav[: n * win].reshape(n, win)
    rms = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-12)
    speech = rms[20 * np.log10(rms) > -45]
    if not len(speech):
        return wav
    cur = 20 * np.log10(np.sqrt(np.mean(speech ** 2)))
    g = 10 ** ((target_db - cur) / 20)
    out = wav * g
    peak = np.max(np.abs(out))
    return out / peak * 0.98 if peak > 0.98 else out


def _norm(s: str) -> str:
    return re.sub(r"[^\w]", "", s.replace("İ", "i").replace("I", "ı").lower())


def align_times(src, tgt, tgt_times):
    sm = difflib.SequenceMatcher(a=[_norm(x) for x in src], b=[_norm(x) for x in tgt], autojunk=False)
    out = [None] * len(src)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[i1 + k] = tgt_times[j1 + k]
        elif tag == "replace":
            for k in range(i2 - i1):
                out[i1 + k] = tgt_times[j1 + int(k * (j2 - j1) / (i2 - i1))]
    known = [i for i, v in enumerate(out) if v is not None]
    if not known:
        return None
    for i in range(len(out)):
        if out[i] is None:
            prev = max([k for k in known if k < i], default=None)
            nxt = min([k for k in known if k > i], default=None)
            if prev is not None and nxt is not None:
                out[i] = out[prev] + (out[nxt] - out[prev]) * (i - prev) / (nxt - prev)
            elif prev is not None:
                out[i] = out[prev] + 0.25 * (i - prev)
            else:
                out[i] = max(out[nxt] - 0.25 * (nxt - i), 0.0)
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] + 0.03)
    return out


def from_words(words: list[tuple[str, float, float]], total_s: float, gap_s=0.8, max_words=45, min_words=12) -> dict:
    """Kendi çekimin için: tek parça transkriptin kelimelerinden (w, start, end) Timeline üretir.
    Segment sınırı: cümle sonu (. ? !) + en az min_words, ya da gap_s'den uzun sessizlik, ya da max_words."""
    segs, cur = [], []

    def flush():
        if cur:
            segs.append(list(cur))
            cur.clear()

    for k, (w, s, e) in enumerate(words):
        if cur and (s - cur[-1][2] > gap_s or len(cur) >= max_words):
            flush()
        cur.append((w, s, e))
        if re.search(r"[.?!…]$", w) and len(cur) >= min_words:
            flush()
    flush()
    out = []
    for i, sg in enumerate(segs):
        ws = [{"w": w.strip(), "s": round(s * FPS), "e": round(e * FPS)} for w, s, e in sg]
        for k in range(len(ws) - 1):
            ws[k]["e"] = ws[k + 1]["s"]
        out.append({"i": i, "s": ws[0]["s"], "e": ws[-1]["e"], "text": " ".join(x["w"] for x in ws), "words": ws})
    total = round(total_s * FPS)
    return {"fps": FPS, "total": total, "outroStart": min(out[-1]["e"] + 20, total) if out else total, "segments": out,
            "chapterFrom": {}, "seconds": round(total_s, 2)}


def build(segments: list[dict], wavs: list[Path], out_wav: Path, chapter_before: set[int] | None = None,
          intro_s=3.2, sent_pause=0.30, chapter_gap=2.4, tail_s=5.5, whisper_model=None, log=print) -> dict:
    """segments: [{tts, text}], wavs: her segmentin wav'ı. Dönen: Timeline + chapterFrom {before: frame}."""
    chapter_before = chapter_before or set()
    clips = [level_match(trim(_mono(w))) for w in wavs]
    parts = [np.zeros(int(intro_s * SR), dtype=np.float32)]
    cursor = intro_s
    times, chapter_from = [], {}
    for i, c in enumerate(clips):
        if i > 0:
            gap = chapter_gap if i in chapter_before else sent_pause
            if i in chapter_before:
                chapter_from[i] = round((cursor + 0.15) * FPS)
            parts.append(np.zeros(int(gap * SR), dtype=np.float32))
            cursor += gap
        times.append((cursor, cursor + len(c) / SR))
        parts.append(c.astype(np.float32))
        cursor += len(c) / SR
    parts.append(np.zeros(int(tail_s * SR), dtype=np.float32))
    total = cursor + tail_s
    raw = out_wav.with_name(out_wav.stem + "_raw.wav")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(raw), np.concatenate(parts), SR)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), "-ac", "1", str(out_wav)], check=True)
    raw.unlink(missing_ok=True)

    if whisper_model is None:
        from faster_whisper import WhisperModel
        whisper_model = WhisperModel("large-v3", device="cuda", compute_type="int8")
    out = []
    tmp = out_wav.with_name("_w.wav")
    for i, c in enumerate(clips):
        s0, s1 = times[i]
        sf.write(str(tmp), c, SR)
        res, _ = whisper_model.transcribe(str(tmp), language="tr", word_timestamps=True, beam_size=5, vad_filter=False)
        ww = [w for r in res for w in (r.words or [])]
        tts_tokens = segments[i]["tts"].split()
        ratio = difflib.SequenceMatcher(a=_norm(segments[i]["tts"]), b=_norm(" ".join(w.word for w in ww))).ratio()
        tts_t = align_times(tts_tokens, [w.word.strip() for w in ww], [float(w.start) for w in ww]) if ww and ratio >= 0.55 else None
        if tts_t is None:
            if ww:
                log(f"  ! seg {i}: whisper eşleşmesi düşük ({ratio:.2f}) -> orantılı zamanlama")
            lens = [len(x) + 2 for x in tts_tokens]
            dur = len(c) / SR
            tts_t = [dur * sum(lens[:k]) / sum(lens) for k in range(len(tts_tokens))]
        disp = segments[i]["text"].split()
        disp_t = align_times(disp, tts_tokens, tts_t) or [0.0] * len(disp)
        words = [{"w": w, "s": round((s0 + t) * FPS), "e": 0} for w, t in zip(disp, disp_t)]
        for k in range(len(words)):
            words[k]["e"] = words[k + 1]["s"] if k + 1 < len(words) else round(s1 * FPS)
        out.append({"i": i, "s": round(s0 * FPS), "e": round(s1 * FPS), "text": segments[i]["text"], "words": words})
    tmp.unlink(missing_ok=True)
    return {"fps": FPS, "total": round(total * FPS), "outroStart": out[-1]["e"] + 20, "segments": out,
            "chapterFrom": chapter_from, "seconds": round(total, 2)}
