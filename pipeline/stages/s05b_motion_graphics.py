"""Aşama 05b: Remotion animasyonlu motion graphics — 16 Eyl eklendi, opsiyonel/additive.

Üç şablon üretir (remotion/src/*.tsx), sırayla:

  1. MarketChart  — s04_visuals._inject_market_charts'ın CANLI matplotlib PNG grafiğiyle
     işaretlediği (is_chart=True) segmentler için: çizgi kendini çizer, fiyat son değere
     sayar, yön rozeti belirir. Fiyat/etiket metnini ASLA bozmaz (gerçek DOM text).
  2. StatCallout / CompareBars — geri kalan (chart olmayan) segmentler arasından, yerel
     LLM (pipeline/motion_graphics_director.py, qwen3) script'te "animasyonlu grafiğe değer"
     tek bir istatistik (ör. "%70 faiz artış ihtimali") ya da aynı cümledeki 2-3 karşılaştırmalı
     değer (ör. "Ağustos 162 bin, Temmuz 21 bin") bulursa, o segment için üretilir.
  3. TitleCard — açılış segmenti (visuals.motion_graphics.title_card_intro: true ise) için
     script.json'daki konu başlığından sinematik bir başlık kartı.

Hepsi Chromium ile render edilir (GPU/diffusion GEREKTİRMEZ), bu yüzden WAN/LTX/FramePack'in
VRAM sınırlarından bağımsızdır ve edit.burn_subtitles'taki ffmpeg drawtext/libass çökme
sorununu hiç görmez.

KAPALI VARSAYILAN (config.yaml -> visuals.motion_graphics.enabled: false). Node.js veya
remotion/ npm bağımlılıkları kurulu değilse, Ollama kapalıysa ya da herhangi bir adım
başarısız olursa segment mevcut statik görseliyle (bugünkü güvenli davranış) KALIR — bu
aşama var olan hiçbir görseli silmez/bozmaz, yalnızca varsa video_broll_manifest.json'a EKLER.

Girdi: script.json (market_symbols, segments, topic), visuals_manifest.json (is_chart
       segmentler), segments_timing.json
Çıktı: output/<job_id>/video_broll/seg_XXX.mp4 (var olan video_broll_manifest.json'a eklenir)
"""
import json
import shutil
import subprocess
import time

from pipeline import market_data, motion_graphics_director
from pipeline.agents import review_loop
from pipeline.agents import reviewer as agent_reviewer
from pipeline.agents import tester as agent_tester
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("s05b_motion_graphics")


def _agents_cfg() -> dict:
    """17 Eyl eklendi -- top-level config.yaml 'agents:' bloğu (Denetleyici/Tester
    açık/kapalı + max_revisions + Drive yükleme tercihi). Yoksa hepsi güvenli varsayılana
    (Reviewer/Tester açık, 2 revizyon, Drive'a yükle) düşer."""
    return load_config().get("agents", {}) or {}


def _render_clip_gated(job_id: str, npx: str, out_dir, idx: int, composition_id: str,
                        props: dict, max_seconds_render: int, render_timeout_ms: int,
                        retry: bool, source_text: str, recent_choices: list[dict],
                        expected_seconds: float | None, label_for_review: str) -> bool:
    """_render_clip'i Editor/Denetleyici/Tester döngüsüyle sarar. Bu üç aday alanının
    ANLAMI 'aday üretme' değil (o iş zaten motion_graphics_director/çağıran fonksiyonda
    yapıldı) -- buradaki Editor rolü tek bir hazır kararı temsil eder; Denetleyici onu
    render'dan ÖNCE kritik eder, Tester render'dan SONRA teknik doğrular. Reddedilirse
    (revizyon üretecek bir "yeniden yaz" yeteneğimiz henüz yok) segment mevcut statik
    görseliyle kalır -- mevcut güvenli davranış hiçbir zaman bozulmaz.

    agents.reviewer.enabled=false VE agents.tester.enabled=false ise düz _render_clip'e
    eşdeğerdir (davranış değişmez).

    17 Eyl (revizyon): canlı testte Denetleyici LLM'in ürettiği StatCallout/CompareBars
    adaylarını GERÇEKTEN reddetti (kaynak metinde olmayan sayı/yüzde uydurma) -- bu doğru
    davranış, ama önceki kod revizyon isteğinde None dönüp segmenti tamamen boş bırakıyordu
    (kapsam kaybı). Şimdi revizyonda LLM'e güvenmek yerine segmentin kendi metninden
    BİREBİR bir alıntıya (KeyQuote) düşülür -- hiçbir sayı icat/yorumlama riski yok, Tester
    zaten teknik olarak doğrulayacak. Ayrıca _render artık candidate'ın KENDİ composition_id/
    props'unu render eder (önceki halinde candidate içeriği render'a hiç ulaşmıyordu -- kritik
    edilen ile render edilen aynı şey değildi)."""
    acfg = _agents_cfg()
    reviewer_on = acfg.get("reviewer", {}).get("enabled", True)
    tester_on = acfg.get("tester", {}).get("enabled", True)
    if not reviewer_on and not tester_on:
        return _render_clip(job_id, npx, out_dir, idx, composition_id, props,
                             max_seconds_render, render_timeout_ms, retry)

    clip_path = out_dir / f"seg_{idx:03d}.mp4"
    fps = props.get("fps", 30)
    seconds = props.get("seconds", expected_seconds or 5.0)

    def _fallback_quote():
        """Reviewer/Tester reddettiğinde kullanılan garanti-güvenli aday: segment
        metninin kendisinden birebir alınan, KELİME SINIRINDA kesilmiş bir alıntı --
        her zaman kaynakta birebir geçtiği için Denetleyici'nin 'uydurma' reddine ASLA
        çarpmaz. _is_fallback=True ile işaretlenir -> _review bu adayı LLM'e tekrar
        sormaz (zaten yapısal olarak güvenli; Denetleyici'nin 'aynı şablon tekrarı'
        veya 'kırpılmış label' gibi ikincil kritikleri kapsam dışıdır, fallback'in
        TEK görevi segmenti asla boş bırakmamaktır). "label" alanı YOK -- gerçek
        KeyQuote adaylarıyla (quote/attribution) aynı şekle sahip, ekstra alan
        Denetleyici'yi (varsa) yanıltmaz."""
        text = (source_text or "").strip()
        if not text:
            return None
        words, quote = text.split(), ""
        for w in words:
            candidate_str = (quote + " " + w).strip()
            if len(candidate_str) > 140:
                break
            quote = candidate_str
        if not quote:
            return None
        return {"composition_id": "KeyQuote", "quote": quote, "attribution": "",
                "fps": fps, "seconds": seconds, "_is_fallback": True}

    def _propose(feedback):
        if feedback is None:
            return {"composition_id": composition_id, "label": label_for_review, **props}
        return _fallback_quote()

    def _review(candidate):
        if candidate.get("_is_fallback"):
            return {"approved": True, "reason": "guaranteed-grounded-fallback"}
        if not reviewer_on:
            return {"approved": True, "reason": "reviewer-disabled"}
        return agent_reviewer.review_candidate(candidate, source_text, recent_choices)

    def _render(candidate):
        cand_composition_id = candidate["composition_id"]
        cand_props = {k: v for k, v in candidate.items()
                       if k not in ("composition_id", "label", "_is_fallback")}
        ok = _render_clip(job_id, npx, out_dir, idx, cand_composition_id, cand_props,
                           max_seconds_render, render_timeout_ms, retry)
        return clip_path if ok else None

    def _validate(candidate, path):
        if not tester_on:
            return {"pass": True, "checks": {"tester-disabled": True}}
        return agent_tester.run_and_report(
            job_id, f"motion_seg{idx:03d}_{candidate['composition_id'].lower()}", path,
            expected_seconds=expected_seconds,
            upload_to_drive=acfg.get("tester", {}).get("upload_to_drive", True),
            # 17 Eyl düzeltildi: bu kartların TÜMÜ kasıtlı koyu temalı (theme.BG=#0d1117,
            # bkz. cardFx.CardBackground) -- ffmpeg blackdetect bu koyu arka planı "bozuk/
            # boş render" ile karıştırıp yanlış pozitif FAIL veriyordu (canlı testte
            # MarketChart %99.7 "siyah" diye reddedildi, oysa grafik doğru render edilmişti).
            # Siyah-kare kontrolü sadece FOTOĞRAF-GERÇEKÇİ içerik (final video, s07_edit) için
            # anlamlı; UI kartlarında kapatılır.
            check_black_frames=False,
        )

    result = review_loop.run_loop(
        _propose, _render, _validate,
        review_fn=_review if reviewer_on else None,
        max_revisions=int(acfg.get("max_revisions", 2)),
    )
    if result["success"]:
        won = result["candidate"]
        won_label = won.get("label") or won.get("title") or won.get("quote") or ""
        recent_choices.append({"composition_id": won["composition_id"], "label": won_label})
    return result["success"]

REMOTION_DIR = ROOT / "remotion"
# Web panelinden gelen override'lar s07_edit.py'nin de kullandığı tek dosyaya yazılır
# (bkz. EDIT_OVERRIDE_KEYS -> "motion_graphics"); burada visuals.motion_graphics.* üzerine uygulanır.
EDIT_SETTINGS_FILE = ROOT / "edit_settings.json"


def _load_config() -> dict:
    cfg = dict(load_config().get("visuals", {}).get("motion_graphics", {}) or {})
    if EDIT_SETTINGS_FILE.exists():
        try:
            overrides = json.loads(EDIT_SETTINGS_FILE.read_text(encoding="utf-8"))
            mg = overrides.get("motion_graphics")
            if isinstance(mg, dict):
                cfg.update(mg)
        except Exception:
            log.warning("edit_settings.json okunamadı, config.yaml motion_graphics kullanılıyor")
    return cfg


def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"{path} okunamadı/bozuk JSON, atlanıyor: {e}")
            return None
    return None


def _render_clip(job_id: str, npx: str, out_dir, idx: int, composition_id: str, props: dict,
                  max_seconds_render: int, render_timeout_ms: int = 60000,
                  retry: bool = True) -> bool:
    """Tek bir segment için verilen Remotion composition'ını render eder. Başarılı olursa
    True döner (clip_path = out_dir/seg_XXX.mp4 diskte hazır demektir); herhangi bir
    hata/timeout'ta False döner ve çağıran taraf statik görsele düşer.

    16 Eyl (akşam) gerçek prodüksiyon testinde görüldü: Remotion'ın Chromium dev-server'ı
    TTS/SDXL'den hemen sonraki kaynak yarışması yüzünden "Visited http://localhost:3000
    but got no response" hatasıyla zaman zaman geç yanıt veriyor -- bu ANLIK/geçici bir
    durum, kod/config hatası değil. Bu yüzden (a) Remotion'a kendi --timeout bayrağıyla
    normalden yüksek bir sayfa zaman aşımı toleransı verilir, (b) ilk deneme başarısız
    olursa kısa bir bekleme sonrası TEK SEFER retry yapılır (Chromium/dev-server'ın
    toparlanması için). İkisi de başarısız olursa hâlâ güvenli statik-görsel düşüşüne gidilir."""
    clip_path = out_dir / f"seg_{idx:03d}.mp4"
    props_file = out_dir / f"seg_{idx:03d}_{composition_id.lower()}_props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    raw_log = job_path(job_id, f"motion_graphics_seg{idx:03d}.log")
    cmd = [
        npx, "remotion", "render", "src/index.ts", composition_id, str(clip_path),
        f"--props={props_file}", f"--timeout={render_timeout_ms}",
    ]

    def _attempt() -> bool:
        try:
            with open(raw_log, "w", encoding="utf-8") as f:
                proc = subprocess.run(
                    cmd, cwd=str(REMOTION_DIR), stdout=f, stderr=subprocess.STDOUT,
                    timeout=max_seconds_render,
                )
        except subprocess.TimeoutExpired:
            log.warning(f"Remotion render zaman aşımına uğradı (segment {idx}, {composition_id})")
            return False
        if proc.returncode != 0 or not clip_path.exists():
            tail = raw_log.read_text(encoding="utf-8", errors="replace")[-1500:]
            log.warning(f"Remotion render başarısız (segment {idx}, {composition_id}):\n{tail}")
            return False
        return True

    if _attempt():
        return True
    if retry:
        log.info(f"Remotion render tekrar deneniyor (segment {idx}, {composition_id}) ...")
        time.sleep(4)
        if _attempt():
            return True
    log.warning(f"Remotion render kalıcı olarak başarısız (segment {idx}, {composition_id}), statik görsel korunuyor")
    return False


def _render_market_charts(job_id, npx, cfg, script_data, manifest, segments_text,
                           duration_by_segment, chart_segments, already, out_dir,
                           max_seconds_render, recent_choices) -> list[dict]:
    """is_chart=True segmentler için CANLI Yahoo Finance verisiyle animasyonlu çizgi grafiği."""
    symbols = script_data.get("market_symbols") or []
    fps = int(cfg.get("fps", 30))
    render_timeout_ms = int(cfg.get("render_timeout_ms", 60000))
    retry = bool(cfg.get("render_retry", True))
    out = []
    for key in symbols:
        meta = market_data.SYMBOLS.get(key)
        if not meta:
            continue
        kws = [key] + meta.get("kw", [])
        matches = [
            i for i in chart_segments
            if i not in already and i < len(segments_text)
            and segments_text[i] and any(k in segments_text[i].lower() for k in kws)
        ]
        if not matches:
            continue
        try:
            series = market_data.fetch_series(key)
            if not series:
                continue
        except Exception as e:
            log.warning(f"Animasyonlu grafik için veri alınamadı ({key}): {e}")
            continue

        base_props = {
            "name": series["name"],
            "currency": series["currency"],
            "closes": series["closes"][-60:],  # son 60 nokta yeterli -> render süresi/dosya boyutu için sınırlı
            "last": series["last"],
            "changePct": series["change_pct"],
            "range": series["range"],
            "source": "Yahoo Finance",
            "fps": fps,
        }
        for idx in matches[:2]:  # sembol başına en çok 2 segment (s04'teki aynı sınır)
            seconds = duration_by_segment.get(idx, 5.0)
            log.info(f"Animasyonlu piyasa grafiği render ediliyor (segment {idx}, {key}, {seconds:.1f}s) ...")
            if not _render_clip_gated(job_id, npx, out_dir, idx, "MarketChart",
                                       dict(base_props, seconds=seconds), max_seconds_render,
                                       render_timeout_ms, retry,
                                       source_text=segments_text[idx] if idx < len(segments_text) else "",
                                       recent_choices=recent_choices, expected_seconds=seconds,
                                       label_for_review=series["name"]):
                continue
            out.append({"segment_index": idx, "video": str(out_dir / f"seg_{idx:03d}.mp4"),
                        "prompt": key, "engine": "remotion"})
            already.add(idx)
    return out


def _render_stat_highlights(job_id, npx, cfg, segments_text, duration_by_segment, already,
                             out_dir, max_seconds_render, recent_choices) -> list[dict]:
    """Chart olmayan segmentler arasından yerel LLM'in seçtiği tek-istatistik (StatCallout)
    veya karşılaştırma (CompareBars) adaylarını render eder."""
    max_highlights = int(cfg.get("max_stat_callouts", 2))
    if max_highlights <= 0:
        return []
    fps = int(cfg.get("fps", 30))
    render_timeout_ms = int(cfg.get("render_timeout_ms", 60000))
    retry = bool(cfg.get("render_retry", True))
    highlights = motion_graphics_director.pick_highlights(segments_text, already, max_highlights)

    out = []
    for h in highlights:
        idx = h["segment_index"]
        seconds = duration_by_segment.get(idx, 5.0)
        if h["type"] == "stat":
            props = {
                "label": h["label"], "value": h["value"], "prefix": h["prefix"],
                "suffix": h["suffix"], "trend": h["trend"], "fps": fps, "seconds": seconds,
            }
            composition_id = "StatCallout"
        elif h["type"] == "compare":
            props = {
                "title": h["title"], "unit": h["unit"], "items": h["items"],
                "fps": fps, "seconds": seconds,
            }
            composition_id = "CompareBars"
        elif h["type"] == "report":
            props = {
                "headline": h["headline"], "sourceLabel": h["sourceLabel"],
                "fps": fps, "seconds": seconds,
            }
            composition_id = "NewspaperHighlight"
        else:
            props = {
                "quote": h["quote"], "attribution": h["attribution"],
                "fps": fps, "seconds": seconds,
            }
            composition_id = "KeyQuote"
        log.info(f"Animasyonlu {composition_id} render ediliyor (segment {idx}, {seconds:.1f}s) ...")
        label_for_review = props.get("label") or props.get("title") or props.get("quote") or composition_id
        if not _render_clip_gated(job_id, npx, out_dir, idx, composition_id, props, max_seconds_render,
                                   render_timeout_ms, retry,
                                   source_text=segments_text[idx] if idx < len(segments_text) else "",
                                   recent_choices=recent_choices, expected_seconds=seconds,
                                   label_for_review=label_for_review):
            continue
        out.append({"segment_index": idx, "video": str(out_dir / f"seg_{idx:03d}.mp4"),
                    "prompt": composition_id, "engine": "remotion"})
        already.add(idx)
    return out


def _render_title_card(job_id, npx, cfg, script_data, duration_by_segment, already, out_dir,
                        max_seconds_render, recent_choices) -> list[dict]:
    """Açılış (segment 0) için sinematik başlık kartı — sadece title_card_intro: true ise
    ve segment 0 başka bir grafikle (chart/highlight) zaten kaplanmadıysa."""
    if not cfg.get("title_card_intro", False) or 0 in already:
        return []
    title = (script_data.get("topic") or "").strip()
    if not title:
        return []
    fps = int(cfg.get("fps", 30))
    seconds = duration_by_segment.get(0, 4.0)
    render_timeout_ms = int(cfg.get("render_timeout_ms", 60000))
    retry = bool(cfg.get("render_retry", True))
    # subtitle'ı DAİMA açıkça geç: Remotion --props defaultProps ile MERGE olur (replace değil),
    # eksik bırakılırsa TitleCard.tsx'in defaultTitleCardProps.subtitle placeholder'ı sızar.
    props = {"title": title, "subtitle": "", "fps": fps, "seconds": seconds}
    log.info(f"Animasyonlu TitleCard render ediliyor (segment 0, {seconds:.1f}s) ...")
    if not _render_clip_gated(job_id, npx, out_dir, 0, "TitleCard", props, max_seconds_render,
                               render_timeout_ms, retry, source_text=title,
                               recent_choices=recent_choices, expected_seconds=seconds,
                               label_for_review=title):
        return []
    already.add(0)
    return [{"segment_index": 0, "video": str(out_dir / "seg_000.mp4"), "prompt": "TitleCard", "engine": "remotion"}]


_ACCENT_VARIANTS = [
    {"variantColor": "#58a6ff", "label": "CANLI VERİ"},   # theme.NEUTRAL
    {"variantColor": "#3fb950", "label": "PİYASA"},        # theme.UP
    {"variantColor": "#f85149", "label": "ANALİZ"},        # theme.DOWN
]


def _render_accent_overlays(job_id: str, npx: str, cfg: dict) -> list:
    """17 Eyl eklendi -- 3 personayla (Maksimalist/Sinematik/Hız-Öncelikli) paralel
    prototip denemesinin ortak sonucu: TÜM segmentlere (sayı/alıntı içermeyen, düz
    Ken-Burns statik görsel olanlar dahil) gelişmiş bir animasyon katmanı eklemek için
    her segmenti ayrı ayrı Chromium'da render etmek yerine SABİT SAYIDA (3) varyant
    BİR KEZ render edilir (kusursuz döngülenebilir, bkz. remotion/src/AccentOverlay.tsx);
    s07_edit.py bunları ffmpeg -stream_loop ile her segmentin kendi süresine uzatıp
    üst üste bindirir. Render maliyeti segment sayısından bağımsız, SABİT kalır.

    Zaten diskte varsa (idempotent) yeniden render etmez. Herhangi bir varyant başarısız
    olursa o varyant listeden düşer -- s07_edit.py eksik varyantla da (kalanları
    round-robin döndürerek) çalışabilir; hepsi başarısız olursa [] döner ve segment
    eskisi gibi düz Ken-Burns kalır (hiçbir şey bozulmaz)."""
    acc_cfg = cfg.get("accent_overlay", {}) or {}
    if not acc_cfg.get("enabled", True):
        return []
    out_dir = job_path(job_id, "video_broll/accent_overlays")
    out_dir.mkdir(parents=True, exist_ok=True)
    seconds = float(acc_cfg.get("seconds", 8))
    fps = int(cfg.get("fps", 30))
    render_timeout_ms = int(cfg.get("render_timeout_ms", 60000))
    max_seconds_render = int(cfg.get("max_render_minutes", 5)) * 60

    paths = []
    for i, variant in enumerate(_ACCENT_VARIANTS):
        out_path = out_dir / f"variant_{i}.webm"
        if out_path.exists() and out_path.stat().st_size > 1024:
            paths.append(out_path)
            continue
        props_file = out_dir / f"variant_{i}_props.json"
        props_file.write_text(json.dumps(dict(variant, seconds=seconds, fps=fps), ensure_ascii=False),
                               encoding="utf-8")
        cmd = [
            npx, "remotion", "render", "src/index.ts", "AccentOverlay", str(out_path),
            f"--props={props_file}", "--image-format=png", "--pixel-format=yuva420p",
            "--codec=vp8", f"--timeout={render_timeout_ms}",
        ]
        raw_log = job_path(job_id, f"accent_overlay_variant{i}.log")
        try:
            with open(raw_log, "w", encoding="utf-8") as f:
                proc = subprocess.run(cmd, cwd=str(REMOTION_DIR), stdout=f, stderr=subprocess.STDOUT,
                                       timeout=max_seconds_render)
            if proc.returncode == 0 and out_path.exists():
                paths.append(out_path)
            else:
                log.warning(f"AccentOverlay varyant {i} render başarısız (kod {proc.returncode})")
        except subprocess.TimeoutExpired:
            log.warning(f"AccentOverlay varyant {i} render zaman aşımına uğradı")
    if paths:
        log.info(f"{len(paths)}/{len(_ACCENT_VARIANTS)} accent-overlay varyantı hazır -> {out_dir}")
    return paths


def run(job_id: str) -> dict:
    cfg = _load_config()
    if not cfg.get("enabled", False):
        log.info("motion_graphics.enabled=false, aşama atlanıyor (statik görseller korunur)")
        return {"skipped": True}

    npx = shutil.which("npx")
    if not npx:
        log.warning("npx (Node.js) bulunamadı, animasyonlu grafik atlanıyor (scripts/setup_remotion.ps1 çalıştır)")
        return {"skipped": True}
    if not (REMOTION_DIR / "node_modules").exists():
        log.warning(f"{REMOTION_DIR}\\node_modules yok, animasyonlu grafik atlanıyor (scripts/setup_remotion.ps1 çalıştır)")
        return {"skipped": True}

    script_data = _load_json(job_path(job_id, "script.json")) or {}
    manifest = _load_json(job_path(job_id, "visuals_manifest.json")) or []
    timing = _load_json(job_path(job_id, "segments_timing.json")) or []
    segments_text = script_data.get("segments") or []
    if not timing:
        return {"skipped": True}

    duration_by_segment = {t["segment_index"]: max((t["end_ms"] - t["start_ms"]) / 1000.0, 1.0) for t in timing}
    chart_segments = {m["segment_index"] for m in manifest if m.get("is_chart")}

    out_dir = job_path(job_id, "video_broll")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = job_path(job_id, "video_broll_manifest.json")
    video_manifest = _load_json(manifest_file) or []
    already = {m["segment_index"] for m in video_manifest}

    max_seconds_render = int(cfg.get("max_render_minutes", 5)) * 60
    added = []
    # Denetleyici'nin "aynı şablonu/metni tekrar etme" kontrolü için bu run() çağrısı
    # boyunca onaylanan tüm grafikler burada birikir (bkz. _render_clip_gated).
    recent_choices: list[dict] = []

    if chart_segments:
        added += _render_market_charts(job_id, npx, cfg, script_data, manifest, segments_text,
                                        duration_by_segment, chart_segments, already, out_dir,
                                        max_seconds_render, recent_choices)
    if segments_text:
        added += _render_stat_highlights(job_id, npx, cfg, segments_text, duration_by_segment,
                                          already, out_dir, max_seconds_render, recent_choices)
        added += _render_title_card(job_id, npx, cfg, script_data, duration_by_segment, already,
                                     out_dir, max_seconds_render, recent_choices)

    # Kalan (chart/highlight/title kaplamayan) segmentler için TÜM videoya gelişmiş
    # animasyon kapsamı -- bkz. _render_accent_overlays. s07_edit.py bu sabit yoldaki
    # varyantları (video_broll/accent_overlays/variant_N.webm) otomatik bulup düz
    # Ken-Burns segmentlerin üzerine bindirir; burada manifest'e eklenmesi gerekmez.
    _render_accent_overlays(job_id, npx, cfg)

    if added:
        video_manifest.extend(added)
        video_manifest.sort(key=lambda m: m["segment_index"])
        manifest_file.write_text(json.dumps(video_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"{len(added)} segment animasyonlu grafiğe yükseltildi -> {manifest_file}")
    return {"count": len(added)}


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
