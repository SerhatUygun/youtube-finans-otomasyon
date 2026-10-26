"""27 Temmuz 2026 altın/gümüş + dünya/ekonomi gündemi için TEMELLENDİRİLMİŞ Türkçe
örnek işleri üretir (gerçek, web-araştırmalı verilerle). Her iş için script.json +
metadata.json yazar ve job_id'leri scripts/overnight_jobs.json'a döker.

Sonra `python scripts/overnight_run.py` (detached) bu işleri sırayla videoya çevirir.
"""
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.persona import generate_grounded_script, unload_model  # noqa: E402
from pipeline.utils.paths import OUTPUT_DIR  # noqa: E402


def _slug(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()[:40] or "job"


# --- Gerçek, doğrulanmış veriler (web araştırması, 27 Temmuz 2026) ---
GOLD_SILVER_FACTS = """
- Gold traded around $4,080 per ounce on Monday July 27, 2026 (roughly $4,074-$4,090 across vendors), up about 0.7% on the day from Friday's ~$4,056.
- Silver rose to $59.43 per ounce, up 2.26% from Friday's $58.12 — outperforming gold.
- The gold/silver ratio fell to 68.93 (from 69.73 on Friday), meaning silver gained faster than gold.
- Main driver: safe-haven demand after fighting between the US and Iran paused, easing fears.
- Markets expected the US Federal Reserve to hold interest rates at its July 28-29 meeting; softer June inflation (headline 3.5%) supported the metals.
- Silver was also lifted by strong industrial demand and a sixth straight year of supply deficit.
- Both metals were still well below their record highs from January 2026 (gold near $5,000, silver near $121).
- The next big catalyst was US PCE inflation data due July 30.
""".strip()

WORLD_ECON_FACTS = """
- Biggest story: the United States and Iran paused their airstrikes, with diplomacy pushing to reopen the Strait of Hormuz and de-escalate the war.
- Oil prices plunged about 8-9% on July 27, 2026 as tensions eased (WTI crude down ~8.7% near $82.6, Brent near $96.8) — a major relief for global inflation.
- Gold traded near $4,080 an ounce (up ~0.7%) and silver jumped to $59.43 (up 2.26%).
- The US Federal Reserve's rate decision was due July 29, widely expected to hold rates steady; US inflation stayed elevated (headline 3.5%, core 2.9%).
- US stocks were mixed; the Nasdaq slipped on worries about heavy AI spending, just ahead of Big Tech earnings (Microsoft, Meta, Apple and Amazon all reporting July 29-30).
- In Europe, wildfires forced more than 360,000 people to evacuate across France and Spain during an intense heat wave.
""".strip()

EXAMPLES = [
    {
        "topic": "27 Temmuz 2026 altın ve gümüş piyasası: fiyatlar ve nedenleri",
        "facts": GOLD_SILVER_FACTS,
        "target_words": 150,
    },
    {
        "topic": "27 Temmuz 2026 dünya ve ekonomi gündemi: öne çıkan başlıklar",
        "facts": WORLD_ECON_FACTS,
        "target_words": 160,
    },
    {
        "topic": "Günün piyasa özeti: altın, gümüş ve petrolde son durum (27 Temmuz 2026)",
        "facts": GOLD_SILVER_FACTS + "\n" + WORLD_ECON_FACTS,
        "target_words": 110,
    },
]


def main():
    job_ids = []
    for i, ex in enumerate(EXAMPLES, 1):
        print(f"\n=== Örnek {i}/{len(EXAMPLES)}: {ex['topic']} ===")
        try:
            gen = generate_grounded_script(
                ex["topic"], ex["facts"], language="tr", target_words=ex["target_words"]
            )
        except Exception as e:
            print(f"  HATA (beyin script üretemedi): {e}")
            continue

        job_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{_slug(ex['topic'])}-ex{i}"
        d = OUTPUT_DIR / job_id
        d.mkdir(parents=True, exist_ok=True)
        script_payload = {
            "topic": gen["topic"],
            "script": gen["script"],
            "segments": gen["segments"],
            "visual_prompts": gen["visual_prompts"],
            "language": "tr",
        }
        (d / "script.json").write_text(json.dumps(script_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (d / "metadata.json").write_text(json.dumps(gen["metadata"], ensure_ascii=False, indent=2), encoding="utf-8")
        job_ids.append(job_id)
        print(f"  {len(gen['segments'])} segment | başlık: {gen['metadata']['title']}")
        for seg in gen["segments"]:
            print(f"    • {seg}")

    unload_model()  # VRAM'i serbest bırak — video aşamaları GPU'ya ihtiyaç duyar

    (ROOT / "scripts" / "overnight_jobs.json").write_text(
        json.dumps(job_ids, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n=== {len(job_ids)} iş hazır, overnight_jobs.json yazıldı ===")
    for j in job_ids:
        print(" ", j)


if __name__ == "__main__":
    main()
