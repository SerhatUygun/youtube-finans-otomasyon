"""Ajan 6 — Denetçi (17 Eki; LLM'SİZ, hafif — günlük koşu sırasında da güvenle çalışır).

Diğer ajanların çıktılarını denetler: bayat mı, boş bölüm var mı, model artığı/uydurma izi var mı, döngüde tekrarlayan hata var mı.
Rakam denetimi: trend_brief.md'deki "N/gün" değerleri trend_brief.json ham verisinde yoksa uydurma sayılır.
Çıktı: output/_agents/audit.json + output/_brain/audit.md (panel + Claude okur); ciddi sorunda alerts.jsonl.

  python tools/agents/qa_auditor.py
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime

from common import OUT, ROOT, alert, log, read_json, write_json

AGENT = "denetci"
BRAIN = ROOT / "output" / "_brain"
AUDIT = OUT / "audit.json"


def age_h(p) -> float | None:
    return (time.time() - p.stat().st_mtime) / 3600 if p.exists() else None


def md_sections(txt: str) -> dict[str, str]:
    out, cur = {}, None
    for ln in txt.splitlines():
        if ln.startswith("## "):
            cur = ln[3:].strip()
            out[cur] = ""
        elif cur:
            out[cur] += ln.strip()
    return out


def check_md(name: str, p, max_age_h: float, issues: list, score: dict) -> str:
    a = age_h(p)
    if a is None:
        issues.append({"ajan": name, "seviye": "hata", "sorun": f"{p.name} yok"})
        score[name] = 0
        return ""
    pts = 100
    if a > max_age_h:
        issues.append({"ajan": name, "seviye": "uyari", "sorun": f"bayat: {a:.1f} saat (sınır {max_age_h})"})
        pts -= 30
    txt = p.read_text(encoding="utf-8")
    empty = [k for k, v in md_sections(txt).items() if not v]
    if empty:
        issues.append({"ajan": name, "seviye": "hata" if len(empty) > 2 else "uyari", "sorun": f"boş bölüm: {', '.join(empty)}"})
        pts -= 12 * len(empty)
    if re.search(r'”\]|"\]|\]\s*,?\s*$|\{\s*"', txt, re.M):
        issues.append({"ajan": name, "seviye": "uyari", "sorun": "JSON/model artığı var"})
        pts -= 10
    if "(sentez yok)" in txt:
        issues.append({"ajan": name, "seviye": "hata", "sorun": "LLM sentezi yok"})
        pts -= 40
    n_bad = txt.count("kanıt doğrulanamadı") + txt.count("uydurma yıl")
    if n_bad:
        issues.append({"ajan": name, "seviye": "uyari", "sorun": f"{n_bad} madde doğrulanamadı/uydurma"})
        pts -= 5 * n_bad
    score[name] = max(pts, 0)
    return txt


def main() -> int:
    issues: list[dict] = []
    score: dict[str, int] = {}

    # trend: md + ham veri rakam denetimi
    ttxt = check_md("trend", BRAIN / "trend_brief.md", 7, issues, score)
    tj = read_json(OUT / "trend_brief.json", {})
    real = {str(v.get("views_per_day")) for v in (tj.get("ham") or {}).get("videos", [])}
    fake = [n for n in re.findall(r"(\d+)/gün", ttxt) if n not in real]
    if fake:
        issues.append({"ajan": "trend", "seviye": "hata", "sorun": f"ham veride olmayan izlenme/gün: {', '.join(fake[:5])}"})
        score["trend"] = max(score.get("trend", 0) - 30, 0)

    # editör: bugünün/dünün notu
    notes = sorted((OUT / "editor_notes").glob("*.md"))
    if notes:
        check_md("editor", notes[-1], 30, issues, score)
    else:
        issues.append({"ajan": "editor", "seviye": "hata", "sorun": "hiç editör notu yok"})

    # haber
    mb = read_json(OUT / "morning_brief.json", {})
    pts = 100
    a = age_h(OUT / "morning_brief.json")
    if a is None or a > 3:
        issues.append({"ajan": "haber", "seviye": "uyari", "sorun": f"morning_brief bayat ({a and round(a, 1)} saat)"})
        pts -= 30
    top = mb.get("top") or []
    if len(top) < 8:
        issues.append({"ajan": "haber", "seviye": "uyari", "sorun": f"yalnız {len(top)} önemli haber"})
        pts -= 20
    if sum(1 for x in top if not x.get("ozet")) > 3:
        issues.append({"ajan": "haber", "seviye": "uyari", "sorun": "özetsiz haber çok (puanlama eksik)"})
        pts -= 15
    bad_ang = [x.get("baslik_fikri") for x in mb.get("angles", []) if "DOĞRULANAMAYAN" in str(x.get("dogrulama", ""))]
    if bad_ang:
        issues.append({"ajan": "haber", "seviye": "uyari", "sorun": f"{len(bad_ang)} açıda doğrulanamayan rakam"})
        pts -= 10 * len(bad_ang)
    score["haber"] = max(pts, 0)

    # döngü + tekrarlayan hatalar
    ls = read_json(OUT / "loop_state.json", {})
    for k, t in (ls.get("tasks") or {}).items():
        if t.get("last_code") not in (0, None):
            issues.append({"ajan": k, "seviye": "hata", "sorun": f"son kod {t.get('last_code')}: {str(t.get('last_msg'))[:100]}"})
    try:
        recent = [json.loads(x) for x in (OUT / "alerts.jsonl").read_text(encoding="utf-8").splitlines()[-60:]]
        errs: dict[str, int] = {}
        for r in recent:
            if r.get("level") == "hata" and r.get("agent") != AGENT:
                errs[r["agent"]] = errs.get(r["agent"], 0) + 1
        for ag, n in errs.items():
            if n >= 3:
                issues.append({"ajan": ag, "seviye": "hata", "sorun": f"son uyarılarda {n} kez hata (tekrarlayan)"})
    except OSError:
        pass

    now = datetime.now().isoformat(timespec="minutes")
    prev = read_json(AUDIT, {})
    write_json(AUDIT, {"at": now, "puan": score, "sorunlar": issues})
    md = [f"# Denetim — {now}", "", "Puan (100 = temiz): " + " · ".join(f"{k} {v}" for k, v in score.items()), ""]
    md += [f"- [{i['seviye']}] **{i['ajan']}**: {i['sorun']}" for i in issues] or ["- sorun yok"]
    (BRAIN / "audit.md").write_text("\n".join(md), encoding="utf-8")
    # yalnız YENİ ciddi sorunları uyar (her turda aynısını tekrarlama)
    old = {(i["ajan"], i["sorun"]) for i in prev.get("sorunlar", [])}
    for i in issues:
        if i["seviye"] == "hata" and (i["ajan"], i["sorun"]) not in old:
            alert(AGENT, "hata", f"{i['ajan']}: {i['sorun']}")
    log(AGENT, f"denetim: {len(issues)} sorun · " + " ".join(f"{k}={v}" for k, v in score.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
