"""Zamanlanmış piyasa/haber Shorts üretici — Windows Task Scheduler tarafından günde
3 kez çağrılır (bkz. scripts/setup_scheduled_tasks.ps1):
  10:30 morning_open  -> Türkiye piyasa açılışı (BIST100, USD/TRY, altın + TR haberleri)
  15:30 us_market     -> ABD borsası açılışı + küresel görünüm (S&P500, Nasdaq, BTC)
  18:00 evening_wrap  -> Günün dünya geneli özeti (GDELT/Google News ağırlıklı)

Web panelindeki "beyin" (/api/brain/create-job, research=true) akışıyla AYNI üretim
yolunu (persona.generate_researched_script -> orchestrator) insansız/CLI olarak
çalıştırır. YouTube yüklemesi HER ZAMAN private kalır (config.yaml youtube.privacy_status);
public'e alma kararı web panelden ("Onay Bekleyenler") insanda kalır -- bkz. app.py
/api/jobs/{id}/publish.

Kullanım:
    python -m tools.run_scheduled_short --slot morning_open
"""
import argparse
import json
import sys
import traceback

import pipeline  # noqa: F401 -- symlink/DLL PATH patch'lerini uygular
from pipeline import persona as _persona
from pipeline import visual_director as _vdir
from pipeline import brain_memory as _brain_memory
from pipeline.orchestrator import process_existing_job
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import job_path, make_job_id

log = get_logger("run_scheduled_short")

# Her slot: konu şablonu (research.deep_research + market_data.topic_data konudan
# ilgili sembolleri/haberleri kendisi tespit eder, bkz. market_data.detect_symbols) +
# hedef kelime sayısı (shorts.target_duration'a göre ~150 kelime/dk konuşma hızı).
SLOTS = {
    "morning_open": {
        "topic": "Türkiye'de piyasalar açılışta ne durumda: Borsa İstanbul BIST 100, "
                 "Dolar/TL kuru ve gram altın için bugünkü açılış tablosu",
        "target_words": 130,
    },
    "us_market": {
        "topic": "ABD borsası açılışı ve dünya genelinde piyasaları bugün ne bekliyor: "
                 "S&P 500, Nasdaq ve Bitcoin için son durum",
        "target_words": 130,
    },
    "evening_wrap": {
        "topic": "Dünyada bugün neler oldu: günün öne çıkan küresel ekonomi ve piyasa haberleri özeti",
        "target_words": 130,
    },
}


def run_slot(slot: str) -> dict:
    if slot not in SLOTS:
        raise SystemExit(f"Bilinmeyen slot: {slot!r} (geçerli: {', '.join(SLOTS)})")
    spec = SLOTS[slot]
    topic = spec["topic"]
    target_words = spec["target_words"]

    log.info(f"=== Zamanlanmış Shorts başlıyor: slot={slot} ===")
    gen = _persona.generate_researched_script(topic, target_words=target_words)

    meta = gen.get("metadata") or {}
    base = meta.get("title") or gen.get("topic") or topic
    job_id = make_job_id(base)

    char = _vdir.resolve_character(gen.get("topic", base), gen.get("segments", []))
    script_payload = {
        "topic": gen.get("topic", base),
        "script": gen.get("script", ""),
        "segments": gen.get("segments", []),
        "visual_prompts": gen.get("visual_prompts", []),
        "visual_character_id": char["id"],
    }
    if gen.get("language"):
        script_payload["language"] = gen["language"]
    if gen.get("sources"):
        script_payload["sources"] = gen["sources"]
    job_path(job_id, "script.json").write_text(
        json.dumps(script_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    job_path(job_id, "metadata.json").write_text(json.dumps({
        "title": (meta.get("title") or base)[:100],
        "description": meta.get("description", ""),
        "tags": meta.get("tags", []),
        "pinned_comment": meta.get("pinned_comment", ""),
        "scheduled_slot": slot,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        _brain_memory.record(gen.get("topic", base), meta.get("title") or base,
                             job_id, gen.get("language", "tr"))
    except Exception as e:
        log.warning(f"hafıza kaydı atlandı: {e}")

    try:
        _persona.unload_model()
    except Exception as e:
        log.warning(f"Ollama modeli boşaltılamadı (devam ediliyor): {e}")

    # skip_upload=False -> s09_upload.run() çalışır ama config.yaml youtube.privacy_status
    # varsayılanı 'private' olduğu için video herkese açık YAYINLANMAZ, sadece insan
    # onayını bekleyen bir taslak olarak yüklenir (bkz. plan: yarı-otomatik onay akışı).
    result = process_existing_job(job_id, skip_upload=False, drive_upload=False)
    log.info(f"=== Zamanlanmış Shorts tamamlandı: slot={slot} job={job_id} ===")
    return result


def main():
    parser = argparse.ArgumentParser(description="Zamanlanmış piyasa/haber Shorts üretici")
    parser.add_argument("--slot", required=True, choices=list(SLOTS.keys()))
    args = parser.parse_args()
    try:
        run_slot(args.slot)
    except Exception:
        log.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
