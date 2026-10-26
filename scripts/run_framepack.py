"""FramePack ile statik görselden UZUN video üretir (bağımsız araç).

FramePack'in İZOLE venv'inde çalıştırılır (diffusers'ın RESMİ FramePack pipeline'ını kullanır —
lllyasviel repo'sunun kararsız iç API'si yerine). SABİT ~6GB VRAM: 1 sn de 60 sn de aynı belleği
kullanır, böylece 16GB'da uzun klip üretilebilir (LTX/Wan uzunluk sınırını çözer).

Çalıştırma (FramePack venv ile):
  vendor/FramePack/.venv/Scripts/python.exe scripts/run_framepack.py \
      --image assets/avatar/character_raw.png --prompt "gentle camera drift, subtle motion" \
      --seconds 5 --out output/_fptest/clip.mp4

NOT: İlk çalıştırmada HunyuanVideo tabanı + FramePack transformer + Siglip iner (~30GB).
"""
import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="Canlandırılacak statik görsel (png/jpg)")
    ap.add_argument("--prompt", required=True, help="Hareket/sahne tarifi")
    ap.add_argument("--out", required=True, help="Çıkış mp4")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--guidance", type=float, default=10.0)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=544)
    args = ap.parse_args()

    try:
        import torch
        from diffusers import HunyuanVideoFramepackPipeline, HunyuanVideoFramepackTransformer3DModel
        from diffusers.utils import export_to_video, load_image
        from transformers import SiglipImageProcessor, SiglipVisionModel
    except Exception as e:
        sys.exit(
            f"Import hatası: {e}\nBu script FramePack venv'inde ve GÜNCEL diffusers ile çalışır "
            "(setup_framepack.ps1 diffusers'ı yükseltir). 'HunyuanVideoFramepack' yoksa: "
            "pip install -U diffusers transformers accelerate"
        )

    print("FramePack modelleri yükleniyor (ilk sefer ~30GB iner) ...")
    transformer = HunyuanVideoFramepackTransformer3DModel.from_pretrained(
        "lllyasviel/FramePackI2V_HY", torch_dtype=torch.bfloat16
    )
    feature_extractor = SiglipImageProcessor.from_pretrained(
        "lllyasviel/flux_redux_bfl", subfolder="feature_extractor"
    )
    image_encoder = SiglipVisionModel.from_pretrained(
        "lllyasviel/flux_redux_bfl", subfolder="image_encoder", torch_dtype=torch.float16
    )
    pipe = HunyuanVideoFramepackPipeline.from_pretrained(
        "hunyuanvideo-community/HunyuanVideo",
        transformer=transformer,
        feature_extractor=feature_extractor,
        image_encoder=image_encoder,
        torch_dtype=torch.float16,
    )
    # 16GB kalibrasyonu: VAE tiling + cpu offload (FramePack'in düşük-VRAM vaadi bunlarla gelir).
    pipe.vae.enable_tiling()
    pipe.enable_model_cpu_offload()

    image = load_image(args.image)
    # FramePack ~30fps; num_frames latent pencere formülüne göre en yakın uygun değere yuvarlanır.
    num_frames = max(int(round(args.seconds * args.fps)), 1)
    num_frames = ((num_frames - 1) // 4) * 4 + 1  # (n-1) % 4 == 0 güvenli varsayım

    print(f"Üretiliyor: {args.seconds}s (~{num_frames} kare) {args.width}x{args.height} ...")
    output = pipe(
        image=image,
        prompt=args.prompt,
        height=args.height,
        width=args.width,
        num_frames=num_frames,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        sampling_type="inverted_anti_drifting",
    ).frames[0]

    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(output, str(out), fps=args.fps)
    print(f"DONE -> {out}")


if __name__ == "__main__":
    main()
