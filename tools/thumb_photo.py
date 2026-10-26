"""3 Eki: Kapaklar için foto-gerçekçi arka plan (RealVisXL, yerel, sıfır maliyet).

thumb.json'daki her `object` kapağı için 1344x768 dramatik ürün fotoğrafı üretir ve
remotion/public/auto/<job>/thumb_bg_<K>.png'ye yazar; ThumbPro `bg` alanı görünce PhotoThumb çizer.
Claude isterse spec'e İngilizce `photo` prompt'u yazar; yoksa nesneye göre hazır prompt kullanılır.
Ayrı süreçte çalıştırılır (VRAM iş bitince tamamen boşalsın):
    python -X utf8 tools/thumb_photo.py <job_dir> [--keys A,C]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STYLE = ("professional financial news photography, dramatic cinematic lighting, shallow depth of field, "
         "high contrast, ultra detailed, 8k, sharp focus, dark moody background, subject on the right side of frame")
NEG = ("text, letters, watermark, logo, words, numbers, people, face, hands, cartoon, illustration, 3d render, cgi, "
       "blurry, lowres, deformed, oversaturated")
# dir: down -> kriz/çöküş havası, up -> yükseliş/parlaklık
OBJ = {
    "gold": {"down": "stack of real gold bullion bars on a dark wooden table, cracked, red warning light glow, smoke",
             "up": "pile of shiny gold bullion bars and gold coins glowing, warm golden light rays, sparks"},
    "silver": {"down": "stack of silver bullion bars on dark table, cold blue and red light, dust",
               "up": "pile of shiny silver bars and silver coins, bright rim light, sparkles"},
    "oil": {"down": "rusty crude oil barrel leaking black oil, red emergency light, smoke, refinery at night",
            "up": "crude oil barrels with fire and flames behind, oil refinery at night, orange glow"},
    "dollar": {"down": "pile of US dollar banknotes burning at the edges, embers, dark background",
               "up": "huge stack of US hundred dollar bills, green light glow, money flying"},
    "lira": {"down": "Turkish lira banknotes burning, embers and ash, dark table, red light",
             "up": "stack of Turkish lira banknotes, warm light, money flying"},
    "bist": {"down": "stock exchange trading screen with red falling numbers, blurred trading floor, red light",
             "up": "stock exchange trading screen with green rising numbers, blurred trading floor, green light"},
    "btc": {"down": "physical bitcoin coin cracked in half on dark surface, red light, smoke",
            "up": "golden physical bitcoin coin glowing, rocket sparks, dark background"},
}


def prompt_for(spec: dict) -> str:
    d = spec.get("dir", "down")
    base = spec.get("photo") or OBJ.get(spec.get("object", "gold"), OBJ["gold"]).get(d, OBJ["gold"]["down"])
    return f"{base}, {STYLE}"


def main(job_dir: Path, keys: list[str] | None = None) -> dict:
    import torch
    from pipeline.stages.s04_visuals import _get_pipeline
    from pipeline.utils.config import load_config

    thumb = json.loads((job_dir / "thumb.json").read_text(encoding="utf-8"))
    vcfg = load_config().get("visuals", {})
    out_dir = ROOT / "remotion" / "public" / "auto" / job_dir.name
    out_dir.mkdir(parents=True, exist_ok=True)
    pipe = _get_pipeline(vcfg.get("engine", "sdxl"), vcfg.get("model_name", "models/RealVisXL_V4.0"))
    done = {}
    for k, spec in thumb.items():
        if keys and k not in keys:
            continue
        if spec.get("style") not in ("object", "face", "photo"):
            continue
        g = torch.Generator("cuda").manual_seed(1000 + ord(k[0]))
        img = pipe(prompt=prompt_for(spec), negative_prompt=NEG, width=1344, height=768,
                   num_inference_steps=int(vcfg.get("num_inference_steps", 40)),
                   guidance_scale=float(vcfg.get("guidance_scale", 7.0)), generator=g).images[0]
        p = out_dir / f"thumb_bg_{k}.png"
        img.save(p)
        done[k] = f"auto/{job_dir.name}/thumb_bg_{k}.png"
        print(f"kapak arka planı: {k} -> {p}", flush=True)
    (job_dir / "_raw").mkdir(exist_ok=True)
    (job_dir / "_raw" / "thumb_bg.json").write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    return done


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir")
    ap.add_argument("--keys")
    a = ap.parse_args()
    main(Path(a.job_dir).resolve(), a.keys.split(",") if a.keys else None)
