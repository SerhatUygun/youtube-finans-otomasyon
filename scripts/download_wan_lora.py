"""Wan2.1-I2V-14B-480P için lightx2v step+CFG distill LoRA indirir.

Bu LoRA (self-forcing / CausVid ailesi) Wan'ı 40 step + CFG yerine 4-6 step,
CFG=1 (guidance kapalı) ile çalıştırır. CFG kapalı olması aktivasyon belleğini
YARIYA indirir (spill'i çözer) ve step başına compute'u da yarılar — 16GB'de
14B kalitesini pratik sürede üretmenin yolu budur.
"""
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[1] / ".cache" / "huggingface"))

from huggingface_hub import hf_hub_download

target = Path(__file__).resolve().parents[1] / "models" / "wan_loras"
print("lightx2v step-distill LoRA indiriliyor ->", target)
path = hf_hub_download(
    "lightx2v/Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v",
    filename="loras/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors",
    local_dir=str(target),
)
print("DONE", path)
