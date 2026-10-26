"""LTX-Video (diffusers formatı) indirme scripti.

Repo kökündeki tek-dosya checkpoint'leri (ComfyUI için, her biri ~6-9GB) İNDİRİLMEZ —
sadece diffusers pipeline'ının kullandığı alt klasörler alınır.

local_dir kullanılıyor (hub cache DEĞİL): standart hub cache modu sembolik link
oluşturmaya çalışıyor, bu makinede (Windows, SeCreateSymbolicLinkPrivilege yok)
WinError 1314 ile başarısız oluyor. local_dir modu symlink kullanmaz.
"""
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / ".cache" / "huggingface"))

from huggingface_hub import snapshot_download

target = Path(__file__).resolve().parents[1] / "models" / "LTX-Video"
print("HF_HOME:", os.environ.get("HF_HOME"))
print("LTX-Video indiriliyor (diffusers alt klasörleri) ->", target)
path = snapshot_download(
    "Lightricks/LTX-Video",
    local_dir=str(target),
    allow_patterns=[
        "model_index.json",
        "transformer/*",
        "vae/*",
        "text_encoder/*",
        "tokenizer/*",
        "scheduler/*",
    ],
)
print("DONE", path)
