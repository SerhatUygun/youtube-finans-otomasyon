"""8 saatlik OTONOM iyileştirme döngüsü — finans kanalı, politika-uyumlu, güncel veri.

Amaç: kendi kendine sürekli video ÜRETİP TEST ederek (a) qwen tabanlı 'beyin'i prompt/
persona iyileştirmeleriyle daha iyi hale getirmek, (b) iyi örneklerden bir VERİ SETİ
biriktirmek (ileride fine-tune için), (c) pipeline'ı sağlamlaştırmak.

Her iterasyon gen_one.py'yi AYRI SÜREÇ olarak çağırır (kod/prompt iyileştirmeleri anında
devreye girsin diye). YÜKLEME YOK. Karışık mod: çoğu iterasyon 'light' (hızlı, WAN'sız),
her N. iterasyon 'full' (WAN video b-roll ile uçtan uca doğrulama).

Çıktılar (output/_logs/):
  auto_improve_results.jsonl  — her videonun tam sonucu (JSON satırları)
  auto_improve_summary.json   — canlı özet (sayımlar, başarı oranı, ort. süreler)
İyi örnekler output/_dataset/<job_id>/ altına kopyalanır.

Kullanım:
  python tools/auto_improve_loop.py --hours 8 --full-every 5
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.utils.paths import job_path  # noqa: E402

LOG_DIR = ROOT / "output" / "_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RESULTS = LOG_DIR / "auto_improve_results.jsonl"
SUMMARY = LOG_DIR / "auto_improve_summary.json"
DATASET = ROOT / "output" / "_dataset"
DATASET.mkdir(parents=True, exist_ok=True)

# Finans konuları — hem evergreen kavramlar hem "güncel" fraz (research.py üretim anında
# DuckDuckGo+Wikipedia'dan güncel veriyi çeker). Politika-uyumlu: hepsi bilgilendirici,
# tavsiye/tahmin değil.
SEED_TOPICS = [
    "How compound interest actually works",
    "What inflation means for everyday prices",
    "How a recession is officially defined",
    "What the stock market index actually measures",
    "How central bank interest rates affect loans",
    "The difference between saving and investing",
    "How an emergency fund protects your finances",
    "What an ETF is and how it works",
    "How credit scores are calculated",
    "Why diversification reduces risk",
    "How bonds work compared to stocks",
    "What GDP tells us about an economy",
    "How exchange rates between currencies move",
    "What dollar-cost averaging means",
    "How mortgages and amortization work",
    "The history and idea behind index funds",
    "How supply and demand set prices",
    "What a bull market and bear market mean",
    "How taxes on income brackets work",
    "Why gold is seen as a safe-haven asset",
    "The latest reported global inflation trends",
    "How this year's interest rate decisions were reported",
    "What recent reports say about the housing market",
    "How the price of oil affects the economy",
    "What the unemployment rate measures",
    "How pension and retirement accounts grow over time",
    "The basics of how cryptocurrencies are valued",
    "What a budget deficit and national debt are",
    "How fintech apps changed everyday banking",
    "Why prices for the same product differ across countries",
]

# Türkçe kanal için Türkçe seed konular (research.py Türkçe Wikipedia/DDG kullanır).
TURKISH_SEED_TOPICS = [
    "Bileşik faiz nasıl çalışır",
    "Enflasyon günlük fiyatları nasıl etkiler",
    "Resesyon resmi olarak nasıl tanımlanır",
    "Borsa endeksi aslında neyi ölçer",
    "Merkez bankası faizleri kredileri nasıl etkiler",
    "Tasarruf ile yatırım arasındaki fark",
    "Acil durum fonu neden önemli",
    "ETF nedir ve nasıl çalışır",
    "Kredi notu nasıl hesaplanır",
    "Çeşitlendirme riski neden azaltır",
    "Tahvil ile hisse senedi arasındaki fark",
    "GSYİH bir ekonomi hakkında ne söyler",
    "Döviz kurları neden değişir",
    "Maliyet ortalaması (DCA) nedir",
    "Konut kredisi ve amortisman nasıl işler",
    "Endeks fonlarının mantığı nedir",
    "Arz ve talep fiyatları nasıl belirler",
    "Boğa ve ayı piyasası ne demek",
    "Gelir vergisi dilimleri nasıl çalışır",
    "Altın neden güvenli liman olarak görülür",
    "Emeklilik hesapları zamanla nasıl büyür",
    "Kripto paralar nasıl değerlenir",
    "Bütçe açığı ve kamu borcu nedir",
    "Fintech uygulamaları bankacılığı nasıl değiştirdi",
    "Enflasyon paranızın değerini nasıl eritiyor",
]

# main() dilinize göre bunları ayarlar; refill_topics bunları kullanır.
ACTIVE_SEEDS = SEED_TOPICS
ACTIVE_LANGUAGE = "en"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{ts} | {msg}", flush=True)


def refill_topics(queue: list):
    """Kuyruk azaldıysa seed'leri karıştırıp ekler; ayrıca beyinden (qwen) taze fikir
    almayı en iyi çabayla dener. (GPU aşaması çalışmadığı ANLARDA çağrılır — güvenli.)

    HAFIZA: daha önce üretilen başlıklar generate_ideas'a 'avoid' olarak verilir ve
    yakın-tekrar seed'ler elenir -> aynı konuların tekrarı azalır (çeşitlilik)."""
    import random
    from pipeline import brain_memory
    # Yakın-tekrar seed'leri ele (geçmişte zaten benzeri yapıldıysa).
    seeds = [s for s in ACTIVE_SEEDS if not brain_memory.is_similar(s)]
    if not seeds:  # hepsi yapılmışsa yine de rotasyona devam et
        seeds = ACTIVE_SEEDS[:]
    random.shuffle(seeds)
    queue.extend(seeds)
    try:
        from pipeline import persona
        ideas = persona.generate_ideas(n=6, avoid=brain_memory.recent_titles(),
                                       language=ACTIVE_LANGUAGE)
        persona.unload_model()  # VRAM'i hemen geri bırak
        fresh = [i for i in ideas if i and i not in queue and not brain_memory.is_similar(i)]
        random.shuffle(fresh)
        queue[:0] = fresh  # taze fikirleri öne al
        log(f"beyin {len(fresh)} taze fikir ekledi (hafıza-farkında)")
    except Exception as e:
        log(f"fikir üretimi atlandı ({type(e).__name__})")


def maybe_save_dataset(res: dict):
    """Politika-uyumlu, kaynaklı, makul uzunlukta iyi örnekleri veri setine kopyalar."""
    if not (res.get("ok") and res.get("researched") and res.get("sources", 0) > 0):
        return
    if not (12 <= res.get("segments", 0) <= 120):
        return
    job_id = res.get("job_id")
    src = ROOT / "output" / job_id
    if not src.exists():
        return
    dst = DATASET / job_id
    dst.mkdir(parents=True, exist_ok=True)
    # critic.json de kopyalanır -> brain_reflect tekrar eden 'issues'ı buradan okur.
    for name in ("script.json", "metadata.json", "critic.json"):
        f = job_path(job_id, name)
        if f.exists():
            shutil.copy2(f, dst / name)


def write_summary(stats: dict):
    SUMMARY.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=8.0)
    # 31 Tem: foto-gerçekçi + gerçek klip ayarlarıyla her video ~1.5 saat -> gece boyu
    # üretkenlik için varsayılan LIGHT-only (full-every çok yüksek). Uzun video için düşür.
    ap.add_argument("--full-every", type=int, default=999, help="her N. video full modda (999=hiç)")
    ap.add_argument("--reflect-every", type=int, default=5,
                    help="her N. videodan sonra beyin refleksiyonu (0=kapalı)")
    ap.add_argument("--language", default="tr", help="script + seslendirme dili (tr/en)")
    args = ap.parse_args()

    # Dile göre seed konu listesi (Türkçe kanal -> Türkçe seed'ler + Türkçe araştırma).
    global ACTIVE_SEEDS, ACTIVE_LANGUAGE
    ACTIVE_SEEDS = TURKISH_SEED_TOPICS if args.language == "tr" else SEED_TOPICS
    ACTIVE_LANGUAGE = args.language

    deadline = time.time() + args.hours * 3600
    started = datetime.now(timezone.utc).isoformat()
    stats = {
        "started": started, "hours": args.hours, "iterations": 0, "ok": 0, "failed": 0,
        "dataset_saved": 0, "by_mode": {"light": 0, "full": 0}, "last_error": None,
        "avg_stage_seconds": {}, "last_update": started,
    }
    stage_totals, stage_counts = {}, {}
    queue: list = []
    i = 0

    # Hafızayı mevcut veri setinden geriye-doldur (tekrar önleme baştan çalışsın).
    try:
        from pipeline import brain_memory
        brain_memory.rebuild()
    except Exception as e:
        log(f"hafıza geriye-doldurma atlandı ({type(e).__name__})")

    log(f"=== OTONOM İYİLEŞTİRME DÖNGÜSÜ BAŞLADI — {args.hours} saat, full her {args.full_every}. video ===")
    while time.time() < deadline:
        if not queue:
            refill_topics(queue)
        topic = queue.pop(0)
        i += 1
        mode = "full" if (i % args.full_every == 0) else "light"
        # 31 Tem: foto-gerçekçi + 12 gerçek i2v klip -> video ~1.5 saat. Timeout geniş.
        timeout_s = 220 * 60 if mode == "full" else 170 * 60
        remaining = deadline - time.time()
        if remaining < 300:  # son 5 dk yeni iş başlatma
            break
        timeout_s = int(min(timeout_s, remaining))

        log(f"[#{i}] mode={mode} konu: {topic!r}")
        wall = time.time()
        res = {"ok": False, "topic": topic, "mode": mode, "error": None, "job_id": None}
        try:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "gen_one.py"),
                 "--topic", topic, "--mode", mode, "--language", args.language],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout_s,
            )
            line = next((ln for ln in reversed(proc.stdout.splitlines())
                         if ln.startswith("RESULT_JSON:")), None)
            if line:
                res = json.loads(line[len("RESULT_JSON:"):])
            else:
                res["error"] = "RESULT_JSON yok; son stderr: " + (proc.stderr or "")[-500:]
        except subprocess.TimeoutExpired:
            res["error"] = f"timeout ({timeout_s}s aşıldı)"
        except Exception as e:
            res["error"] = f"{type(e).__name__}: {e}"

        res["wall_seconds"] = round(time.time() - wall, 1)
        res["ts"] = datetime.now(timezone.utc).isoformat()
        with RESULTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")

        stats["iterations"] = i
        stats["by_mode"][mode] = stats["by_mode"].get(mode, 0) + 1
        if res.get("ok"):
            stats["ok"] += 1
            maybe_save_dataset(res)
            if (DATASET / (res.get("job_id") or "")).exists():
                stats["dataset_saved"] = sum(1 for _ in DATASET.iterdir())
            for st, sec in (res.get("stages") or {}).items():
                stage_totals[st] = stage_totals.get(st, 0) + sec
                stage_counts[st] = stage_counts.get(st, 0) + 1
            log(f"[#{i}] OK job={res.get('job_id')} {res.get('wall_seconds')}s "
                f"words={res.get('words')} src={res.get('sources')} char={res.get('visual_character')} "
                f"video={res.get('video_mb')}MB")
        else:
            stats["failed"] += 1
            stats["last_error"] = res.get("error")
            log(f"[#{i}] BAŞARISIZ: {str(res.get('error'))[:200]}")

        stats["avg_stage_seconds"] = {
            k: round(stage_totals[k] / stage_counts[k], 1) for k in stage_totals
        }
        stats["last_update"] = datetime.now(timezone.utc).isoformat()
        write_summary(stats)

        # REFLEKSIYON: her N. videodan sonra beyin skorlardan ders çıkarır (GPU boş).
        # Böylece learned_guidance bir sonraki üretimlere enjekte olur -> koşu sırasında adapte.
        if args.reflect_every and i % args.reflect_every == 0:
            try:
                from tools import brain_reflect
                brain_reflect.reflect(recent=max(args.reflect_every * 3, 30))
            except Exception as e:
                log(f"refleksiyon atlandı ({type(e).__name__}: {e})")

        time.sleep(3)

    stats["finished"] = datetime.now(timezone.utc).isoformat()
    write_summary(stats)
    log(f"=== DÖNGÜ BİTTİ — {stats['iterations']} iterasyon, {stats['ok']} OK, "
        f"{stats['failed']} başarısız, veri seti {stats['dataset_saved']} örnek ===")


if __name__ == "__main__":
    main()
