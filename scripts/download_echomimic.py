#!/usr/bin/env python
"""EchoMimic V2 ağırlık indirici — setup_echomimic.ps1 tarafından çağrılır.
BadToBest/EchoMimicV2 deposu tüm gerekli ağırlıkları içerir:
denoising_unet.pth, reference_unet.pth, motion_module.pth, pose_encoder.pth,
sd-vae-ft-mse/, audio_processor/tiny.pt
Kullanım: python download_echomimic.py <pretrained_weights_dizini>"""
import sys
from pathlib import Path

dest = sys.argv[1] if len(sys.argv) > 1 else "vendor/EchoMimicV2/pretrained_weights"
Path(dest).mkdir(parents=True, exist_ok=True)

from huggingface_hub import snapshot_download

snapshot_download(repo_id="BadToBest/EchoMimicV2", local_dir=dest,
                  local_dir_use_symlinks=False)
print(f"[download] EchoMimic V2 ağırlıkları indirildi -> {dest}")
