"""Denetleyici (Reviewer) ajanı -- Editor'ün önerdiği bir motion graphics/edit kararını
RENDER ETMEDEN ÖNCE yerel LLM (Ollama qwen3, aynı persona._ollama deseni) ile kalite
rubriğine göre kritik eder. Amaç: motion-skills/video-skills-toolkit gibi referans
skill kütüphanelerinin savunduğu "tekrarlayan/monoton olmama, gerçek veriye dayanma,
doğru şablon seçimi" kurallarını insan gözetimi olmadan otomatik uygulamak.

Savunmacı: Ollama kapalıysa/timeout olursa/geçersiz JSON dönerse "onaylandı" (approved=True)
döner -- bu kritik ASLA üretimi durduran zorunlu bir kapı değildir, sadece isteğe bağlı bir
iyileştirme turu tetikler (review_loop.run_loop üzerinden)."""
import json

from pipeline.persona import DEFAULT_MODEL, _extract_json, _ollama
from pipeline.utils.logging import get_logger

log = get_logger("agents.reviewer")

RUBRIC = (
    "You are a strict VIDEO MOTION GRAPHICS REVIEWER (denetleyici) for a Turkish "
    "finance YouTube channel. You check a PROPOSED on-screen graphic (not yet rendered) "
    "against this rubric before approving it for render:\n"
    "1. GROUNDING: every number/label/quote must come from the given source text -- "
    "nothing invented or paraphrased.\n"
    "2. VARIETY: it should not repeat the same template or near-identical wording as the "
    "recently approved graphics listed below.\n"
    "3. RELEVANCE: the template must fit the content (one striking number -> StatCallout, "
    "2-3 comparable named values in one sentence -> CompareBars, a real time series -> "
    "MarketChart, a striking standalone claim -> KeyQuote).\n"
    "4. CLARITY: label/title text must be short, concrete Turkish, not vague filler.\n"
    "Be lenient on style, strict on grounding (rule 1) and outright repetition (rule 2).\n"
)


def review_candidate(candidate: dict, source_text: str, recent_choices: list[dict] | None = None,
                      model: str | None = None, timeout: int = 150) -> dict:
    """candidate: {"composition_id": "StatCallout"|"CompareBars"|"MarketChart"|"TitleCard"|...,
    ...props...}. Döner: {"approved": bool, "reason": str, "suggested_fix": str|None}."""
    recent_choices = recent_choices or []
    recent = "\n".join(
        f"- {c.get('composition_id')}: "
        f"{c.get('label') or c.get('title') or c.get('quote') or ''}"
        for c in recent_choices[-5:]
    ) or "(henüz yok)"

    prompt = (
        RUBRIC
        + f"\nBu segmentin gerçek script metni (kaynak):\n{source_text}\n"
        + f"\nBu videoda az önce onaylanan son grafikler:\n{recent}\n"
        + f"\nDeğerlendirilecek aday (JSON):\n{json.dumps(candidate, ensure_ascii=False)}\n"
        + '\nReply ONLY as JSON: {"approved": true|false, "reason": "<short Turkish reason, '
          'max 20 words>", "suggested_fix": "<short Turkish instruction to fix it, or null '
          'if approved>"}'
    )
    try:
        raw = _ollama(prompt, model or DEFAULT_MODEL, timeout=timeout)
        data = _extract_json(raw)
        return {
            "approved": bool(data.get("approved", True)),
            "reason": str(data.get("reason") or "")[:300],
            "suggested_fix": (str(data["suggested_fix"])[:300]
                               if data.get("suggested_fix") else None),
        }
    except Exception as e:
        log.warning(f"Denetleyici çalışmadı (Ollama kapalı/timeout), varsayılan onay: {e}")
        return {"approved": True, "reason": "reviewer-unavailable", "suggested_fix": None}
