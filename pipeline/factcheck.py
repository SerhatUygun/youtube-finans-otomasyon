"""Beynin DOĞRULAMA katmanı — script'teki sayısal/olgusal iddiaları verified-facts'e karşı denetler.

Finans/haber videolarında yanlış rakam = izleyici güveninin ve monetizasyonun en büyük riski
(YouTube yanlış-bilgi + inauthentic politikaları). Bu modül, üretilen script'teki HER sayı,
yüzde, tarih, fiyat ve özel adın gather_facts + market_data'dan gelen DOĞRULANMIŞ verilerle
desteklenip desteklenmediğini qwen3 beyniyle kontrol eder ve desteklenmeyenleri işaretler.

TASARIM GÜVENLİĞİ: facts yoksa veya ollama kapalıysa no-op döner (checked=False, ok=True) —
üretimi ASLA bloklamaz; yalnızca insan-onay kapısı için bir rapor üretir + istenirse 1 düzeltme.

Kullanım:
    from pipeline import factcheck
    rep = factcheck.verify(gen)   # gen: generate_researched_script çıktısı ("segments"+"facts")
    # rep = {"checked": bool, "ok": bool, "flagged": [{"claim","why"}], "count": n, "fix_hint": str}
"""
from __future__ import annotations

import re

from pipeline import persona
from pipeline.utils.logging import get_logger

log = get_logger("factcheck")

# Sayı/veri sinyali — hiç sayısal iddia yoksa (ör. tanım videosu) doğrulamaya gerek yok.
_HAS_DATA = re.compile(r"\d|%|\$|₺|€|yüzde|percent", re.I)


def verify(gen: dict, model: str | None = None) -> dict:
    """Script'teki sayısal iddiaları verified-facts'e karşı doğrular. Desteklenmeyenleri işaretler."""
    facts = (gen.get("facts") or "").strip()
    segments = gen.get("segments") or []
    script_text = gen.get("script") or " ".join(segments)
    result = {"checked": False, "ok": True, "flagged": [], "count": 0, "fix_hint": ""}

    # Doğrulanacak facts yoksa (araştırmasız üretim) veya script'te hiç sayı yoksa: no-op.
    if not facts or not script_text.strip():
        return result
    if not _HAS_DATA.search(script_text):
        result["checked"] = True  # kontrol edildi ama sayısal iddia yok -> temiz
        return result

    p = persona.load_persona()
    mdl = model or p.get("model", persona.DEFAULT_MODEL)
    from datetime import datetime
    today_str = datetime.now().strftime("%d %B %Y")
    prompt = (
        "You are a strict FACT-CHECKER for a finance/news video script.\n\n"
        f"TODAY'S REAL DATE IS {today_str}. The VERIFIED FACTS below were gathered live, TODAY, "
        "from the internet — treat every date in them as real and current, NOT as a future or "
        "implausible date. Your own training knowledge has an earlier cutoff than today; NEVER "
        "flag a claim merely because a date in it is later than what you personally recall — "
        "your only job is comparing the SCRIPT against the VERIFIED FACTS text, not judging "
        "plausibility from memory.\n\n"
        "VERIFIED FACTS (the ONLY allowed source of numbers/dates/names):\n"
        f"{facts}\n\n"
        "SCRIPT TO CHECK:\n"
        f"{script_text}\n\n"
        "TASK: List EVERY specific number, price, percentage, date, or named recent event in the\n"
        "SCRIPT that is NOT directly supported by the VERIFIED FACTS above (invented, altered,\n"
        "rounded differently, or whose meaning was changed — e.g. a forecast stated as a current\n"
        "price, a monthly change called weekly). General/common explanatory knowledge (definitions,\n"
        "how something works) is NOT a violation — only unsupported SPECIFIC FIGURES/EVENTS are.\n\n"
        "Return ONLY JSON: {\"unsupported\": [{\"claim\": \"<the exact claim>\", \"why\": \"<short reason>\"}]}.\n"
        "If everything is supported, return {\"unsupported\": []}."
    )
    try:
        raw = persona._ollama(prompt, mdl)
        data = persona._extract_json(raw) or {}
    except Exception as e:
        log.warning(f"Fact-check çalıştırılamadı (atlanıyor): {e}")
        return result  # ollama kapalı vb. -> no-op, bloklamaz

    flagged = []
    for item in (data.get("unsupported") or []):
        claim = str(item.get("claim", "")).strip()
        why = str(item.get("why", "")).strip()
        if claim:
            flagged.append({"claim": claim, "why": why})

    result["checked"] = True
    result["flagged"] = flagged
    result["count"] = len(flagged)
    result["ok"] = len(flagged) == 0
    if flagged:
        result["fix_hint"] = (
            "Remove or correct these unsupported figures/claims (use ONLY the verified facts; if a "
            "number isn't in the facts, drop it): "
            + " | ".join(f"{f['claim']} ({f['why']})" for f in flagged[:8])
        )
        log.warning(f"Fact-check: {len(flagged)} desteklenmeyen iddia işaretlendi")
    else:
        log.info("Fact-check: tüm sayısal iddialar doğrulanmış verilerle destekli ✓")
    return result


if __name__ == "__main__":
    import json
    import sys

    # Basit manuel test: facts + script'i JSON dosyasından oku.
    if len(sys.argv) > 1:
        gen = json.loads(open(sys.argv[1], encoding="utf-8").read())
    else:
        gen = {
            "facts": "GÜNCEL: Altın bugün 4.132 USD. Gümüş 59,62 USD.",
            "segments": ["Altın bugün 4.132 dolar.", "Gümüş 80 dolara fırladı.", "Altın güvenli limandır."],
            "script": "Altın bugün 4.132 dolar. Gümüş 80 dolara fırladı. Altın güvenli limandır.",
        }
    print(json.dumps(verify(gen), ensure_ascii=False, indent=2))
