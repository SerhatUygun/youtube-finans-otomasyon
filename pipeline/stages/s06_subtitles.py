"""Aşama 06: Altyazı.

Girdi: output/<job_id>/audio.wav  (+ varsa segments_timing.json — TERCİH edilir)
Çıktı: output/<job_id>/subtitles.srt

İki yol:
  1) TERCİH — segments_timing.json varsa: altyazı BİLİNEN script metninden üretilir
     (s02 TTS'in seslendirdiği metin), her segmentin zaman penceresi kelimelere orantılı
     dağıtılır ve 3-4 kelimelik kısa bloklara bölünür. Böylece altyazı metni script'le
     BİREBİR aynıdır (whisper transkript hataları — "ons" -> "10" gibi — OLMAZ). KUSURSUZ.
  2) YEDEK — timing yoksa (ör. elle eklenmiş ses): faster-whisper ile kelime-seviyesi
     transkript + 3-4 kelimelik bloklama.
"""
import json

from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import job_path

log = get_logger("s06_subtitles")

_WHISPER_MODEL_CACHE = {}


def _get_model(model_size: str, device: str, compute_type: str):
    key = (model_size, device, compute_type)
    if key not in _WHISPER_MODEL_CACHE:
        from faster_whisper import WhisperModel
        log.info(f"faster-whisper modeli yükleniyor: {model_size} ({device}, {compute_type})")
        _WHISPER_MODEL_CACHE[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _WHISPER_MODEL_CACHE[key]


def _format_timestamp(seconds: float) -> str:
    ms = int(round(max(seconds, 0.0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _write_srt(cues, srt_file):
    """cues: [(start_s, end_s, text), ...] -> SRT dosyası (bloklar çakışmaz)."""
    lines = []
    for i, (start, end, text) in enumerate(cues, start=1):
        if i < len(cues):
            nxt = cues[i][0]
            if end > nxt:
                end = nxt
        lines.append(str(i))
        lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(max(end, start + 0.05))}")
        lines.append(text)
        lines.append("")
    srt_file.write_text("\n".join(lines), encoding="utf-8")


def _flat_words_from_timing(timing):
    """Bilinen segment metinlerinden HER kelime için ayrı (start_s, end_s, text) üretir.
    [start_ms, end_ms] penceresi, kelimenin karakter uzunluğuna orantılı dağıtılır
    (konuşma hızına yakın, akıcı; metin script'le birebir doğru). Karaoke-stili kelime
    vurgusu için gereken tekil kelime zaman damgalarının kaynağı budur."""
    words_out = []
    for seg in sorted(timing, key=lambda t: t.get("start_ms", 0)):
        text = (seg.get("text") or "").strip()
        words = text.split()
        if not words:
            continue
        seg_start = seg.get("start_ms", 0) / 1000.0
        seg_end = seg.get("end_ms", seg.get("start_ms", 0)) / 1000.0
        seg_dur = max(seg_end - seg_start, 0.15)
        total_chars = sum(len(w) for w in words) or 1

        cum = []
        c = 0
        for w in words:
            cum.append(c)
            c += len(w)

        for i, w in enumerate(words):
            chars_before = cum[i]
            chars_after = cum[i] + len(w)
            start = seg_start + seg_dur * (chars_before / total_chars)
            end = seg_start + seg_dur * (chars_after / total_chars)
            words_out.append((start, end, w))
    return words_out


def _group_words(words, group_size):
    """Düz kelime listesini ~group_size'lık bloklara ayırır (sıralı, kelime bütünlüğü korunur)."""
    step = max(int(group_size), 1)
    return [words[k:k + step] for k in range(0, len(words), step) if words[k:k + step]]


def _cues_from_word_groups(word_groups):
    """Bloklardan SRT/animasyonsuz altyazı cue'ları üretir: [(start_s, end_s, text), ...]."""
    return [(g[0][0], g[-1][1], " ".join(w[2] for w in g)) for g in word_groups]


def _karaoke_from_word_groups(word_groups):
    """Bloklardan, HER kelimenin kendi zaman damgasını koruyan karaoke yapısı üretir
    (Remotion Captions.tsx'in aktif kelimeyi vurgulaması için)."""
    return [
        {
            "start": g[0][0],
            "end": g[-1][1],
            "words": [{"text": w[2], "start": w[0], "end": w[1]} for w in g],
        }
        for g in word_groups
    ]


def _write_karaoke(word_groups, out_file):
    if not word_groups:
        return
    out_file.write_text(
        json.dumps(_karaoke_from_word_groups(word_groups), ensure_ascii=False), encoding="utf-8"
    )


def _whisper_word_groups(audio_file, cfg, words_per_cue):
    """YEDEK: faster-whisper ile kelime-seviyesi transkript + bloklama. Kelime zaman damgaları
    yoksa (words_per_cue < 1) segment-seviyesinde tek-kelimelik sahte blok döner (karaoke devre
    dışı kalır, SRT yine de doğru üretilir)."""
    language = cfg.get("language", "tr")
    model = _get_model(cfg["model_size"], cfg.get("device", "cuda"), cfg.get("compute_type", "int8"))
    log.info(f"Altyazı whisper ile çıkarılıyor (yedek yol): {audio_file} (dil={language})")
    segments, info = model.transcribe(
        str(audio_file), language=language, vad_filter=True,
        word_timestamps=words_per_cue >= 1,
    )
    all_words = []
    for seg in segments:
        words = list(getattr(seg, "words", None) or [])
        if words_per_cue >= 1 and words:
            for w in words:
                text = w.word.strip()
                if text:
                    all_words.append((w.start, w.end, text))
        else:
            text = seg.text.strip()
            if text:
                all_words.append((seg.start, seg.end, text))
    return _group_words(all_words, words_per_cue)


def _whisperx_word_groups(audio_file, cfg, words_per_cue):
    """YEDEK (whisperx motoru): faster-whisper transkript + wav2vec2 FORCED ALIGNMENT ->
    <100ms kelime zaman damgaları (karaoke/kelime-vurgu için faster-whisper'dan daha kesin).
    İzole gerektirmez; ana venv'e `pip install whisperx` (setup_whisperx.ps1) ile kurulur."""
    import whisperx

    device = cfg.get("device", "cuda")
    language = cfg.get("language", "tr")
    compute_type = cfg.get("compute_type", "int8")
    log.info(f"Altyazı WhisperX ile çıkarılıyor (forced-alignment): {audio_file} (dil={language})")
    model = whisperx.load_model(cfg.get("model_size", "large-v3"), device, compute_type=compute_type,
                                language=language)
    audio = whisperx.load_audio(str(audio_file))
    result = model.transcribe(audio, language=language)
    align_model, metadata = whisperx.load_align_model(language_code=language, device=device)
    aligned = whisperx.align(result["segments"], align_model, metadata, audio, device,
                             return_char_alignments=False)

    all_words = []
    for seg in aligned.get("segments", []):
        for w in seg.get("words", []):
            if w.get("start") is not None and w.get("end") is not None:
                text = w["word"].strip()
                if text:
                    all_words.append((w["start"], w["end"], text))
    return _group_words(all_words, words_per_cue)


def run(job_id: str) -> dict:
    cfg = load_config()["subtitles"]
    audio_file = job_path(job_id, "audio.wav")
    if not audio_file.exists():
        raise RuntimeError(f"Ses dosyası bulunamadı: {audio_file}")

    words_per_cue = int(cfg.get("words_per_cue", 3) or 1)
    srt_file = job_path(job_id, "subtitles.srt")
    karaoke_file = job_path(job_id, "captions_words.json")

    # Dil per-iş (script.json) — log/yedek için.
    language = cfg.get("language", "tr")
    script_file = job_path(job_id, "script.json")
    if script_file.exists():
        try:
            language = json.loads(script_file.read_text(encoding="utf-8")).get("language") or language
        except Exception:
            pass

    # 1) TERCİH: bilinen script metni + segment zamanlaması (whisper hatası olmaz).
    timing_file = job_path(job_id, "segments_timing.json")
    if timing_file.exists():
        try:
            timing = json.loads(timing_file.read_text(encoding="utf-8"))
        except Exception:
            timing = None
        if timing:
            words_flat = _flat_words_from_timing(timing)
            word_groups = _group_words(words_flat, words_per_cue)
            cues = _cues_from_word_groups(word_groups)
            if cues:
                _write_srt(cues, srt_file)
                _write_karaoke(word_groups, karaoke_file)
                log.info(
                    f"Altyazı yazıldı (script metninden, kusursuz): {srt_file} "
                    f"({len(cues)} blok, ~{words_per_cue} kelime/blok, dil={language})"
                )
                return {"srt_file": str(srt_file), "segment_count": len(cues), "source": "script"}
        log.warning("segments_timing.json'dan altyazı üretilemedi, whisper'a düşülüyor")

    # 2) YEDEK: transkript. engine=whisperx ise forced-alignment (daha kesin kelime zamanı),
    #    aksi halde faster-whisper. (Not: TERCİH yolu script-timing olduğu için bu yol çoğu
    #    işte hiç çalışmaz; yalnızca elle eklenmiş ses için devreye girer.)
    engine = (cfg.get("engine") or "faster-whisper").lower()
    if engine == "whisperx":
        try:
            word_groups = _whisperx_word_groups(audio_file, cfg, words_per_cue)
        except Exception as e:
            log.warning(f"WhisperX başarısız ({e}), faster-whisper'a düşülüyor")
            word_groups = _whisper_word_groups(audio_file, cfg, words_per_cue)
    else:
        word_groups = _whisper_word_groups(audio_file, cfg, words_per_cue)
    cues = _cues_from_word_groups(word_groups)
    _write_srt(cues, srt_file)
    if words_per_cue >= 1:
        _write_karaoke(word_groups, karaoke_file)
    log.info(
        f"Altyazı yazıldı (whisper yedek): {srt_file} "
        f"({len(cues)} blok, ~{words_per_cue} kelime/blok)"
    )
    return {"srt_file": str(srt_file), "segment_count": len(cues), "source": "whisper"}


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
