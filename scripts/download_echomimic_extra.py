#!/usr/bin/env python
"""EchoMimic V2 EK ağırlıklar — ana BadToBest/EchoMimicV2 snapshot'ında OLMAYAN
temel modeller (infer.yaml/infer_acc.yaml bunları bekler).
Kullanım: python download_echomimic_extra.py <pretrained_weights_dizini>"""
import sys
import urllib.request
from pathlib import Path

base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("vendor/EchoMimicV2/pretrained_weights")
base.mkdir(parents=True, exist_ok=True)

from huggingface_hub import snapshot_download

jobs = [
    ("lambdalabs/sd-image-variations-diffusers", base / "sd-image-variations-diffusers"),
    ("stabilityai/sd-vae-ft-mse", base / "sd-vae-ft-mse"),
    ("facebook/wav2vec2-base-960h", base / "wav2vec2-base-960h"),
]
for repo, dest in jobs:
    dest.mkdir(parents=True, exist_ok=True)
    print(f"[dl] {repo} -> {dest}", flush=True)
    try:
        snapshot_download(repo_id=repo, local_dir=str(dest), local_dir_use_symlinks=False)
    except Exception as e:
        print(f"[dl] UYARI {repo}: {e}", flush=True)

# whisper tiny.pt (audio_processor) — orijinal openai checkpoint
ap = base / "audio_processor"
ap.mkdir(parents=True, exist_ok=True)
tiny = ap / "tiny.pt"
if not tiny.exists():
    url = "https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e/tiny.pt"
    print(f"[dl] whisper tiny.pt -> {tiny}", flush=True)
    try:
        urllib.request.urlretrieve(url, str(tiny))
    except Exception as e:
        print(f"[dl] UYARI tiny.pt: {e}", flush=True)

print("[dl] EchoMimic ek ağırlıklar tamam")
