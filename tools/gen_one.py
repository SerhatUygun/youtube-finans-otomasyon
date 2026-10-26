"""Tek video üretici — otonom iyileştirme döngüsü (auto_improve_loop.py) tarafından
her iterasyonda AYRI BİR SÜREÇ olarak çağrılır. Ayrı süreç olması kritik: böylece
döngü sürerken pipeline koduna/prompt'lara yapılan iyileştirmeler bir sonraki videoda
otomatik devreye girer (modül önbelleği taşınmaz).

Akış (finans kanalı, politika-uyumlu, GÜNCEL VERİ):
  persona.generate_researched_script (DuckDuckGo+Wikipedia -> qwen3, uzman-olmayan ton)
  -> script.json + metadata.json
  -> s02 TTS -> s04 görseller -> (full modda s05 WAN video b-roll) -> s06 altyazı -> s07 montaj
  YÜKLEME YOK (yerel output/ altında kalır).

Mod (30 Tem'den beri İKİ modda da LTX i2v video b-roll çalışır — gerçekçilik için):
  light : ~288 kelime (daha kısa/hızlı), en uzun config.max_clips segment gerçek hareketli.
  full  : ~600 kelime (daha uzun), aynı i2v ama daha fazla segment/statik içerir.

Sonuç değerlendirmesi tek satır JSON olarak "RESULT_JSON:{...}" ile stdout'a yazılır
(döngü çalıştırıcı bunu ayrıştırır).
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pipeline.utils.paths import job_path, make_job_id  # noqa: E402


def run_one(topic: str, mode: str, target_words: int | None, language: str = "en") -> dict:
    from pipeline import persona, policy, visual_director, critic, brain_memory, brain_learn
    from pipeline.utils.config import load_config

    # full 1300 kelime -> 44 segment tüm aşamaları (44 SDXL görsel, whisper, edit) ~90dk yapıyordu.
    # Full'un amacı i2v/tam-pipeline DOĞRULAMASI; 600 kelime bunu daha hızlı (~45dk) sağlar.
    tw = target_words or (288 if mode == "light" else 600)
    result = {
        "ok": False, "topic": topic, "mode": mode, "job_id": None, "error": None,
        "stages": {}, "words": 0, "segments": 0, "sources": 0, "researched": None,
        "policy": [], "disclaimer": False, "visual_character": None,
        "video_exists": False, "video_mb": 0.0,
        "critic_overall": None, "critic_verdict": None, "critic_revised": False,
    }

    # 1) Beyin: güncel veriyle temellendirilmiş, uzman-olmayan finans script'i
    t0 = time.time()
    gen = persona.generate_researched_script(topic, target_words=tw, language=language)

    # 1b) ÖZ-DEĞERLENDİRME: script'i render'dan ÖNCE puanla; zayıfsa hedefli 1 kez yeniden üret.
    crit = critic.score_script(gen, topic)
    try:
        retries = int((load_config().get("brain") or {}).get("critic_retries", 1))
    except Exception:
        retries = 1
    if crit.get("verdict") == "revise" and retries > 0 and crit.get("fix_hint"):
        gen2 = persona.generate_researched_script(
            topic, target_words=tw, language=language, feedback=crit["fix_hint"])
        crit2 = critic.score_script(gen2, topic)
        result["critic_revised"] = True
        # Daha yüksek puanlıyı kullan (yeniden-üretim her zaman daha iyi olmayabilir).
        if crit2.get("overall", 0) >= crit.get("overall", 0):
            gen, crit = gen2, crit2
    result["stages"]["script"] = round(time.time() - t0, 1)
    result["critic_overall"] = crit.get("overall")
    result["critic_verdict"] = crit.get("verdict")

    # 1c) FACT-CHECK: script'teki sayısal iddiaları DOĞRULANMIŞ verilere karşı denetle.
    # Desteklenmeyen rakam varsa 1 kez hedefli düzeltme dene; rapor insan-onay kapısı için saklanır.
    from pipeline import factcheck
    fc = factcheck.verify(gen)
    if fc.get("checked") and not fc.get("ok") and fc.get("fix_hint"):
        genf = persona.generate_researched_script(
            topic, target_words=tw, language=language, feedback=fc["fix_hint"])
        fcf = factcheck.verify(genf)
        if fcf.get("count", 99) <= fc.get("count", 99):  # daha az işaretliyi kullan
            gen, fc = genf, fcf
    result["factcheck_checked"] = fc.get("checked")
    result["factcheck_flagged"] = fc.get("count", 0)
    result["factcheck_ok"] = fc.get("ok")

    segments = gen.get("segments") or []
    if not segments:
        raise RuntimeError("script üretilemedi (segment yok)")
    script_text = gen.get("script", "")
    meta = gen.get("metadata") or {}
    sources = gen.get("sources") or []

    job_id = make_job_id(topic)
    result["job_id"] = job_id
    from pipeline.utils.logging import attach_job_log_file
    attach_job_log_file(job_id)

    char = visual_director.resolve_character(topic, segments)
    script_payload = {
        "topic": gen.get("topic", topic),
        "script": script_text,
        "segments": segments,
        "visual_prompts": gen.get("visual_prompts", []),
        "language": gen.get("language", "en"),
        "visual_character_id": char["id"],
    }
    if sources:
        script_payload["sources"] = sources
    # Canlı piyasa sembolleri (altın/dolar/bitcoin...) — s04 bunları okuyup ilgili segmentlerin
    # görselini o günün GERÇEK grafiğiyle değiştirir (grafik tam o varlık anlatılırken ekrana gelir).
    if gen.get("market_symbols"):
        script_payload["market_symbols"] = gen["market_symbols"]
    if crit.get("scored"):
        script_payload["critic"] = {"overall": crit["overall"], "scores": crit["scores"]}
    # Fact-check işaretlerini script.json'a iliştir -> insan onay kapısında görünür.
    if fc.get("checked") and fc.get("flagged"):
        script_payload["factcheck"] = {"ok": fc["ok"], "flagged": fc["flagged"]}
    job_path(job_id, "script.json").write_text(
        json.dumps(script_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    job_path(job_id, "metadata.json").write_text(json.dumps({
        "title": (meta.get("title") or topic)[:100],
        "description": meta.get("description", ""),
        "tags": meta.get("tags", []),
        # pinned_comment/sources brain'de zaten üretiliyordu (persona.generate_researched_script)
        # ama diske hiç yazılmıyordu -> yükleme sırasında elle sabitlenecek yorum metni kayboluyordu.
        "pinned_comment": meta.get("pinned_comment", ""),
        "sources": meta.get("sources", []),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    # Critic detayını ayrı sakla (refleksiyon 'issues'ı buradan okur) + skor tablosunu güncelle.
    if crit.get("scored"):
        job_path(job_id, "critic.json").write_text(
            json.dumps(crit, ensure_ascii=False, indent=2), encoding="utf-8")
        brain_learn.update_leaderboard(job_id, crit)
    # Fact-check raporu (insan onay kapısı bunu okur; desteklenmeyen rakam varsa yayından önce düzelt).
    if fc.get("checked"):
        job_path(job_id, "factcheck.json").write_text(
            json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")
    # Hafıza: bu konu/başlık üretildi -> gelecekte tekrar önerilmesin.
    brain_memory.record(topic, meta.get("title") or topic, job_id, gen.get("language", "en"))

    # İçerik değerlendirmesi (uyum + kalite sinyalleri)
    cats = policy.classify_topic(topic, script_text)
    result.update({
        "words": len(script_text.split()),
        "segments": len(segments),
        "sources": len(sources),
        "researched": gen.get("researched"),
        "policy": cats,
        "disclaimer": bool(policy.disclaimer_line(cats, gen.get("language", "en"))
                           and policy.disclaimer_line(cats, gen.get("language", "en")) in (meta.get("description") or "")),
        "visual_character": char["id"],
    })

    # 2) GPU aşamalarından ÖNCE Ollama modelini VRAM'den boşalt (yoksa SDXL/WAN OOM)
    persona.unload_model()

    # 3) Render aşamaları (avatar KAPALI). Her aşama süresi ölçülür.
    def _stage(name, fn):
        s = time.time()
        fn()
        result["stages"][name] = round(time.time() - s, 1)

    from pipeline.stages import (
        s02_tts, s04_visuals, s05_video_broll, s05b_motion_graphics, s06_subtitles, s07_edit,
    )
    _stage("tts", lambda: s02_tts.run(job_id))
    # Konuşan KARAKTER (config avatar.enabled ise): sesten dudak-senkronlu avatar.mp4 üretir,
    # s07 yeşil ekranı chroma-key'leyip bindirir. Kapalıysa atlanır (karaktersiz devam).
    if load_config().get("avatar", {}).get("enabled"):
        from pipeline.stages import s03_avatar
        try:
            _stage("avatar", lambda: s03_avatar.run(job_id))
        except Exception as e:
            print(f"[avatar atlandı: {type(e).__name__}: {e}]", file=sys.stderr)
    _stage("visuals", lambda: s04_visuals.run(job_id))
    # 30 Tem: gerçekçilik için HER modda video b-roll (LTX i2v) çalışır — en uzun
    # config.max_clips (6) segment gerçek hareketli olur, kalanı statik+Ken Burns.
    # Full sadece daha uzun (~600 kelime) olduğu için daha fazla segment/statik içerir.
    _stage("video_broll", lambda: s05_video_broll.run(job_id))
    # Animasyonlu motion graphics (Remotion, opsiyonel/additive) — orchestrator.py'nin
    # sırasıyla aynı: s05_video_broll'dan SONRA, s06_subtitles'dan ÖNCE. Eskiden gen_one.py'de
    # hiç çağrılmıyordu (sadece orchestrator.py yolunda çalışıyordu) -> Editor/Denetleyici/
    # Tester döngüsü (pipeline/agents/) buradan hiç geçmiyordu. 17 Eyl eklendi.
    try:
        _stage("motion_graphics", lambda: s05b_motion_graphics.run(job_id))
    except Exception as e:
        print(f"[motion_graphics atlandı: {type(e).__name__}: {e}]", file=sys.stderr)
    _stage("subtitles", lambda: s06_subtitles.run(job_id))
    _stage("edit", lambda: s07_edit.run(job_id))

    # 4) Otomatik Shorts Üretimi
    shorts_cfg = load_config().get("shorts", {})
    if shorts_cfg.get("auto_generate", True):
        from tools import make_shorts
        dur = float(shorts_cfg.get("target_duration", 45))
        _stage("shorts", lambda: make_shorts.generate_short_for_job(job_id, duration=dur))

    video = job_path(job_id, "video.mp4")
    short_v = job_path(job_id, "short.mp4")
    if video.exists():
        result["video_exists"] = True
        result["video_mb"] = round(video.stat().st_size / 1_048_576, 2)
    if short_v.exists():
        result["short_exists"] = True
        result["short_mb"] = round(short_v.stat().st_size / 1_048_576, 2)
    result["ok"] = result["video_exists"]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--mode", choices=["light", "full"], default="light")
    ap.add_argument("--target-words", type=int, default=None)
    ap.add_argument("--language", default="en", help="script + seslendirme dili (ör. tr, en)")
    args = ap.parse_args()

    result = {"ok": False, "topic": args.topic, "mode": args.mode, "error": None}
    try:
        result = run_one(args.topic, args.mode, args.target_words, language=args.language)
    except Exception as e:
        result["ok"] = False
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-2000:]

    print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
