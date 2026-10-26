"""Beynin HAFIZASI — daha önce ne ürettiğini hatırlar, tekrarı önler.

Önceki durum: persona.generate_ideas geçmişi hiç görmüyordu -> aynı konuları
(ör. 'credit scores') tekrar tekrar öneriyordu. Bu modül üretilen her videonun
başlığını/konusunu kompakt bir JSONL geçmişte tutar ve:
  - fikir üretimine "bunları zaten yaptın, farklılaş" bağlamı sağlar,
  - yakın-tekrar (keyword örtüşmesi) tespiti yapar.

Harici bağımlılık yok — basit tokenizasyon + Jaccard benzerliği. Tamamen yerel.
"""
import json
import re
import time
from pathlib import Path

from pipeline.utils.paths import OUTPUT_DIR
from pipeline.utils.logging import get_logger

log = get_logger("brain_memory")

BRAIN_DIR = OUTPUT_DIR / "_brain"
HISTORY = BRAIN_DIR / "history.jsonl"
DATASET = OUTPUT_DIR / "_dataset"

# Çok yaygın kelimeler benzerlik/örtüşme sinyali taşımaz — elenir.
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "how",
    "what", "why", "your", "you", "it", "its", "with", "that", "this", "from", "by",
    "as", "at", "be", "do", "does", "actually", "work", "works", "mean", "means",
    "ve", "ile", "bir", "bu", "ne", "nasıl", "nedir", "için", "de", "da",
}


def _keywords(text: str) -> set[str]:
    toks = re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+", (text or "").lower())
    return {t for t in toks if len(t) > 2 and t not in _STOP}


def _iter_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def record(topic: str, title: str, job_id: str, language: str = "en") -> None:
    """Başarılı bir üretimi geçmişe işler (script.json yazıldıktan sonra çağrılır)."""
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "topic": (topic or "").strip(),
        "title": (title or "").strip(),
        "job_id": job_id,
        "language": language,
        "keywords": sorted(_keywords(f"{topic} {title}")),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def recent_titles(n: int = 40) -> list[str]:
    seen, out = set(), []
    for e in reversed(_iter_history()):
        t = (e.get("title") or e.get("topic") or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= n:
            break
    return out


def recent_topics(n: int = 40) -> list[str]:
    seen, out = set(), []
    for e in reversed(_iter_history()):
        t = (e.get("topic") or "").strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= n:
            break
    return out


def is_similar(topic: str, threshold: float = 0.6) -> bool:
    """Konu geçmişteki bir kayda keyword-Jaccard olarak yakınsa True (yakın-tekrar)."""
    kw = _keywords(topic)
    if not kw:
        return False
    for e in _iter_history():
        ek = set(e.get("keywords") or [])
        if not ek:
            continue
        inter = len(kw & ek)
        union = len(kw | ek)
        if union and inter / union >= threshold:
            return True
    return False


def rebuild() -> int:
    """Mevcut output/_dataset/*/metadata.json başlıklarından geçmişi geriye-doldurur.
    Zaten kaydı olan job_id'leri atlar (idempotent). Kaç yeni kayıt eklendiğini döner."""
    if not DATASET.exists():
        return 0
    known = {e.get("job_id") for e in _iter_history()}
    added = 0
    for d in sorted(DATASET.iterdir()):
        if not d.is_dir() or d.name in known:
            continue
        meta_f = d / "metadata.json"
        script_f = d / "script.json"
        title = topic = ""
        try:
            if meta_f.exists():
                title = (json.loads(meta_f.read_text(encoding="utf-8")).get("title") or "").strip()
            if script_f.exists():
                topic = (json.loads(script_f.read_text(encoding="utf-8")).get("topic") or "").strip()
        except Exception:
            pass
        if title or topic:
            record(topic or title, title or topic, d.name)
            added += 1
    if added:
        log.info(f"hafıza geriye-dolduruldu: {added} yeni kayıt (_dataset)")
    return added
