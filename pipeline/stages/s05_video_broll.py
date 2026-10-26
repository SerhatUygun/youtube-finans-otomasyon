"""Aşama 05: Video b-roll — Faz 3, opsiyonel.

Dört motor desteklenir (config.yaml -> visuals.video_broll.engine):

  framepack (16 Eyl eklendi — düşük risk önceliği): izole venv + subprocess
      (scripts/run_framepack.py). WAN/LTX'in aksine SABİT ~6GB VRAM kullanır (video
      uzunluğundan bağımsız) -> bu makinede diğer motorları çökerten "uzunluk arttıkça
      VRAM/RAM şişmesi" sorununu yapısal olarak yaşamaz. İlk çalıştırmada HunyuanVideo
      tabanı ~30GB iner (bkz. scripts/run_framepack.py, scripts/setup_framepack.ps1).

  wan-i2v (kalite önceliği): s04_visuals'ın ürettiği statik görseli canlandırır
      (Wan2.1-I2V-14B-480P, GGUF Q4 quantize transformer). Açık kaynak modeller
      içinde en yüksek hareket/detay kalitesi; klip başına LTX'ten kat kat yavaş.
      İki fazlı yükleme LTX ile aynı desendedir (UMT5 ~ T5 ile aynı boyut sınıfı).

  ltx-i2v (hız önceliği): aynı i2v yaklaşımı, Lightricks/LTX-Video ile.
      Videoda görünen sahne, statik görselle birebir aynı olduğu için kesintisiz
      bir bütünlük verir ve CogVideoX'ten belirgin şekilde hızlıdır.

  cogvideox-t2v (eski davranış): metin prompt'undan sıfırdan video üretir
      (THUDM/CogVideoX-2b). Yavaş; üretilen sahne statik görsellerle tutarsız
      olabilir.

En ağır/yavaş aşama olduğu için varsayılan olarak KAPALI
(config.yaml -> visuals.video_broll.enabled: false). Açıldığında, en uzun süren
birkaç segment (max_clips) için klip üretir; kalan segmentler statik görsellerini
kullanmaya devam eder. s07_edit.py bu klipleri varsa statik görsel yerine kullanır.

Girdi: output/<job_id>/segments_timing.json, visuals_manifest.json
Çıktı: output/<job_id>/video_broll/seg_XXX.mp4 + output/<job_id>/video_broll_manifest.json
"""
import json
import subprocess

from pipeline import visual_director
from pipeline.utils import proc_guard
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("s05_video_broll")

_PIPE_CACHE = {}

# FramePack icin hareket eki (LTX ile ayni sinematik kelime dagarcigi kullanilir --
# ayri bir karakter alani eklemek panel/semaya gereksiz alan katardi, bkz. visual_director._CHAR_KEYS).
FRAMEPACK_MOTION_SUFFIX = (
    ", slow gentle camera drift, subtle natural motion in the scene, "
    "smooth cinematic movement, consistent lighting"
)

# LTX hareket kalitesi için önerilen negative prompt (model kartından)
LTX_NEGATIVE_PROMPT = "worst quality, inconsistent motion, blurry, jittery, distorted"

# Statik görseli canlandırırken prompt'a eklenen hareket ipucu — LTX ayrıntılı,
# hareketi tarif eden prompt'larla çok daha iyi sonuç veriyor.
LTX_MOTION_SUFFIX = (
    ", slow gentle camera drift, subtle natural motion in the scene, "
    "smooth cinematic movement, consistent lighting"
)

# Wan2.1 resmi negatif prompt (model kartından, Çince — model bu dille eğitildi;
# İngilizce çevirisi belirgin daha zayıf sonuç veriyor). config'te
# wan_negative_prompt verilirse onun yerine o kullanılır.
WAN_NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，"
    "低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，畸形的，"
    "毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)

# Wan için hareket eki — çocuk içeriğine uygun: yumuşak, oyuncu, sakin kamera.
# Wan da LTX gibi hareketi açıkça tarif eden prompt'larla çok daha iyi çalışıyor.
WAN_MOTION_SUFFIX = (
    ", gentle smooth animation, soft playful natural movement, "
    "calm slow camera motion, bright cheerful consistent lighting, high quality"
)


def _resolve_model_path(model_name: str) -> str:
    """Göreli lokal yol verildiyse (ör. models/LTX-Video) proje köküne göre çözer;
    lokal yol yoksa HuggingFace repo id olarak olduğu gibi bırakır."""
    local = ROOT / model_name
    return str(local) if local.exists() else model_name


def _embed_cache_path(model_name: str, prompt: str, negative: str):
    """Prompt embed'leri (T5 çıktısı) globalde önbellenir: T5'in her koşuda GPU'ya
    yüklenmesi ~16dk sürüyor (19GB fp32 disk okuması). Aynı prompt için ikinci koşu
    T5'e hiç dokunmaz. model_name hash'e dahil: video_broll.model_name değişirse
    (farklı LTX/T5 sürümü) eski embed'ler sessizce yanlış modelle kullanılmasın."""
    import hashlib

    key = hashlib.sha256(f"{model_name}\x00{prompt}\x00{negative}".encode("utf-8")).hexdigest()[:32]
    cache_dir = ROOT / ".cache" / "ltx_prompt_embeds"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}.pt"


def _ltx_encode_prompts(model_name: str, prompt_pairs: list[tuple[str, str]]):
    """Faz 1/2: SADECE T5 metin kodlayıcıyı yükleyip tüm prompt'ları kodlar, sonra
    modeli bellekten atar. Bu makinede 16GB RAM var; T5 (~9.5GB) + transformer + VAE
    aynı anda RAM'e sığmıyor (ilk denemede shard yüklemesi disk paging yüzünden
    5dk+/shard sürdü ve süreç öldü). İki fazlı yükleme tepe belleği yarıya indirir."""
    import gc

    import torch

    # Önce disk önbelleğine bak — hepsi varsa T5'e hiç dokunma
    encoded = {}
    missing = []
    for i, (prompt, negative) in enumerate(prompt_pairs):
        cache = _embed_cache_path(model_name, prompt, negative)
        if cache.exists():
            encoded[i] = tuple(torch.load(cache, weights_only=True))
        else:
            missing.append(i)
    if not missing:
        log.info("Tüm prompt embed'leri önbellekten yüklendi, T5 atlanıyor")
        return [encoded[i] for i in range(len(prompt_pairs))]

    from diffusers import LTXImageToVideoPipeline
    from transformers import T5EncoderModel

    # T5 diskte fp32 (~19GB, 4 shard). Önce CPU'ya yükleyip sonra GPU'ya taşımak
    # 16GB RAM'li bu makinede paging ile sistemi kilitliyor (iki kez süreç öldü).
    # device_map="cuda" shard'ları doğrudan GPU'ya akıtır: CPU tepe kullanımı tek
    # shard (~5GB), T5 bf16 GPU'da ~9.5GB — boş 16GB VRAM'e sığar.
    log.info(f"LTX faz 1/2: T5 metin kodlayıcı GPU'ya yükleniyor ({len(missing)} prompt kodlanacak)")
    text_encoder = T5EncoderModel.from_pretrained(
        model_name, subfolder="text_encoder", torch_dtype=torch.bfloat16, device_map="cuda"
    )
    pipe_txt = LTXImageToVideoPipeline.from_pretrained(
        model_name, transformer=None, vae=None, text_encoder=text_encoder, torch_dtype=torch.bfloat16
    )

    # ÖNEMLİ: encode_prompt'u pipe.__call__ dışında MANUEL çağırıyoruz — diffusers'ın
    # kendi __call__'ı tipik olarak @torch.no_grad() ile sarmalı, ama public
    # encode_prompt metodu tek başına çağrıldığında bu korumadan YOKSUN. no_grad
    # olmadan T5'in forward pass'i (4096 gizli boyut, onlarca katman) tam autograd
    # grafiğini bellekte tutuyor — VRAM'in gerçek ihtiyacın çok üzerinde şişip
    # (T5 kendisi ~9.5GB iken toplam 14GB+'a çıkıyor) donuk/thrashing durumuna
    # yol açtığı gözlemlendi (GPU util %0, VRAM %87 dolu, del+empty_cache sonrası
    # bile ~11.5GB rezidü kalıyordu).
    with torch.no_grad():
        for i in missing:
            prompt, negative = prompt_pairs[i]
            pe, pam, ne, nam = pipe_txt.encode_prompt(
                prompt=prompt,
                negative_prompt=negative,
                do_classifier_free_guidance=True,
                device="cuda",
            )
            cpu_tensors = (pe.cpu(), pam.cpu(), ne.cpu(), nam.cpu())
            torch.save(cpu_tensors, _embed_cache_path(model_name, prompt, negative))
            encoded[i] = cpu_tensors
            del pe, pam, ne, nam, cpu_tensors

    del pipe_txt, text_encoder
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    log.info(f"VRAM (T5 serbest bırakıldıktan sonra): {torch.cuda.memory_allocated() / 1e9:.1f}GB")
    return [encoded[i] for i in range(len(prompt_pairs))]


def _get_ltx_pipeline_no_text(model_name: str):
    """Faz 2/2: T5'siz pipeline (transformer + VAE, ~6GB) — tamamen GPU'da çalışır."""
    key = ("ltx-notext", model_name)
    if key not in _PIPE_CACHE:
        import torch
        from diffusers import LTXImageToVideoPipeline

        log.info("LTX faz 2/2: transformer + VAE yükleniyor (üretim)")
        # transformer da diskte fp32 (~7.7GB); RAM tepe kullanımını düşük tutmak için
        # doğrudan GPU'ya akıtılır (bkz. faz 1 notu).
        from diffusers import LTXVideoTransformer3DModel

        transformer = LTXVideoTransformer3DModel.from_pretrained(
            model_name, subfolder="transformer", torch_dtype=torch.bfloat16, device_map="cuda"
        )
        pipe = LTXImageToVideoPipeline.from_pretrained(
            model_name, text_encoder=None, tokenizer=None, transformer=transformer,
            torch_dtype=torch.bfloat16,
        )
        pipe.to("cuda")
        pipe.vae.enable_tiling()
        _PIPE_CACHE[key] = pipe
        log.info(f"VRAM (yükleme sonrası): {torch.cuda.memory_allocated() / 1e9:.1f}GB")
    return _PIPE_CACHE[key]


def _wan_embed_cache_path(model_name: str, prompt: str, negative: str):
    """Wan prompt embed disk önbelleği — _embed_cache_path ile aynı mantık, ayrı
    dizinde (UMT5 embed'leri T5 embed'leriyle karışmasın)."""
    import hashlib

    key = hashlib.sha256(f"{model_name}\x00{prompt}\x00{negative}".encode("utf-8")).hexdigest()[:32]
    cache_dir = ROOT / ".cache" / "wan_prompt_embeds"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}.pt"


def _wan_encode_prompts(model_name: str, prompt_pairs: list[tuple[str, str]]):
    """Faz 1/2: SADECE UMT5 metin kodlayıcıyı yükleyip tüm prompt'ları kodlar, sonra
    modeli bellekten atar. UMT5-xxl bf16 GPU'da ~11.5GB — T5 ile aynı iki fazlı
    desen (bkz. _ltx_encode_prompts): CPU'ya yükleyip taşımak 16GB RAM'de paging
    ile makineyi kilitliyor; device_map="cuda" shard'ları doğrudan GPU'ya akıtır."""
    import gc

    import torch

    # Önce disk önbelleğine bak — hepsi varsa UMT5'e hiç dokunma
    encoded = {}
    missing = []
    for i, (prompt, negative) in enumerate(prompt_pairs):
        cache = _wan_embed_cache_path(model_name, prompt, negative)
        if cache.exists():
            encoded[i] = tuple(torch.load(cache, weights_only=True))
        else:
            missing.append(i)
    if not missing:
        log.info("Tüm Wan prompt embed'leri önbellekten yüklendi, UMT5 atlanıyor")
        return [encoded[i] for i in range(len(prompt_pairs))]

    from diffusers import WanImageToVideoPipeline
    from transformers import UMT5EncoderModel

    log.info(f"Wan faz 1/2: UMT5 metin kodlayıcı GPU'ya yükleniyor ({len(missing)} prompt kodlanacak)")
    text_encoder = UMT5EncoderModel.from_pretrained(
        model_name, subfolder="text_encoder", torch_dtype=torch.bfloat16, device_map="cuda"
    )
    # transformer safetensors'ları diske hiç indirilmedi (GGUF kullanılıyor) —
    # transformer=None şart, yoksa from_pretrained eksik shard'larda patlar.
    # image_encoder=None: CLIP ViT-H (~5GB) bu fazda gereksiz, RAM'e yüklenmesin.
    pipe_txt = WanImageToVideoPipeline.from_pretrained(
        model_name,
        transformer=None,
        vae=None,
        image_encoder=None,
        text_encoder=text_encoder,
        torch_dtype=torch.bfloat16,
    )

    # encode_prompt, pipe.__call__ dışında manuel çağrıldığında no_grad korumasız —
    # LTX'te yaşanan VRAM şişmesi dersi (bkz. _ltx_encode_prompts içindeki not).
    # Wan'ın encode_prompt'u LTX'ten farklı: attention mask DÖNDÜRMEZ, sadece
    # (prompt_embeds, negative_prompt_embeds) döndürür (pipeline_wan_i2v.py:330).
    with torch.no_grad():
        for i in missing:
            prompt, negative = prompt_pairs[i]
            pe, ne = pipe_txt.encode_prompt(
                prompt=prompt,
                negative_prompt=negative,
                do_classifier_free_guidance=True,
                max_sequence_length=512,  # Wan resmi değeri (__call__ varsayılanı)
                device="cuda",
            )
            cpu_tensors = (pe.cpu(), ne.cpu())
            torch.save(cpu_tensors, _wan_embed_cache_path(model_name, prompt, negative))
            encoded[i] = cpu_tensors
            del pe, ne, cpu_tensors

    del pipe_txt, text_encoder
    gc.collect()
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    log.info(f"VRAM (UMT5 serbest bırakıldıktan sonra): {torch.cuda.memory_allocated() / 1e9:.1f}GB")
    return [encoded[i] for i in range(len(prompt_pairs))]


def _get_wan_pipeline_no_text(model_name: str, gguf_path: str, flow_shift: float, lora_path: str = None):
    """Faz 2/2: UMT5'siz pipeline — GGUF Q4 transformer (~9.5GB) + CLIP image
    encoder + VAE, tamamı bf16 GPU'da (fp32 CLIP+VAE kaliteyi çok az artırır ama
    16GB VRAM'e Q4 transformer ile birlikte sığmaz)."""
    key = ("wan-notext", model_name, gguf_path, lora_path)
    if key not in _PIPE_CACHE:
        import gc

        import torch
        from diffusers import (
            GGUFQuantizationConfig,
            UniPCMultistepScheduler,
            WanImageToVideoPipeline,
            WanTransformer3DModel,
        )

        log.info(f"Wan faz 2/2: GGUF transformer yükleniyor: {gguf_path}")
        transformer = WanTransformer3DModel.from_single_file(
            gguf_path,
            quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
            config=model_name,
            subfolder="transformer",
            torch_dtype=torch.bfloat16,
        )
        gc.collect()

        log.info("Wan faz 2/2: VAE + CLIP image encoder yükleniyor")
        pipe = WanImageToVideoPipeline.from_pretrained(
            model_name,
            transformer=transformer,
            text_encoder=None,
            tokenizer=None,
            torch_dtype=torch.bfloat16,
        )
        # Model kartı önerisi: UniPC, flow_shift 480p için 3.0 (720p: 5.0).
        # lightx2v distill LoRA ile flow_shift genelde 5.0 kullanılır (config'ten gelir).
        pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=flow_shift)

        # Hızlandırma LoRA'sı (lightx2v self-forcing / CausVid step+CFG distill):
        # Wan'ı 40 step + CFG yerine 4-6 step, CFG=1 ile çalıştırır. GGUF Q4 tabana
        # FUSE ETMİYORUZ (quantize ağırlığa fuse dequant gerektirir); rank-64 adapter
        # olarak yüklenip runtime'da uygulanır. diffusers 0.39 non-diffusers/musubi Wan
        # LoRA anahtarlarını otomatik çevirir (_convert_non_diffusers_wan_lora).
        if lora_path:
            log.info(f"Wan hızlandırma LoRA'sı yükleniyor (adapter): {lora_path}")
            pipe.load_lora_weights(lora_path, adapter_name="lightx2v")
            log.info("LoRA adapter yüklendi (fuse edilmedi — GGUF tabanla uyum için)")

        # 16GB VRAM kalibrasyonu: her şey GPU'da dinlenmede 12.5GB'a sığıyor AMA 81
        # karelik üretimin aktivasyon belleği tepeyi ~15.8GB'a çıkarıp Windows WDDM
        # spill'i ile fiilen kilitliyordu (24dk'da tek step bitmedi). model_cpu_offload:
        # accelerate hook'larıyla yalnızca AKTİF modül GPU'da kalır. Denoising döngüsünde
        # transformer 40 step boyunca aralıksız aktif olduğu için tek sefer GPU'ya alınıp
        # rezident kalır (her step'te taşınmaz -> hız kaybı yok); CLIP image encoder işini
        # görüp CPU'ya çekilir (~2.5GB boşalır), VAE decode sadece en sonda GPU'ya gelir.
        # Böylece sampling tepe VRAM'i ~transformer(9.5GB)+aktivasyon <16GB'da kalır.
        # NOT: offlanan modüller CPU RAM'de durur (transformer Q4 ~10GB + CLIP ~2.5GB);
        # 16GB RAM'e sığar — LTX'i öldüren 19GB fp32 T5 senaryosu burada yok.
        pipe.enable_model_cpu_offload()
        if hasattr(pipe.vae, "enable_tiling"):
            pipe.vae.enable_tiling()
        _PIPE_CACHE[key] = pipe
        log.info(f"VRAM (yükleme sonrası): {torch.cuda.memory_allocated() / 1e9:.1f}GB")
    return _PIPE_CACHE[key]


def _get_cogvideox_pipeline(model_name: str):
    key = ("cog", model_name)
    if key not in _PIPE_CACHE:
        import torch
        from diffusers import CogVideoXPipeline

        log.info(f"CogVideoX modeli yükleniyor: {model_name} (ilk seferde büyük indirme olabilir)")
        pipe = CogVideoXPipeline.from_pretrained(model_name, torch_dtype=torch.float16)
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        _PIPE_CACHE[key] = pipe
    return _PIPE_CACHE[key]


def _load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning(f"{path} okunamadı/bozuk JSON, atlanıyor: {e}")
            return None
    return None


def _snap32(v: int) -> int:
    """LTX çözünürlüğü 32'ye bölünebilir olmalı."""
    return max((v // 32) * 32, 32)


def _generate_ltx(pipe, cfg, embeds, image_path: str):
    from diffusers.utils import load_image

    width, height = cfg.get("i2v_resolution", [960, 544])
    width, height = _snap32(width), _snap32(height)
    num_frames = cfg.get("num_frames", 121)  # 8*k+1 olmalı; 121 ≈ 5s @ 24fps
    if (num_frames - 1) % 8 != 0:
        num_frames = ((num_frames - 1) // 8) * 8 + 1

    pe, pam, ne, nam = embeds
    image = load_image(image_path)
    return pipe(
        image=image,
        prompt_embeds=pe.to("cuda"),
        prompt_attention_mask=pam.to("cuda"),
        negative_prompt_embeds=ne.to("cuda"),
        negative_prompt_attention_mask=nam.to("cuda"),
        width=width,
        height=height,
        num_frames=num_frames,
        num_inference_steps=cfg.get("num_inference_steps", 40),
    ).frames[0]


def _snap16(v: int) -> int:
    """Wan çözünürlüğü 16'ya bölünebilir olmalı (VAE stride 8 x patch 2;
    pipeline_wan_i2v.py check_inputs %16 kontrolü yapıyor)."""
    return max((v // 16) * 16, 16)


def _generate_wan(pipe, cfg, embeds, image_path: str):
    from diffusers.utils import load_image

    width, height = cfg.get("wan_resolution", [480, 832])
    width, height = _snap16(width), _snap16(height)
    num_frames = cfg.get("wan_num_frames", 81)  # 4*k+1 olmalı; 81 ≈ 5.1s @ 16fps
    if (num_frames - 1) % 4 != 0:
        num_frames = ((num_frames - 1) // 4) * 4 + 1

    pe, ne = embeds
    # Pipeline görseli video_processor.preprocess ile verilen height/width'e kendisi
    # yeniden boyutlandırıyor (pipeline_wan_i2v.py:710) — burada resize gerekmez.
    image = load_image(image_path)
    return pipe(
        image=image,
        prompt_embeds=pe.to("cuda"),
        negative_prompt_embeds=ne.to("cuda"),
        width=width,
        height=height,
        num_frames=num_frames,
        num_inference_steps=cfg.get("wan_num_inference_steps", 40),
        guidance_scale=cfg.get("wan_guidance_scale", 5.0),
    ).frames[0]


def _generate_cogvideox(pipe, cfg, prompt: str):
    return pipe(
        prompt=prompt,
        num_videos_per_prompt=1,
        num_inference_steps=cfg.get("num_inference_steps", 50),
        num_frames=cfg.get("num_frames", 49),
        guidance_scale=6,
    ).frames[0]


def _run_framepack(job_id: str, selected, image_by_segment, prompt_by_segment, motion_suffix) -> dict:
    """FramePack: izole venv + subprocess (scripts/run_framepack.py). WAN/LTX'in aksine
    SABIT ~6GB VRAM kullanir (video uzunlugundan bagimsiz) -> bu makinede WAN/LTX/EchoMimic'i
    cokerten "uzunluk arttikca VRAM/RAM sisiyor" sorununu yapisal olarak yasamaz. Yine de
    proc_guard ile RAM/VRAM izlenir (guvenlik payi); segment basarisiz olursa atlanip statik
    gorsele dusulur, diger segmentler etkilenmez."""
    cfg = load_config().get("enhancements", {}).get("framepack", {})
    venv_python = (ROOT / cfg.get("venv_python", "vendor/FramePack/.venv/Scripts/python.exe")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"FramePack venv python yok: {venv_python} (scripts/setup_framepack.ps1 calistir)")
    script = (ROOT / "scripts" / "run_framepack.py").resolve()
    fps = int(cfg.get("fps", 30))
    steps = int(cfg.get("steps", 25))
    max_seconds = int(cfg.get("max_render_minutes", 30)) * 60
    min_free_ram_gb = float(cfg.get("min_free_ram_gb", 2.5))
    min_free_vram_gb = float(cfg.get("min_free_vram_gb", 1.0))

    out_dir = job_path(job_id, "video_broll")
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_file = job_path(job_id, "video_broll_manifest.json")

    manifest_out = []
    for n, seg in enumerate(selected):
        idx = seg["segment_index"]
        prompt = (prompt_by_segment.get(idx) or seg.get("text", "")) + motion_suffix
        seconds = max((seg["end_ms"] - seg["start_ms"]) / 1000.0, 1.0)
        clip_path = out_dir / f"seg_{idx:03d}.mp4"
        raw_log = job_path(job_id, f"framepack_seg{idx:03d}.log")
        cmd = [
            str(venv_python), str(script),
            "--image", str(image_by_segment[idx]),
            "--prompt", prompt,
            "--out", str(clip_path),
            "--seconds", f"{seconds:.2f}",
            "--fps", str(fps),
            "--steps", str(steps),
        ]
        log.info(f"FramePack klip {n + 1}/{len(selected)} (segment {idx}, {seconds:.1f}s) uretiliyor: {prompt[:80]}...")
        with open(raw_log, "w", encoding="utf-8") as f:
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT)
            try:
                proc_guard.wait_render_process(
                    proc, raw_log, "FramePack", max_seconds,
                    min_free_ram_gb=min_free_ram_gb, min_free_vram_gb=min_free_vram_gb,
                )
            except RuntimeError as e:
                log.error(f"FramePack segment {idx} durduruldu, statik gorsele dusuluyor: {e}")
                continue
        if proc.returncode != 0 or not clip_path.exists():
            tail = raw_log.read_text(encoding="utf-8", errors="replace")[-2000:]
            log.error(f"FramePack segment {idx} basarisiz, statik gorsele dusuluyor:\n{tail}")
            continue
        manifest_out.append({"segment_index": idx, "video": str(clip_path), "prompt": prompt, "engine": "framepack"})
        manifest_file.write_text(json.dumps(manifest_out, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(f"{len(manifest_out)} FramePack klip uretildi -> {out_dir}")
    return {"video_broll_manifest": str(manifest_file), "count": len(manifest_out)}


def run(job_id: str) -> dict:
    cfg = load_config().get("visuals", {}).get("video_broll", {})
    if not cfg.get("enabled", False):
        log.info("video_broll.enabled=false, aşama atlanıyor")
        return {"skipped": True}

    timing = _load_json(job_path(job_id, "segments_timing.json"))
    manifest = _load_json(job_path(job_id, "visuals_manifest.json")) or []
    if not timing:
        log.warning("segments_timing.json yok, video b-roll atlanıyor")
        return {"skipped": True}

    prompt_by_segment = {m["segment_index"]: m["prompt"] for m in manifest}
    image_by_segment = {m["segment_index"]: m["image"] for m in manifest}

    # Görsel karakter (sanat yönetmeni): hareket tarzı buradan gelir. s04 ile AYNI karakter
    # kullanılsın diye script.json'daki visual_character_id okunur; yoksa default karaktere düşer.
    script_data = _load_json(job_path(job_id, "script.json")) or {}
    char = visual_director.get_character(script_data.get("visual_character_id"))
    wan_motion = char.get("wan_motion_suffix") or WAN_MOTION_SUFFIX
    ltx_motion = char.get("ltx_motion_suffix") or LTX_MOTION_SUFFIX
    log.info(f"Video b-roll görsel karakter: {char['id']} — {char.get('name')}")

    engine = cfg.get("engine", "ltx-i2v")
    max_clips = cfg.get("max_clips", 3)
    # Grafik enjekte edilmiş segmentleri (s04_visuals._inject_market_charts, is_chart=True)
    # i2v adaylığından hariç tut — canlandırma fiyat/etiket metnini görsel olarak bozabilir
    # (finans videosunda doğruluk riski), ayrıca zaten sabit/gerçek bir grafik olarak yeterli.
    chart_idx = {m["segment_index"] for m in manifest if m.get("is_chart")}
    durations = sorted(
        (t for t in timing if t["segment_index"] not in chart_idx),
        key=lambda t: t["end_ms"] - t["start_ms"], reverse=True,
    )
    selected = durations[:max_clips]

    if engine == "framepack":
        selected = [s for s in selected if s["segment_index"] in image_by_segment]
        if not selected:
            log.warning("FramePack icin canlandirilacak statik gorsel yok (s04_visuals calismamis), atlaniyor")
            return {"skipped": True}
        framepack_motion = char.get("ltx_motion_suffix") or FRAMEPACK_MOTION_SUFFIX
        return _run_framepack(job_id, selected, image_by_segment, prompt_by_segment, framepack_motion)

    if engine == "wan-i2v":
        # i2v canlandıracak statik görsel ister; görseli olmayan segmentler elenir
        selected = [s for s in selected if s["segment_index"] in image_by_segment]
        if not selected:
            log.warning("i2v için canlandırılacak statik görsel yok (s04_visuals çalışmamış), atlanıyor")
            return {"skipped": True}
        model_name = _resolve_model_path(cfg.get("wan_model_name", "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers"))
        gguf_path = str(ROOT / cfg.get("wan_gguf_file", "models/Wan2.1-I2V-14B-480P/gguf/wan2.1-i2v-14b-480p-Q4_K_M.gguf"))
        lora_rel = cfg.get("wan_lora_file")
        lora_path = str(ROOT / lora_rel) if lora_rel else None
        negative = cfg.get("wan_negative_prompt", WAN_NEGATIVE_PROMPT)
        prompt_pairs = [
            ((prompt_by_segment.get(s["segment_index"]) or s.get("text", "")) + wan_motion, negative)
            for s in selected
        ]
        wan_embeds = _wan_encode_prompts(model_name, prompt_pairs)
        pipe = _get_wan_pipeline_no_text(model_name, gguf_path, cfg.get("wan_flow_shift", 3.0), lora_path)
    elif engine == "ltx-i2v":
        # i2v canlandıracak statik görsel ister; görseli olmayan segmentler elenir
        selected = [s for s in selected if s["segment_index"] in image_by_segment]
        if not selected:
            log.warning("i2v için canlandırılacak statik görsel yok (s04_visuals çalışmamış), atlanıyor")
            return {"skipped": True}
        model_name = _resolve_model_path(cfg.get("model_name", "Lightricks/LTX-Video"))
        negative = cfg.get("negative_prompt", LTX_NEGATIVE_PROMPT)
        prompt_pairs = [
            ((prompt_by_segment.get(s["segment_index"]) or s.get("text", "")) + ltx_motion, negative)
            for s in selected
        ]
        ltx_embeds = _ltx_encode_prompts(model_name, prompt_pairs)
        pipe = _get_ltx_pipeline_no_text(model_name)
    elif engine == "cogvideox-t2v":
        if not selected:
            return {"skipped": True}
        pipe = _get_cogvideox_pipeline(cfg.get("model_name", "THUDM/CogVideoX-2b"))
    else:
        raise ValueError(f"Bilinmeyen video_broll.engine: {engine} (wan-i2v | ltx-i2v | cogvideox-t2v | framepack)")

    from diffusers.utils import export_to_video

    if engine == "wan-i2v":
        fps = cfg.get("wan_fps", 16)  # Wan'ın doğal fps'i 16 — cfg.fps LTX'e ait
    else:
        fps = cfg.get("fps", 24 if engine == "ltx-i2v" else 8)
    out_dir = job_path(job_id, "video_broll")
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = job_path(job_id, "video_broll_manifest.json")
    manifest_out = []
    for n, seg in enumerate(selected):
        idx = seg["segment_index"]
        prompt = prompt_by_segment.get(idx) or seg.get("text", "")
        log.info(f"Video klip {n + 1}/{len(selected)} (segment {idx}, {engine}) üretiliyor: {prompt[:80]}...")
        if engine == "wan-i2v":
            video = _generate_wan(pipe, cfg, wan_embeds[n], image_by_segment[idx])
        elif engine == "ltx-i2v":
            video = _generate_ltx(pipe, cfg, ltx_embeds[n], image_by_segment[idx])
        else:
            video = _generate_cogvideox(pipe, cfg, prompt)
        clip_path = out_dir / f"seg_{idx:03d}.mp4"
        export_to_video(video, str(clip_path), fps=fps)
        manifest_out.append({"segment_index": idx, "video": str(clip_path), "prompt": prompt, "engine": engine})
        # Her klip sonrası diske yaz (bkz. s04_visuals: yarıda hata olursa üretilmiş
        # klipler manifest'siz kalıp boşa gitmesin).
        manifest_file.write_text(json.dumps(manifest_out, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(f"{len(manifest_out)} video klip üretildi -> {out_dir}")
    return {"video_broll_manifest": str(manifest_file), "count": len(manifest_out)}


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
