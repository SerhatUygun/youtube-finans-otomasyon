"""Aşama 07: Montaj (ffmpeg).

Girdi:
  - output/<job_id>/audio.wav (zorunlu)
  - output/<job_id>/subtitles.srt (varsa altyazı gömülür)
  - output/<job_id>/segments_timing.json (varsa segment başına arka plan geçişi yapılır)
  - output/<job_id>/visuals_manifest.json (varsa segment başına üretilmiş görsel kullanılır)
  - output/<job_id>/avatar.mp4 (varsa köşede konuşan karakter overlay edilir)
  - yoksa: assets/images/* round-robin, o da yoksa düz renk arka plan

GPU'ya ihtiyaç duymaz; CPU'da (gerekirse NVENC ile) çalışır.
"""
import json
import os
import re
import shutil
import subprocess

from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("s07_edit")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
REMOTION_DIR = ROOT / "remotion"
_SRT_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")

# Altyazı stili varsayılanları. Web arayüzü bunları subtitle_style.json'a yazarak
# override eder (bkz. load_subtitle_style). config.yaml edit.subtitle_style de override eder.
SUBTITLE_STYLE_DEFAULTS = {
    "font_name": "Segoe UI",
    "font_size": 24,          # libass PlayResY=384 ölçeğinde; video yüksekliğine oranla ölçeklenir
    "bold": True,
    "primary_colour": "#FFFFFF",   # yazı rengi (hex)
    "outline_colour": "#000000",   # kenarlık/kutu rengi (hex)
    "outline_opacity": 0.50,       # kenarlık/kutu opaklığı (0=şeffaf, 1=tam opak)
    "border_style": 3,             # 1=kenarlık+gölge, 3=opak arka kutu
    "outline": 2,                  # kenarlık/kutu kalınlığı
    "shadow": 0,
    "alignment": 2,                # libass numpad: 8=üst-orta, 5=orta, 2=alt-orta
    "margin_v": 70,                # dikey kenar boşluğu (alignment'a göre alttan/üstten)
}

SUBTITLE_STYLE_FILE = ROOT / "subtitle_style.json"
EDIT_SETTINGS_FILE = ROOT / "edit_settings.json"

# Web panelinden ayarlanabilen montaj alanları (config.yaml edit.* varsayılanlarını override eder).
# animated_captions/transitions/burn_subtitles nesne halinde (tüm alt-anahtarlarıyla) override
# edilir -- load_edit_settings() cfg.update() ile bütün alt-sözlüğü değiştirir. motion_graphics
# edit.* altında değil (visuals.motion_graphics), s05b_motion_graphics.py aynı edit_settings.json
# dosyasını kendi override anahtarı için ayrıca okur (bkz. o dosyadaki _load_cfg).
EDIT_OVERRIDE_KEYS = {
    "avatar_intro_seconds", "avatar_intro_height_ratio", "avatar_width_ratio",
    "avatar_position", "avatar_chroma_similarity", "avatar_chroma_blend",
    "avatar_center_full",
    "burn_subtitles", "animated_captions", "transitions", "motion_graphics", "chapter_bar",
    "parallax",
}


def load_edit_settings() -> dict:
    """config.yaml edit.* + edit_settings.json (web override) birleşimi."""
    cfg = dict(load_config().get("edit", {}) or {})
    if EDIT_SETTINGS_FILE.exists():
        try:
            overrides = json.loads(EDIT_SETTINGS_FILE.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in overrides.items() if k in EDIT_OVERRIDE_KEYS and v is not None})
        except Exception:
            log.warning("edit_settings.json okunamadı, config kullanılıyor")
    return cfg


_NVENC_AVAILABLE = None


def _has_nvenc() -> bool:
    """ffmpeg'in NVIDIA donanım encoder'ı (h264_nvenc) bu makinede var mı? Süreç başına
    bir kez kontrol edilir (subprocess.run cache'lenir)."""
    global _NVENC_AVAILABLE
    if _NVENC_AVAILABLE is None:
        try:
            res = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=15,
            )
            _NVENC_AVAILABLE = "h264_nvenc" in (res.stdout or "")
        except Exception:
            _NVENC_AVAILABLE = False
    return _NVENC_AVAILABLE


def _video_encoder_args(cfg: dict, use_nvenc: bool) -> list[str]:
    """Final render kod çözücüsü. 16 Eyl: bu makinede final encode (libx264 -preset slow,
    tam CPU) uzun videolarda sistem RAM'ini (16GB, GPU'dan bağımsız) zorluyordu. NVENC
    (RTX 5060 Ti'nin ayrı donanım encode bloğu -- CUDA/VRAM compute'tan bağımsız, Ollama/
    SDXL ile VRAM için yarışmaz) encode işini CPU/RAM'den GPU'ya taşır. edit.encoder: "cpu"
    ile elle zorlanabilir (varsayılan "auto" -> NVENC varsa kullanılır)."""
    if use_nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "18",
                "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "18"]


def _corner_overlay_xy(position: str, margin: int) -> str:
    """avatar köşe konumu -> ffmpeg overlay x:y ifadesi."""
    pos = (position or "bottom-right").lower()
    vy = "top" if "top" in pos else "bottom"
    if "left" in pos:
        hx = "left"
    elif "center" in pos:
        hx = "center"
    else:
        hx = "right"
    x = {"left": f"{margin}", "right": f"W-w-{margin}", "center": "(W-w)/2"}[hx]
    y = {"top": f"{margin}", "bottom": f"H-h-{margin}"}[vy]
    return f"{x}:{y}"


def _hex_to_ass_colour(hex_color: str, opacity: float = 1.0) -> str:
    """#RRGGBB + opaklık -> ASS &HAABBGGRR (ASS'te alpha ters: 00=opak, FF=şeffaf)."""
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(round((1.0 - max(0.0, min(1.0, opacity))) * 255))
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def load_subtitle_style() -> dict:
    """Varsayılan -> config.yaml edit.subtitle_style -> subtitle_style.json sırasıyla birleştirir."""
    style = dict(SUBTITLE_STYLE_DEFAULTS)
    cfg_style = (load_config().get("edit", {}) or {}).get("subtitle_style") or {}
    style.update({k: v for k, v in cfg_style.items() if v is not None})
    if SUBTITLE_STYLE_FILE.exists():
        try:
            style.update(json.loads(SUBTITLE_STYLE_FILE.read_text(encoding="utf-8")))
        except Exception:
            log.warning("subtitle_style.json okunamadı, varsayılan/config kullanılıyor")
    return style


def build_subtitle_force_style(style: dict) -> str:
    """Birleştirilmiş stil dict'inden libass force_style dizesi üretir."""
    prim = _hex_to_ass_colour(style.get("primary_colour", "#FFFFFF"), 1.0)
    outl = _hex_to_ass_colour(style.get("outline_colour", "#000000"), float(style.get("outline_opacity", 0.5)))
    parts = [
        f"FontName={style.get('font_name', 'Segoe UI')}",
        f"FontSize={int(style.get('font_size', 24))}",
        f"Bold={1 if style.get('bold', True) else 0}",
        f"PrimaryColour={prim}",
        f"OutlineColour={outl}",
        f"BackColour={outl}",
        f"BorderStyle={int(style.get('border_style', 3))}",
        f"Outline={int(style.get('outline', 2))}",
        f"Shadow={int(style.get('shadow', 0))}",
        f"Alignment={int(style.get('alignment', 2))}",
        f"MarginV={int(style.get('margin_v', 70))}",
    ]
    return ",".join(parts)


def _ffprobe_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return float(out.stdout.strip())


def _escape_filter_path(path) -> str:
    # ffmpeg filtergraph path escaping: forward slashes, escape ':' (Windows drive letter) and '\''
    s = str(path).replace("\\", "/")
    s = s.replace(":", "\\:")
    return s


def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"{path} okunamadı/bozuk JSON, atlanıyor: {e}")
            return None
    return None


def _kenburns_filter(input_idx: int, seg_no: int, dur_s: float, width: int, height: int, fps: int, zoom_max: float) -> str:
    """Statik bir görsele yavaş zoom/pan (Ken Burns) uygular. Segment sırasına göre
    6 hareket deseni döner (içeri/dışarı zoom, sağa/sola pan, iki köşegen pan) —
    ardışık segmentlerin aynı hissi vermemesi için (17 Eyl: 4'ten 6'ya çıkarıldı,
    kullanıcı geri bildirimi -- "monoton", "animasyon yok"). zoompan tam sayı piksel
    örneklemesinde titrediği için görsel önce 2x ara çözünürlüğe büyütülür."""
    frames = max(int(round(dur_s * fps)), 2)
    iw, ih = width * 7 // 5, height * 7 // 5  # ara çözünürlük (1.4x): titreme azalır, CPU makul kalır
    iw, ih = iw - iw % 2, ih - ih % 2
    z_span = zoom_max - 1.0

    pattern = seg_no % 6
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    pan_zoom = f"{1.0 + z_span * 0.7:.4f}"
    right_x = f"(iw-iw/zoom)*on/{frames}"
    left_x = f"(iw-iw/zoom)*(1-on/{frames})"
    bottom_y = f"(ih-ih/zoom)*on/{frames}"
    top_y = f"(ih-ih/zoom)*(1-on/{frames})"
    if pattern == 0:      # içeri zoom
        z = f"1+{z_span:.4f}*on/{frames}"
        x, y = center_x, center_y
    elif pattern == 1:    # dışarı zoom
        z = f"{zoom_max:.4f}-{z_span:.4f}*on/{frames}"
        x, y = center_x, center_y
    elif pattern == 2:    # sağa pan (hafif sabit zoom)
        z, x, y = pan_zoom, right_x, center_y
    elif pattern == 3:    # sola pan
        z, x, y = pan_zoom, left_x, center_y
    elif pattern == 4:    # köşegen: sol-alttan sağ-üste pan
        z, x, y = pan_zoom, right_x, top_y
    else:                 # köşegen: sağ-üstten sol-alta pan
        z, x, y = pan_zoom, left_x, bottom_y

    return (
        f"[{input_idx}:v]scale={iw}:{ih}:force_original_aspect_ratio=increase,"
        f"crop={iw}:{ih},setsar=1,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps},"
        f"trim=duration={dur_s:.3f},setpts=PTS-STARTPTS[v{input_idx}]"
    )


def _build_transition_chain(seg_backgrounds, width, height, fps, motion, zoom_max,
                             transition_types, transition_dur, accent_variants=None):
    """seg_backgrounds'ı sert kesme yerine ZİNCİRLENMİŞ xfade geçişleriyle birleştirir.

    Standart çoklu-xfade tekniği: iki klip crossfade edildiğinde output süresi
    (d0+d1-transition_dur) olur -- yani her geçiş toplam süreden transition_dur kadar
    çalar. Bunu TELAFİ ETMEK için her segmentin render süresi transition_dur/2 kadar
    UZATILIR (ortadakiler her iki taraftan, ilk/son segment tek taraftan) -> zincirin
    sonunda TOPLAM süre segmentlerin NOMİNAL toplamıyla (audio.wav süresiyle) birebir
    eşleşir, ses/altyazı senkronu BOZULMAZ. Uzatılan pay Ken Burns'ün biraz daha uzun
    sürmesi ya da video b-roll'un biraz daha fazla loop'lanması olarak karşılanır.

    Döner: (inputs, filter_parts, son_etiket)."""
    n = len(seg_backgrounds)
    # Çok kısa segmentlerde geçiş süresi segment süresini aşmasın (negatif offset ffmpeg'i
    # patlatır) -- en kısa segmentin ~%40'ıyla sınırla.
    shortest = min(dur_s for _, dur_s, _ in seg_backgrounds)
    t = max(min(transition_dur, shortest * 0.4), 0.0)

    inputs = []
    filter_parts = []
    render_durs = []
    for i, (src, dur_s, kind) in enumerate(seg_backgrounds):
        pad_before = t / 2 if i > 0 else 0.0
        pad_after = t / 2 if i < n - 1 else 0.0
        render_dur = dur_s + pad_before + pad_after
        render_durs.append(render_dur)

        if kind == "video":
            inputs += ["-stream_loop", "-1", "-t", f"{render_dur:.3f}", "-i", str(src)]
            filter_parts.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={fps}[v{i}]"
            )
        elif motion:
            inputs += ["-i", str(src)]
            filter_parts.append(_kenburns_filter(i, i, render_dur, width, height, fps, zoom_max))
        else:
            inputs += ["-loop", "1", "-t", f"{render_dur:.3f}", "-i", str(src)]
            filter_parts.append(
                f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},setsar=1,fps={fps}[v{i}]"
            )

    # 17 Eyl eklendi: "sadece sayı/alıntı içeren segmentler animasyonlu, gerisi düz Ken-Burns"
    # şikayetine karşı -- motion-graphics'in (video, kind=="video") KAPLAMADIĞI her segmente
    # (düz statik görsel + Ken-Burns) s05b_motion_graphics.py'nin BİR KEZ render ettiği
    # döngülenebilir accent-overlay varyantlarından biri (round-robin) bindirilir. Segment
    # sayısından bağımsız SABİT render maliyeti (3 varyant), her segmente ayrı Chromium
    # render'ı YOK. accent_variants boşsa/verilmezse davranış AYNI kalır (eski Ken-Burns-only).
    label_overrides = {}
    if accent_variants:
        accent_base_index = n
        accent_counter = 0
        for i, (_, _, kind) in enumerate(seg_backgrounds):
            if kind == "video":
                continue
            accent_path = accent_variants[i % len(accent_variants)]
            ffmpeg_idx = accent_base_index + accent_counter
            accent_counter += 1
            inputs += ["-stream_loop", "-1", "-t", f"{render_durs[i]:.3f}", "-c:v", "libvpx", "-i", str(accent_path)]
            filter_parts.append(f"[{ffmpeg_idx}:v]format=yuva420p[acc{i}]")
            filter_parts.append(f"[v{i}][acc{i}]overlay=0:0:shortest=1[va{i}]")
            label_overrides[i] = f"va{i}"

    def lbl(i: int) -> str:
        return label_overrides.get(i, f"v{i}")

    if n == 1 or t <= 0.0:
        concat_inputs = "".join(f"[{lbl(i)}]" for i in range(n))
        filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vcat]")
        return inputs, filter_parts, "vcat"

    cumulative = render_durs[0]
    prev_label = lbl(0)
    for i in range(1, n):
        ttype = transition_types[(i - 1) % len(transition_types)]
        offset = max(cumulative - t, 0.0)
        out_label = "vcat" if i == n - 1 else f"vx{i}"
        filter_parts.append(
            f"[{prev_label}][{lbl(i)}]xfade=transition={ttype}:duration={t:.3f}:"
            f"offset={offset:.3f}[{out_label}]"
        )
        cumulative = cumulative + render_durs[i] - t
        prev_label = out_label

    return inputs, filter_parts, "vcat"


def _parse_srt_cues(path) -> list[tuple[float, float, str]]:
    """SRT dosyasını [(start_s, end_s, text), ...] listesine çözer (saniye cinsinden)."""
    def parse_ts(s: str) -> float:
        m = _SRT_TS.match(s.strip())
        h, mi, se, ms = map(int, m.groups())
        return h * 3600 + mi * 60 + se + ms / 1000.0

    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    cues = []
    for b in blocks:
        lines = [ln for ln in b.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        tl = next((ln for ln in lines if "-->" in ln), None)
        if not tl:
            continue
        a, bb = tl.split("-->")
        text = " ".join(lines[lines.index(tl) + 1:]).strip()
        cues.append((parse_ts(a), parse_ts(bb), text))
    return cues


def _video_covered_time_ranges(job_id: str, duration: float) -> list:
    """17 Eyl eklendi -- motion-graphics'in (video_broll_manifest.json) KAPLADIĞI
    segmentlerin zaman aralıkları. Kullanıcı ekran görüntüsüyle bildirdi: bir kart
    (StatCallout/KeyQuote) kendi metnini gösterirken, animasyonlu altyazı (karaoke)
    ÜSTÜNE binip okunaksız çakışma oluşturuyordu -- kart zaten metni gösteriyor,
    altyazıya ihtiyaç yok. Bu aralıklardaki altyazı cue'ları _render_animated_captions
    tarafından atlanır."""
    timing = _load_json(job_path(job_id, "segments_timing.json")) or []
    video_manifest = _load_json(job_path(job_id, "video_broll_manifest.json")) or []
    covered = {m["segment_index"] for m in video_manifest}
    if not covered or not timing:
        return []
    timing = sorted(timing, key=lambda t: t["start_ms"])
    total_ms = round(duration * 1000)
    ranges = []
    for i, seg in enumerate(timing):
        if seg["segment_index"] not in covered:
            continue
        start_ms = seg["start_ms"]
        end_ms = timing[i + 1]["start_ms"] if i + 1 < len(timing) else total_ms
        ranges.append((start_ms / 1000.0, end_ms / 1000.0))
    return ranges


def _render_animated_captions(job_id: str, srt_file, duration: float, cfg: dict, exclude_ranges=None):
    """SRT altyazısını Remotion'ın Captions.tsx şablonuyla ŞEFFAF (alpha kanallı) bir WebM'e
    render eder -- ffmpeg'in libass tabanlı `subtitles=` filtresini (bu makinede fontconfig
    ACCESS_VIOLATION ile çöküyor, bkz. burn_subtitles notu) HİÇ KULLANMAZ; Chromium kendi font
    render'ını yapar. Herhangi bir adım başarısız olursa None döner -- çağıran taraf mevcut
    (kapalı) subtitles= yoluna dokunmadan altyazısız devam eder, video hiçbir zaman bozulmaz."""
    npx = shutil.which("npx")
    if not npx:
        log.warning("npx (Node.js) bulunamadı, animasyonlu altyazı atlanıyor (scripts/setup_remotion.ps1 çalıştır)")
        return None
    if not (REMOTION_DIR / "node_modules").exists():
        log.warning(f"{REMOTION_DIR}\\node_modules yok, animasyonlu altyazı atlanıyor")
        return None

    # Kelime-seviyeli zamanlama varsa (s06_subtitles.py'nin ürettiği captions_words.json)
    # karaoke-stili aktif-kelime vurgusu için kullanılır; yoksa eski blok-bazlı pop-in'e düşülür.
    karaoke_file = job_path(job_id, "captions_words.json")
    karaoke_groups = None
    if karaoke_file.exists():
        try:
            karaoke_groups = json.loads(karaoke_file.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"captions_words.json okunamadı, kelime vurgusu atlanıyor: {e}")
            karaoke_groups = None

    if karaoke_groups:
        cues_payload = karaoke_groups
    else:
        try:
            cues = _parse_srt_cues(srt_file)
        except Exception as e:
            log.warning(f"SRT okunamadı, animasyonlu altyazı atlanıyor: {e}")
            return None
        if not cues:
            return None
        cues_payload = [{"start": a, "end": b, "text": t} for a, b, t in cues]

    if exclude_ranges:
        def _overlaps(cue):
            cs, ce = cue["start"], cue["end"]
            return any(cs < r_end and ce > r_start for r_start, r_end in exclude_ranges)
        before = len(cues_payload)
        cues_payload = [c for c in cues_payload if not _overlaps(c)]
        skipped = before - len(cues_payload)
        if skipped:
            log.info(f"{skipped} altyazı cue'su motion-graphics kartlarıyla çakıştığı için atlandı")
    if not cues_payload:
        return None

    fps = int(cfg.get("fps", 30))
    props = {
        "cues": cues_payload,
        "totalSeconds": duration,
        "fps": fps,
    }
    out_dir = job_path(job_id, "captions_render")
    out_dir.mkdir(parents=True, exist_ok=True)
    props_file = out_dir / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    out_webm = out_dir / "captions.webm"
    raw_log = job_path(job_id, "animated_captions.log")
    cmd = [
        npx, "remotion", "render", "src/index.ts", "Captions", str(out_webm),
        f"--props={props_file}",
        "--image-format=png", "--pixel-format=yuva420p", "--codec=vp8",
    ]
    max_seconds = int(cfg.get("max_render_minutes", 10)) * 60
    log.info(f"Animasyonlu altyazı render ediliyor ({len(cues_payload)} blok, {duration:.1f}s, "
             f"{'karaoke' if karaoke_groups else 'düz'}) ...")
    try:
        with open(raw_log, "w", encoding="utf-8") as f:
            proc = subprocess.run(
                cmd, cwd=str(REMOTION_DIR), stdout=f, stderr=subprocess.STDOUT, timeout=max_seconds,
            )
    except subprocess.TimeoutExpired:
        log.warning("Animasyonlu altyazı render zaman aşımına uğradı, atlanıyor")
        return None
    if proc.returncode != 0 or not out_webm.exists():
        tail = raw_log.read_text(encoding="utf-8", errors="replace")[-1500:]
        log.warning(f"Animasyonlu altyazı render başarısız, atlanıyor:\n{tail}")
        return None
    return out_webm


_CHAPTER_LABELS = ["01. Olay", "02. Neden-Sonuç", "03. Etki", "04. Büyük Resim"]


def _derive_chapters(job_id: str, duration: float) -> list[dict]:
    """18 Eyl eklendi (SIFIR_MALIYET rehberi Modül 6) -- script.json'daki bölüm/chapter
    yapısı yoksa (yok -- şu an segment listesi düz), segmentleri süreye göre 4 KABACA eşit
    gruba böler ("keep it simple over clever"). Video 4 gruba bölünemeyecek kadar kısaysa
    (ör. 2-3 segmentlik test job'u) daha az bölüm döner."""
    timing = _load_json(job_path(job_id, "segments_timing.json"))
    if not timing:
        return []
    timing = sorted(timing, key=lambda t: t["start_ms"])
    n = len(timing)
    n_chapters = min(4, n)
    if n_chapters < 2:
        return []
    chapters = []
    for c in range(n_chapters):
        seg_idx_in_timing = round(c * n / n_chapters)
        start_s = timing[seg_idx_in_timing]["start_ms"] / 1000.0
        chapters.append({"label": _CHAPTER_LABELS[c] if c < len(_CHAPTER_LABELS) else f"{c + 1:02d}. Bölüm",
                          "startSeconds": round(start_s, 2)})
    return chapters


def _render_chapter_progress(job_id: str, duration: float, cfg: dict):
    """Videonun TAMAMI boyunca üstte akan, şeffaf (alpha) WebM bölüm çubuğu -- desen
    _render_animated_captions ile BİREBİR AYNI (Chromium render, libvpx alpha, herhangi
    bir adım başarısız olursa None -- video hiçbir zaman bozulmaz, sadece çubuksuz kalır)."""
    npx = shutil.which("npx")
    if not npx or not (REMOTION_DIR / "node_modules").exists():
        return None
    chapters = _derive_chapters(job_id, duration)
    if not chapters:
        return None
    fps = int(cfg.get("fps", 30))
    props = {"chapters": chapters, "totalSeconds": duration, "fps": fps}
    out_dir = job_path(job_id, "chapter_bar_render")
    out_dir.mkdir(parents=True, exist_ok=True)
    props_file = out_dir / "props.json"
    props_file.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    out_webm = out_dir / "chapter_bar.webm"
    raw_log = job_path(job_id, "chapter_bar.log")
    cmd = [
        npx, "remotion", "render", "src/index.ts", "ChapterProgress", str(out_webm),
        f"--props={props_file}",
        "--image-format=png", "--pixel-format=yuva420p", "--codec=vp8",
    ]
    max_seconds = int(cfg.get("max_render_minutes", 10)) * 60
    log.info(f"Bölüm çubuğu render ediliyor ({len(chapters)} bölüm, {duration:.1f}s) ...")
    try:
        with open(raw_log, "w", encoding="utf-8") as f:
            proc = subprocess.run(
                cmd, cwd=str(REMOTION_DIR), stdout=f, stderr=subprocess.STDOUT, timeout=max_seconds,
            )
    except subprocess.TimeoutExpired:
        log.warning("Bölüm çubuğu render zaman aşımına uğradı, atlanıyor")
        return None
    if proc.returncode != 0 or not out_webm.exists():
        tail = raw_log.read_text(encoding="utf-8", errors="replace")[-1500:]
        log.warning(f"Bölüm çubuğu render başarısız, atlanıyor:\n{tail}")
        return None
    return out_webm


def _segment_backgrounds(job_id: str, duration: float, cfg: dict | None = None):
    """[(path, duration_seconds, "image"|"video"), ...] listesi döner. Segment
    zamanlaması yoksa None döner (çağıran yerde eski davranışa düşülür).
    video_broll_manifest.json'da olan segmentler için video klip, kalanı için
    visuals_manifest.json'daki statik görsel kullanılır (Faz 3, opsiyonel).

    18 Eyl eklendi (SIFIR_MALIYET rehberi Modül 5, edit.parallax.enabled): düz statik
    görsel kalan segmentler için -- video-broll KAPLAMAYAN -- 2.5D parallax klip üretmeyi
    dener (bkz. pipeline/utils/cinematic_motion.py). Başarılı olursa segment "video" türüne
    yükseltilir (Ken Burns yerine bu klip oynatılır); herhangi bir hata/model sorununda
    sessizce mevcut "image" (Ken Burns) davranışına düşer -- video ASLA bozulmaz."""
    timing = _load_json(job_path(job_id, "segments_timing.json"))
    if not timing:
        return None

    manifest = _load_json(job_path(job_id, "visuals_manifest.json")) or []
    image_by_segment = {m["segment_index"]: m["image"] for m in manifest}
    if not image_by_segment:
        return None

    video_manifest = _load_json(job_path(job_id, "video_broll_manifest.json")) or []
    video_by_segment = {m["segment_index"]: m["video"] for m in video_manifest}

    timing = sorted(timing, key=lambda t: t["start_ms"])
    total_ms = round(duration * 1000)

    parallax_cfg = (cfg or {}).get("parallax", {}) or {}
    parallax_on = parallax_cfg.get("enabled", False)
    width, height = (cfg or {}).get("resolution", [1920, 1080])
    fps = (cfg or {}).get("fps", 30)

    plan = []
    for i, seg in enumerate(timing):
        start_ms = seg["start_ms"]
        end_ms = timing[i + 1]["start_ms"] if i + 1 < len(timing) else total_ms
        dur_s = max((end_ms - start_ms) / 1000.0, 0.05)
        seg_idx = seg["segment_index"]
        if seg_idx in video_by_segment:
            plan.append((video_by_segment[seg_idx], dur_s, "video"))
            continue
        image = image_by_segment.get(seg_idx)
        if image is None:
            return None
        if parallax_on:
            clip = _try_parallax_clip(job_id, image, dur_s, fps, width, height, seg_idx)
            if clip:
                plan.append((clip, dur_s, "video"))
                continue
        plan.append((image, dur_s, "image"))
    return plan


def _try_parallax_clip(job_id: str, image_path, dur_s: float, fps: int, width: int,
                        height: int, seg_idx: int):
    """_segment_backgrounds için tek segmentlik parallax deneme sarmalayıcısı --
    herhangi bir hata (model yok, VRAM sorunu, vb.) sessizce None döner."""
    try:
        from pipeline.utils import cinematic_motion
        out_dir = job_path(job_id, "video_broll")
        out_dir.mkdir(parents=True, exist_ok=True)
        clip_path = out_dir / f"parallax_seg_{seg_idx:03d}.mp4"
        if clip_path.exists():
            return clip_path  # aynı iş tekrar çalıştırılırsa (resume) yeniden üretme
        ok = cinematic_motion.render_parallax_clip(
            image_path, clip_path, dur_s, fps=fps, width=width, height=height, seg_no=seg_idx)
        return clip_path if ok else None
    except Exception as e:
        log.warning(f"Parallax denemesi başarısız (segment {seg_idx}), Ken Burns'e düşülüyor: {e}")
        return None


def run(job_id: str) -> dict:
    cfg = load_edit_settings()  # config edit.* + web override (edit_settings.json)
    audio_file = job_path(job_id, "audio.wav")
    srt_file = job_path(job_id, "subtitles.srt")
    avatar_file = job_path(job_id, "avatar.mp4")
    if not audio_file.exists():
        raise RuntimeError(f"Ses dosyası bulunamadı: {audio_file}")

    duration = _ffprobe_duration(audio_file)
    width, height = cfg.get("resolution", [1920, 1080])
    fps = cfg.get("fps", 30)

    inputs = []
    filter_parts = []

    seg_backgrounds = _segment_backgrounds(job_id, duration, cfg)
    if seg_backgrounds:
        n_video = sum(1 for _, _, kind in seg_backgrounds if kind == "video")
        log.info(
            f"{len(seg_backgrounds)} segment için üretilmiş görsellerle arka plan geçişleri kuruluyor"
            + (f" ({n_video} video b-roll klip dahil)" if n_video else "")
        )
        motion = cfg.get("motion", True)
        zoom_max = cfg.get("motion_zoom_max", 1.12)

        trans_cfg = cfg.get("transitions", {}) or {}
        # 17 Eyl eklendi: s05b_motion_graphics._render_accent_overlays'ın BİR KEZ render
        # ettiği döngülenebilir accent katmanları -- varsa, motion-graphics KAPLAMADIĞI
        # (düz Ken-Burns) her segmente bindirilir. Yoksa (aşama kapalı/başarısız) davranış
        # eskisiyle AYNI kalır.
        accent_dir = job_path(job_id, "video_broll/accent_overlays")
        accent_variants = sorted(accent_dir.glob("variant_*.webm")) if accent_dir.exists() else []
        if accent_variants:
            log.info(f"{len(accent_variants)} accent-overlay varyantı bulundu, düz Ken-Burns segmentlere bindirilecek")

        if trans_cfg.get("enabled", True) and len(seg_backgrounds) > 1:
            raw_types = trans_cfg.get("type", "fade")
            types = raw_types if isinstance(raw_types, list) else [raw_types]
            t_inputs, t_filters, t_label = _build_transition_chain(
                seg_backgrounds, width, height, fps, motion, zoom_max,
                types, float(trans_cfg.get("duration", 0.5)), accent_variants,
            )
            inputs += t_inputs
            filter_parts += t_filters
            log.info(f"{len(seg_backgrounds)} segment {types} geçişleriyle bağlanıyor "
                     f"({trans_cfg.get('duration', 0.5)}s)")
        else:
            for i, (src, dur_s, kind) in enumerate(seg_backgrounds):
                if kind == "video":
                    inputs += ["-stream_loop", "-1", "-t", f"{dur_s:.3f}", "-i", str(src)]
                    filter_parts.append(
                        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height},setsar=1,fps={fps}[v{i}]"
                    )
                elif motion:
                    # Statik görsele Ken Burns hareketi: zoompan kendi kare üretimini
                    # yaptığı için görsel tek kare olarak verilir (-loop yok).
                    inputs += ["-i", str(src)]
                    filter_parts.append(_kenburns_filter(i, i, dur_s, width, height, fps, zoom_max))
                else:
                    inputs += ["-loop", "1", "-t", f"{dur_s:.3f}", "-i", str(src)]
                    filter_parts.append(
                        f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height},setsar=1,fps={fps}[v{i}]"
                    )
            concat_inputs = "".join(f"[v{i}]" for i in range(len(seg_backgrounds)))
            filter_parts.append(f"{concat_inputs}concat=n={len(seg_backgrounds)}:v=1:a=0[vcat]")
            accent_variants = []  # bu (geçiş-siz) yolda accent-overlay henüz bağlanmadı
        # accent-overlay her non-video segment için _build_transition_chain'in inputs
        # listesine EK bir -i eklediğinden (bkz. yukarıdaki fonksiyon), sonraki girdilerin
        # (avatar/altyazı/ses) index'i bunu hesaba katmalı -- yoksa -map yanlış akışa
        # işaret eder (canlı testte "Stream map matches no streams" hatasıyla yakalandı).
        n_accent_inputs = (sum(1 for _, _, k in seg_backgrounds if k != "video")
                           if accent_variants else 0)
        next_input_index = len(seg_backgrounds) + n_accent_inputs
    else:
        images_dir = ROOT / cfg.get("background_images_dir", "assets/images")
        images = sorted(p for p in images_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS) if images_dir.exists() else []
        if images:
            log.info(f"visuals üretilmemiş; {images_dir} altındaki sabit görseller kullanılacak")
            per_image = duration / len(images)
            for i, img in enumerate(images):
                inputs += ["-loop", "1", "-t", f"{per_image:.3f}", "-i", str(img)]
                filter_parts.append(
                    f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]"
                )
            concat_inputs = "".join(f"[v{i}]" for i in range(len(images)))
            filter_parts.append(f"{concat_inputs}concat=n={len(images)}:v=1:a=0[vcat]")
            next_input_index = len(images)
        else:
            log.info("Görsel bulunamadı, düz renk arka plan kullanılacak")
            inputs += ["-f", "lavfi", "-i", f"color=c=0x1b1e27:s={width}x{height}:d={duration:.3f}:r={fps}"]
            filter_parts.append("[0:v]setsar=1[vcat]")
            next_input_index = 1

    last_label = "vcat"

    if avatar_file.exists():
        avatar_input_index = next_input_index
        inputs += ["-i", str(avatar_file)]
        next_input_index += 1

        avatar_w = int(width * cfg.get("avatar_width_ratio", 0.42))
        margin = int(width * 0.02)
        chroma = cfg.get("avatar_chroma_key", True)
        intro = float(cfg.get("avatar_intro_seconds", 0))
        # Arka plan rengi anahtarlanır. Foto YEŞİL ekrana taşındığı için (rembg ile
        # arka plan kaldırılıp yeşile kondu) yeşil tenden/beyaz gömlekten çok farklı;
        # yüksek tolerans temizce siler, gömlek/cilt korunur. Beyaz zeminli fotoya
        # dönersen chroma_color=white + düşük tolerans (0.05) kullan.
        color = cfg.get("avatar_chroma_color", "0x00FF00")
        sim = cfg.get("avatar_chroma_similarity", 0.20)
        blend = cfg.get("avatar_chroma_blend", 0.10)
        key = f",colorkey={color}:{sim}:{blend}" if chroma else ""

        center_full = bool(cfg.get("avatar_center_full", False))

        if center_full:
            # KARAKTER HEP ORTADA: karakter tüm video boyunca ekranda ortada (yatayda
            # ortalı, alta yaslı) kalır — köşeye küçülmez. Arkasındaki foto-gerçekçi
            # görsel/b-roll background olarak görünür (gerçek sunucu/haber spikeri düzeni).
            center_h = int(height * float(cfg.get("avatar_intro_height_ratio", 0.92)))
            center_h -= center_h % 2
            # Çerçeveye SIĞDIRARAK ölçekle (decrease) -> hiçbir en-boy oranında aşırı
            # kırpma/zoom olmaz, karakter tam görünür. Sonra chroma key ile yeşil silinir.
            filter_parts.append(
                f"[{avatar_input_index}:v]scale=w={width}:h={center_h}:force_original_aspect_ratio=decrease{key}[avc]"
            )
            filter_parts.append(f"[vcat][avc]overlay=(W-w)/2:H-h:shortest=1[vcomp]")
            last_label = "vcomp"
        elif intro > 0:
            # KARAKTER ÖNCE: intro süresince avatar tam ekran (yatayda ortalı, alta
            # yaslı) konuşur; süre dolunca köşe overlay'e geçer. Aynı avatar akışı
            # split ile iki kez ölçeklenir; enable ifadeleri hangisinin görüneceğini
            # zamana göre seçer (ses senkronu bozulmaz, iki kopya da t=0'dan başlar).
            intro_h = int(height * float(cfg.get("avatar_intro_height_ratio", 0.92)))
            intro_h -= intro_h % 2
            filter_parts.append(f"[{avatar_input_index}:v]split=2[avsrc_a][avsrc_b]")
            # Avatar yatay da olabilir (preprocess=full tüm fotoğrafı tutar); çerçeveye
            # SIĞDIRARAK ölçekle (force_original_aspect_ratio=decrease) — böylece hiçbir
            # en-boy oranında aşırı zoom/kırpma olmaz, karakter tam görünür.
            filter_parts.append(
                f"[avsrc_a]scale=w={width}:h={intro_h}:force_original_aspect_ratio=decrease{key}[avbig]"
            )
            filter_parts.append(f"[avsrc_b]scale={avatar_w}:-2{key}[avsmall]")
            corner_xy = _corner_overlay_xy(cfg.get("avatar_position", "bottom-right"), margin)
            filter_parts.append(
                f"[vcat][avbig]overlay=(W-w)/2:H-h:enable='lte(t,{intro:.3f})':shortest=1[vintro]"
            )
            filter_parts.append(
                f"[vintro][avsmall]overlay={corner_xy}:enable='gt(t,{intro:.3f})':shortest=1[vcomp]"
            )
        else:
            corner_xy = _corner_overlay_xy(cfg.get("avatar_position", "bottom-right"), margin)
            av_chain = f"[{avatar_input_index}:v]scale={avatar_w}:-2{key}[avf]"
            filter_parts.append(av_chain)
            filter_parts.append(f"[vcat][avf]overlay={corner_xy}:shortest=1[vcomp]")
        last_label = "vcomp"
    else:
        log.info("avatar.mp4 yok, overlay atlanıyor (sadece arka plan)")

    # Profesyonel "stüdyo" görünümü: hafif sinematik grade + vinyet + ince keskinlik.
    # Altyazıdan ÖNCE uygulanır ki beyaz altyazı grade'den etkilenmesin. (config edit.studio_look)
    if cfg.get("studio_look", True):
        from pipeline.utils import studio
        chain = studio.studio_filter(cfg.get("studio_style"))
        if chain:
            filter_parts.append(f"[{last_label}]{chain}[vgraded]")
            last_label = "vgraded"

    # Ekran-üstü politika/bilgilendirme ve kaynak overlay'leri
    meta = _load_json(job_path(job_id, "metadata.json")) or {}

    # 1) Disclaimer overlay (videonun ilk 12 saniyesinde sol alt köşede zarif bilgilendirme kutusu)
    if cfg.get("overlay_disclaimer", True):
        from pipeline import policy
        disc_text = policy.get_overlay_disclaimer_text(language=cfg.get("default_language", "tr"))
        disc_escaped = disc_text.replace(":", "\\:").replace("'", "\\'")
        filter_parts.append(
            f"[{last_label}]drawtext=text='{disc_escaped}':fontsize=16:fontcolor=white@0.90:"
            f"box=1:boxcolor=black@0.50:boxborderw=6:x=32:y=H-th-32:enable='lte(t,12)'[vdisc]"
        )
        last_label = "vdisc"

    # 2) Sources overlay (varsa ilk 15 saniyede sağ üst köşede kullanılan kaynaklar)
    if cfg.get("overlay_sources", True):
        sources = meta.get("sources") or []
        if not sources:
            sc = _load_json(job_path(job_id, "script.json")) or {}
            sources = sc.get("sources") or []
        if sources:
            src_names = []
            for s in sources:
                s_low = str(s).lower()
                if "wikipedia" in s_low:
                    src_names.append("Wikipedia")
                elif "yahoo" in s_low or "finance.yahoo" in s_low:
                    src_names.append("Yahoo Finance")
                elif "tcmb" in s_low:
                    src_names.append("TCMB")
                elif "coingecko" in s_low:
                    src_names.append("CoinGecko")
                else:
                    clean = re.sub(r"^https?://(www\.)?", "", str(s)).split("/")[0]
                    src_names.append(clean[:20])
            src_names = list(dict.fromkeys(src_names))[:3]
            if src_names:
                src_label = "Kaynak: " + " • ".join(src_names)
                src_escaped = src_label.replace(":", "\\:").replace("'", "\\'")
                filter_parts.append(
                    f"[{last_label}]drawtext=text='{src_escaped}':fontsize=15:fontcolor=white@0.85:"
                    f"box=1:boxcolor=black@0.40:boxborderw=5:x=W-tw-32:y=32:enable='lte(t,15)'[vsrc]"
                )
                last_label = "vsrc"

    if cfg.get("burn_subtitles", True) and srt_file.exists() and srt_file.stat().st_size > 0:
        srt_escaped = _escape_filter_path(srt_file)
        # Altyazı stili web arayüzünden tasarlanabilir (subtitle_style.json). Değerler
        # libass PlayResY=384 ölçeğindedir (video yüksekliğine oranla ölçeklenir), piksel değil.
        force_style = build_subtitle_force_style(load_subtitle_style())
        filter_parts.append(
            f"[{last_label}]subtitles='{srt_escaped}':force_style='{force_style}'[vout]"
        )
        last_label = "vout"

    # 16 Eyl eklendi: Remotion ile ANİMASYONLU altyazı (TikTok/CapCut tarzı pop-in) — yukarıdaki
    # libass `subtitles=` filtresinin ALTERNATİFİ. Chromium ile render edilir, fontconfig/libass
    # HİÇ KULLANMAZ -> bu makinedeki ACCESS_VIOLATION çökmesini (burn_subtitles notu) tamamen
    # atlar. Şeffaf (alpha) WebM olarak render edilip en üst katman olarak overlay edilir.
    caps_cfg = cfg.get("animated_captions", {}) or {}
    if caps_cfg.get("enabled", False) and srt_file.exists() and srt_file.stat().st_size > 0:
        exclude_ranges = _video_covered_time_ranges(job_id, duration)
        caps_webm = _render_animated_captions(job_id, srt_file, duration, caps_cfg, exclude_ranges)
        if caps_webm:
            cap_input_index = next_input_index
            # -c:v libvpx: ffmpeg'in VARSAYILAN vp8 kod çözücüsü WebM alpha bloğunu
            # okumuyor (doğrulandı) -- libvpx'i AÇIKÇA istemek gerekiyor.
            inputs += ["-c:v", "libvpx", "-i", str(caps_webm)]
            next_input_index += 1
            filter_parts.append(f"[{cap_input_index}:v]format=yuva420p[capfmt]")
            filter_parts.append(f"[{last_label}][capfmt]overlay=0:0[vcaps]")
            last_label = "vcaps"

    # 18 Eyl eklendi (SIFIR_MALIYET rehberi Modül 6): videonun TAMAMI boyunca üstte akan
    # şeffaf bölüm çubuğu -- animated_captions ile AYNI desen (Chromium render, libvpx
    # alpha overlay), en üst katman olarak (altyazının da üstüne) bindirilir.
    chapter_cfg = cfg.get("chapter_bar", {}) or {}
    if chapter_cfg.get("enabled", True):
        chapter_webm = _render_chapter_progress(job_id, duration, chapter_cfg)
        if chapter_webm:
            chapter_input_index = next_input_index
            inputs += ["-c:v", "libvpx", "-i", str(chapter_webm)]
            next_input_index += 1
            filter_parts.append(f"[{chapter_input_index}:v]format=yuva420p[chapfmt]")
            filter_parts.append(f"[{last_label}][chapfmt]overlay=0:0[vchap]")
            last_label = "vchap"

    audio_input_index = next_input_index
    inputs += ["-i", str(audio_file)]
    next_input_index += 1
    audio_map = f"{audio_input_index}:a"

    # 18 Eyl eklendi (SFX Director, Modül 1): motion-graphics/para/dramatik-düşüş anlarına
    # otomatik mikro ses efekti (whoosh/pop/coin/boom/ticker) ekler. Herhangi bir adım
    # başarısız olursa (dosya yok, manifest bozuk) cues boş döner -> davranış eskisiyle AYNI.
    sfx_cfg = cfg.get("sfx", {}) or {}
    if sfx_cfg.get("enabled", True):
        try:
            from pipeline import sfx_director
            cues = sfx_director.pick_cues(job_id)
            if cues:
                sfx_inputs, sfx_filters, mixed_label = sfx_director.build_audio_filter(
                    cues, audio_map, next_input_index)
                inputs += sfx_inputs
                filter_parts += sfx_filters
                next_input_index += len(cues)
                audio_map = f"[{mixed_label}]"
                log.info(f"{len(cues)} SFX ipucu ana sese karıştırıldı")
        except Exception as e:
            log.warning(f"SFX Director başarısız oldu, sessiz devam ediliyor: {e}")

    # 18 Eyl: loudnorm ARTIK filter_complex ZİNCİRİNİN İÇİNDE uygulanıyor (aşağıdaki -af
    # satırı KALDIRILDI). Sebep: SFX açıkken audio_map bir complex-filter çıktısı oluyor
    # ([sfxmix] gibi köşeli parantezli bir label) ve ffmpeg aynı akışa hem complex-filter
    # hem de -af (simple filter) uygulanmasına izin vermiyor ("Simple and complex filtering
    # cannot be used together for the same stream" hatasıyla video.mp4 hiç yazılamıyordu).
    # Loudnorm'u burada tek bir [aout] node'una taşımak SFX açık/kapalı her iki durumda da
    # çalışır (audio_map köşeli parantezli ya da düz "N:a" olabilir, ikisi de filtre girdisi
    # olarak köşeli parantezle sarılabilir).
    loudnorm_input = audio_map if audio_map.startswith("[") else f"[{audio_map}]"
    filter_parts.append(f"{loudnorm_input}loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    audio_map = "[aout]"

    filter_complex = ";".join(filter_parts)

    video_file = job_path(job_id, "video.mp4")
    # filter_complex'i DOSYAYA yaz, komut satırına gömme: uzun (15dk+, 150+ segmentlik)
    # videolarda zoompan/scale zincirleri onbinlerce karaktere ulaşıp Windows'un
    # CreateProcess komut satırı üst sınırını aşıyor (WinError 206, 7 Ağu'da tespit edildi).
    # -filter_complex_script bu sınırı tamamen ortadan kaldırır (girdi sayısı arttıkça
    # -i listesi büyümeye devam eder ama tek başına limitin çok altında kalır).
    filter_script_file = job_path(job_id, "_filter_complex.txt")
    filter_script_file.write_text(filter_complex, encoding="utf-8")

    encoder_pref = str(cfg.get("encoder", "auto")).lower()
    use_nvenc = _has_nvenc() if encoder_pref != "cpu" else False

    def _build_cmd(nvenc: bool) -> list[str]:
        return [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex_script", str(filter_script_file),
            "-map", f"[{last_label}]",
            "-map", audio_map,
            # 31 Tem: KALİTE -> crf 20->18 (daha az sıkıştırma) / eşdeğer NVENC cq 18.
            # loudnorm artık filter_complex içinde ([aout] node'u, yukarıda) uygulanıyor.
            *_video_encoder_args(cfg, nvenc),
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(video_file),
        ]

    log.info(f"ffmpeg montaj başlıyor ({'NVENC GPU' if use_nvenc else 'libx264 CPU'}) -> {video_file}")
    # 18 Ağu OLAYI: bu makinede sistem genelinde fonts.conf hiç yok (fontconfig paketi
    # kurulu değil) -> subtitles/drawtext filtreleri libass/fontconfig'i tetikleyince ffmpeg
    # "Fontconfig error: Cannot load default config file" ile ACCESS_VIOLATION (kod
    # 3221225477) vererek çöktü. Repo içi minimal fonts.conf (Windows font dizinine işaret
    # eder) FONTCONFIG_FILE ile enjekte edilir -> sistem kurulumuna bağımlı kalmaz.
    ffmpeg_env = dict(os.environ)
    ffmpeg_env.setdefault("FONTCONFIG_FILE", str(ROOT / "assets" / "fontconfig" / "fonts.conf"))
    result = subprocess.run(
        _build_cmd(use_nvenc), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=ffmpeg_env,
    )
    if result.returncode != 0 and use_nvenc and encoder_pref != "nvenc":
        # NVENC (donanım encode session limiti, sürücü vb.) başarısız olursa CPU'ya düş --
        # 16 Eyl: bu makinede önceki ffmpeg filtre çökmeleri (drawtext/libass) yaşandığı için
        # yeni bir encode yolu asla videoyu tamamen üretmez halde bırakmamalı.
        log.warning("NVENC encode başarısız oldu, libx264 (CPU) ile yeniden deneniyor: "
                    + result.stderr[-800:])
        result = subprocess.run(
            _build_cmd(False), capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=ffmpeg_env,
        )
    if result.returncode != 0:
        log.error(result.stderr[-4000:])
        raise RuntimeError(f"ffmpeg başarısız oldu (kod {result.returncode})")

    log.info(f"Video yazıldı: {video_file} ({duration:.1f}s)")

    # 17 Eyl eklendi -- Tester ajanı: final video.mp4'ü ffprobe/ffmpeg ile teknik olarak
    # doğrular (süre eşleşiyor mu, video akışı var mı, siyah kare oranı) ve raporu +
    # (config açıksa) videonun kendisini Google Drive'a yükler. Editor/Denetleyici bu
    # aşamada devrede değil (montaj kararları deterministik, LLM kritiği gerektirmiyor) --
    # bkz. pipeline/agents/. HERHANGİ bir hata videoyu asla etkilemez, sadece loglanır.
    agents_cfg = load_config().get("agents", {}) or {}
    if agents_cfg.get("tester", {}).get("enabled", True):
        try:
            from pipeline.agents import tester as agent_tester
            agent_tester.run_and_report(
                job_id, "final_edit", video_file, expected_seconds=duration,
                upload_to_drive=agents_cfg.get("tester", {}).get("upload_to_drive", True),
            )
        except Exception as e:
            log.warning(f"Tester doğrulaması yapılamadı (video etkilenmedi): {e}")

    # Toplu çıktı: bitmiş videolar tek klasörde okunaklı isimle toplansın (iş klasörünü
    # tek tek aramaya gerek kalmasın). output/_videos alt çizgili -> list_jobs onu atlar.
    try:
        collected = _collect_video(job_id, video_file)
        if collected:
            log.info(f"Video koleksiyona kopyalandı: {collected}")
    except Exception as e:
        log.warning(f"Video koleksiyona kopyalanamadı: {e}")

    return {"video_file": str(video_file), "duration_s": duration}


def _collect_video(job_id: str, video_file) -> str | None:
    """Bitmiş video.mp4'ü output/_videos/<job_id>.mp4 olarak kopyalar (toplu galeri) +
    kapak görseli (thumbnail) çıkarır."""
    import shutil
    videos_dir = ROOT / "output" / "_videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    dst = videos_dir / f"{job_id}.mp4"
    shutil.copy2(video_file, dst)
    # Kapak: videonun ~%25'inden yüksek kaliteli tek kare (foto-gerçekçi -> iyi thumbnail).
    try:
        dur = _ffprobe_duration(video_file)
        ts = max(dur * 0.25, 1.0)
        thumb = videos_dir / f"{job_id}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", str(video_file),
             "-frames:v", "1", "-q:v", "2", str(thumb)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except Exception as e:
        log.warning(f"thumbnail çıkarılamadı: {e}")
    return str(dst)


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
