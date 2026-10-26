"""Wan2.1-I2V-14B-480P indirme scripti (GGUF quantize edilmis transformer ile).

Iki parca indirilir:
  1. Wan-AI/Wan2.1-I2V-14B-480P-Diffusers — pipeline bilesenleri (text_encoder,
     vae, image_encoder, tokenizer, scheduler). transformer/ SAFETENSORS'LARI
     INDIRILMEZ (~28GB bf16); sadece config.json alinir — GGUF yuklemesi
     from_single_file'a config olarak lazim.
  2. city96/Wan2.1-I2V-14B-480P-gguf — Q4_K_M quantize transformer (~9-10GB).
     16GB VRAM'e transformer + CLIP image encoder + VAE birlikte sigsin diye
     Q4_K_M secildi; kalite yetersiz kalirsa Q5_K_S denenebilir (daha buyuk).

local_dir kullaniliyor (hub cache DEGIL): standart hub cache modu sembolik link
olusturmaya calisiyor, bu makinede (Windows, SeCreateSymbolicLinkPrivilege yok)
WinError 1314 ile basarisiz oluyor. local_dir modu symlink kullanmaz.
"""
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / ".cache" / "huggingface"))

from huggingface_hub import hf_hub_download, snapshot_download

target = Path(__file__).resolve().parents[1] / "models" / "Wan2.1-I2V-14B-480P"
print("HF_HOME:", os.environ.get("HF_HOME"))

print("1/2: Diffusers bilesenleri indiriliyor ->", target)
path = snapshot_download(
    "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers",
    local_dir=str(target),
    allow_patterns=[
        "model_index.json",
        "text_encoder/*",
        "tokenizer/*",
        "vae/*",
        "image_encoder/*",
        "image_processor/*",
        "scheduler/*",
        "transformer/config.json",
    ],
)
print("Diffusers bilesenleri OK:", path)

print("2/2: GGUF transformer (Q4_K_M) indiriliyor ->", target / "gguf")
gguf_path = hf_hub_download(
    "city96/Wan2.1-I2V-14B-480P-gguf",
    filename="wan2.1-i2v-14b-480p-Q4_K_M.gguf",
    local_dir=str(target / "gguf"),
)
print("GGUF OK:", gguf_path)
print("DONE")
