"""Claude'un yazdığı günlük iş dosyalarını (video.json, reels.json, thumb.json, brief.json, series.json)
render'dan ÖNCE denetler. Hatalar (errors) Claude'a düzeltme için geri gönderilir; uyarılar (warnings) rapora yazılır.

Kontroller: şema, uzunluk (uzun video ≥ 1300 tts kelime), tts'te rakam, segment uzunluğu, sahne şablon adları,
cue sözdizimi + artan sıra + segment sınırı, grafik sembollerinin series.json'da olması, yasaklı yatırım dili,
kapak iddialarının videoda geçmesi (yanıltıcı kapak), Reels süresi.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TEMPLATES = {
    "Intro", "KineticTitle", "Stamp", "StatCards", "Gauge", "Dots", "ReasonCards", "Quote", "Chart", "Normalized", "Compare",
    "Ladder", "Scenario", "RangeBar", "Vote", "Bars", "Volatility", "Timeline", "CoinFlip", "Tug", "AssetCards", "Chapter",
    "Disclaimer", "Poll", "Outro", "DateQuestion",
    # 29 Eyl kütüphane turu 1
    "Candles", "Heatmap", "WorldMap", "YieldCurve", "Breaking", "Countdown", "Headline", "Metal3D", "Globe3D", "Object3D", "Bars3D", "Stack3D", "Scale3D", "HostStage",
    "PumpBoard", "Waterfall", "DominoChain",
}
REEL_TEMPLATES = {"KineticTitle", "Stamp", "Gauge", "StatCards", "Chart", "Compare", "Scenario", "Dots", "AssetCards", "Bars", "Poll", "Outro", "DateQuestion", "Candles", "Breaking", "Countdown", "Metal3D", "Headline", "Object3D", "Bars3D", "Stack3D", "Scale3D", "HostStage"}
SFX = {"sub_boom", "stamp_press", "pop_clean", "bubble_pop", "impact_soft", "coin_drop", "cash_register", "whoosh_fast", "whoosh_subtle", "paper_slide",
       # 30 Eyl sentez kütüphanesi (scripts/gen_sfx.py)
       "impact_deep_1", "impact_deep_2", "impact_tight", "riser_1", "riser_2", "downer_1", "downer_2", "chime_up", "chime_soft", "chime_down",
       "heartbeat", "glitch", "ui_pop_1", "ui_pop_2", "metal_ring_gold", "metal_ring_silver", "alert_breaking", "counter_ticks", "blips",
       # 9 Eki yön sesleri
       "rise_steps", "fall_steps", "lift_whoosh", "drop_whoosh", "number_lock"}
HISTORY = Path(__file__).resolve().parents[2] / "output" / "_brain" / "daily_history.jsonl"
# 10 Eki: son 2 haftada 6+ uzun başlıkta kullanılıp abone akışı dışına çıkamayan kalıplar
BANNED_TITLE = [r"^\s*(gram\s+)?alt[ıi]n\s+ne\s+olacak", r"\|\s*(günün olayı|haftanın kapanışı|haftaya başlarken|uzun vade)\s*$"]


def _head(t: str, n: int = 3) -> str:
    return " ".join(re.findall(r"\w+", t.lower())[:n])


def _title_repeat_errors(titles: list[str]) -> list[str]:
    """Yasaklı kalıp + son 5 uzun videonun başlığıyla aynı ilk 3 kelime -> hata."""
    errs = []
    prev = []
    try:
        for line in HISTORY.read_text(encoding="utf-8").splitlines()[-12:]:
            t = (json.loads(line).get("title") or "").strip()
            if t and "#shorts" not in t.lower():
                prev.append(t)
    except Exception:  # noqa: BLE001
        pass
    heads = {_head(t) for t in prev[-5:]}
    for k, t in enumerate(x for x in titles if x):
        for p in BANNED_TITLE:
            if re.search(p, t, re.I):
                errs.append(f"başlık[{k}] '{t}': yıpranmış kalıp ({p}) — farklı yapı kur (soru/rakam/sonuç/karşılaştırma), seri adı başlığa değil açılışa")
        if _head(t) in heads:
            errs.append(f"başlık[{k}] '{t}': ilk 3 kelime son 5 uzun videodan biriyle aynı ('{_head(t)}') — başlıklar birbirini yiyor, farklı aç")
    return errs


BANNED = [r"\bkesin(likle)? (yükselecek|düşecek|yükselir|düşer)\b", r"\bhemen (al|satın al|sat)\b", r"\bgaranti(li)? (kazanç|getiri)\b",
          r"\bzengin ol", r"\bkaçırmayın\b.*\bfırsat", r"\byatırım tavsiyesi(dir)?\b(?!\s*değil)"]
CUE_RE = re.compile(r"^(\d+)(?::(.+?))?([+-]\d+)?$")
MIN_LONG_WORDS = 1300
WORDS_PER_SEC = 153.5 / 60


def _words(s: str) -> int:
    return len(s.split())


def _norm(s: str) -> str:
    return re.sub(r"[^\w]", "", s.replace("İ", "i").replace("I", "ı").lower())


def _check_segments(segs: list, where: str, errors: list, warnings: list, min_words: int, max_words: int = 45):
    if not isinstance(segs, list) or not segs:
        errors.append(f"{where}: segments boş")
        return 0
    total = 0
    for i, s in enumerate(segs):
        tts, text = (s or {}).get("tts", ""), (s or {}).get("text", "")
        if not tts or not text:
            errors.append(f"{where} seg {i}: tts ve text zorunlu")
            continue
        if re.search(r"\d", tts):
            digits = re.findall(r"[^ ]*\d[^ ]*", tts)[:3]
            errors.append(f"{where} seg {i}: tts'te rakam var ({digits}) — sayıları kelimeyle yaz")
        n = _words(tts)
        total += n
        if n < min_words:
            warnings.append(f"{where} seg {i}: {n} kelime (<{min_words}) — kısa tek segment ses tonunu oynatabilir")
        if n > max_words:
            warnings.append(f"{where} seg {i}: {n} kelime (>{max_words})")
        # 18 Eki analitik dersi: rakam yığını ve yol haritası cümleleri tutma uçurumu yaratıyor (retention.json)
        for sent in re.split(r"(?<=[.!?;])\s+", text):
            nums = re.findall(r"\d[\d.,]*", sent)
            if len(nums) > 2:
                warnings.append(f"{where} seg {i}: bir cümlede {len(nums)} rakam (uçurum riski, en fazla 2; fazlası ekrana) — '{sent[:70]}'")
        if re.search(r"bu videoda \w+ şey|videonun sonunda|hepsini kendim ölçtüm", text, re.IGNORECASE):
            warnings.append(f"{where} seg {i}: yol haritası/yöntem cümlesi (izleyici burada ayrılıyor) — '{text[:70]}'")
        for pat in BANNED:
            if re.search(pat, _norm_space(text), re.IGNORECASE):
                errors.append(f"{where} seg {i}: yasaklı yatırım dili ({pat}) — '{text[:80]}'")
    return total


def _norm_space(s: str) -> str:
    return s.replace("İ", "i").lower()


def _check_scenes(scenes: list, segs: list, where: str, series: dict, errors: list, warnings: list, allowed: set):
    if not scenes:
        errors.append(f"{where}: scenes boş")
        return
    last = -1
    prev_t = None
    for i, sc in enumerate(scenes):
        t = sc.get("t")
        if t not in allowed:
            errors.append(f"{where} sahne {i}: bilinmeyen/izin verilmeyen şablon '{t}'")
            continue
        if t == "Chapter":
            b = sc.get("before")
            if not isinstance(b, int) or not (0 < b < len(segs)):
                errors.append(f"{where} sahne {i}: Chapter 'before' geçerli bir segment no olmalı")
            else:
                last = max(last, b - 1)
            continue
        if i == 0 and t == "Intro":
            continue
        cue = str(sc.get("cue", ""))
        m = CUE_RE.match(cue)
        if not m:
            errors.append(f"{where} sahne {i} ({t}): geçersiz cue '{cue}'")
            continue
        seg = int(m.group(1))
        if seg >= len(segs):
            errors.append(f"{where} sahne {i} ({t}): cue segmenti {seg} yok (toplam {len(segs)})")
        if _cue_trap(cue, segs):
            errors.append(f"{where} sahne {i} ({t}): cue {_cue_trap(cue, segs)}")
        if seg < last:
            errors.append(f"{where} sahne {i} ({t}): cue {cue} önceki sahneden geride — sahneler segment sırasıyla ilerlemeli")
        last = max(last, seg)
        if t == prev_t and t not in ("Chart",):
            warnings.append(f"{where} sahne {i}: '{t}' art arda iki kez")
        prev_t = t
        p = sc.get("p") or {}
        syms = [p.get("symbol")] + [x.get("symbol") for x in p.get("lines", []) + p.get("items", []) if isinstance(x, dict)]
        for s in [s for s in syms if s]:
            if s not in series:
                errors.append(f"{where} sahne {i} ({t}): sembol '{s}' series.json'da yok — market_snapshot ile ekle")
        _check_inner_cues(p, segs, f"{where} sahne {i} ({t})", errors, warnings)


def _cue_trap(cue: str, segs: list) -> str | None:
    """29 Eyl QA bulgusu: "15:25" gibi 1–2 haneli anahtar KELİME SIRASI okunur; yazar ise çoğu zaman rakamı kastediyor
    (bir videoda 7 sahne yanlış anda girdi). Rakam segmentte geçiyorsa ya da sıra kelime sayısını aşıyorsa hata."""
    m = CUE_RE.match(str(cue))
    if not m or not m.group(2) or not re.fullmatch(r"\d{1,2}", m.group(2)) or int(m.group(1)) >= len(segs):
        return None
    words = segs[int(m.group(1))]["text"].split()
    k = int(m.group(2))
    if k >= len(words):
        return f"'{cue}': segmentte {len(words)} kelime var, {k}. kelime yok (1–2 haneli sayı KELİME SIRASIDIR)"
    if any(re.sub(r"\D", "", w).startswith(m.group(2)) for w in words):
        return f"'{cue}': 1–2 haneli sayı kelime sırası olarak okunur, rakam olarak değil — rakamın yanındaki kelimeyi kullan"
    return None


def _check_inner_cues(obj, segs, where, errors, warnings):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if (k == "cue" or k.endswith("Cue")) and isinstance(v, (str, int)):
                m = CUE_RE.match(str(v))
                if not m:
                    errors.append(f"{where}: geçersiz {k} '{v}'")
                elif int(m.group(1)) >= len(segs):
                    errors.append(f"{where}: {k} '{v}' segmenti yok")
                elif _cue_trap(str(v), segs):
                    errors.append(f"{where}: {k} {_cue_trap(str(v), segs)}")
                elif m.group(2) and not re.fullmatch(r"\d+|end", m.group(2).split("#")[0]):
                    word = _norm(m.group(2).split("#")[0])
                    words = [_norm(w) for w in segs[int(m.group(1))]["text"].split()]
                    if not any(w.startswith(word) for w in words):
                        warnings.append(f"{where}: {k} '{v}' — kelime segmentin ekran metninde yok, segment başına düşer")
            else:
                _check_inner_cues(v, segs, where, errors, warnings)
    elif isinstance(obj, list):
        for x in obj:
            _check_inner_cues(x, segs, where, errors, warnings)


THREE_D = {"Metal3D", "Globe3D", "Object3D", "Bars3D", "Stack3D", "Scale3D", "HostStage"}


def _check_design(job_dir: Path, scenes_sets: dict, errors: list, warnings: list) -> None:
    """18 Eki: storyboard.json + bible.json zorunlu; 3D (three.js) sahne payı ve kahraman nesne zinciri."""
    sb, bb = job_dir / "storyboard.json", job_dir / "bible.json"
    for f in (sb, bb):
        if not f.exists():
            errors.append(f"{f.name} yok — önce storyboard + tasarım rehberi yaz (prompt bölüm 2b)")
    try:
        board = json.loads(sb.read_text(encoding="utf-8")) if sb.exists() else {}
        bible = json.loads(bb.read_text(encoding="utf-8")) if bb.exists() else {}
    except Exception as e:  # noqa: BLE001
        errors.append(f"storyboard/bible geçersiz JSON: {e}")
        return
    if bb.exists() and not all(bible.get(k) for k in ("palette", "hero_chain", "camera", "entrances", "banned")):
        warnings.append("bible.json: palette/hero_chain/camera/entrances/banned alanlarından biri boş")
    for where, scenes in scenes_sets.items():
        ts = [s.get("t") for s in scenes or []]
        n3 = sum(t in THREE_D for t in ts)
        need = 8 if where == "video" else 2
        if n3 < need:
            warnings.append(f"{where}: {n3} adet 3D sahne — en az {need} olmalı (three.js görsel omurga, 18 Eki)")
        for a, b in zip(ts, ts[1:]):
            if a == b and a in THREE_D:
                warnings.append(f"{where}: {a} art arda iki kez")
                break
        if board and not (board.get(where) or {}).get("shots"):
            warnings.append(f"storyboard.json: '{where}' için shots listesi yok")


def validate(job_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    load = {}
    for name in ("brief.json", "video.json", "reels.json", "thumb.json", "series.json"):
        f = job_dir / name
        if not f.exists():
            errors.append(f"{name} yok")
            continue
        try:
            load[name] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name} geçersiz JSON: {e}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    series = {k: v for k, v in load["series.json"].items() if isinstance(v, dict) and "series" in v}
    video, reels, thumb, brief = load["video.json"], load["reels.json"], load["thumb.json"], load["brief.json"]

    for k in ("title", "description", "segments", "scenes"):
        if not video.get(k):
            errors.append(f"video.json: '{k}' eksik")
    if len(video.get("title", "")) > 100:
        errors.append("video.json: başlık 100 karakteri aşıyor")
    segs = video.get("segments", [])
    total = _check_segments(segs, "video", errors, warnings, min_words=18, max_words=50)
    est = total / WORDS_PER_SEC + len(segs) * 0.35 + 9
    import os
    min_words = int(int(os.environ["SP_MEGA_MIN"]) * WORDS_PER_SEC * 60 * 0.9) if os.environ.get("SP_MEGA_MIN") else MIN_LONG_WORDS
    if total < min_words:
        errors.append(f"video: toplam {total} tts kelime (< {min_words}); tahmini süre {est / 60:.1f} dk — 8 dk'nın üstüne çıkmak için metni genişlet")
    _check_scenes(video.get("scenes", []), segs, "video", series, errors, warnings, TEMPLATES)
    for h in video.get("hits", []):
        if h.get("sfx") not in SFX:
            warnings.append(f"video hit: bilinmeyen sfx '{h.get('sfx')}' atlanır")
    for s in video.get("ticker", []):
        if s not in series:
            warnings.append(f"ticker: {s} series.json'da yok, atlanır")
    # 29 Eyl: başlık testi (3 varyant), sakin tempo, "birazdan" köprüleri, açılış A/B varyantları
    titles = video.get("titles") or []
    if len(titles) != 3:
        warnings.append(f"video: 'titles' 3 varyant olmalı ({len(titles)} var) — YouTube başlık testi için")
    for k, t in enumerate(titles):
        if len(t) > 100:
            errors.append(f"video: titles[{k}] 100 karakteri aşıyor")
        elif len(t) > 75:
            warnings.append(f"video: titles[{k}] {len(t)} karakter — mobilde ~60'tan sonrası kesilir, ≤70 hedefle")
    # 10 Eki (analiz): uzun videolar neredeyse yalnız abonelerden izleniyor, önerilen ~0 — aynı kalıptaki başlıklar ("Altın Ne Olacak?…",
    # "| Günün Olayı") birbirini yiyor ve "tekrarlayan içerik" sinyali veriyor -> hata: Claude başlığı yeniden yazar
    errors += _title_repeat_errors([video.get("title", "")] + list(titles))
    # 10 Eki: Türkçe başlık+kapak çifti denetimi (yalnız uyarı; pipeline/daily/lint_tr.py)
    try:
        from pipeline.daily.lint_tr import lint_messages
        _ta = thumb.get("A") or {}
        _thumb_txt = " ".join(_ta.get("headline") or []) or _ta.get("text", "")
        for k, t in enumerate(titles):
            warnings += lint_messages(title=t, thumb_text=_thumb_txt, where=f"titles[{k}] ")
    except Exception:
        pass
    if len(video.get("hits", [])) > 10:
        warnings.append(f"video: {len(video['hits'])} ses efekti — en fazla 8 (finans izleyicisi abartıyı sevmiyor)")
    teasers = sum(len(re.findall(r"\bbirazdan\b", _norm_space(s.get("text", "")))) for s in segs)
    if teasers < 2:
        warnings.append(f"video: {teasers} 'birazdan' köprüsü — 3–4 olmalı (izlenme süresi)")
    for v_i, hv in enumerate(video.get("hook_variants", [])):
        where = f"hook{chr(66 + v_i)}"
        hs = hv.get("segments", [])
        if len(hs) != 1:
            errors.append(f"{where}: tam 1 segment olmalı (ana videonun ilk segmentinin yerine geçer)")
            continue
        _check_segments(hs, where, errors, warnings, min_words=20, max_words=50)
        if _norm_space(hs[0].get("text", "")).startswith("merhaba"):
            warnings.append(f"{where}: selamla başlıyor — kanca ilk cümlede olmalı (açılış araştırması)")
        _check_scenes(hv.get("scenes", []), hs, where, series, errors, warnings, TEMPLATES)

    if segs and _norm_space(segs[0].get("text", "")).startswith("merhaba"):
        warnings.append("video seg 0: selamla başlıyor — ilk 5 sn kanca olmalı, selam en fazla 2. cümlede")
    full_text = " ".join(s.get("text", "") for s in segs)
    if not re.search(r"yatırım tavsiyesi değil", _norm_space(full_text)):
        errors.append("video: seslendirmede 'yatırım tavsiyesi değildir' uyarısı yok")
    if not brief.get("sources"):
        errors.append("brief.json: kaynak listesi boş")

    _check_reels(reels, series, errors, warnings)
    _check_thumbs(thumb, full_text, series, errors, warnings)
    _check_design(job_dir, {"video": video.get("scenes", []), **{f"reel{i + 1}": r.get("scenes", []) for i, r in enumerate(reels if isinstance(reels, list) else [])}}, errors, warnings)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "tts_words": total, "est_seconds": round(est)}


def validate_shorts(job_dir: Path) -> dict:
    """9 Eki: yalnız-Shorts günü (uzun video yok): brief + series + reels."""
    errors: list[str] = []
    warnings: list[str] = []
    load = {}
    for name in ("brief.json", "reels.json", "series.json"):
        f = job_dir / name
        if not f.exists():
            errors.append(f"{name} yok")
            continue
        try:
            load[name] = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name} geçersiz JSON: {e}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}
    series = {k: v for k, v in load["series.json"].items() if isinstance(v, dict) and "series" in v}
    if not load["brief.json"].get("sources"):
        errors.append("brief.json: kaynak listesi boş")
    _check_reels(load["reels.json"], series, errors, warnings)
    rl = load["reels.json"] if isinstance(load["reels.json"], list) else []
    _check_design(job_dir, {f"reel{i + 1}": r.get("scenes", []) for i, r in enumerate(rl)}, errors, warnings)
    return {"ok": not errors, "errors": errors, "warnings": warnings, "tts_words": 0, "est_seconds": 0}


def _check_reels(reels, series, errors: list[str], warnings: list[str]) -> None:
    from pipeline.utils.config import load_config
    n_reels = int(load_config().get("daily", {}).get("reels_count", 3))  # 9 Eki: günde 3 Shorts (config daily.reels_count)
    if not isinstance(reels, list) or len(reels) != n_reels:
        errors.append(f"reels.json: tam {n_reels} reel olmalı")
    else:
        for r_i, r in enumerate(reels):
            rs = r.get("segments", [])
            n = _check_segments(rs, f"reel{r_i + 1}", errors, warnings, min_words=12, max_words=45)
            if not (55 <= n <= 105):
                errors.append(f"reel{r_i + 1}: {n} kelime — 60–95 kelime olmalı (25–38 sn; Shorts'ta tamamlanma oranı için)")
            _check_scenes(r.get("scenes", []), rs, f"reel{r_i + 1}", series, errors, warnings, REEL_TEMPLATES)
            # 10 Eki: yarım biten son cümle seste "kesilmiş" gibi duyuluyor (kullanıcı şikâyeti) -> hata
            for key in ("tts", "text"):
                tail = (rs[-1].get(key) or "").strip() if rs else ""
                if tail and (tail[-1] not in ".!?" or tail.endswith("…")
                             or tail.rstrip(".!?").lower().endswith(("işte bu yüzden", " çünkü", " ve", " ama", " yani"))):
                    errors.append(f"reel{r_i + 1}: son segment '{key}' tam cümleyle ('.', '!' ya da '?') bitmeli; yarım cümle sesi kesilmiş gösterir: «{tail[-50:]}»")
                    break
            if not r.get("title") or not r.get("caption"):
                errors.append(f"reel{r_i + 1}: title/caption eksik")
            try:  # 10 Eki: kanca (ilk cümleler) + başlık denetimi, yalnız uyarı
                from pipeline.daily.lint_tr import lint_messages
                warnings += lint_messages(title=r.get("title"), hook_text=(rs[0].get("text", "") if rs else ""), where=f"reel{r_i + 1} ")
            except Exception:
                pass


def _check_thumbs(thumb, full_text: str, series, errors: list[str], warnings: list[str]) -> None:
    # Kapak dürüstlüğü: rozet/başlık sayıları ve anahtar kelimeleri videoda geçmeli
    digits_in_video = set(re.findall(r"\d+(?:[.,]\d+)?", full_text.replace(".", "")))
    for key in ("A", "B", "C"):
        spec = thumb.get(key)
        if not spec:
            errors.append(f"thumb.json: {key} eksik")
            continue
        if spec.get("style"):
            if spec["style"] not in ("object", "chart", "face"):
                errors.append(f"thumb {key}: style object|chart|face olmalı")
            if len((spec.get("text") or "").split()) > 4:
                errors.append(f"thumb {key}: kapak yazısı en fazla 4 kelime ('{spec.get('text')}')")
            if spec["style"] == "chart" and spec.get("symbol") not in series:
                errors.append(f"thumb {key}: chart kapağı için symbol series.json'da olmalı")
        claims = [spec.get("badge", ""), str(spec.get("gauge", "") or ""), str(spec.get("number", "") or ""), str(spec.get("threshold", "") or "")]
        for c in claims:
            for num in re.findall(r"\d+(?:[.,]\d+)?", c.replace(".", "")):
                if num not in digits_in_video:
                    errors.append(f"thumb {key}: kapaktaki '{c}' videoda geçmiyor (yanıltıcı kapak riski)")
        for line in spec.get("headline", []) + [r.get("text", "") for r in spec.get("rows", [])]:
            w = _norm(line.split()[0]) if line.split() else ""
            if len(w) > 3 and w not in _norm(full_text):
                warnings.append(f"thumb {key}: başlık kelimesi '{line}' metinde birebir geçmiyor — iddiayla uyumlu olduğundan emin ol")


if __name__ == "__main__":
    import sys
    print(json.dumps(validate(Path(sys.argv[1])), ensure_ascii=False, indent=1))
