"""Beynin REFLEKSİYON adımı — biriken critic skorlarından DERS çıkarır (kapalı döngü).

Öncesinde iyileştirme tamamen insan eliyle (improvement_report.md) yapılıyordu.
Bu araç döngüyü kapatır: critic skorları + tekrar eden sorunlar -> qwen özetler ->
  1) learned_guidance.txt : ≤5 additive ipucu, bir sonraki üretime OTOMATİK enjekte edilir
                            (düşük risk — sadece ekleme yapan yönlendirme),
  2) reflections.md       : ne değişti + neden (insan-okur şeffaflık günlüğü),
  3) persona_suggestions.json : persona'nın hook_style/rules gibi YAPISAL alanları için
                            ÖNERİLER — otomatik UYGULANMAZ, panelde insan onayına bırakılır.

Kullanım:
  python tools/brain_reflect.py [--recent 30]
auto_improve_loop bunu her ~10 iterasyonda bir çağırır (GPU boştayken) -> beyin koşu
sırasında adapte olur. qwen çağrısı sonrası model VRAM'den boşaltılır.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import persona  # noqa: E402
from pipeline.utils.paths import OUTPUT_DIR  # noqa: E402

BRAIN_DIR = OUTPUT_DIR / "_brain"
LEADERBOARD = BRAIN_DIR / "leaderboard.json"
LEARNED_GUIDANCE = BRAIN_DIR / "learned_guidance.txt"
REFLECTIONS = BRAIN_DIR / "reflections.md"
PERSONA_SUGGESTIONS = BRAIN_DIR / "persona_suggestions.json"
DATASET = OUTPUT_DIR / "_dataset"

_DIMS = ["hook_strength", "clarity", "factual_grounding", "originality",
         "policy_tone", "completeness"]


def _load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _aggregate(recent: int) -> dict:
    board = _load_json(LEADERBOARD, {})
    rows = list(board.items())
    if not rows:
        return {}
    # En yeni job_id'ler zaman-damgalı önekli olduğu için ada göre sıralamak ~kronolojik.
    rows = sorted(rows, key=lambda kv: kv[0])[-recent:]
    dim_sum = {d: 0.0 for d in _DIMS}
    dim_cnt = {d: 0 for d in _DIMS}
    overalls = []
    for _jid, v in rows:
        overalls.append(v.get("overall", 0.0))
        for d in _DIMS:
            s = (v.get("scores") or {}).get(d)
            if isinstance(s, (int, float)):
                dim_sum[d] += s
                dim_cnt[d] += 1
    dim_avg = {d: round(dim_sum[d] / dim_cnt[d], 2) for d in _DIMS if dim_cnt[d]}
    # Tekrar eden sorunlar: _dataset/*/critic.json issues (mevcut olanlardan).
    issues = []
    if DATASET.exists():
        for d in sorted(DATASET.iterdir())[-recent:]:
            cj = d / "critic.json"
            if cj.exists():
                issues.extend(_load_json(cj, {}).get("issues") or [])
    return {
        "count": len(rows),
        "overall_avg": round(sum(overalls) / len(overalls), 2) if overalls else 0.0,
        "dim_avg": dim_avg,
        "issues": issues[-40:],
    }


def reflect(recent: int = 30) -> dict:
    agg = _aggregate(recent)
    if not agg:
        print("REFLECT: skor verisi yok (leaderboard boş) — atlanıyor.")
        return {}

    p = persona.load_persona()
    weak = sorted(agg["dim_avg"].items(), key=lambda x: x[1])[:3]
    weak_str = ", ".join(f"{k}={v}" for k, v in weak)
    dim_str = ", ".join(f"{k}={v}" for k, v in agg["dim_avg"].items())
    issue_str = "\n".join(f"- {i}" for i in dict.fromkeys(agg["issues"]))  # tekilleştir, sıra korunur

    prompt = (
        "You are the editorial coach for a YouTube channel's local AI script writer. "
        "Below are the average QUALITY scores (0-10) its scripts received from a strict "
        "critic, plus recurring problems. Diagnose the systematic weaknesses and produce "
        "concrete, channel-specific improvements.\n\n"
        f"Channel niche: {p.get('niche')}\n"
        f"Current hook_style: {p.get('hook_style')}\n"
        f"Current rules: {p.get('rules')}\n\n"
        f"Videos graded: {agg['count']} | overall avg: {agg['overall_avg']}\n"
        f"Per-dimension averages: {dim_str}\n"
        f"Weakest dimensions: {weak_str}\n"
        f"Recurring issues:\n{issue_str or '- (none recorded)'}\n\n"
        "Return ONLY JSON:\n"
        '{"learned_guidance": ["<=5 short imperative tips the writer should ALWAYS follow, '
        'each targeting a weak dimension>"], '
        '"reflection": "2-3 sentences: what is systematically wrong and what you changed", '
        '"persona_suggestions": {"hook_style": "<improved hook_style or empty>", '
        '"rules": "<improved rules or empty>"}}'
    )

    try:
        data = persona._extract_json(persona._ollama(prompt, p.get("model", persona.DEFAULT_MODEL)))
    finally:
        persona.unload_model()  # VRAM'i hemen geri bırak (GPU aşamaları güvenli kalsın)

    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    tips = [str(t).strip() for t in (data.get("learned_guidance") or []) if str(t).strip()][:5]
    reflection = str(data.get("reflection") or "").strip()
    suggestions = data.get("persona_suggestions") or {}
    suggestions = {k: str(v).strip() for k, v in suggestions.items()
                   if k in ("hook_style", "rules") and str(v).strip()}

    if tips:
        LEARNED_GUIDANCE.write_text("\n".join(f"- {t}" for t in tips), encoding="utf-8")

    ts = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
    entry = [f"\n## {ts} UTC — {agg['count']} video, overall {agg['overall_avg']}/10"]
    entry.append(f"- En zayıf: {weak_str}")
    if reflection:
        entry.append(f"- Refleksiyon: {reflection}")
    if tips:
        entry.append("- learned_guidance güncellendi:")
        entry.extend(f"  - {t}" for t in tips)
    if suggestions:
        entry.append("- Persona ÖNERİSİ (uygulanmadı — panelde onay bekliyor): "
                     + "; ".join(f"{k}→{v[:80]}…" for k, v in suggestions.items()))
    with REFLECTIONS.open("a", encoding="utf-8") as f:
        f.write("\n".join(entry) + "\n")

    if suggestions:
        prev = _load_json(PERSONA_SUGGESTIONS, [])
        prev.append({"ts": ts, "based_on": agg["count"], "suggestions": suggestions,
                     "applied": False})
        PERSONA_SUGGESTIONS.write_text(json.dumps(prev, ensure_ascii=False, indent=2),
                                       encoding="utf-8")

    print(f"REFLECT: {agg['count']} video değerlendirildi, overall {agg['overall_avg']}/10 | "
          f"{len(tips)} ipucu yazıldı | {len(suggestions)} persona önerisi (onay bekliyor)")
    return {"tips": tips, "reflection": reflection, "suggestions": suggestions, "agg": agg}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, default=30, help="son N videonun skorunu değerlendir")
    args = ap.parse_args()
    reflect(args.recent)


if __name__ == "__main__":
    main()
