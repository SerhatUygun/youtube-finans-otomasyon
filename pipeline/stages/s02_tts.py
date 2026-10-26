"""Aşama 02: Seslendirme (ses klonlama) — İKİ motor (config tts.engine ile seçilir):

  - xtts_v2 : Coqui XTTS-v2 (varsayılan). In-process, çok dilli, iyi Türkçe. Coqui kapandı
              (2024) ama model açık kaynak topluluğunda çalışıyor.
  - f5tts   : (2 Ağu) F5-TTS — daha doğal + daha temiz ses klonlama. İzole venv
              (vendor/F5-TTS) + subprocess CLI (f5-tts_infer-cli). Blackwell için torch cu128.
              KAPALI kalır (engine değiştirilene kadar). setup_f5tts.ps1 ile kurulur.
  - voxcpm  : (24 Eyl) VoxCPM2 — Türkçe dahil 30 dil, 48kHz, Apache-2.0. İzole venv
              (vendor/VoxCPM) + toplu subprocess (scripts/run_voxcpm.py, model bir kez yüklenir).
              setup_voxcpm.ps1 ile kurulur.

Girdi: output/<job_id>/script.json
Çıktı: output/<job_id>/audio.wav
"""
import json
import os
import subprocess
from pathlib import Path

from pipeline import tr_number_speech
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("s02_tts")

# XTTS-v2, Coqui'nin ticari olmayan CPML lisansı altındadır (bkz. https://coqui.ai/cpml).
# Kanal parasal kazanç amaçlıysa Coqui'den ticari lisans almayı değerlendir.
# Bu satır, Task Scheduler ile denetimsiz çalışacağı için etkileşimli [y/n] TOS
# sorusunu otomatik "evet" ile geçer.
os.environ.setdefault("COQUI_TOS_AGREED", "1")

_TTS_MODEL_CACHE = {}

# XTTS-v2 her segment seslendirmesinde speaker_wav'dan konuşmacı özelliğini yeniden
# çıkarır. Referans dosyası çok uzunsa (örn. tam bir kayıt) bu işlem segment başına
# ciddi şekilde yavaşlar ve kalite de kısa/temiz bir klipten daha iyi olmaz.
# Bu yüzden uzun dosyalardan tek seferlik kısa bir kesit çıkarıp onu kullanıyoruz.
MAX_RAW_REFERENCE_SECONDS = 45
REFERENCE_CLIP_SECONDS = 25
REFERENCE_CLIP_OFFSET_SECONDS = 60


def _ffprobe_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return float(out.stdout.strip())


def _prepare_reference_clip(speaker_wav):
    duration = _ffprobe_duration(speaker_wav)
    if duration <= MAX_RAW_REFERENCE_SECONDS:
        return speaker_wav

    cache_dir = speaker_wav.parent / ".cache"
    cache_dir.mkdir(exist_ok=True)
    src_stat = speaker_wav.stat()
    clip_path = cache_dir / f"{speaker_wav.stem}_clip_{int(src_stat.st_mtime)}.wav"
    if clip_path.exists():
        return clip_path

    offset = min(REFERENCE_CLIP_OFFSET_SECONDS, max(duration - REFERENCE_CLIP_SECONDS, 0))
    log.info(
        f"Referans kaydı {duration:.0f}s uzunluğunda; {offset:.0f}s-{offset + REFERENCE_CLIP_SECONDS:.0f}s "
        f"arası {REFERENCE_CLIP_SECONDS}s'lik kesit tek seferlik çıkarılıp önbelleğe alınıyor -> {clip_path.name}"
    )
    cmd = [
        "ffmpeg", "-y", "-ss", str(offset), "-t", str(REFERENCE_CLIP_SECONDS),
        "-i", str(speaker_wav), str(clip_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        log.error(result.stderr[-2000:])
        raise RuntimeError("Referans ses kesiti çıkarılamadı (ffmpeg başarısız)")
    return clip_path


def _patch_torchaudio_soundfile():
    """8 Ağu: XTTS (torchaudio.load ile referans sesi okur) bu makinede (Blackwell GPU)
    torchcodec DLL'lerini yükleyemiyor ('Could not find module libtorchcodec_core*.dll')
    -> senteze hiç başlamadan çöküyordu. CosyVoice tarafında zaten uygulanan aynı fix:
    (1) vendor/ffmpeg-shared/bin'i DLL arama yoluna ekle, (2) torchaudio.load/save'i
    torchcodec'i hiç kullanmayan soundfile tabanlı sürümle değiştir."""
    import torch
    import torchaudio
    if getattr(torchaudio, "_soundfile_patched", False):
        return
    ffbin = ROOT / "vendor" / "ffmpeg-shared" / "bin"
    if hasattr(os, "add_dll_directory") and ffbin.exists():
        os.add_dll_directory(str(ffbin))
    import soundfile as sf

    def _ta_load(uri, *a, **k):
        if isinstance(uri, torch.Tensor):
            return uri, 16000
        data, sr = sf.read(str(uri), dtype="float32", always_2d=True)
        return torch.from_numpy(data.T).contiguous(), sr

    def _ta_save(uri, src, sample_rate, *a, **k):
        arr = src.detach().cpu().numpy()
        if arr.ndim == 2:
            arr = arr.T
        sf.write(str(uri), arr, int(sample_rate))

    torchaudio.load, torchaudio.save = _ta_load, _ta_save
    torchaudio._soundfile_patched = True


def _get_model(model_name: str, device: str):
    if model_name not in _TTS_MODEL_CACHE:
        _patch_torchaudio_soundfile()
        from TTS.api import TTS
        log.info(f"XTTS modeli yükleniyor: {model_name} ({device})")
        _TTS_MODEL_CACHE[model_name] = TTS(model_name).to(device)
    return _TTS_MODEL_CACHE[model_name]


def _synth_f5_segment(cfg, seg_text, speaker_wav, seg_path, language):
    """Tek segmenti F5-TTS ile seslendirir (izole venv, subprocess CLI). F5-TTS ses
    klonlama için referans ses + O SESİN METNİ (ref_text) ister. Çıktı seg_path'e yazılır."""
    venv_python = (ROOT / cfg.get("f5_venv_python", "vendor/F5-TTS/.venv/Scripts/python.exe")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"F5-TTS venv python yok: {venv_python} (scripts/setup_f5tts.ps1 çalıştır)")
    ref_text = cfg.get("f5_ref_text")
    if not ref_text:
        raise RuntimeError(
            "F5-TTS için tts.f5_ref_text gerekli (referans ses kaydının BİREBİR metni). "
            "config.yaml tts.f5_ref_text'e speaker_wav'daki konuşmanın transkriptini yaz."
        )
    out_dir = seg_path.parent
    out_name = seg_path.name
    cmd = [
        str(venv_python), "-m", "f5_tts.infer.infer_cli",
        "--model", cfg.get("f5_model", "F5TTS_v1_Base"),
        "--ref_audio", str(speaker_wav),
        "--ref_text", ref_text,
        "--gen_text", seg_text,
        "--output_dir", str(out_dir),
        "--output_file", out_name,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not seg_path.exists():
        raise RuntimeError(f"F5-TTS segment sentezi başarısız:\n{(res.stderr or res.stdout)[-1500:]}")


def _synth_cosy_segment(cfg, seg_text, speaker_wav, seg_path, language):
    """Tek segmenti CosyVoice2 ile seslendirir (izole venv, subprocess).
    Zero-shot klonlama: referans ses + (opsiyonel) referans metni. ref_text boşsa
    run_cosyvoice.py faster-whisper ile otomatik yazıya döker. Çıktı seg_path'e yazılır.
    NOT: run() artık çoklu-segmentli işler için bunun yerine _synth_cosy_batch kullanır
    (bkz. aşağı) — bu fonksiyon tekli/manuel kullanım için saklı kalır."""
    venv_python = (ROOT / cfg.get("cosy_venv_python", "vendor/CosyVoice/.venv/Scripts/python.exe")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"CosyVoice venv python yok: {venv_python} (scripts/setup_cosyvoice.ps1 çalıştır)")
    script = (ROOT / "scripts" / "run_cosyvoice.py").resolve()
    cmd = [
        str(venv_python), str(script),
        "--ref", str(speaker_wav),
        "--text", seg_text,
        "--out", str(seg_path),
        "--lang", language,
        "--speed", str(cfg.get("cosy_speed", 1.0)),
    ]
    if cfg.get("cosy_ref_text"):
        cmd += ["--ref-text", cfg["cosy_ref_text"]]
    if cfg.get("cosy_model_dir"):
        cmd += ["--model", str((ROOT / cfg["cosy_model_dir"]).resolve())]
    if cfg.get("cosy_stream"):
        cmd.append("--stream")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not seg_path.exists():
        raise RuntimeError(f"CosyVoice segment sentezi başarısız:\n{(res.stderr or res.stdout)[-1800:]}")


def _synth_cosy_batch(cfg, items, speaker_wav, out_dir, language):
    """TÜM CosyVoice segmentlerini TEK subprocess çağrısında sentezler — model yalnızca
    BİR KEZ yüklenir (7 Ağu: segment başına ayrı subprocess ~2-3dk model yükleme maliyeti
    getiriyordu; 150+ segmentlik bir haftalık videoda bu saatlerce sürüyordu).
    items: [(seg_path: Path, seg_text: str), ...]."""
    venv_python = (ROOT / cfg.get("cosy_venv_python", "vendor/CosyVoice/.venv/Scripts/python.exe")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"CosyVoice venv python yok: {venv_python} (scripts/setup_cosyvoice.ps1 çalıştır)")
    script = (ROOT / "scripts" / "run_cosyvoice.py").resolve()

    manifest = [{"text": text, "out": str(seg_path)} for seg_path, text in items]
    manifest_path = out_dir / "_cosy_batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    cmd = [
        str(venv_python), str(script),
        "--ref", str(speaker_wav),
        "--batch-manifest", str(manifest_path),
        "--lang", language,
        "--speed", str(cfg.get("cosy_speed", 1.0)),
    ]
    if cfg.get("cosy_ref_text"):
        cmd += ["--ref-text", cfg["cosy_ref_text"]]
    if cfg.get("cosy_model_dir"):
        cmd += ["--model", str((ROOT / cfg["cosy_model_dir"]).resolve())]
    if cfg.get("cosy_stream"):
        cmd.append("--stream")

    log.info(f"CosyVoice toplu sentez başlıyor: {len(items)} segment (model bir kez yüklenecek)")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    missing = [str(p) for p, _ in items if not p.exists()]
    if res.returncode != 0 or missing:
        raise RuntimeError(
            f"CosyVoice toplu sentez başarısız (eksik: {len(missing)}/{len(items)}):\n"
            f"{(res.stderr or res.stdout)[-2500:]}"
        )


def _synth_voxcpm_batch(cfg, items, speaker_wav, out_dir):
    """TÜM segmentleri VoxCPM2 ile TEK subprocess çağrısında sentezler (model bir kez yüklenir).
    items: [(seg_path: Path, seg_text: str), ...]."""
    venv_python = (ROOT / cfg.get("voxcpm_venv_python", "vendor/VoxCPM/.venv/Scripts/python.exe")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"VoxCPM venv python yok: {venv_python} (scripts/setup_voxcpm.ps1 çalıştır)")
    script = (ROOT / "scripts" / "run_voxcpm.py").resolve()

    manifest = [{"text": text, "out": str(seg_path)} for seg_path, text in items]
    manifest_path = out_dir / "_voxcpm_batch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    cmd = [
        str(venv_python), str(script),
        "--ref", str(speaker_wav),
        "--batch-manifest", str(manifest_path),
        "--model", cfg.get("voxcpm_model", "openbmb/VoxCPM2"),
        "--cfg", str(cfg.get("voxcpm_cfg", 2.0)),
        "--steps", str(cfg.get("voxcpm_steps", 10)),
    ]
    if cfg.get("voxcpm_ref_text"):
        cmd += ["--ref-text", cfg["voxcpm_ref_text"]]

    log.info(f"VoxCPM2 toplu sentez başlıyor: {len(items)} segment (model bir kez yüklenecek)")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    missing = [str(p) for p, _ in items if not p.exists()]
    if res.returncode != 0 or missing:
        raise RuntimeError(
            f"VoxCPM2 toplu sentez başarısız (eksik: {len(missing)}/{len(items)}):\n"
            f"{(res.stderr or res.stdout)[-2500:]}"
        )


def run(job_id: str) -> dict:
    cfg = load_config()["tts"]
    speaker_wav = ROOT / cfg["speaker_wav"]
    if not speaker_wav.exists():
        raise RuntimeError(
            f"Ses referans dosyası bulunamadı: {speaker_wav}\n"
            "10-30 saniyelik temiz bir ses kaydını assets/voice_reference/sample.wav olarak kaydet."
        )

    speaker_wav = _prepare_reference_clip(speaker_wav)

    script_file = job_path(job_id, "script.json")
    script_data = json.loads(script_file.read_text(encoding="utf-8"))
    segments = script_data["segments"] or [script_data["script"]]

    # Dil per-iş override edilebilir (manuel metin işlerinde script.json'a yazılır);
    # yoksa config'teki genel dil kullanılır.
    language = script_data.get("language") or cfg.get("language", "tr")

    # Motor seçimi: cosyvoice (ÖNERİLEN) | xtts_v2 (in-process) | f5tts (izole venv).
    engine = (cfg.get("engine") or "xtts_v2").lower()
    use_f5 = engine in ("f5tts", "f5-tts", "f5")
    use_cosy = engine in ("cosyvoice", "cosyvoice2", "cosy")
    use_voxcpm = engine in ("voxcpm", "voxcpm2")

    # XTTS yalnızca xtts_v2 motorunda yüklenir (F5/CosyVoice/VoxCPM kendi izole venv'lerinde çalışır).
    tts = None
    if not use_f5 and not use_cosy and not use_voxcpm:
        tts = _get_model(cfg["model_name"], cfg.get("device", "cuda"))

    # Takılma (kelime tekrarı / kekeleme / uzun "ııı") önleyici XTTS parametreleri.
    # config tts.* altından okunur; verilmezse XTTS'in kendi varsayılanları geçerli olur.
    split_sentences = bool(cfg.get("split_sentences", True))
    infer_kwargs = {}
    for key in ("repetition_penalty", "temperature", "length_penalty", "top_k", "top_p", "speed"):
        if cfg.get(key) is not None:
            infer_kwargs[key] = cfg[key]

    out_dir = job_path(job_id, "tts_segments")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sesletilecek (index, metin, çıktı yolu) listesini önce topla; motor seçimine göre
    # ya TEK toplu çağrıda (cosyvoice — model bir kez yüklenir) ya da segment-segment
    # (xtts_v2/f5tts, eski davranışla birebir aynı) sentezlenir.
    pending: list[tuple[int, str, Path]] = []
    for i, seg_text in enumerate(segments):
        seg_text = seg_text.strip()
        if not seg_text:
            continue
        # 8 Ağu: rakam/yüzde ifadeleri ("47,69", "%1,9") TTS'te anlaşılmaz okunuyordu —
        # sadece SESLENDİRME girdisini Türkçe kelimelere çeviriyoruz; script.json/altyazı
        # metnindeki orijinal rakam DEĞİŞMİYOR (bkz. pipeline/tr_number_speech.py).
        if language == "tr":
            seg_text = tr_number_speech.normalize_for_tts(seg_text)
        seg_path = out_dir / f"seg_{i:03d}.wav"
        pending.append((i, seg_text, seg_path))

    if not pending:
        raise RuntimeError("Seslendirilecek segment bulunamadı")

    if use_cosy:
        _synth_cosy_batch(
            cfg, [(seg_path, seg_text) for _, seg_text, seg_path in pending],
            speaker_wav, out_dir, language,
        )
    elif use_voxcpm:
        _synth_voxcpm_batch(
            cfg, [(seg_path, seg_text) for _, seg_text, seg_path in pending],
            speaker_wav, out_dir,
        )
    else:
        for i, seg_text, seg_path in pending:
            log.info(f"Segment {i + 1}/{len(segments)} seslendiriliyor ({len(seg_text)} karakter, motor={engine})")
            if use_f5:
                _synth_f5_segment(cfg, seg_text, speaker_wav, seg_path, language)
            else:
                tts.tts_to_file(
                    text=seg_text,
                    speaker_wav=str(speaker_wav),
                    language=language,
                    file_path=str(seg_path),
                    # Cümlelere bölerek sentez uzun metinde takılmayı, repetition_penalty ise
                    # kelime tekrarını/kekelemeyi bastırır (bkz. config.yaml tts.*).
                    split_sentences=split_sentences,
                    **infer_kwargs,
                )

    segment_indices = [i for i, _, _ in pending]
    segment_files = [seg_path for _, _, seg_path in pending]

    from pydub import AudioSegment
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=int(cfg.get("segment_pause_ms", 350)))
    timing = []
    for pos, (i, seg_path) in enumerate(zip(segment_indices, segment_files)):
        clip = AudioSegment.from_wav(seg_path)
        start_ms = len(combined)
        combined += clip
        timing.append({"segment_index": i, "text": segments[i], "start_ms": start_ms, "end_ms": len(combined)})
        if pos < len(segment_files) - 1:
            combined += pause

    audio_file = job_path(job_id, "audio.wav")
    combined.export(audio_file, format="wav")

    timing_file = job_path(job_id, "segments_timing.json")
    timing_file.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(f"Birleştirilmiş ses yazıldı: {audio_file} ({len(combined) / 1000:.1f}s)")
    return {"audio_file": str(audio_file), "duration_ms": len(combined)}


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
