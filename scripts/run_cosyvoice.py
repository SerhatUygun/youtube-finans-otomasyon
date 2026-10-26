#!/usr/bin/env python
"""CosyVoice2 zero-shot ses klonlama sarmalayıcısı — izole venv (vendor/CosyVoice) içinde çalışır.

s02_tts.py bunu subprocess olarak çağırır. İKİ mod var:
  - Tekli:  <venv> scripts/run_cosyvoice.py --ref <sample.wav> --text "<metin>" --out <seg.wav>
  - Toplu:  <venv> scripts/run_cosyvoice.py --ref <sample.wav> --batch-manifest <manifest.json>
            (manifest: [{"text": "...", "out": "seg_000.wav"}, ...])
            Model BİR KEZ yüklenir, tüm öğeler aynı süreçte sentezlenir. CosyVoice2 modelini
            (~birkaç saniye import + saniyeler süren ağırlık yükleme) her segmentte yeniden
            başlatmak 15dk'lık, 150+ segmentli bir videoda segment başına ~2-3dk'lık gereksiz
            bir sabit maliyete (7 Ağu'da ölçüldü) yol açıyordu — toplu mod bunu ORTADAN KALDIRIR.

Referans metni (--ref-text) verilmezse faster-whisper ile otomatik yazıya döker (yalnızca ilk
kullanımda; config.yaml tts.cosy_ref_text doldurulmuşsa hiç çalışmaz).
WeTextProcessing (pynini) Windows'ta kurulamadığı için metin normalizasyonu no-op shim'lenir.
"""
import argparse
import json
import sys
import types
from pathlib import Path


def _install_tn_shim():
    """WeTextProcessing 'tn' normalizer'larını kimlik (no-op) ile değiştir — CosyVoice
    frontend'i pynini olmadan kurulabilsin. Türkçe düz metin görece temizdir."""
    if "tn" in sys.modules:
        return

    class _Id:
        def __init__(self, *a, **k):
            pass

        def normalize(self, text):
            return text

    mods = {}
    tn = types.ModuleType("tn")
    for lang in ("chinese", "english"):
        pkg = types.ModuleType(f"tn.{lang}")
        norm = types.ModuleType(f"tn.{lang}.normalizer")
        norm.Normalizer = _Id
        setattr(pkg, "normalizer", norm)
        setattr(tn, lang, pkg)
        mods[f"tn.{lang}"] = pkg
        mods[f"tn.{lang}.normalizer"] = norm
    mods["tn"] = tn
    sys.modules.update(mods)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="referans ses (klonlanacak)")
    ap.add_argument("--ref-text", default="", help="referans sesin metni (boşsa otomatik yazılır)")
    ap.add_argument("--text", help="seslendirilecek metin (tekli mod)")
    ap.add_argument("--text-file", dest="text_file", help="metni dosyadan oku (boşluk/tırnak sorunlarını önler)")
    ap.add_argument("--out", help="çıktı wav yolu (tekli mod)")
    ap.add_argument("--batch-manifest", dest="batch_manifest",
                     help="toplu mod: [{'text':..,'out':..}, ...] içeren JSON dosyası; model BİR KEZ yüklenir")
    ap.add_argument("--model", default="", help="model dizini (boşsa vendor default)")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--lang", default="tr", help="referans otomatik-transkripsiyon dili")
    a = ap.parse_args()

    batch_items = None
    if a.batch_manifest:
        batch_items = json.loads(Path(a.batch_manifest).read_text(encoding="utf-8"))
        if not batch_items:
            ap.error("--batch-manifest boş")
    else:
        if a.text_file:
            a.text = Path(a.text_file).read_text(encoding="utf-8").strip()
        if not a.text:
            ap.error("--text, --text-file veya --batch-manifest gerekli")
        if not a.out:
            ap.error("--out gerekli (tekli mod)")

    root = Path(__file__).resolve().parent.parent
    repo = root / "vendor" / "CosyVoice"
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo / "third_party" / "Matcha-TTS"))
    _install_tn_shim()

    # torchaudio 2.11 ses I/O'yu torchcodec'e devrediyor; torchcodec de FFmpeg DLL'lerini
    # arar. vendor/ffmpeg-shared/bin'i DLL yoluna ekle (yoksa 'TorchCodec is required' hatası).
    import os
    ffbin = root / "vendor" / "ffmpeg-shared" / "bin"
    if hasattr(os, "add_dll_directory") and ffbin.exists():
        os.add_dll_directory(str(ffbin))

    import torch
    import torchaudio

    # torchaudio 2.11'in torchcodec decoder'ı Blackwell'de bozuk ('video_tensor must be
    # kUInt8') VE 'backend' parametresini yok sayıyor. torchaudio.load/save'i tamamen
    # soundfile ile DEĞİŞTİR (torchcodec devre dışı). CosyVoice'un load_wav'ı hem dosya
    # yolu hem de önceden-yüklenmiş tensör geçirdiği için ikisini de ele al.
    import soundfile as sf

    def _ta_load(uri, *a, **k):
        if isinstance(uri, torch.Tensor):
            return uri, 16000  # prompt_speech_16k zaten 16kHz tensör
        data, sr = sf.read(str(uri), dtype="float32", always_2d=True)  # (frames, ch)
        return torch.from_numpy(data.T).contiguous(), sr

    def _ta_save(uri, src, sample_rate, *a, **k):
        arr = src.detach().cpu().numpy()
        if arr.ndim == 2:
            arr = arr.T  # (frames, ch)
        sf.write(str(uri), arr, int(sample_rate))

    torchaudio.load, torchaudio.save = _ta_load, _ta_save

    from cosyvoice.cli.cosyvoice import CosyVoice2
    from cosyvoice.utils.file_utils import load_wav

    model_dir = a.model or str(repo / "pretrained_models" / "CosyVoice2-0.5B")

    ref_text = a.ref_text.strip()
    if not ref_text:
        # NOT: faster-whisper (ctranslate2) Blackwell/sm_120'de cuBLAS_NOT_SUPPORTED verir.
        # Referans transkripsiyonu tek seferlik + kısa olduğu için CPU'da çalıştırıyoruz;
        # CosyVoice'un ASIL sentezi GPU'da (torch cu128, Blackwell'de çalışıyor) kalır.
        from faster_whisper import WhisperModel
        wm = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = wm.transcribe(a.ref, language=a.lang)
        ref_text = " ".join(s.text for s in segs).strip()
        del wm
    print(f"[cosy] ref_text: {ref_text[:80]!r}")

    cosy = CosyVoice2(model_dir, load_jit=False, load_trt=False, fp16=False)
    prompt_16k = load_wav(a.ref, 16000)

    def _synth_one(text: str, out_path: Path, speed: float) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        chunks = []
        for r in cosy.inference_zero_shot(text, ref_text, prompt_16k, stream=a.stream, speed=speed):
            chunks.append(r["tts_speech"])
        if not chunks:
            raise RuntimeError("CosyVoice hiç ses üretmedi")
        speech = torch.cat(chunks, dim=1) if len(chunks) > 1 else chunks[0]
        torchaudio.save(str(out_path), speech, cosy.sample_rate)
        print(f"[cosy] yazıldı: {out_path} ({speech.shape[-1] / cosy.sample_rate:.1f}s)")

    if batch_items is not None:
        # Model BİR KEZ yüklendi (yukarıda); tüm öğeler aynı süreçte, tekrar yükleme olmadan
        # sentezlenir — 150+ segmentlik bir işte segment başına ~2-3dk'lık yükleme maliyetini
        # tamamen ortadan kaldırır (yalnızca bu subprocess'in ilk açılışında bir kez ödenir).
        n = len(batch_items)
        for idx, item in enumerate(batch_items):
            out_path = Path(item["out"])
            speed = float(item.get("speed", a.speed))
            _synth_one(item["text"], out_path, speed)
            print(f"[cosy] toplu {idx + 1}/{n} tamam")
    else:
        _synth_one(a.text, Path(a.out), a.speed)


if __name__ == "__main__":
    main()
