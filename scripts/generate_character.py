"""AI-üretimi TUTARLI sunucu karakteri üretir (foto-gerçekçi, telifsiz).

Kullanıcı gerçek yüz yerine AI-üretimi tutarlı bir sunucu istedi. Bu script RealVisXL
(Faz 3 checkpoint'i) + SABİT seed ile kanonik bir sunucu portresi üretir — sabit seed
+ sabit prompt aynı yüzü verir (tutarlılık). Çıktı yeşil-ekran hazırlığına (Faz 7)
verilebilecek düz arka planlı bir portredir.

Akış:
  python scripts/generate_character.py            # assets/avatar/character_raw.png üretir
  python scripts/prepare_avatar_photo.py          # -> yeşil ekran photo.png (chroma key için)

Not: pipeline.stages.s04_visuals._get_pipeline yeniden kullanılır (aynı yükleme/VAE ayarı).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Tutarlı, foto-gerçekçi, YEŞİL-EKRAN'a hazır (düz açık arka plan -> rembg temiz keser) sunucu.
CHARACTER_PROMPT = (
    "photorealistic portrait of a friendly professional TV presenter, warm confident smile, "
    "upper body, facing camera, business casual outfit, clean solid light gray studio background, "
    "soft even studio lighting, sharp focus, natural skin texture, high detail, 8k, dslr photo"
)
CHARACTER_NEGATIVE = (
    "cartoon, anime, 3d render, cgi, illustration, painting, deformed, distorted, disfigured, "
    "mutated, extra limbs, extra fingers, bad hands, bad anatomy, low quality, worst quality, "
    "blurry, jpeg artifacts, text, watermark, logo, multiple people, busy background, cluttered"
)
DEFAULT_SEED = 776655  # tutarlılık için sabit — aynı seed = aynı yüz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--steps", type=int, default=45)
    ap.add_argument("--out", default=str(ROOT / "assets" / "avatar" / "character_raw.png"))
    # Portre oranı (sunucu üst gövde). SDXL portre kovası: 832x1216.
    ap.add_argument("--width", type=int, default=832)
    ap.add_argument("--height", type=int, default=1216)
    args = ap.parse_args()

    import torch
    from pipeline.stages import s04_visuals as s04

    pipe = s04._get_pipeline("sdxl", "models/RealVisXL_V4.0")
    gen = torch.Generator(device="cuda").manual_seed(args.seed)
    print(f"Karakter üretiliyor (seed={args.seed}, {args.width}x{args.height}, {args.steps} adım)...")
    img = pipe(
        prompt=CHARACTER_PROMPT, negative_prompt=CHARACTER_NEGATIVE,
        num_inference_steps=args.steps, guidance_scale=7.0,
        width=args.width, height=args.height, generator=gen,
    ).images[0]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"DONE -> {out}")
    print("Sonraki adım: python scripts/prepare_avatar_photo.py  (yeşil ekran + photo.png)")


if __name__ == "__main__":
    main()
