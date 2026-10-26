"""Günlük otomasyon (Görev Zamanlayıcı 14:00 -> bu betik).

 1. Kilit + iş klasörü: output/daily-YYYYMMDD/
 2. Claude Code headless (`claude -p`): prompts/daily_video.md -> brief/video/reels/thumb/series.json
 3. pipeline/daily/validate.py; hata varsa aynı Claude oturumuna düzeltme turu (config daily.claude.max_fix_rounds)
 4. pipeline/daily/build.py: ses -> zaman çizelgesi -> render -> süre kontrolü -> YouTube PRIVATE -> Drive -> geçmiş
 5. Rapor: output/_daily/YYYY-MM-DD.md (+ hata olursa _HATA.txt)

Kullanım:
  python tools/daily_run.py                 # tam koşu
  python tools/daily_run.py --no-upload     # yükleme/Drive yok (deneme)
  python tools/daily_run.py --skip-claude   # iş klasöründeki mevcut dosyalarla devam (--job ile)
  python tools/daily_run.py --job daily-20260928 --resume
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

def _lock_stale(lock: Path) -> bool:
    """Kilit, bilgisayar yeniden başladıktan önce yazıldıysa ya da sahibi PID yaşamıyorsa eskidir
    (ör. elektrik kesintisi sonrası geride kalan kilit)."""
    try:
        import psutil
        if lock.stat().st_mtime < psutil.boot_time():
            return True
        pid = int(lock.read_text(encoding="utf-8").strip() or 0)
        return not psutil.pid_exists(pid)
    except Exception:
        return False


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from pipeline.daily.validate import validate, validate_shorts  # noqa: E402
from pipeline.utils.config import load_config  # noqa: E402

DAILY = ROOT / "output" / "_daily"
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
ALLOWED = ",".join([
    "WebSearch", "WebFetch", "Read", "Write", "Edit", "Glob", "Grep",
    "Bash(.venv/Scripts/python.exe tools/market_snapshot.py:*)", "Bash(.venv\\Scripts\\python.exe tools/market_snapshot.py:*)",
    "Bash(.venv/Scripts/python.exe tools\\market_snapshot.py:*)", "Bash(python tools/market_snapshot.py:*)",
])


class Log:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg: str):
        line = f"{datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


REQUIRED = ("brief.json", "series.json", "video.json", "reels.json", "thumb.json")
LIMIT_RE = re.compile(r"hit your .*?limit.*?resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE | re.DOTALL)


class ClaudeLimit(RuntimeError):
    def __init__(self, msg: str, reset: datetime | None, session: str | None):
        super().__init__(msg)
        self.reset, self.session = reset, session


def _reset_time(text: str) -> datetime | None:
    m = LIMIT_RE.search(text or "")
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    now = datetime.now()
    t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


def claude_resilient(prompt: str, job_dir: Path, log: Log, session: str | None = None) -> dict:
    """Kullanım limitine takılırsa: sıfırlanma saati `daily.claude.max_wait_min` içindeyse bekleyip AYNI oturumu sürdürür;
    değilse ve `api_fallback: true` ise ANTHROPIC_API_KEY ile (ücretli) sürdürür; aksi halde hata."""
    cfg = load_config().get("daily", {}).get("claude", {})
    try:
        return claude(prompt, job_dir, log, session)
    except ClaudeLimit as e:
        sess = e.session or session
        cont = ("Kullanım limiti nedeniyle yarıda kaldın. Klasördeki mevcut dosyaları oku; EKSİK olanları "
                f"({', '.join(n for n in REQUIRED if not (job_dir / n).exists())}) talimattaki şemaya göre tamamla. Bitmiş dosyaları baştan yazma.")
        wait = (e.reset - datetime.now()).total_seconds() / 60 if e.reset else None
        if wait is not None and wait <= float(cfg.get("max_wait_min", 90)):
            log(f"Claude limiti: {e.reset:%H:%M}'de sıfırlanıyor, {wait:.0f} dk bekleniyor…")
            time.sleep(max(wait * 60 + 120, 60))
            return claude(cont, job_dir, log, sess)
        if cfg.get("api_fallback") and os.environ.get("ANTHROPIC_API_KEY"):
            log("Claude limiti: API yedeğiyle (ücretli) devam ediliyor")
            return claude(cont, job_dir, log, sess, use_api=True)
        raise


def claude(prompt: str, job_dir: Path, log: Log, session: str | None = None, use_api: bool = False) -> dict:
    cfg = load_config().get("daily", {}).get("claude", {})
    cmd = ["claude", "-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--allowedTools", ALLOWED,
           "--disallowedTools", "Bash(git:*)", "--effort", str(cfg.get("effort", "high"))]
    if session:
        cmd += ["--resume", session]
    exe = "claude.cmd" if sys.platform == "win32" else "claude"
    cmd[0] = exe
    t0 = time.time()
    env = dict(os.environ)
    if not use_api:
        # Abonelik kotasıyla çalış: .env'den gelen API anahtarı CLI'yi ücretli API'ye geçirmesin.
        env.pop("ANTHROPIC_API_KEY", None)
    for attempt in range(2):
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT),
                           timeout=int(cfg.get("timeout_min", 40)) * 60 * (3 if os.environ.get("SP_MEGA_MIN") else 1), env=env)
        # 3 Eki: 0xC000013A (Ctrl+C/konsol kapandı) veya boş çıktı -> geçici kesinti, bir kez yeniden dene
        if attempt == 0 and not (r.stdout or "").strip() and r.returncode in (3221225786, -1073741510, 1):
            log(f"claude kesildi (kod {r.returncode}): {(r.stderr or '')[-200:].strip()} — 60 sn sonra yeniden deneniyor")
            time.sleep(60)
            continue
        break
    (job_dir / "_raw").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    (job_dir / "_raw" / f"claude_{stamp}.json").write_text(r.stdout or "", encoding="utf-8")
    if r.stderr:
        (job_dir / "_raw" / f"claude_{stamp}.err").write_text(r.stderr, encoding="utf-8")
    try:
        out = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        raise RuntimeError(f"claude çıktısı okunamadı (kod {r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    if out.get("is_error"):
        res = str(out.get("result"))
        if LIMIT_RE.search(res):
            if out.get("session_id"):
                (job_dir / "_raw" / "claude_session.txt").write_text(out["session_id"], encoding="utf-8")
            raise ClaudeLimit(f"Claude kullanım limiti: {res[:200]}", _reset_time(res), out.get("session_id") or session)
        raise RuntimeError(f"claude hata döndü: {res[:800]}")
    log(f"claude bitti ({time.time() - t0:.0f}s, ${out.get('total_cost_usd', 0):.2f} eşdeğeri): {str(out.get('result', ''))[:300]}")
    return out


def build_prompt(job_dir: Path, topic: str | None = None, shorts_only: bool = False) -> str:
    now = datetime.now()
    tpl = (ROOT / "prompts" / "daily_video.md").read_text(encoding="utf-8")
    rel = job_dir.relative_to(ROOT).as_posix()
    out = (tpl.replace("{{DATE_TR}}", f"{now.day} {AYLAR[now.month - 1]} {now.year}")
           .replace("{{WEEKDAY_TR}}", GUNLER[now.weekday()]).replace("{{JOB_DIR}}", rel))
    if shorts_only:
        out += ("\n\n## BUGÜN YALNIZ-SHORTS GÜNÜ (haftada 3 uzun video: Pzt/Çar/Cum)\n"
                "`video.json` ve `thumb.json` YAZMA. Yalnız `brief.json`, `series.json` ve `reels.json` (2 Shorts) yaz. Uzun videoya ait "
                "bölümleri (açılış varyantları, kapak, bölümler) atla. Shorts günün haberini taşır; son cümle izleyiciyi kanaldaki "
                "son uzun videoya yönlendirsin (\"tam analiz kanalda\").\n")
    if topic:
        out += ("\n\n## KONU KANAL SAHİBİ TARAFINDAN SABİTLENDİ\n"
                f"Konu seçme adımını atla; ana konu: **{topic}**\n"
                "\"Son 10 günde işlenen konuyu tekrar etme\" kuralı bu konu için geçersiz — ama önceki videodan farklı, "
                "bugüne özgü açı ve güncel veriler kullan. Sebepleri araştırmayla doğrula; doğrulanamayan sebebi söyleme.\n")
    try:  # 15 Eki: sahne çeşitliliği denetimi — son 5 videoda hangi şablonlar kaç kez kullanıldı; az kullanılanları öne çıkar
        import collections
        src = (ROOT / "remotion" / "src" / "auto" / "AutoVideo.tsx").read_text(encoding="utf-8")
        blk = src[src.index("export const TEMPLATES"):src.index("// ---------------- Çekim")]
        known = set(re.findall(r"([A-Z][A-Za-z0-9]+): [ABCD]\.", blk)) | {"Gauge", "Dots"}
        cnt = collections.Counter()
        vids = sorted((ROOT / "output").glob("daily-2*/video.json"), key=lambda p: p.stat().st_mtime)[-5:]
        for vp in vids:
            for sc in json.loads(vp.read_text(encoding="utf-8")).get("scenes", []):
                cnt[sc.get("t")] += 1
        if cnt:
            heavy = ", ".join(f"{k}×{v}" for k, v in cnt.most_common(6))
            unused = sorted((k for k in known if cnt[k] <= 2 and k not in ("Intro", "Outro", "Chapter", "Disclaimer")), key=lambda k: cnt[k])
            nl = chr(10)
            out += (nl * 2 + "## SAHNE ÇEŞİTLİLİĞİ (otomatik denetim, son %d videonun şablon sayımı)" + nl +
                    "Çok kullanılanlar: %s. Bu videoda bunları azalt; aynı şablonu art arda kullanma ve toplam şablon çeşidini ARTIR (en az 9 farklı tür). "
                    "Hiç/az (≤2) kullanılmış, bu konuya uyabilecek şablonlar: %s. Konuya gerçekten uyuyorsa en az 3 tanesini dene "
                    "(uymayanı zorlama; veri doğruluğu çeşitlilikten önce gelir)." + nl) % (len(vids), heavy, ", ".join(unused[:14]) or "-")
    except Exception:  # noqa: BLE001
        pass
    return out


def main():
    # 9 Eki: PC uyku modundayken görev uyandırır (WakeToRun); iş bitene kadar Windows yeniden uyumasın.
    # Süreç bitince bayrak kendiliğinden kalkar, normal uyku ayarı geri döner.
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="iş klasörü adı (varsayılan daily-YYYYMMDD)")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--skip-claude", action="store_true")
    ap.add_argument("--resume", action="store_true", help="tamamlanan üretim adımlarını atla")
    ap.add_argument("--topic", help="konuyu sabitle (Claude konu seçmez)")
    ap.add_argument("--twin", action="store_true", help="uzun videoyu dijital ikizle (kendi çekimin + dudak senkronu) üret")
    ap.add_argument("--auto", action="store_true", help="Görev Zamanlayıcı koşusu: tarayıcıda yetki istemez, hata verir")
    ap.add_argument("--shorts-only", action="store_true", help="bugün uzun video yok, yalnız Shorts")
    ap.add_argument("--long", action="store_true", help="uzun video gününü zorla (long_days dışında da)")
    ap.add_argument("--mega", type=int, metavar="DK", help="özel uzun format: hedef dakika (ör. 40); uzun video gününü de zorlar")
    ap.add_argument("--publish-long", help="uzun video yayın saati (ör. 17:00), config auto_publish.long'u ezer")
    a = ap.parse_args()
    if os.name == "nt":  # 26 Eki: zamanlayıcıyla uyanan PC ~2-5 dk sonra "System Idle" ile geri uyuyordu -> koşu boyunca uyanık tut
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000040)  # CONTINUOUS|SYSTEM_REQUIRED|AWAYMODE
        except Exception:
            pass
    if a.mega:
        os.environ["SP_MEGA_MIN"] = str(a.mega)
        a.long = True
    if a.publish_long:
        os.environ["SP_PUBLISH_LONG"] = a.publish_long
    if a.auto:
        os.environ["SP_UNATTENDED"] = "1"

    today = datetime.now()
    job_id = a.job or f"daily-{today:%Y%m%d}"
    # 9 Eki: haftada 3 uzun video (config daily.long_days, 0=Pzt), diğer günler yalnız 3 Shorts
    global REQUIRED
    long_days = load_config().get("daily", {}).get("long_days", [0, 2, 4])
    shorts_only = (a.shorts_only or today.weekday() not in long_days) and not a.long
    if shorts_only:
        REQUIRED = ("brief.json", "series.json", "reels.json")
    job_dir = ROOT / "output" / job_id
    log = Log(DAILY / f"{today:%Y-%m-%d}.log")
    lock = DAILY / ".lock"
    if lock.exists() and _lock_stale(lock):
        log(f"eski kilit temizlendi ({lock.read_text(encoding='utf-8').strip()}) — sahibi yaşamıyor/yeniden başlatma")
        lock.unlink(missing_ok=True)
    if lock.exists() and time.time() - lock.stat().st_mtime < 14 * 3600:
        log(f"kilit var ({lock}), başka bir koşu sürüyor — çıkılıyor")
        return 2
    lock.write_text(str(os.getpid()), encoding="utf-8")
    report = {"job": job_id, "start": today.isoformat(timespec="seconds")}
    if not a.no_upload:  # 15 Eki: token düşmüşse saatlerce üretip sonda yüklenemeyen koşuyu başlatma
        try:
            from pipeline.stages import s09_upload
            s09_upload._get_credentials()
        except Exception as e:  # noqa: BLE001
            msg = str(e)[:160]
            log(f"YOUTUBE YETKİSİ GEÇERSİZ — üretim başlatılmadı: {msg}. Çözüm: python tools/reauth_google.py")
            try:  # görünür uyarı (otomatik koşuda kullanıcı ekranda değil)
                import subprocess
                subprocess.run(["msg", "*", "Saglam Para: YouTube yetkisi dustu. python tools/reauth_google.py calistir."],
                               timeout=10, check=False)
            except Exception:  # noqa: BLE001
                pass
            lock.unlink(missing_ok=True)
            return 3
    try:  # 30 Eyl: kapak CTR raporlarını güncelle (Reporting API) -> output/_brain/ctr.json; hata olursa üretim sürer
        from tools import ctr_report
        ctr_report.main()
    except Exception as e:  # noqa: BLE001
        log(f"CTR raporu alınamadı (üretim sürüyor): {str(e)[:120]}")
    try:  # 30 Eyl: YouTube arama önerileri (gerçek Türkçe sorgular) -> output/_brain/yt_suggest.json (başlık/etiket SEO)
        from tools import yt_suggest
        yt_suggest.main(yt_suggest.SEEDS)
    except Exception as e:  # noqa: BLE001
        log(f"arama önerileri alınamadı: {str(e)[:120]}")
    try:  # 30 Eyl: elle yüklenen videolarda AI beyanı unutulmasın (Studio varsayılanı "Hayır")
        from tools import ensure_ai_disclosure
        ensure_ai_disclosure.main(2, log=log)
    except Exception as e:  # noqa: BLE001
        log(f"AI beyanı kontrolü yapılamadı: {str(e)[:120]}")
    try:  # 1 Eki: kanal performans geri bildirimi (konu kategorisi başına izlenme / izlenme oranı) -> output/_brain/perf.json
        from tools import perf_report
        perf_report.main()
    except Exception as e:  # noqa: BLE001
        log(f"performans raporu alınamadı: {str(e)[:120]}")
    try:  # 30 Eyl: Google Trends TR günlük yükselen aramalar -> output/_brain/trends_tr.json (konu zamanlaması)
        from tools import trends_tr
        trends_tr.main()
    except Exception as e:  # noqa: BLE001
        log(f"trendler alınamadı: {str(e)[:120]}")
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        missing = [n for n in REQUIRED if not (job_dir / n).exists()]
        sess_file = job_dir / "_raw" / "claude_session.txt"
        if not a.skip_claude and missing:
            prev = sess_file.read_text(encoding="utf-8").strip() if sess_file.exists() else None
            if prev and len(missing) < len(REQUIRED):
                log(f"== {job_id}: yarım kalan Claude oturumu sürdürülüyor (eksik: {missing})")
                out = claude_resilient("Yarıda kaldın. Klasördeki dosyaları oku ve EKSİK olanları (" + ", ".join(missing)
                                       + ") talimattaki şemaya göre tamamla. Bitmiş dosyaları baştan yazma.", job_dir, log, prev)
            else:
                log(f"== {job_id}: Claude araştırma + yazım başlıyor")
                log(f"== {job_id}: " + ("YALNIZ-SHORTS günü" if shorts_only else "uzun video + Shorts günü"))
                tf = DAILY / f"topic_{datetime.now():%Y-%m-%d}.txt"  # 25 Eki: o güne sabit konu (Görev Zamanlayıcı koşusu için)
                if not a.topic and tf.exists():
                    a.topic = tf.read_text(encoding="utf-8").strip() or None
                    log(f"sabit konu dosyası: {a.topic[:80] if a.topic else '-'}")
                out = claude_resilient(build_prompt(job_dir, a.topic, shorts_only), job_dir, log)
            session = out.get("session_id")
            from pipeline.daily.parts import merge_parts
            log(f"video parçaları birleştirildi: {merge_parts(job_dir)}")
            (job_dir / "_raw").mkdir(parents=True, exist_ok=True)
            sess_file.write_text(session or "", encoding="utf-8")
            rounds = int(load_config().get("daily", {}).get("claude", {}).get("max_fix_rounds", 2))
            for k in range(rounds + 1):
                v = (validate_shorts if shorts_only else validate)(job_dir)
                (job_dir / "_raw" / "validation.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
                log(f"doğrulama: ok={v['ok']} hata={len(v['errors'])} uyarı={len(v['warnings'])} kelime={v.get('tts_words')} tahmini={v.get('est_seconds')}s")
                if v["ok"]:
                    break
                if k == rounds:
                    raise RuntimeError("doğrulama düzeltilemedi:\n- " + "\n- ".join(v["errors"][:25]))
                fix = ("Doğrulayıcı şu HATALARI buldu, dosyaları düzelt (yalnızca gerekli yerleri değiştir, aynı klasöre yaz):\n- "
                       + "\n- ".join(v["errors"][:40]) + ("\n\nUyarılar (mümkünse düzelt):\n- " + "\n- ".join(v["warnings"][:20]) if v["warnings"] else ""))
                log(f"düzeltme turu {k + 1}")
                out = claude_resilient(fix, job_dir, log, session=session)
                session = out.get("session_id", session)
                merge_parts(job_dir)
        else:
            v = (validate_shorts if shorts_only else validate)(job_dir)
            log(f"doğrulama (mevcut dosyalar): ok={v['ok']} {v['errors'][:5]}")
            if not v["ok"]:
                raise RuntimeError("mevcut dosyalar doğrulamadan geçmedi")
        report["validation"] = json.loads((job_dir / "_raw" / "validation.json").read_text(encoding="utf-8")) if (job_dir / "_raw" / "validation.json").exists() else None
        try:  # Türkçe kanca puanı (yalnız rapor; koşuyu asla durdurmaz)
            sys.path.insert(0, str(ROOT / "tools"))
            import hookscore_tr
            hs = [dict(hookscore_tr.score(t), label=lab) for lab, t in hookscore_tr.from_daily(job_dir)]
            (job_dir / "_raw" / "hookscore.json").write_text(json.dumps(hs, ensure_ascii=False, indent=1), encoding="utf-8")
            report["hookscore"] = [{k: r[k] for k in ("label", "verdict", "band", "weakest")} for r in hs]
            log("kanca puanı: " + ", ".join(f"{r['label']}={r['verdict']} ({r['weakest']})" for r in hs))
        except Exception as e:
            log(f"kanca puanı atlandı: {e}")

        from pipeline.daily.build import Build
        log("== üretim başlıyor (ses -> render -> yükleme)")
        b = Build(job_dir, log=log, twin=a.twin)
        if not a.resume:
            b.status = {k: v for k, v in b.status.items() if k in ("upload", "drive", "history")}
        res = b.run(upload=not a.no_upload)
        report.update(result=res, ok=True)
        log(f"== BİTTİ: {res['title']} · {res['seconds'] / 60:.2f} dk · {res.get('upload', {}).get('url', 'yüklenmedi')}")
    except Exception as e:  # noqa: BLE001
        report.update(ok=False, error=str(e), trace=traceback.format_exc())
        log(f"!! HATA: {e}")
        (DAILY / f"{today:%Y-%m-%d}_HATA.txt").write_text(f"{e}\n\n{traceback.format_exc()}", encoding="utf-8")
    finally:
        report["end"] = datetime.now().isoformat(timespec="seconds")
        (DAILY / f"{today:%Y-%m-%d}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        _md(report, DAILY / f"{today:%Y-%m-%d}.md", job_dir)
        lock.unlink(missing_ok=True)
    return 0 if report.get("ok") else 1


def _md(rep: dict, path: Path, job_dir: Path):
    lines = [f"# Günlük rapor · {rep['job']}", "", f"- Başlangıç: {rep['start']}  ·  Bitiş: {rep.get('end')}", f"- Durum: {'✅ tamam' if rep.get('ok') else '❌ HATA'}"]
    if rep.get("ok"):
        r = rep["result"]
        lines += [f"- Başlık: **{r['title']}**", f"- Süre: {r['seconds'] / 60:.2f} dk", f"- YouTube (private): {r.get('upload', {}).get('url', '-')}",
                  "- 16:00: YouTube Studio'dan yayına al + sabit yorumu yapıştır. Reels: Drive klasöründeki reels_metinleri.txt"]
    else:
        lines += ["", "```", str(rep.get("error")), "```"]
    v = rep.get("validation") or {}
    if v.get("warnings"):
        lines += ["", "## Doğrulama uyarıları", *[f"- {w}" for w in v["warnings"][:30]]]
    st = job_dir / "_raw" / "status.json"
    if st.exists():
        lines += ["", "## Adımlar", "```json", st.read_text(encoding="utf-8"), "```"]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
