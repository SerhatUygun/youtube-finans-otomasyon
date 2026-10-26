"""Aşama 04: Arka plan/b-roll görselleri (SDXL / FLUX, lokal diffusers).

Girdi: output/<job_id>/script.json (visual_prompts varsa) ve segments_timing.json
Çıktı: output/<job_id>/visuals/seg_XXX.png + output/<job_id>/visuals_manifest.json

visual_prompts alanı olmayan eski script'ler için (ör. API çağrısı yapılmadan test
amaçlı) segment metninden Ollama ile İngilizce bir görsel prompt'u türetilir.

ÖNEMLİ — geçmiş hata: guidance_scale burada 0.0 olarak hardcode edilmişti (FLUX-schnell
için doğru, SDXL için felaket: CFG=0'da SDXL tutarsız mozaik/bulamaç üretir). Artık
üretim parametreleri config'den okunur ve motora göre makul varsayılanlar kullanılır.

SDXL için varsayılan olarak "ensemble of expert denoisers" (base+refiner) iki aşamalı
üretim kullanılır (Stability AI'nin resmi yüksek kalite yöntemi): base model adımların
ilk %80'ini atar ve TAM görsel yerine gürültülü bir latent üretir (denoising_end),
refiner model kalan %20'yi tamamlayıp ince detayları/dokuyu belirgin şekilde iyileştirir.
Toplam adım sayısı (steps) ikisi arasında bölünür — tek pipe'lı üretimden çok daha
yavaş DEĞİLDİR, sadece iki model art arda yüklenir (VRAM güvenliği için önce base ile
TÜM segmentlerin latent'leri üretilir, base GPU'dan düşürülür, sonra refiner yüklenip
TÜM latent'ler işlenir — s05'teki T5 iki fazlı yükleme deseniyle aynı mantık).
"""
import json
import re
import time

from pipeline import visual_director
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("s04_visuals")

_PIPE_CACHE = {}
_OLLAMA_FAILED_PERMANENTLY = False

# Pozitif prompt'a stil; "no text/no watermark" gibi OLUMSUZLAMALAR pozitif prompt'ta
# İŞE YARAMAZ (model olumsuzlamayı anlamaz, tam tersine "text" kavramını çağırır) —
# onlar negative_prompt'ta durmalı.
# Kanal yönü: İngilizce çocuk Shorts — renkli, storybook/Pixar-vari 3D karikatür stili
# (önceki sinematik-fotoğraf stili yatay/yetişkin içeriğe aitti).
# NOT: Stil artık görsel karakterden (pipeline/visual_director.py) geliyor; aşağıdaki sabit
# yalnızca YEDEK'tir (karakter/style_suffix yoksa) ve 'cocuk-storybook' karakteriyle aynıdır.
STYLE_SUFFIX = (
    ", vibrant colorful 3d cartoon style, pixar style render, storybook illustration, "
    "soft rounded shapes, cheerful bright lighting, kid-friendly, high detail"
)

# DİKKAT: karikatür stiline geçildiği için eski negative'deki "cartoon, anime,
# illustration, 3d render, cgi" yasakları KALDIRILDI (stil ile çelişiyordu);
# yerine çocuk güvenliği (korkutucu/şiddet) yasakları eklendi. Fotogerçekçi
# insan yüzü yasağı korundu — SDXL'in gerçekçi yüz artefaktlarından kaçınmak için
# stilize karakterler serbest.
DEFAULT_NEGATIVE_PROMPT = (
    "text, watermark, logo, signature, caption, subtitles, letters, numbers, "
    "collage, grid, tiled, split screen, multiple panels, frame, border, "
    "photorealistic human face, photo portrait, person looking at camera, "
    "scary, creepy, horror, nightmare, dark and gloomy, violent, blood, weapon, "
    "deformed, distorted, disfigured, mutated, extra limbs, extra fingers, "
    "low quality, worst quality, blurry, jpeg artifacts, oversaturated"
)

# Motor bazlı makul varsayılanlar — config'de değer varsa config kazanır.
ENGINE_DEFAULTS = {
    "sdxl": {"steps": 30, "guidance": 7.0, "use_negative": True, "use_refiner": True},
    "flux-schnell": {"steps": 4, "guidance": 0.0, "use_negative": False, "use_refiner": False},
}

DEFAULT_REFINER_MODEL = "stabilityai/stable-diffusion-xl-refiner-1.0"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b"

# Çeviri/visual_prompt tamamen eksikse nötr ama kanala uygun bir arka plan üret
# (çocuk içeriği: renkli, yumuşak, güvenli).
NEUTRAL_FALLBACK_PROMPT = (
    "colorful cheerful abstract background, soft pastel clouds and twinkling stars, "
    "playful storybook feel"
)


def _resolve_model_path(model_name: str) -> str:
    """Göreli lokal yol verildiyse (ör. models/sdxl-refiner-1.0) proje köküne göre
    çözer; yoksa HuggingFace repo id olarak olduğu gibi bırakır (bkz. s05_video_broll
    ile aynı desen — hub cache'in Windows symlink gereksinimi nedeniyle bazı modeller
    local_dir ile models/ altına indiriliyor)."""
    local = ROOT / model_name
    return str(local) if local.exists() else model_name


def _get_pipeline(engine: str, model_name: str):
    model_name = _resolve_model_path(model_name)
    key = ("base", model_name)
    if key not in _PIPE_CACHE:
        import torch
        from diffusers import AutoPipelineForText2Image

        log.info(f"Görsel modeli yükleniyor: {model_name} (ilk seferde büyük indirme olabilir)")
        pipe = AutoPipelineForText2Image.from_pretrained(
            model_name, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
        )
        pipe = pipe.to("cuda")
        # SDXL'in VAE decode adımı 1344x768 gibi çözünürlüklerde bilinen bir VRAM
        # sıçraması yapıyor (topluluk genelinde bilinen sorun). Bu sıçrama VRAM'i
        # %95+ doldurup Windows WDDM'in sistem RAM'ine spill etmesine yol açıyor —
        # bu da (LTX'te gördüğümüzle aynı mekanizma) adım başına 60-90sn'ye varan
        # dramatik yavaşlamaya neden oluyor. Slicing/tiling VAE'yi parçalar halinde
        # işleyip tepe VRAM kullanımını düşürür, kalite kaybı yok.
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        # 17 Eyl: canlı testte segment başına 20-25dk gözlendi (bu donanımda normali
        # 15-30sn) -- VAE slicing DENOISING LOOP'unu (UNet forward, asıl VRAM tüketicisi)
        # kapsamıyordu. attention_slicing tepe VRAM'i orada da düşürür, WDDM spill'ini
        # önler; kalite kaybı yok (sadece bellek/hız ödünleşimi, çıktı pikselleri aynı).
        pipe.enable_attention_slicing("max")
        _PIPE_CACHE[key] = pipe
    return _PIPE_CACHE[key]


def _get_refiner_pipeline(model_name: str):
    model_name = _resolve_model_path(model_name)
    key = ("refiner", model_name)
    if key not in _PIPE_CACHE:
        import torch
        from diffusers import StableDiffusionXLImg2ImgPipeline

        log.info(f"SDXL refiner modeli yükleniyor: {model_name} (ilk seferde büyük indirme olabilir)")
        pipe = StableDiffusionXLImg2ImgPipeline.from_pretrained(
            model_name, torch_dtype=torch.float16, variant="fp16", use_safetensors=True
        )
        pipe = pipe.to("cuda")
        # bkz. _get_pipeline'daki VAE sıçraması notu — refiner'ın img2img decode adımı
        # aynı sorunu yaşıyor, hatta VRAM zaten daha az boş olduğu için daha kritik.
        pipe.vae.enable_slicing()
        pipe.vae.enable_tiling()
        pipe.enable_attention_slicing("max")  # bkz. _get_pipeline'daki 17 Eyl notu
        _PIPE_CACHE[key] = pipe
    return _PIPE_CACHE[key]


def _free_pipeline(key):
    import gc

    import torch

    if key in _PIPE_CACHE:
        del _PIPE_CACHE[key]
        gc.collect()
        torch.cuda.empty_cache()


def _ollama_visual_prompt(segment_text: str, topic: str, retries: int = 2) -> str | None:
    """SDXL'in İngilizce CLIP kodlayıcısı Türkçe metinde anlamsız görseller üretiyor.
    visual_prompts alanı olmayan script'ler için lokal Ollama üzerinden kısa bir
    İngilizce sahne betimlemesi türetilir. İlk çağrıda model belleğe yüklenirken
    zaman aşımı yaşanabildiği için birkaç kez denenir (geçmişte ilk segmentin
    prompt'u bu yüzden ham Türkçe gitmişti)."""
    global _OLLAMA_FAILED_PERMANENTLY
    if _OLLAMA_FAILED_PERMANENTLY:
        return None
    import requests

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": (
                        f'This is one sentence from a YouTube video script about "{topic}". '
                        "Convert ONLY this sentence into ONE short English visual scene description "
                        "for colorful storybook/cartoon b-roll image generation, staying strictly on "
                        "the video's topic above (max 15 words, cute and kid-friendly, no realistic "
                        "human faces, concrete and visualizable, no quotes, no explanation):\n\n"
                        f"{segment_text}"
                    ),
                    "stream": False,
                },
                timeout=90,
            )
            resp.raise_for_status()
            text = resp.json().get("response", "").strip().strip('"').strip()
            if text:
                return text
        except Exception as e:
            last_err = e
            time.sleep(2)

    log.warning(f"Ollama çevirisi {retries} denemede başarısız: {last_err}")
    if isinstance(last_err, requests.ConnectionError):
        _OLLAMA_FAILED_PERMANENTLY = True  # servis kapalı; her segmentte tekrar deneme
    return None


def _looks_english(text: str) -> bool:
    """Kaba kontrol: Türkçe'ye özgü karakter içeren prompt'lar CLIP'e gitmemeli."""
    return not re.search(r"[çğıöşüÇĞİÖŞÜ]", text)


def _build_prompts(segments: list[str], visual_prompts: list[str], topic: str) -> list[str]:
    """Her segment için İngilizce, görüntülenebilir bir prompt döndürür. Öncelik:
    1) script.json'daki visual_prompts (Claude üretimi, İngilizce)
    2) Ollama çevirisi (retry'lı)
    3) Bu koşudaki son başarılı prompt (görsel süreklilik, ham Türkçe'den iyi)
    4) Nötr sinematik fallback"""
    prompts = []
    last_good = None
    for i, seg_text in enumerate(segments):
        vp = visual_prompts[i].strip() if i < len(visual_prompts) and visual_prompts[i] else ""
        if vp and _looks_english(vp):
            prompts.append(vp)
            last_good = vp
            continue
        translated = _ollama_visual_prompt(seg_text, topic)
        if translated and _looks_english(translated):
            prompts.append(translated)
            last_good = translated
        elif last_good:
            log.warning(f"Segment {i}: çeviri yok, önceki segmentin görsel teması yeniden kullanılıyor")
            prompts.append(last_good)
        else:
            log.warning(f"Segment {i}: çeviri yok, nötr fallback prompt kullanılıyor")
            prompts.append(NEUTRAL_FALLBACK_PROMPT)
    return prompts


def _inject_market_charts(job_id, segments, script_data, manifest, manifest_file):
    """script.json'da market_symbols varsa (finans videosu), o günün CANLI grafiğini üretir ve
    ilgili varlığın anlatıldığı segment(ler)in görselini grafikle DEĞİŞTİRİR — böylece gerçek
    fiyat grafiği tam o an ekranda görünür. Defansif: hata s04'ü ASLA bozmaz (AI görseli kalır)."""
    symbols = script_data.get("market_symbols") or []
    if not symbols:
        return
    try:
        from pipeline import market_data
    except Exception as e:
        log.warning(f"market_data yüklenemedi, grafik enjeksiyonu atlanıyor: {e}")
        return

    charts_dir = job_path(job_id, "charts")
    charts_dir.mkdir(parents=True, exist_ok=True)
    by_index = {m["segment_index"]: m for m in manifest}
    injected = 0
    for key in symbols:
        meta = market_data.SYMBOLS.get(key)
        if not meta:
            continue
        try:
            series = market_data.fetch_series(key)
            if not series:
                continue
            chart_path = str(charts_dir / f"chart_{key}.png")
            market_data.render_chart(series, chart_path)
        except Exception as e:
            log.warning(f"Grafik üretilemedi ({key}): {e}")
            continue
        # Bu sembolün anlatıldığı İLK segment(ler)i bul (anahtar veya eş anlamlıları geçen).
        kws = [key] + meta.get("kw", [])
        matches = [i for i, s in enumerate(segments)
                   if s and any(k in s.lower() for k in kws) and i in by_index]
        for i in matches[:2]:   # sembol başına en çok 2 segment (ekranı grafikle boğmadan)
            by_index[i]["image"] = chart_path
            by_index[i]["is_chart"] = True
            injected += 1
    if injected:
        manifest.sort(key=lambda m: m["segment_index"])
        manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"{injected} segmentin görseli canlı piyasa grafiğiyle değiştirildi")


def run(job_id: str) -> dict:
    cfg = load_config()["visuals"]
    script_data = json.loads(job_path(job_id, "script.json").read_text(encoding="utf-8"))
    segments = script_data["segments"]
    visual_prompts = script_data.get("visual_prompts") or []
    topic = script_data.get("topic", "")

    # Görsel karakter (sanat yönetmeni): stil ve negatif prompt buradan gelir. script.json'da
    # visual_character_id yoksa (eski işler) default karaktere düşer -> eski davranışla birebir aynı.
    char = visual_director.get_character(script_data.get("visual_character_id"))
    style_suffix = char.get("style_suffix") or STYLE_SUFFIX

    out_dir = job_path(job_id, "visuals")
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = cfg.get("engine", "sdxl")
    defaults = ENGINE_DEFAULTS.get(engine, ENGINE_DEFAULTS["sdxl"])
    # Varsayılan YATAY (16:9); config'te visuals.resolution her zaman tanımlı.
    width, height = cfg.get("resolution", [1344, 768])
    steps = cfg.get("num_inference_steps", defaults["steps"])
    guidance = cfg.get("guidance_scale", defaults["guidance"])
    char_negative = char.get("negative_prompt") or DEFAULT_NEGATIVE_PROMPT
    negative = cfg.get("negative_prompt", char_negative) if defaults["use_negative"] else None
    seed = cfg.get("seed")  # null -> her koşuda farklı; sayı -> tekrarlanabilir
    use_refiner = cfg.get("use_refiner", defaults.get("use_refiner", False))
    model_name = _resolve_model_path(cfg["model_name"])
    refiner_model = _resolve_model_path(cfg.get("refiner_model_name", DEFAULT_REFINER_MODEL))
    high_noise_frac = cfg.get("refiner_high_noise_frac", 0.8)

    log.info(
        f"Üretim ayarları: engine={engine} {width}x{height} steps={steps} cfg={guidance} "
        f"refiner={'açık' if use_refiner else 'kapalı'} karakter={char['id']}"
    )

    prompts = _build_prompts(segments, visual_prompts, topic)

    import torch

    manifest_file = job_path(job_id, "visuals_manifest.json")
    manifest = []
    valid_indices = [i for i, seg_text in enumerate(segments) if seg_text.strip()]

    def _make_kwargs(i: int) -> dict:
        kwargs = {
            "prompt": prompts[i] + style_suffix,
            "guidance_scale": guidance,
        }
        if negative:
            kwargs["negative_prompt"] = negative
        if seed is not None:
            kwargs["generator"] = torch.Generator("cuda").manual_seed(int(seed) + i)
        return kwargs

    if not use_refiner:
        pipe = _get_pipeline(engine, model_name)
        for i in valid_indices:
            img_path = out_dir / f"seg_{i:03d}.png"
            log.info(f"Segment {i + 1}/{len(segments)} için görsel üretiliyor: {prompts[i][:80]}...")
            kwargs = _make_kwargs(i)
            kwargs.update(width=width, height=height, num_inference_steps=steps)
            image = pipe(**kwargs).images[0]
            image.save(img_path)
            manifest.append({"segment_index": i, "image": str(img_path), "prompt": kwargs["prompt"]})
            # Her segment sonrası diske yaz: yarıda hata olursa üretilmiş görseller
            # manifest'siz (kullanılamaz) kalmasın.
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        del pipe
        _free_pipeline(("base", model_name))
    else:
        # FAZ 1/2: base model her segment için TAM görsel yerine bir latent üretir
        # (denoising_end=high_noise_frac ile adımların ilk %80'i). Latent'ler küçük
        # (~130KB/görsel @ 1344x768) — hepsi rahatça bellekte tutulabilir.
        base_pipe = _get_pipeline(engine, model_name)
        latents_by_index = {}
        for i in valid_indices:
            log.info(f"Segment {i + 1}/{len(segments)} için base latent üretiliyor: {prompts[i][:80]}...")
            kwargs = _make_kwargs(i)
            kwargs.update(
                width=width, height=height, num_inference_steps=steps,
                denoising_end=high_noise_frac, output_type="latent",
            )
            latents_by_index[i] = base_pipe(**kwargs).images
        # ÖNEMLİ: _free_pipeline sadece _PIPE_CACHE'teki referansı siliyor; bu
        # fonksiyondaki `base_pipe` yerel değişkeni hâlâ aynı nesneyi tutuyor ve
        # Python referans sayımı yüzünden CUDA belleği GERÇEKTEN boşalmıyordu —
        # refiner VRAM'i %97 doldurup Windows WDDM spill'i ile adım başına
        # 60-90sn'ye varan yavaşlamaya yol açıyordu (LTX'te gördüğümüzle aynı kalıp).
        del base_pipe
        _free_pipeline(("base", model_name))

        # FAZ 2/2: refiner, base'in bıraktığı yerden (denoising_start=high_noise_frac)
        # devam edip kalan adımları tamamlayarak ince detay/dokuyu iyileştirir.
        import torch as _torch

        refiner_pipe = _get_refiner_pipeline(refiner_model)
        for i in valid_indices:
            img_path = out_dir / f"seg_{i:03d}.png"
            log.info(f"Segment {i + 1}/{len(segments)} refiner ile tamamlanıyor...")
            kwargs = _make_kwargs(i)
            kwargs.update(
                image=latents_by_index[i], num_inference_steps=steps, denoising_start=high_noise_frac,
            )
            image = refiner_pipe(**kwargs).images[0]
            image.save(img_path)
            manifest.append({"segment_index": i, "image": str(img_path), "prompt": kwargs["prompt"]})
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            # 17 Eyl: refiner VRAM'i zaten ~%97 dolu (yukarıdaki not); segmentler arası
            # ara ürünler (attention/latent tensörleri) serbest bırakılmadan VRAM
            # fragmante olup eşiği daha da yukarı itebiliyor, bu da WDDM spill'i ile
            # adım başına 60-90sn'ye varan yavaşlamaya katkıda bulunuyordu (gerçek bir
            # 9 segmentlik job'da refiner aşaması 8dk yerine 4.5 saat sürdü). Modeli
            # GPU'da TUTARAK (yeniden yükleme yok) sadece kullanılmayan bloğu boşalt.
            del image
            _torch.cuda.empty_cache()
        del refiner_pipe
        _free_pipeline(("refiner", refiner_model))

    # SDXL/refiner GPU'dan düşürüldü: orchestrator aynı process içinde hemen ardından
    # s05_video_broll'u çağırıyor, o da T5'i (~9.5GB) doğrudan GPU'ya yüklüyor.
    # Burada bırakılırsa 16GB kartta toplam VRAM'i taşırıp sessiz OOM'a yol açıyor
    # (orchestrator'daki geniş except onu yutup statik görsele düşüyor — b-roll hiç
    # çalışmamış oluyor, hata hiç görünmüyor).
    manifest.sort(key=lambda m: m["segment_index"])
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"{len(manifest)} görsel üretildi -> {out_dir}")

    # Canlı piyasa grafiklerini ilgili segmentlere enjekte et (finans videosu ise; değilse no-op).
    _inject_market_charts(job_id, segments, script_data, manifest, manifest_file)

    return {"visuals_manifest": str(manifest_file), "count": len(manifest)}


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
