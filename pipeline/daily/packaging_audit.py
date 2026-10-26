"""Yükleme öncesi paketleme denetçisi (15 Eki): başlık + kapak + Shorts başlıkları izleyiciyi tıklatacak seviyede mi?

Zayıfsa Claude düzeltir (başlık/kapak yazısı), kapak gerekirse yeniden render edilir. Hat boyunca SON adımdır:
Build.upload()'tan hemen önce çalışır. Hata/limit olursa yüklemeyi ENGELLEMEZ (mevcut paketle devam eder).
Dürüstlük kuralı: clickbait = merak + somut rakam + gerilim; ama yalan/abartı/getiri vaadi YOK (YouTube + finans politikası).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RUBRIC = """Sen bir YouTube paketleme (başlık + kapak) denetçisisin. Kanal: Finans Kanalı (Türkçe finans, altın/gümüş/Fed/TL).
Görevin: aşağıdaki başlık, kapak ve Shorts başlıklarını izleyiciyi TIKLATACAK seviyede mi diye denetlemek; değilse DÜZELTMEK.
"Biraz clickbait" istiyoruz: merak boşluğu, somut rakam, gerilim/tehdit ya da zıtlık. ANCAK:
- Başlık/kapaktaki her rakam ve iddia brief.json'daki doğrulanmış gerçeklerle uyumlu olmalı; yalan, abartı, kesin tahmin, "yatırım tavsiyesi", getiri vaadi YASAK.
- Kapakta gerçek insan yüzü YOK; kendini tanıtma ("Ben <sunucu>" vb.) YOK.
- Başlık kalıp tekrarı yasak: aşağıdaki SON BAŞLIKLAR ile aynı kalıba (aynı ilk 2 kelime / aynı yapı) benzemesin.
Ölçütler (0-10 puan ver): başlık = merak+rakam+duygu, ideal 45-65 karakter, anahtar kelime başta, kesilmez;
kapak = en çok 3-4 büyük kelime, tek büyük rakam, yüksek kontrast, başlıkla AYNI cümleyi tekrar etmeyip tamamlar.
Her ikisi >=8 ise "ok" de ve dokunma. Biri <8 ise "fix" de ve düzeltilmiş halini yaz.
Kapak görselini Read aracıyla aç: {thumb}
ÇIKTI: yalnız tek bir JSON nesnesi (başka metin yok), şema:
{"title_score":int,"thumb_score":int,"verdict":"ok"|"fix","reasons":"kısa gerekçe",
 "title":"son başlık (<=70 karakter)","titles":["alternatif1","alternatif2","alternatif3"],
 "thumb_A":{"text":"kapak yazısı BÜYÜK HARF, <=4 kelime","number":"tek büyük rakam/oran ya da boş"} | null,
 "reel_titles":["reel1 başlığı","reel2 başlığı"]}
Kapak iyiyse thumb_A=null. Reel başlıkları zayıfsa düzelt, iyiyse aynen yaz.
"""


def _claude_json(prompt: str, log) -> dict:
    from pipeline.utils.config import load_config
    cfg = load_config().get("daily", {}).get("claude", {})
    exe = "claude.cmd" if sys.platform == "win32" else "claude"
    cmd = [exe, "-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--allowedTools", "Read",
           "--disallowedTools", "Bash,Write,Edit", "--effort", str(cfg.get("effort", "high"))]
    import os
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), timeout=15 * 60, env=env)
    out = json.loads(r.stdout)
    if out.get("is_error"):
        raise RuntimeError(str(out.get("result"))[:300])
    txt = str(out.get("result", ""))
    a, b = txt.find("{"), txt.rfind("}")
    if a < 0 or b <= a:
        raise RuntimeError(f"JSON yok: {txt[:200]}")
    return json.loads(txt[a:b + 1])


def _recent_titles(n: int = 12) -> list[str]:
    h = ROOT / "output" / "_brain" / "daily_history.jsonl"
    titles: list[str] = []
    if h.exists():
        for line in h.read_text(encoding="utf-8").splitlines()[-n:]:
            try:
                titles.append(json.loads(line).get("title", ""))
            except Exception:  # noqa: BLE001
                pass
    return [t for t in titles if t]


def audit(b, reels_only: bool = False) -> dict | None:
    """b: pipeline.daily.build.Build. Başlık/kapağı (gerekirse) düzeltir; sonucu _raw/packaging_audit.json'a yazar."""
    from pipeline.utils.config import load_config
    if not load_config().get("daily", {}).get("packaging_audit", {}).get("enabled", True):
        return None
    if b._skip("packaging_audit"):
        return None
    log = b.log
    try:
        meta_f = b.job / "metadata.json"
        meta = json.loads(meta_f.read_text(encoding="utf-8")) if (meta_f.exists() and not reels_only) else {}
        thumb = b.job / "thumbnail.jpg"
        brief = json.loads((b.job / "brief.json").read_text(encoding="utf-8"))
        ctx = {
            "brief": {k: brief.get(k) for k in ("topic", "why_today", "facts")},
            "uzun_baslik": None if reels_only else meta.get("title"),
            "baslik_alternatifleri": None if reels_only else meta.get("title_variants"),
            "kapak_A_ayarlari": None if reels_only else b.thumb.get("A"),
            "reel_basliklari": [r.get("title") for r in b.reels],
            "SON BAŞLIKLAR (kalıp tekrarı yasak)": _recent_titles(),
        }
        if reels_only:
            prompt = RUBRIC.replace("Kapak görselini Read aracıyla aç: {thumb}", "Bu koşuda uzun video/kapak yok: yalnız reel_titles'ı denetle; thumb_A=null, title=\"\".")
        else:
            prompt = RUBRIC.replace("{thumb}", str(thumb))
        prompt += "\nBAĞLAM:\n" + json.dumps(ctx, ensure_ascii=False, indent=1)
        t0 = time.time()
        res = _claude_json(prompt, log)
        (b.raw / "packaging_audit.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"paketleme denetimi ({time.time() - t0:.0f}s): başlık {res.get('title_score')}/10, kapak {res.get('thumb_score')}/10 → {res.get('verdict')} — {str(res.get('reasons'))[:200]}")
        if res.get("verdict") == "fix":
            _apply(b, res, meta, meta_f, reels_only)
        b._done("packaging_audit", verdict=res.get("verdict"), title_score=res.get("title_score"), thumb_score=res.get("thumb_score"))
        return res
    except Exception as e:  # noqa: BLE001
        log(f"paketleme denetimi atlandı (yükleme mevcut paketle sürüyor): {str(e)[:200]}")
        return None


def _apply(b, res: dict, meta: dict, meta_f: Path, reels_only: bool):
    log = b.log
    # reel başlıkları
    rt = res.get("reel_titles") or []
    changed = False
    for i, r in enumerate(b.reels):
        if i < len(rt) and rt[i] and rt[i].strip() != r.get("title"):
            log(f"  reel{i + 1} başlığı: {r.get('title')!r} → {rt[i]!r}")
            r["title"] = rt[i].strip()[:100]
            changed = True
    if changed:
        (b.job / "reels.json").write_text(json.dumps(b.reels, ensure_ascii=False, indent=1), encoding="utf-8")
    if reels_only:
        return
    # uzun video başlığı
    new = (res.get("title") or "").strip()
    if new and new != meta.get("title"):
        log(f"  başlık: {meta.get('title')!r} → {new!r}")
        meta["title"] = new[:100]
        if res.get("titles"):
            meta["title_variants"] = [t[:100] for t in res["titles"]][:3]
        meta_f.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        b.video["title"] = meta["title"]
        vf = b.job / "video.json"
        v = json.loads(vf.read_text(encoding="utf-8"))
        v["title"] = meta["title"]
        vf.write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
    # kapak A: yazı/rakam değişirse yeniden render
    fix = res.get("thumb_A")
    if fix and isinstance(fix, dict):
        pf = b.raw / "props_thumb_A.json"
        props = json.loads(pf.read_text(encoding="utf-8"))
        spec = props["spec"]
        upd = {k: str(fix[k]) for k in ("text", "number") if k in fix and fix[k] is not None and str(fix[k]) != str(spec.get(k, ""))}
        if upd:
            log(f"  kapak A: {({k: spec.get(k) for k in upd})} → {upd} (yeniden render)")
            spec.update(upd)
            pf.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
            b.thumb["A"].update(upd)
            tf = b.job / "thumb.json"
            t = json.loads(tf.read_text(encoding="utf-8"))
            t["A"].update(upd)
            tf.write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
            b._npx(["still", "src/auto/index.ts", "AutoThumb", str(b.job / "thumb_A.png"), f"--props={pf}", "--gl=angle", "--scale=1.5", "--overwrite"], "thumb_A_audit.log")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(b.job / "thumb_A.png"), "-q:v", "2", str(b.job / "thumbnail.jpg")], check=True)
