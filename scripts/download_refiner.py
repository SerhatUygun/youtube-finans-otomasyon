"""SDXL refiner (diffusers formatı) indirme scripti — local_dir modu (bkz. download_ltx.py:
hub cache symlink modu bu makinede WinError 1314 veriyor)."""
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / ".cache" / "huggingface"))

from huggingface_hub import snapshot_download

target = Path(__file__).resolve().parents[1] / "models" / "sdxl-refiner-1.0"
print("İndiriliyor -> ", target)
path = snapshot_download(
    "stabilityai/stable-diffusion-xl-refiner-1.0",
    local_dir=str(target),
    allow_patterns=[
        "model_index.json",
        "unet/*fp16*", "unet/config.json",
        "vae/*fp16*", "vae/config.json",
        "text_encoder_2/*fp16*", "text_encoder_2/config.json",
        "tokenizer_2/*",
        "scheduler/*",
    ],
)
print("DONE", path)
