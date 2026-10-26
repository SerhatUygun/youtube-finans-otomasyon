"""Uçtan uca: Claude ile Türkçe finans scripti üret -> tam pipeline (s02..s07) render et.

Karakterli (SadTalker parçalı, ekranda ortada), foto-gerçekçi arka planlı, küçük/kelime-seviyesi
altyazılı YATAY video üretir. YouTube'a YÜKLEMEZ (output/ klasöründe insan onayı bekler).

Kullanım:
    # kısa doğrulama (~1.5 dk) — tüm zinciri hızlı test et:
    python tools/make_finance_video.py --topic "Bu hafta altın ve gümüşte ne oldu" \
        --facts-file data/altin_gumus_facts.txt --target-words 230 --job-suffix dogrulama

    # tam 8+ dk hero video:
    python tools/make_finance_video.py --topic "Bu hafta altın ve gümüşte ne oldu" \
        --facts-file data/altin_gumus_facts.txt --target-words 1400 --job-suffix v1
"""
import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/ (gen_finance_script importu için)

from dotenv import load_dotenv  # noqa: E402

from pipeline.utils.logging import get_logger  # noqa: E402
from gen_finance_script import generate_script_json  # noqa: E402

log = get_logger("make_finance_video")


def main():
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Claude finans scripti + karakterli video render")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--facts-file", required=True)
    ap.add_argument("--target-words", type=int, default=1400)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--job-suffix", default="finans", help="job_id sonuna eklenir (v1, dogrulama vb.)")
    args = ap.parse_args()

    facts = open(args.facts_file, encoding="utf-8").read()
    job_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-altin-gumus-{args.job_suffix}"
    log.info(f"=== İş başlıyor: {job_id} (hedef≈{args.target_words} kelime) ===")

    # 1) Claude ile script.json + metadata.json üret
    res = generate_script_json(
        job_id, args.topic, facts, target_words=args.target_words, model=args.model
    )
    log.info(f"Script hazır: {res['word_count']} kelime, {len(res['script']['segments'])} segment")

    # 2) Tam pipeline: s02 TTS -> s03 avatar (SadTalker parçalı) -> s04 görsel -> s06 altyazı -> s07 montaj
    #    (s01 atlanır çünkü script.json'ı biz yazdık). Yükleme KAPALI.
    from pipeline.orchestrator import process_existing_job
    try:
        result = process_existing_job(job_id, skip_upload=True)
    except Exception:
        log.error(traceback.format_exc())
        print(f"RESULT_JSON:{json.dumps({'job_id': job_id, 'status': 'failed'})}")
        return

    video = ROOT / "output" / "_videos" / f"{job_id}.mp4"
    log.info(f"=== TAMAM: {job_id} -> {video} ===")
    print(f"RESULT_JSON:{json.dumps({'job_id': job_id, 'video': str(video), 'result': result})}")


if __name__ == "__main__":
    main()
