"""Sabit bir konu listesinden SIRALI video üretir (elle/planlı toplu üretim).

auto_improve_loop'tan farkı: rastgele seed/otonom değil — verilen konuları, verilen
dilde/mod/uzunlukta üretir. Her konu gen_one.py'yi AYRI SÜREÇ olarak çağırır (VRAM
izolasyonu; kod/prompt iyileştirmeleri anında devreye girer). Bir video hata verse de
döngü durmaz, sıradakine geçer.

Kullanım:
  python tools/make_batch.py --language tr --mode full --target-words 720
  python tools/make_batch.py --topics-file konular.json      # ["konu1", "konu2", ...]

Çıktılar (output/_logs/):
  batch_results.jsonl  — her videonun tam RESULT_JSON'u
  batch_summary.json   — canlı özet
Videolar output/<job_id>/video.mp4 altında (1920x1080; config edit.resolution).
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "output" / "_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS = LOG_DIR / "batch_results.jsonl"
SUMMARY = LOG_DIR / "batch_summary.json"

# Varsayılan: 5 Türkçe finans konusu (bilgilendirici, politika-uyumlu, kanal nişi).
DEFAULT_TOPICS = [
    "Enflasyon paranızın değerini nasıl eritiyor",
    "Bileşik faiz nasıl çalışır",
    "Acil durum fonu neden önemli",
    "Borsa endeksi aslında neyi ölçer",
    "Tasarruf ile yatırım arasındaki fark",
]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{ts} | {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--language", default="tr", help="script + seslendirme dili (tr/en)")
    ap.add_argument("--mode", choices=["light", "full"], default="full")
    ap.add_argument("--target-words", type=int, default=720, help="~kelime (720 ≈ 5 dk)")
    ap.add_argument("--topics-file", default=None, help="JSON konu listesi (yoksa varsayılan 5)")
    ap.add_argument("--timeout-min", type=int, default=90, help="video başına üst sınır")
    args = ap.parse_args()

    topics = DEFAULT_TOPICS
    if args.topics_file:
        topics = json.loads(Path(args.topics_file).read_text(encoding="utf-8"))

    started = datetime.now(timezone.utc).isoformat()
    stats = {"started": started, "language": args.language, "mode": args.mode,
             "target_words": args.target_words, "total": len(topics), "done": 0,
             "ok": 0, "failed": 0, "videos": [], "last_update": started}

    log(f"=== TOPLU ÜRETİM — {len(topics)} video, dil={args.language}, mod={args.mode}, "
        f"~{args.target_words} kelime ===")
    for i, topic in enumerate(topics, 1):
        log(f"[#{i}/{len(topics)}] {topic!r}")
        wall = time.time()
        res = {"ok": False, "topic": topic, "error": None, "job_id": None}
        try:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "gen_one.py"),
                 "--topic", topic, "--mode", args.mode,
                 "--language", args.language, "--target-words", str(args.target_words)],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=args.timeout_min * 60,
            )
            line = next((ln for ln in reversed(proc.stdout.splitlines())
                         if ln.startswith("RESULT_JSON:")), None)
            if line:
                res = json.loads(line[len("RESULT_JSON:"):])
            else:
                res["error"] = "RESULT_JSON yok; son stderr: " + (proc.stderr or "")[-800:]
        except subprocess.TimeoutExpired:
            res["error"] = f"timeout ({args.timeout_min}dk aşıldı)"
        except Exception as e:
            res["error"] = f"{type(e).__name__}: {e}"

        res["wall_seconds"] = round(time.time() - wall, 1)
        res["ts"] = datetime.now(timezone.utc).isoformat()
        with RESULTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")

        stats["done"] = i
        if res.get("ok"):
            stats["ok"] += 1
            stats["videos"].append({"topic": topic, "job_id": res.get("job_id"),
                                    "critic": res.get("critic_overall"),
                                    "video_mb": res.get("video_mb")})
            log(f"[#{i}] OK job={res.get('job_id')} {res.get('wall_seconds')}s "
                f"kalite={res.get('critic_overall')} video={res.get('video_mb')}MB")
        else:
            stats["failed"] += 1
            log(f"[#{i}] BAŞARISIZ: {str(res.get('error'))[:200]}")

        stats["last_update"] = datetime.now(timezone.utc).isoformat()
        SUMMARY.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    stats["finished"] = datetime.now(timezone.utc).isoformat()
    SUMMARY.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"=== BİTTİ — {stats['ok']}/{stats['total']} başarılı, {stats['failed']} hata ===")


if __name__ == "__main__":
    main()
