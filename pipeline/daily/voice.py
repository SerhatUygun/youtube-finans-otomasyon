"""Tutarlı ses: tüm segmentler (uzun video + Reels) TEK VoxCPM çağrısında (model bir kez yüklenir),
temiz istem klibiyle "devam" modunda, sabit tohumla ve ses kapısıyla (aykırı perde/tınıyı yeniden üret) sentezlenir.

27 Eyl ölçümü (tools/voice_consistency.py): cümle cümle eski ayar perde std 2,75 yarıton / maks 6,2;
devam modu + 2-3 cümlelik paragraf segmentleri (20-45 kelime): std 0,56 / maks 0,9, tını cv %5,6.
Asıl kazanç paragraf uzunluğundan — kısa tek cümleyi model "vurgulu sunucu" tonunda (ince/parlak) okuyor.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pipeline.utils.config import load_config
from pipeline.utils.paths import ROOT


def synth(items: list[dict], log_file: Path, report_file: Path) -> dict:
    """items: [{"text": tts, "out": wav yolu}] -> run_voxcpm.py --gate. Dönen: kapı raporu."""
    cfg = load_config()["tts"]
    d = load_config().get("daily", {}).get("voice", {})
    venv = (ROOT / cfg.get("voxcpm_venv_python", "vendor/VoxCPM/.venv/Scripts/python.exe")).resolve()
    prompt = (ROOT / d.get("prompt_wav", "assets/voice_reference/prompt_clean.wav")).resolve()
    manifest = log_file.with_name("_voice_manifest.json")
    manifest.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    cmd = [str(venv), str(ROOT / "scripts" / "run_voxcpm.py"),
           "--ref", str(prompt), "--prompt-wav", str(prompt), "--ref-text", d["prompt_text"],
           "--seed", str(d.get("seed", 1234)), "--cfg", str(d.get("cfg", 2.0)), "--steps", str(d.get("steps", 10)),
           "--model", cfg.get("voxcpm_model", "openbmb/VoxCPM2"), "--batch-manifest", str(manifest),
           "--gate", "--gate-semitones", str(d.get("gate_semitones", 1.8)), "--gate-timbre", str(d.get("gate_timbre", 0.22)),
           "--gate-retries", str(d.get("gate_retries", 2)), "--gate-report", str(report_file)]
    with open(log_file, "w", encoding="utf-8") as lf:
        r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(ROOT))
    if r.returncode != 0:
        raise RuntimeError(f"VoxCPM başarısız (kod {r.returncode}), log: {log_file}")
    return json.loads(report_file.read_text(encoding="utf-8"))
