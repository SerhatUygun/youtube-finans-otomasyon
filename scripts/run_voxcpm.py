#!/usr/bin/env python
"""VoxCPM2 zero-shot ses klonlama sarmalayıcısı — izole venv (vendor/VoxCPM) içinde çalışır.

24 Eyl: XTTS-v2'ye (2023) alternatif olarak eklendi. VoxCPM2 (openbmb, Apache-2.0) Türkçe
dahil 30 dil destekler, 48kHz çıktı verir, ~8GB VRAM ister.

s02_tts.py bunu subprocess olarak çağırır; arayüz run_cosyvoice.py ile aynıdır:
  - Tekli:  <venv> scripts/run_voxcpm.py --ref <sample.wav> --text "<metin>" --out <seg.wav>
  - Toplu:  <venv> scripts/run_voxcpm.py --ref <sample.wav> --batch-manifest <manifest.json>
            (manifest: [{"text": "...", "out": "seg_000.wav"}, ...]) — model BİR KEZ yüklenir.

--ref-text verilirse "ultimate cloning" (referans ses + transkript -> en yüksek benzerlik)
kullanılır; boşsa yalnızca referans sesle "controllable cloning" yapılır (transkript gerekmez).
"""
import argparse
import contextlib
import json
import time
from pathlib import Path


@contextlib.contextmanager
def _skip_random_init():
    """24 Eyl: VoxCPM2.from_local modeli önce CPU'da fp32 RASTGELE ağırlıklarla kurup sonra
    checkpoint'i üzerine yüklüyor — 2B parametrelik rastgele init bu makinede yüklemenin
    ~5 dakikasını yiyordu. Ağırlıklar zaten checkpoint'ten ezildiği için torch.nn.init
    fonksiyonlarını yükleme süresince no-op yapıyoruz (sonuç bit-bit aynı)."""
    import torch.nn.init as init
    names = ["uniform_", "normal_", "trunc_normal_", "kaiming_uniform_", "kaiming_normal_",
             "xavier_uniform_", "xavier_normal_", "orthogonal_", "zeros_", "ones_", "constant_"]
    saved = {n: getattr(init, n) for n in names if hasattr(init, n)}
    for n in saved:
        setattr(init, n, lambda t, *a, **k: t)
    try:
        yield
    finally:
        for n, f in saved.items():
            setattr(init, n, f)


def _seed_all(seed: int):
    import random

    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _voice_features_arr(wav, sr):
    """(medyan F0 Hz, medyan spektral merkez Hz) — 24 kHz'e indirilmiş, baş/son sessizlik kırpılmış."""
    import librosa
    import numpy as np
    y = librosa.resample(np.asarray(wav, dtype=np.float32), orig_sr=sr, target_sr=24000)
    yt, _ = librosa.effects.trim(y, top_db=35)
    if len(yt) < 24000 * 0.3:
        yt = y
    f0, vflag, _ = librosa.pyin(yt, fmin=60, fmax=300, sr=24000, frame_length=1024)
    f0v = f0[vflag & ~np.isnan(f0)] if f0 is not None else np.array([])
    f0m = float(np.median(f0v)) if len(f0v) else float("nan")
    cent = float(np.median(librosa.feature.spectral_centroid(y=yt, sr=24000)))
    return f0m, cent


def _voice_features(path):
    import soundfile as sf
    w, sr = sf.read(str(path), dtype="float32")
    if w.ndim > 1:
        w = w.mean(axis=1)
    return _voice_features_arr(w, sr)


def _dist(feat, target, a):
    """Normalize sapma: 1.0 = tolerans sınırı. Perde yarıton, tını log-oran cinsinden."""
    import math
    f0, cent = feat
    d_pitch = abs(12 * math.log2(f0 / target[0])) / a.gate_semitones if f0 == f0 and f0 > 0 else 1.5
    d_timbre = abs(math.log(cent / target[1])) / math.log(1 + a.gate_timbre)
    return max(d_pitch, d_timbre), feat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="referans ses (klonlanacak)")
    ap.add_argument("--ref-text", default="", help="referans sesin BİREBİR metni (opsiyonel, benzerliği artırır)")
    ap.add_argument("--text", help="seslendirilecek metin (tekli mod)")
    ap.add_argument("--out", help="çıktı wav yolu (tekli mod)")
    ap.add_argument("--batch-manifest", dest="batch_manifest",
                    help="toplu mod: [{'text':..,'out':..}, ...] içeren JSON dosyası; model BİR KEZ yüklenir")
    ap.add_argument("--model", default="openbmb/VoxCPM2", help="HF model id veya yerel dizin")
    ap.add_argument("--cfg", type=float, default=2.0, help="cfg_value (yüksek = metne/referansa daha sadık)")
    ap.add_argument("--steps", type=int, default=10, help="inference_timesteps (yüksek = daha kaliteli, yavaş)")
    ap.add_argument("--denoise", action="store_true", help="referans sesi denoiser'dan geçir")
    # 27 Eyl: ses tutarlılığı. Her cümle bağımsız örneklendiği için perde ±6 yarıton, tını %20
    # oynuyordu ("her bölümde farklı kişi"). Sabit tohum + temiz cümle-sonu istem klibiyle
    # "devam" (continuation) modu her segmenti aynı kaydın devamı gibi üretir.
    ap.add_argument("--prompt-wav", default="", help="devam modu istem klibi (boşsa --ref); --ref-text bu klibin BİREBİR metni olmalı")
    ap.add_argument("--seed", type=int, default=-1, help=">=0: her segment bu tohumla (manifestte 'seed' ile ezilebilir)")
    # Ses kapısı: her segment üretilir üretilmez perde (F0) ve tını (spektral merkez) ölçülür; hedef "ses
    # parmak izinden" sapan segment farklı tohumla yeniden üretilir, adaylardan en yakını tutulur.
    # Hedef: istem klibinin ölçümüyle başlar, kabul edilen segmentlerin medyanına doğru güncellenir.
    ap.add_argument("--gate", action="store_true", help="ses tutarlılık kapısını aç")
    ap.add_argument("--gate-semitones", type=float, default=1.8, help="perde toleransı (yarıton)")
    ap.add_argument("--gate-timbre", type=float, default=0.22, help="tını toleransı (oran, 0.22 = ±%%22)")
    ap.add_argument("--gate-retries", type=int, default=2, help="aykırı segment için ek deneme sayısı")
    ap.add_argument("--gate-report", default="", help="segment ölçümlerini yazacağı JSON")
    a = ap.parse_args()

    if a.batch_manifest:
        items = json.loads(Path(a.batch_manifest).read_text(encoding="utf-8"))
        if not items:
            ap.error("--batch-manifest boş")
    else:
        if not a.text or not a.out:
            ap.error("--text ve --out gerekli (ya da --batch-manifest)")
        items = [{"text": a.text, "out": a.out}]

    import soundfile as sf
    from voxcpm import VoxCPM

    t0 = time.time()
    with _skip_random_init():
        model = VoxCPM.from_pretrained(a.model, load_denoiser=a.denoise)
    sr = model.tts_model.sample_rate
    print(f"[voxcpm] model yüklendi ({time.time() - t0:.0f}s)", flush=True)

    clone_kwargs = {"reference_wav_path": a.ref}
    ref_text = a.ref_text.strip()
    if ref_text:
        clone_kwargs.update(prompt_wav_path=a.prompt_wav or a.ref, prompt_text=ref_text)
    print(f"[voxcpm] sr={sr} mod={'ultimate' if ref_text else 'reference-only'}", flush=True)

    def synth(text: str, seed: int):
        if seed >= 0:
            _seed_all(seed)
        wav = model.generate(text=text, cfg_value=a.cfg, inference_timesteps=a.steps, **clone_kwargs)
        if wav is None or len(wav) == 0:
            raise RuntimeError(f"VoxCPM hiç ses üretmedi: {text[:60]!r}")
        return wav

    target = None
    accepted: list[tuple[float, float]] = []
    report = []
    if a.gate:
        import numpy as np
        pf = _voice_features(a.prompt_wav or a.ref)
        target = pf
        print(f"[gate] istem parmak izi: f0={pf[0]:.0f}Hz tını={pf[1]:.0f}Hz", flush=True)

    n = len(items)
    for idx, item in enumerate(items):
        out_path = Path(item["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        seed = int(item.get("seed", a.seed))
        wav = synth(item["text"], seed)
        info = {"i": idx, "out": str(out_path), "tries": 1}
        if a.gate and not item.get("no_gate"):
            import numpy as np
            best, best_d, best_f = wav, *_dist(_voice_features_arr(wav, sr), target, a)
            k = 0
            while best_d > 1.0 and k < a.gate_retries:
                k += 1
                cand = synth(item["text"], (seed if seed >= 0 else 1234) + 7919 * k)
                d, f = _dist(_voice_features_arr(cand, sr), target, a)
                print(f"[gate] {idx + 1}: deneme {k + 1} sapma={d:.2f} (önceki en iyi {best_d:.2f})", flush=True)
                if d < best_d:
                    best, best_d, best_f = cand, d, f
            wav = best
            info.update(tries=k + 1, score=round(best_d, 3), f0=round(best_f[0], 1), timbre=round(best_f[1], 1))
            if best_d <= 1.0 and not np.isnan(best_f[0]):
                accepted.append(best_f)
                # hedefi kabul edilenlerin medyanına doğru yumuşakça taşı (model sesi istemden hafif farklı olabilir)
                if len(accepted) >= 6:
                    med = (float(np.median([x[0] for x in accepted])), float(np.median([x[1] for x in accepted])))
                    target = (0.5 * target[0] + 0.5 * med[0], 0.5 * target[1] + 0.5 * med[1])
        sf.write(str(out_path), wav, sr)
        report.append(info)
        print(f"[voxcpm] {idx + 1}/{n} yazıldı: {out_path} ({len(wav) / sr:.1f}s) {info.get('score', '')}", flush=True)
    if a.gate_report:
        Path(a.gate_report).write_text(json.dumps({"target": target, "items": report}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
