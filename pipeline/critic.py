"""Beynin ÖZ-DEĞERLENDİRME katmanı — üretilen script'i render'dan ÖNCE puanlar.

Mevcut hafıza/kalite tanımı çok zayıftı: "render oldu + ≥1 kaynak + 12-120 segment".
Bu modül aynı yerel qwen3 beynini bir JÜRİ (critic) olarak kullanıp script'i bir
RUBRİK'e göre 0-10 puanlar; zayıf çıktılarda döngü/panel tek seferlik hedefli bir
yeniden-üretim yapabilsin diye somut 'fix_hint' üretir.

Tamamen yerel (Ollama), sıfır API maliyeti. Sadece METİN üzerinde çalışır (render'dan
önce, GPU boşaltılmadan) — saniyeler sürer, render süresini domine etmez.

Not: persona._ollama + persona._extract_json yeniden kullanılır (yeni istemci yazılmaz).
"""
from pipeline import persona, policy
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger

log = get_logger("critic")

# Rubrik boyutları (0-10). Ağırlıklar overall hesabında kullanılır.
_DIMENSIONS = {
    "hook_strength": "Does the FIRST sentence stop the scroll? Specific, surprising, no generic wind-up.",
    "clarity": "Plain language, one idea per sentence, a general audience follows easily. No jargon dumps.",
    "factual_grounding": "Specific numbers/dates/names are attributed to sources; nothing sounds invented or hand-wavy.",
    "originality": "No repeated facts, no restating the same point, no empty filler ('an important tool', 'draws attention').",
    "policy_tone": "Neutral informational narrator — NOT posing as an expert/advisor, no buy/sell/treat/vote advice.",
    "completeness": "Actually teaches the topic (what it is, how it works, why it matters, a concrete example).",
}
_WEIGHTS = {
    "hook_strength": 1.4, "clarity": 1.0, "factual_grounding": 1.3,
    "originality": 1.2, "policy_tone": 1.1, "completeness": 1.0,
}


def _brain_cfg() -> dict:
    try:
        return load_config().get("brain") or {}
    except Exception:
        return {}


def threshold() -> float:
    """overall bu eşiğin ALTINDAysa verdict='revise'."""
    try:
        return float(_brain_cfg().get("critic_threshold", 6.5))
    except Exception:
        return 6.5


def _overall(scores: dict) -> float:
    num = den = 0.0
    for k, w in _WEIGHTS.items():
        v = scores.get(k)
        if isinstance(v, (int, float)):
            num += float(v) * w
            den += w
    return round(num / den, 2) if den else 0.0


def score_script(gen: dict, topic: str) -> dict:
    """Bir script.json-benzeri sözlüğü (script/segments/sources/metadata) rubriğe göre puanlar.

    Döner: {"scores": {boyut: 0-10}, "overall": float, "verdict": "pass"|"revise",
            "issues": [str], "fix_hint": str}
    Beyin/ağ hatasında güvenli bir "pass" (nötr) sonuç döner — asla akışı kırmaz.
    """
    p = persona.load_persona()
    segments = gen.get("segments") or []
    script_text = (gen.get("script") or " ".join(segments)).strip()
    meta = gen.get("metadata") or {}
    title = meta.get("title") or gen.get("topic") or topic
    sources = gen.get("sources") or []
    cats = policy.classify_topic(topic, script_text)

    rubric = "\n".join(f"- {k} (0-10): {desc}" for k, desc in _DIMENSIONS.items())
    keys = ", ".join(f'"{k}": int' for k in _DIMENSIONS)
    sensitive_note = ""
    if cats:
        sensitive_note = (
            f"\nThis is a SENSITIVE topic ({', '.join(cats)}). Score policy_tone HARSHLY if the "
            "narrator sounds like an expert/advisor or gives buy/sell/treat/vote advice.\n"
        )

    prompt = (
        "You are a STRICT YouTube script editor for the channel below. Grade the DRAFT "
        "against the rubric. Be critical: a generic hook or any repeated/filler sentence "
        "must lose points. This is a quality gate, not encouragement.\n\n"
        f"Channel niche: {p.get('niche')}\nAudience: {p.get('audience')}\n"
        f"Hook style expected: {p.get('hook_style')}\n"
        f"Number of cited sources: {len(sources)}\n"
        f"{sensitive_note}\n"
        "RUBRIC:\n" + rubric + "\n\n"
        f"DRAFT TITLE: {title}\n\nDRAFT SCRIPT:\n{script_text}\n\n"
        "Return ONLY JSON: {\"scores\": {" + keys + "}, "
        "\"issues\": [\"short concrete problem\", ...], "
        "\"fix_hint\": \"one paragraph of concrete, actionable fixes the writer should apply on a rewrite\"}. "
        "issues: at most 4, each a short phrase. If the draft is strong, issues may be empty."
    )

    try:
        data = persona._extract_json(persona._ollama(prompt, p.get("model", persona.DEFAULT_MODEL)))
    except Exception as e:
        log.warning(f"critic puanlayamadı ({type(e).__name__}: {e}) — nötr pass dönülüyor")
        return {"scores": {}, "overall": 0.0, "verdict": "pass", "issues": [],
                "fix_hint": "", "scored": False}

    raw = data.get("scores") or {}
    scores = {}
    for k in _DIMENSIONS:
        v = raw.get(k)
        if isinstance(v, (int, float)):
            scores[k] = max(0.0, min(10.0, float(v)))
    overall = _overall(scores)
    issues = [str(x).strip() for x in (data.get("issues") or []) if str(x).strip()][:4]
    fix_hint = str(data.get("fix_hint") or "").strip()
    verdict = "revise" if (scores and overall < threshold()) else "pass"
    return {"scores": scores, "overall": overall, "verdict": verdict,
            "issues": issues, "fix_hint": fix_hint, "scored": bool(scores)}
