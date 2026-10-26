"""Uçtan uca: HAFTALIK ekonomi özetini araştır -> Claude ile ~15dk TR script üret -> fact-check ->
tam pipeline (s02..s07) render et. KARAKTERSİZ (avatar varsayılan KAPALI, kullanıcı sesi klonu +
canlı piyasa grafikleri + sınırlı AI b-roll + foto-gerçekçi statik görsel). YouTube'a YÜKLEMEZ
(output/ klasöründe insan onayı bekler).

Araştırma: pipeline/weekly_digest.py (döviz/altın/gümüş/BIST/faiz/küresel/kripto, son 1 hafta,
sıfır API maliyeti — DuckDuckGo+Wikipedia+Google News+GDELT+Yahoo Finance).

Kullanım:
    # kısa doğrulama (~3-4 dk) — tüm zinciri (araştırma+ses klonu+render) hızlı test et:
    python tools/make_weekly_video.py --target-words 500 --job-suffix dogrulama

    # tam ~15 dk haftalık video:
    python tools/make_weekly_video.py --target-words 2000 --job-suffix v1
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

from pipeline import factcheck, weekly_digest  # noqa: E402
from pipeline.utils.logging import get_logger  # noqa: E402
from gen_finance_script import generate_script_json  # noqa: E402

log = get_logger("make_weekly_video")

DEFAULT_TOPIC = "Bu hafta Türkiye ve dünya ekonomisinde ne oldu — haftalık özet"


def main():
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Haftalık ekonomi özeti: araştır + karaktersiz video render")
    ap.add_argument("--topic", default=DEFAULT_TOPIC)
    ap.add_argument("--target-words", type=int, default=2000)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--job-suffix", default="haftalik", help="job_id sonuna eklenir (v1, dogrulama vb.)")
    ap.add_argument("--news-timespan", default="1w", help="GDELT/haber tazelik penceresi (ör. 1w, 3d)")
    # 8 Ağu: KULLANICI İSTEĞİ — daha fazla segment gerçek hareketli klip alsın (görsel
    # zenginlik/senkron için "klipleri arttır"). 18 -> 30 (LTX ~3dk/klip -> +~35-40dk render).
    ap.add_argument("--max-broll-clips", type=int, default=30,
                     help="AI i2v b-roll üretilecek en fazla segment sayısı (render süresini sınırlar)")
    ap.add_argument("--broll-engine", default="ltx-i2v", choices=["ltx-i2v", "wan-i2v", "cogvideox-t2v"])
    ap.add_argument("--with-avatar", action="store_true",
                     help="varsayılan KAPALI (karaktersiz); karakterli render için bu bayrağı ver")
    args = ap.parse_args()

    job_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-haftalik-ozet-{args.job_suffix}"
    log.info(f"=== İş başlıyor: {job_id} (hedef≈{args.target_words} kelime) ===")

    # 1) Haftalık araştırma: sabit konu seti (döviz/altın/gümüş/BIST/faiz/küresel/kripto) + son 1 hafta haberleri.
    digest = weekly_digest.gather_weekly_digest(
        out_dir=str(ROOT / "output" / job_id / "charts_digest"),
        news_timespan=args.news_timespan,
    )
    if not digest.get("facts", "").strip():
        raise RuntimeError("Haftalık araştırma boş döndü (ağ engelli olabilir) — üretim durduruldu")
    log.info(f"Araştırma hazır: {len(digest['sources'])} kaynak, semboller={digest['symbols']}")

    # 2) Claude ile ~15dk TR script üret (digest facts'ine dayalı, market_symbols s04'e grafik enjeksiyonu için gider).
    res = generate_script_json(
        job_id, args.topic, digest["facts"], target_words=args.target_words,
        model=args.model, max_tokens=24000, market_symbols=digest["symbols"],
    )
    log.info(f"Script hazır: {res['word_count']} kelime, {len(res['script']['segments'])} segment")

    # 3) Fact-check: script'teki sayısal iddiaları haftalık araştırma verisine karşı denetle.
    #    Desteklenmeyen rakam varsa 1 kez hedefli düzeltme dene (tools/gen_one.py ile aynı desen).
    gen_for_check = {"facts": digest["facts"], "segments": res["script"]["segments"],
                      "script": res["script"]["script"]}
    fc = factcheck.verify(gen_for_check)
    if fc.get("checked") and not fc.get("ok") and fc.get("fix_hint"):
        log.warning(f"Fact-check: {fc['count']} desteklenmeyen iddia — düzeltilmiş script deneniyor")
        topic_fix = f"{args.topic}\n\nDÜZELTME NOTU (önceki taslakta desteklenmeyen iddialar bulundu, DÜZELT): {fc['fix_hint']}"
        res2 = generate_script_json(
            job_id, topic_fix, digest["facts"], target_words=args.target_words,
            model=args.model, max_tokens=24000, market_symbols=digest["symbols"],
        )
        gen_for_check2 = {"facts": digest["facts"], "segments": res2["script"]["segments"],
                           "script": res2["script"]["script"]}
        fc2 = factcheck.verify(gen_for_check2)
        if fc2.get("count", 99) <= fc.get("count", 99):  # daha az işaretliyi kullan
            res, fc = res2, fc2
    job_dir = ROOT / "output" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "factcheck.json").write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Fact-check: checked={fc.get('checked')} ok={fc.get('ok')} flagged={fc.get('count', 0)}")

    # 4) Bu işe ÖZEL render ayarları — process-içi override, config.yaml diske YAZILMAZ
    #    (diğer kanal/işleri etkilememesi için). Karaktersiz + sınırlı AI b-roll:
    #    15dk'lık script ~150-190 segment üretir; max_clips=99 (config.yaml varsayılanı)
    #    ile tam AI video b-roll saatlerce sürer, bu yüzden burada sınırlanır.
    from pipeline.utils.config import load_config
    cfg = load_config()
    cfg["avatar"]["enabled"] = bool(args.with_avatar)
    cfg["visuals"]["video_broll"]["engine"] = args.broll_engine
    cfg["visuals"]["video_broll"]["max_clips"] = args.max_broll_clips
    log.info(
        f"Render ayarları: avatar={'AÇIK' if args.with_avatar else 'KAPALI (karaktersiz)'}, "
        f"broll_engine={args.broll_engine}, max_clips={args.max_broll_clips}"
    )

    # 5) Tam pipeline: s02 TTS (CosyVoice klon) -> (s03 avatar atlanır) -> s04 görsel+canlı grafik
    #    -> s05 sınırlı i2v b-roll -> s06 altyazı -> s07 montaj. Yükleme KAPALI (insan onayı bekler).
    from pipeline.orchestrator import process_existing_job
    try:
        result = process_existing_job(job_id, skip_upload=True)
    except Exception:
        log.error(traceback.format_exc())
        print(f"RESULT_JSON:{json.dumps({'job_id': job_id, 'status': 'failed'})}")
        return

    video = ROOT / "output" / "_videos" / f"{job_id}.mp4"
    log.info(f"=== TAMAM: {job_id} -> {video} ===")
    summary = {
        "job_id": job_id, "video": str(video), "word_count": res["word_count"],
        "factcheck_ok": fc.get("ok"), "factcheck_flagged": fc.get("count", 0), "result": result,
    }
    print(f"RESULT_JSON:{json.dumps(summary)}")


if __name__ == "__main__":
    main()
