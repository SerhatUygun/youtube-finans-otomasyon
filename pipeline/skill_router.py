"""Beyin SKILL sistemi — konuya göre ALAN UZMANLIĞI paketleri.

persona genel bir kişilik; ama finans/bilim/tarih gibi alanların kendine özgü
anlatım kuralları, terminolojisi, örnekleme biçimi ve tercih edilen görsel stili var.
Bir "skill" = bir alan için { anahtar kelimeler, üretim rehberliği, tercih edilen
görsel karakter, araştırma ipuçları, critic odağı }. Konu bir skill'e eşleşince o
skill'in rehberliği üretim prompt'una enjekte edilir -> beyin o alanda "uzmanlaşır".

Kullanıcı/panel yeni skill ekleyebilir (skills.json). Dosya yoksa DEFAULT_SKILLS kullanılır
-> kurulum olmadan bugünkü davranış korunur (skill eşleşmezse enjeksiyon "" olur).

Tamamen yerel, sıfır maliyet. `persona._skill_context` bunu prompt'a ekler.
"""
import json
import re

from pipeline.utils.paths import ROOT
from pipeline.utils.logging import get_logger

log = get_logger("skill_router")

SKILLS_FILE = ROOT / "skills.json"

# Politika uyumu korunur: rehberlik "uzman personası" DEĞİL, iyi anlatım kuralları verir.
DEFAULT_SKILLS = [
    {
        "id": "finance",
        "name": "Finans / Ekonomi",
        "enabled": True,
        "keywords": ["finance", "financial", "para", "money", "ekonomi", "economy",
                     "enflasyon", "inflation", "faiz", "interest", "tasarruf", "savings",
                     "yatirim", "invest", "borsa", "stock", "hisse", "kredi", "credit",
                     "banka", "bank", "butce", "budget", "vergi", "tax", "emeklilik",
                     "retirement", "kripto", "crypto", "bilesik", "compound", "gdp",
                     "fon", "fund", "etf", "gelir", "income", "mortgage"],
        "guidance": (
            "FINANCE SKILL: 3rd-person documentary storytelling ONLY (no 'I'/'we'/'ben'). "
            "Synthesize breaking news and market data into a gripping narrative arc. Translate every abstract "
            "figure into everyday money the viewer feels (e.g. 'a 3% price rise means a 100 TL basket now costs 103 TL'). "
            "Connect the dots between institutional actions (central banks/governments) and real-life household consequences. "
            "Attribute every number to its source. No jargon without an immediate intuitive real-world analogy."
        ),
        "visual_character_id": "belgesel-sinematik",
        "research_queries": ["latest official data", "statistics report"],
        "critic_focus": ["clarity", "factual_grounding"],
    },
    {
        "id": "science",
        "name": "Bilim / Teknoloji",
        "enabled": True,
        "keywords": ["bilim", "science", "scientific", "teknoloji", "technology", "uzay",
                     "space", "fizik", "physics", "biyoloji", "biology", "kimya", "chemistry",
                     "evren", "universe", "quantum", "kuantum", "dna", "gen", "gene"],
        "guidance": (
            "SCIENCE SKILL: Open with the counter-intuitive 'wow' fact. Explain ONE mechanism with a "
            "simple everyday analogy. Build from concrete to abstract, one idea per sentence. Attribute "
            "claims to research/consensus, avoid overclaiming certainty. End with why it matters."
        ),
        "visual_character_id": "belgesel-sinematik",
        "research_queries": ["recent study", "how it works explained"],
        "critic_focus": ["hook_strength", "clarity"],
    },
    {
        "id": "history",
        "name": "Tarih",
        "enabled": True,
        "keywords": ["tarih", "history", "historical", "savas", "war", "empire", "imparatorluk",
                     "medeniyet", "civilization", "antik", "ancient", "osmanli", "ottoman"],
        "guidance": (
            "HISTORY SKILL: Anchor to specific dates, places and named figures. Tell it as a narrative "
            "with cause-and-effect, not a list. One vivid concrete detail per segment. Attribute to "
            "historical sources; distinguish established fact from interpretation. Neutral, no modern "
            "political judgement."
        ),
        "visual_character_id": "belgesel-sinematik",
        "research_queries": ["history facts", "what happened"],
        "critic_focus": ["completeness", "factual_grounding"],
    },
]


def _match_keywords(topic: str, keywords: list[str]) -> int:
    t = (topic or "").lower()
    score = 0
    for kw in keywords or []:
        if kw and re.search(r"\b" + re.escape(kw.lower()), t):
            score += 1
    return score


def load_skills() -> list[dict]:
    skills = DEFAULT_SKILLS
    if SKILLS_FILE.exists():
        try:
            data = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                skills = data
            elif isinstance(data, dict) and isinstance(data.get("skills"), list):
                skills = data["skills"]
        except Exception:
            log.warning("skills.json okunamadı, varsayılan skill'ler kullanılıyor")
    return [s for s in skills if s.get("enabled", True)]


def save_skills(payload) -> list[dict]:
    skills = payload.get("skills") if isinstance(payload, dict) else payload
    if not isinstance(skills, list):
        raise ValueError("skills bir liste olmalı")
    cleaned = []
    for s in skills:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        cleaned.append({
            "id": s["id"],
            "name": s.get("name", s["id"]),
            "enabled": bool(s.get("enabled", True)),
            "keywords": [str(k).strip().lower() for k in (s.get("keywords") or []) if str(k).strip()],
            "guidance": str(s.get("guidance", "")).strip(),
            "visual_character_id": s.get("visual_character_id") or "",
            "research_queries": [str(q).strip() for q in (s.get("research_queries") or []) if str(q).strip()],
            "critic_focus": [str(c).strip() for c in (s.get("critic_focus") or []) if str(c).strip()],
        })
    SKILLS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def match_skill(topic: str) -> dict | None:
    """Konuya en çok örtüşen (enabled) skill'i döndürür; eşleşme yoksa None."""
    best, best_score = None, 0
    for s in load_skills():
        score = _match_keywords(topic, s.get("keywords") or [])
        if score > best_score:
            best, best_score = s, score
    return best


def skill_guidance(topic: str) -> str:
    """Üretim prompt'una eklenecek skill rehberlik bloğu (eşleşme yoksa '')."""
    s = match_skill(topic)
    if not s or not s.get("guidance"):
        return ""
    return f"\n\n{s['guidance']}\n"


def preferred_character(topic: str) -> str | None:
    """Konuya eşleşen skill'in tercih ettiği görsel karakter id'si (yoksa None)."""
    s = match_skill(topic)
    return (s.get("visual_character_id") or None) if s else None
