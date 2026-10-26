"""Beynin ÖĞRENME katmanı — birikmiş iyi örneklerden ve refleksiyonlardan besleme.

İki mekanizma (ikisi de sıfır maliyet, fine-tune YOK):
  (A) few-shot: en yüksek critic skorlu örnek(ler) üretim prompt'una "mükemmel örnek"
      olarak enjekte edilir -> beyin kendi en iyi işini taklit eder.
  (B) learned_guidance: tools/brain_reflect.py'nin skorlardan çıkardığı additive
      ipuçları (learned_guidance.txt) üretim prompt'una eklenir.

TASARIM GÜVENLİĞİ: _brain/ boşsa TÜM fonksiyonlar boş döner ve üretim davranışı
bugünküyle BİREBİR aynı kalır (no-op fallback).
"""
import json
from pathlib import Path

from pipeline.utils.paths import OUTPUT_DIR
from pipeline.utils.logging import get_logger

log = get_logger("brain_learn")

BRAIN_DIR = OUTPUT_DIR / "_brain"
LEADERBOARD = BRAIN_DIR / "leaderboard.json"
LEARNED_GUIDANCE = BRAIN_DIR / "learned_guidance.txt"
# GERÇEK performans kılavuzu — tools/pull_analytics.py yazar (YouTube Analytics'ten türetilmiş).
# Yoksa no-op (döngü henüz kapatılmamış); varsa üretim prompt'una eklenir.
ANALYTICS_GUIDANCE = BRAIN_DIR / "analytics_guidance.txt"
DATASET = OUTPUT_DIR / "_dataset"


def _read_leaderboard() -> dict:
    if not LEADERBOARD.exists():
        return {}
    try:
        return json.loads(LEADERBOARD.read_text(encoding="utf-8"))
    except Exception:
        return {}


def update_leaderboard(job_id: str, critic: dict) -> None:
    """Bir job'ın critic skorunu skor tablosuna yazar (few-shot seçimi bunu kullanır)."""
    if not job_id or not critic or not critic.get("scored"):
        return
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    board = _read_leaderboard()
    board[job_id] = {
        "overall": critic.get("overall", 0.0),
        "scores": critic.get("scores", {}),
    }
    LEADERBOARD.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")


def learned_guidance() -> str:
    """brain_reflect'in yazdığı additive ipuçları (yoksa '')."""
    if not LEARNED_GUIDANCE.exists():
        return ""
    return LEARNED_GUIDANCE.read_text(encoding="utf-8").strip()


def analytics_guidance() -> str:
    """pull_analytics.py'nin GERÇEK performanstan türettiği kılavuz (yoksa '')."""
    if not ANALYTICS_GUIDANCE.exists():
        return ""
    return ANALYTICS_GUIDANCE.read_text(encoding="utf-8").strip()


def best_exemplars(k: int = 1, min_overall: float = 7.5) -> list[dict]:
    """Skor tablosundaki en yüksek critic skorlu k örneği _dataset'ten okuyup döndürür.
    Her öğe: {"title", "script", "overall"}. Uygun örnek yoksa boş liste."""
    board = _read_leaderboard()
    ranked = sorted(
        ((jid, v.get("overall", 0.0)) for jid, v in board.items()),
        key=lambda x: x[1], reverse=True,
    )
    out = []
    for job_id, overall in ranked:
        if overall < min_overall or len(out) >= k:
            break
        d = DATASET / job_id
        script_f, meta_f = d / "script.json", d / "metadata.json"
        if not script_f.exists():
            continue
        try:
            sj = json.loads(script_f.read_text(encoding="utf-8"))
            title = ""
            if meta_f.exists():
                title = json.loads(meta_f.read_text(encoding="utf-8")).get("title", "")
            script = sj.get("script") or " ".join(sj.get("segments") or [])
            if script:
                out.append({"title": title, "script": script.strip(), "overall": overall})
        except Exception:
            continue
    return out


def prompt_context(k: int = 1) -> str:
    """generate_* prompt'larına eklenecek öğrenme bloğu (learned_guidance + few-shot).
    _brain/ boşsa '' döner (no-op)."""
    parts = []
    lg = learned_guidance()
    if lg:
        parts.append(
            "\n\nLEARNED GUIDANCE (accumulated from grading past videos on THIS channel — apply it):\n"
            + lg
        )
    # GERÇEK performans verisi (YouTube Analytics) — critic'in öz-değerlendirmesinden daha güçlü
    # sinyal; varsa üretime dahil edilir (döngü kapatılmışsa).
    ag = analytics_guidance()
    if ag:
        parts.append("\n\n" + ag)
    try:
        ex = best_exemplars(k=k)
    except Exception:
        ex = []
    if ex:
        blocks = []
        for e in ex:
            head = f"[{e['overall']}/10] {e['title']}".strip()
            blocks.append(f"{head}\n{e['script']}")
        parts.append(
            "\n\nEXCELLENT PAST EXAMPLE for this channel (match this quality/structure, do NOT copy its topic):\n"
            + "\n---\n".join(blocks)
        )
    return "".join(parts)
