"""SFX Director — 18 Eyl eklendi (SIFIR_MALIYET_PROFESYONEL_EDIT_GELISTIRME_REHBERI.md
Modül 1). Bir işin script.json + segments_timing.json + video_broll_manifest.json'ına
bakıp hangi milisaniyede hangi ses efektinin çalacağına karar verir; s07_edit.py bu
cue listesini ffmpeg'in tek montaj komutuna (adelay+amix) ekler.

Herhangi bir adım başarısız olursa (sfx dosyası yok, manifest bozuk, vb.) BOŞ liste
döner — çağıran taraf sessizce sfx'siz devam eder, video hiçbir zaman bozulmaz.
"""
import json
import re

from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("sfx_director")

SFX_DIR = ROOT / "assets" / "sfx"

# composition_id (s05b_motion_graphics.py'nin ürettiği video_broll_manifest "prompt" alanı)
# -> segment başlangıcında çalacak sfx dosyası.
_MOTION_GRAPHIC_SFX = {
    "TitleCard": "whoosh_fast",
    "MarketChart": "whoosh_subtle",
    "StatCallout": "pop_clean",
    "CompareBars": "bubble_pop",
    "KeyQuote": "impact_soft",
    "NewspaperHighlight": "paper_slide",  # Modül 2 henüz yoksa bu prompt hiç üretilmez, no-op
}

# MarketChart segmentlerinin altına, segment süresince (kırpılarak) döşenen döngü sesi.
_TICKER_SFX = "ticker_loop"

_MONEY_KEYWORDS = (
    "lira", "dolar", "euro", "avro", "bütçe", "enflasyon", "maaş", "fiyat",
    "borsa", "faiz", "kredi", "vergi", "gelir", "gider", "zam",
)
_DROP_PATTERN = re.compile(r"%\s*\d+|(düş|çök|gerile|kayb|kriz|resesyon|sok|şok)", re.IGNORECASE)


def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"{path} okunamadı/bozuk JSON, atlanıyor: {e}")
    return None


def _sfx_path(name: str):
    p = SFX_DIR / f"{name}.wav"
    return p if p.exists() else None


def pick_cues(job_id: str) -> list[dict]:
    """[{"start_ms": int, "file": Path, "gain_db": float, "trim_s": float|None}, ...] döner.
    Aynı milisaniyede (segment başında) birden fazla aday varsa (ör. hem motion-graphic
    hem para-anahtar-kelimesi) sadece EN ÖNCELİKLİSİ (motion-graphic) kullanılır — üst üste
    binen sfx'ler karman çorman ses vermesin diye."""
    script_data = _load_json(job_path(job_id, "script.json")) or {}
    timing = _load_json(job_path(job_id, "segments_timing.json")) or []
    video_manifest = _load_json(job_path(job_id, "video_broll_manifest.json")) or []
    segments_text = script_data.get("segments") or []
    if not timing:
        return []

    prompt_by_segment = {m["segment_index"]: m.get("prompt") for m in video_manifest}
    duration_by_segment = {
        t["segment_index"]: max((t["end_ms"] - t["start_ms"]) / 1000.0, 0.3) for t in timing
    }
    start_by_segment = {t["segment_index"]: t["start_ms"] for t in timing}

    cues = []
    used_segments = set()

    # 1) Motion-graphic segmentleri -> her birine kendi girizgah sfx'i.
    for seg_idx, prompt in prompt_by_segment.items():
        sfx_name = _MOTION_GRAPHIC_SFX.get(prompt)
        if not sfx_name:
            continue
        sfx_file = _sfx_path(sfx_name)
        if not sfx_file or seg_idx not in start_by_segment:
            continue
        cues.append({"start_ms": start_by_segment[seg_idx], "file": sfx_file, "gain_db": -9.0, "trim_s": None})
        used_segments.add(seg_idx)
        # MarketChart altına, segment süresi kadar kırpılmış ticker döşe.
        if prompt == "MarketChart":
            ticker_file = _sfx_path(_TICKER_SFX)
            if ticker_file:
                cues.append({
                    "start_ms": start_by_segment[seg_idx], "file": ticker_file, "gain_db": -18.0,
                    "trim_s": duration_by_segment.get(seg_idx, 5.0),
                })

    # 2) Chart olmayan segmentlerde metin bazlı vurgular (para / dramatik düşüş).
    for t in timing:
        seg_idx = t["segment_index"]
        if seg_idx in used_segments or seg_idx >= len(segments_text):
            continue
        text = (segments_text[seg_idx] or "").lower()
        if not text:
            continue
        sfx_name = None
        if _DROP_PATTERN.search(text):
            sfx_name = "sub_boom"
        elif any(k in text for k in _MONEY_KEYWORDS):
            sfx_name = "coin_drop"
        if not sfx_name:
            continue
        sfx_file = _sfx_path(sfx_name)
        if not sfx_file:
            continue
        cues.append({"start_ms": t["start_ms"], "file": sfx_file, "gain_db": -11.0, "trim_s": None})
        used_segments.add(seg_idx)

    cues.sort(key=lambda c: c["start_ms"])
    return cues


def build_audio_filter(cues: list[dict], narration_label: str, first_input_index: int):
    """cues + narration'ı tek bir amix zincirine bağlayan (extra_inputs, filter_parts,
    output_label) üçlüsü döner. cues boşsa (None, [], narration_label) döner -> çağıran
    taraf narration_label'ı OLDUĞU GİBİ map'lemeye devam eder, davranış değişmez."""
    if not cues:
        return [], [], narration_label

    extra_inputs = []
    mix_labels = [narration_label]
    idx = first_input_index
    for i, cue in enumerate(cues):
        extra_inputs += ["-i", str(cue["file"])]
        lbl = f"sfx{i}"
        chain = f"[{idx}:a]"
        if cue.get("trim_s"):
            chain += f"atrim=0:{cue['trim_s']:.3f},"
        chain += f"adelay={cue['start_ms']}|{cue['start_ms']},volume={cue['gain_db']}dB[{lbl}]"
        mix_labels.append(lbl)
        idx += 1

    filter_parts = []
    for i, cue in enumerate(cues):
        chain = f"[{first_input_index + i}:a]"
        if cue.get("trim_s"):
            chain += f"atrim=0:{cue['trim_s']:.3f},"
        chain += f"adelay={cue['start_ms']}|{cue['start_ms']},volume={cue['gain_db']}dB[sfx{i}]"
        filter_parts.append(chain)

    inputs_ref = "".join(f"[{lbl}]" for lbl in mix_labels)
    filter_parts.append(
        f"{inputs_ref}amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0:normalize=0[aoutmix]"
    )
    return extra_inputs, filter_parts, "aoutmix"
