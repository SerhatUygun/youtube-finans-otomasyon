"""17-18 Eyl standalone test: Wan2.1-VACE-1.3B gerçekten bu makinede (16GB RAM) çalışıyor mu?
SIFIR_MALIYET_PROFESYONEL_EDIT_GELISTIRME_REHBERI.md'nin "Wan 2.1 1.3B (I2V)" önerisi -- böyle
bir model YOK (sadece T2V-1.3B ve VACE-1.3B var, ikisi de doğrulandı), en yakın gerçek karşılığı
VACE-1.3B (first-frame conditioning ile görsel canlandırma, Apache 2.0, ~8GB VRAM iddiası).
Orchestrator'a bağlamadan ÖNCE burada tek başına doğrulanıyor (14B'nin RAM'de öldüğü tecrübe edildi).

Kullanım: .venv/Scripts/python.exe scripts/run_wan_vace_test.py --image <png> --out <mp4>
"""
import argparse
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", default="output/_wan_vace_test/test.mp4")
    ap.add_argument("--prompt", default="cinematic slow motion, subtle camera drift, photorealistic")
    ap.add_argument("--frames", type=int, default=41)  # ~2.5s @ 16fps, kısa smoke test
    args = ap.parse_args()

    from pathlib import Path
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Model indiriliyor/yükleniyor: Wan-AI/Wan2.1-VACE-1.3B ...", flush=True)
    import torch
    from diffusers import AutoencoderKLWan, WanVACEPipeline
    from diffusers.utils import export_to_video, load_image

    model_id = "Wan-AI/Wan2.1-VACE-1.3B-diffusers"
    vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanVACEPipeline.from_pretrained(model_id, vae=vae, torch_dtype=torch.bfloat16)
    pipe.to("cuda")
    print(f"[{time.strftime('%H:%M:%S')}] Model yüklendi ({time.time() - t0:.1f}s), üretim başlıyor ...", flush=True)

    image = load_image(args.image)
    w, h = image.size
    # VACE 480P civarında eğitilmiş; en-boy oranını koruyup en yakın 16'ya yuvarla.
    max_area = 832 * 480
    aspect = h / w
    out_w = round((max_area / aspect) ** 0.5 / 16) * 16
    out_h = round((max_area * aspect) ** 0.5 / 16) * 16
    image = image.resize((out_w, out_h))

    t1 = time.time()
    result = pipe(
        prompt=args.prompt,
        reference_images=[image],
        height=out_h, width=out_w,
        num_frames=args.frames,
        guidance_scale=5.0,
        num_inference_steps=20,
    )
    print(f"[{time.strftime('%H:%M:%S')}] Üretim bitti ({time.time() - t1:.1f}s)", flush=True)
    export_to_video(result.frames[0], args.out, fps=16)
    print(f"[{time.strftime('%H:%M:%S')}] Yazıldı: {args.out} (toplam {time.time() - t0:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
