"""Foto-gerçekçi SDXL checkpoint (RealVisXL V4.0) indirme — diffusers formatı, local_dir modu.

Neden: varsayılan SDXL base + minimal-flat karakteri "sulu boya"/vektör görünüm veriyordu.
RealVisXL foto-gerçekçi bir SDXL fine-tune'u; aynı pipeline (AutoPipelineForText2Image)
ile SIFIR kod değişikliğiyle yüklenir — sadece config.yaml visuals.model_name değişir.

local_dir modu: hub cache symlink'i bu makinede WinError 1314 veriyor (bkz. download_ltx.py).
"""
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / ".cache" / "huggingface"))

from huggingface_hub import list_repo_files, snapshot_download

REPO = "SG161222/RealVisXL_V4.0"
target = Path(__file__).resolve().parents[1] / "models" / "RealVisXL_V4.0"

print(f"Repo dosyaları listeleniyor: {REPO}")
try:
    files = list_repo_files(REPO)
    for f in files:
        print("  ", f)
except Exception as e:
    print("list_repo_files hata:", e)

print(f"\nİndiriliyor -> {target}")
path = snapshot_download(
    REPO,
    local_dir=str(target),
    allow_patterns=[
        "model_index.json",
        "scheduler/*",
        "tokenizer/*", "tokenizer_2/*",
        "text_encoder/*.safetensors", "text_encoder/config.json",
        "text_encoder_2/*.safetensors", "text_encoder_2/config.json",
        "unet/*.safetensors", "unet/config.json",
        "vae/*.safetensors", "vae/config.json",
    ],
)
print("DONE", path)
