#!/usr/bin/env python
"""CosyVoice2-0.5B model indirici — setup_cosyvoice.ps1 tarafından çağrılır.
Kullanım: python download_cosyvoice.py <hedef_dizin>"""
import sys
from pathlib import Path

dest = sys.argv[1] if len(sys.argv) > 1 else "vendor/CosyVoice/pretrained_models/CosyVoice2-0.5B"
Path(dest).mkdir(parents=True, exist_ok=True)

# Önce ModelScope (resmi kaynak), olmazsa HuggingFace'e düş.
try:
    from modelscope import snapshot_download
    snapshot_download("iic/CosyVoice2-0.5B", local_dir=dest)
    print(f"[download] ModelScope'tan indirildi -> {dest}")
except Exception as e:
    print(f"[download] ModelScope başarısız ({e}); HuggingFace deneniyor...")
    from huggingface_hub import snapshot_download as hf_download
    hf_download(repo_id="FunAudioLLM/CosyVoice2-0.5B", local_dir=dest)
    print(f"[download] HuggingFace'ten indirildi -> {dest}")
