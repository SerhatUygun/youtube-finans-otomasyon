"""Ajan 8 — Beyin (18 Eki; yerel qwen3:14b, kendi kurallarını evrimle geliştirir).

Her tur: GÖZLEM (brief'ler + geçmiş başlıklar + hafıza) -> ARAŞTIRMA (modelin seçtiği 2 sorgu: DuckDuckGo + Google News)
-> FİKİR (video fikirleri) -> PUAN (KOD verir, model değil) -> EVRİM (kendi kural listesinde 1 değişiklik dener;
puan ortalaması düşerse geri alır, yükselirse tutar).
Uyku: 11:30-14:30 arası hiçbir şey yapmaz (günlük koşu GPU'yu kullanır).
Sınır: kod değiştiremez, yükleme yapamaz; yalnız output/_brain/brain_* dosyalarını yazar.
Çıktı: output/_brain/brain_brief.md (günlük prompt İLHAM okur), brain_rules.json, brain_memory.jsonl.

  python tools/agents/brain.py [--force]   (--force: uyku saatini yok say)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, time as dtime

from common import OUT, ROOT, llm_json, log, ollama_up, read_json, unload, wait_free, write_json

sys.path.insert(0, str(ROOT))
AGENT = "beyin"
MODEL = "qwen3:14b"
BRAIN = ROOT / "output" / "_brain"
RULES = BRAIN / "brain_rules.json"
MEM = BRAIN / "brain_memory.jsonl"
IDEAS = BRAIN / "brain_ideas.json"
SLEEP = (dtime(11, 30), dtime(14, 30))
SEED_RULES = ["Her fikir izleyicinin cebine (TL, maaş, birikim, gram altın) dokunsun.",
              "Rakamı yalnız VERİ ve ARAŞTIRMA metninden al; yoksa rakamsız yaz.",
              "Son başlıklarımızı tekrar etme; gündemde olup bizde olmayan konuya öncelik ver."]


def rd(p, n=2500) -> str:
    return p.read_text(encoding="utf-8")[:n] if p.exists() else ""


def memory(n=15) -> list[dict]:
    if not MEM.exists():
        return []
    out = []
    for ln in MEM.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def remember(d: dict) -> None:
    with MEM.open("a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")


def research(queries: list[str]) -> list[dict]:
    try:
        from pipeline.research import ddg_search, google_news_rss
    except Exception as e:  # noqa: BLE001
        log(AGENT, f"araştırma modülü yok: {e}")
        return []
    out = []
    for q in queries[:2]:
        for fn in (lambda: google_news_rss(q, language="tr", max_results=5), lambda: ddg_search(q, max_results=4)):
            try:
                for r in fn() or []:
                    out.append({"q": q, "title": r.get("title", ""), "snippet": (r.get("snippet") or r.get("summary") or "")[:300],
                                "url": r.get("url") or r.get("link", "")})
            except Exception:  # noqa: BLE001
                pass
    return out[:16]


def nums(s: str) -> set[str]:
    return {n.replace(".", "").replace(",", "") for n in re.findall(r"\d[\d.,]*", s) if len(n.replace(".", "").replace(",", "")) >= 2}


def score(idea: dict, src: str, ours: list[str], eksik: list[str], heads: list[str]) -> tuple[int, list[str]]:
    """Deterministik puan (0-100) + gerekçe."""
    pts, why = 40, []
    title = str(idea.get("baslik", ""))
    text = title + " " + str(idea.get("neden", ""))
    bad = [n for n in nums(text) if n not in src]
    if bad:
        pts -= 15 * len(bad)
        why.append(f"doğrulanamayan rakam {','.join(sorted(bad))}")
    else:
        pts += 15
    if 35 <= len(title) <= 75:
        pts += 10
    else:
        why.append("başlık uzunluğu kötü")
    if "|" in title or re.search(r"\b20\d\d\b", title):
        pts -= 30
        why.append("haber başlığı kopyası/tarihli")
    tw = set(re.findall(r"\w{4,}", title.lower()))
    if any(len(tw & set(re.findall(r"\w{4,}", h.lower()))) >= 4 for h in heads):
        pts -= 25
        why.append("araştırma başlığına çok benziyor")
    if any(len(tw & set(re.findall(r"\w{4,}", o.lower()))) >= 3 for o in ours):
        pts -= 20
        why.append("bizim son başlığa çok benziyor")
    else:
        pts += 10
    if any(k.split("/")[0] in text.lower() for k in eksik):
        pts += 15
        why.append("eksik konuyu dolduruyor")
    if idea.get("kaynak_no") and str(idea["kaynak_no"]).strip("A").isdigit():
        pts += 10
    else:
        why.append("kaynak yok")
    return max(0, min(100, pts)), why


def main(force: bool) -> int:
    now = datetime.now()
    if not force and SLEEP[0] <= now.time() < SLEEP[1]:
        log(AGENT, "uyku saati (günlük koşu) — düşünmüyorum")
        return 0
    if not ollama_up() or not wait_free(AGENT, max_wait_s=1200):
        log(AGENT, "model/GPU müsait değil")
        return 0
    st = read_json(RULES, {"rules": SEED_RULES, "history": [], "candidate": None})
    ours = []
    hp = BRAIN / "daily_history.jsonl"
    if hp.exists():
        for ln in hp.read_text(encoding="utf-8").splitlines()[-14:]:
            try:
                ours.append(json.loads(ln).get("title", ""))
            except ValueError:
                pass
    gap = read_json(OUT / "gap.json", {})
    eksik = gap.get("bizde_eksik", [])
    news = [x.get("title", "") for x in (read_json(OUT / "morning_brief.json", {}).get("top") or [])][:15]
    mem = memory()
    ctx = {"son_basliklarimiz": ours, "gundem": news, "bizde_eksik": eksik, "asiri_tekrar": gap.get("asiri_tekrar", []),
           "trend_ozet": rd(BRAIN / "trend_brief.md", 1800), "denetim": rd(BRAIN / "audit.md", 600),
           "bizim_performans": json.dumps(read_json(OUT / "perf_notes.json", {}), ensure_ascii=False)[:1500],
           "onceki_dusunceler": [m.get("ders", "") for m in mem if m.get("ders")][-6:]}
    try:
        # 1) neyi araştırayım?
        plan = llm_json(MODEL, "Finans Kanalı (TR kişisel finans YouTube) beyni olarak verilere bak; içerik açığını kapatmak için "
                        'internette araştırılacak 2 Türkçe arama sorgusu seç. JSON: {"dusunce":"...","sorgular":["...","..."]}. VERİ: '
                        + json.dumps(ctx, ensure_ascii=False), temp=0.5, timeout=600, keep="10m")
        found = research(plan.get("sorgular", []) if isinstance(plan, dict) else [])
        for i, r in enumerate(found, 1):
            r["no"] = f"A{i}"
        rules = st["candidate"]["rules"] if st.get("candidate") else st["rules"]
        # 2) fikir üret
        out = llm_json(MODEL, "KURALLARIN:\n- " + "\n- ".join(rules) + "\n\nGörev: aşağıdaki VERİ ve ARAŞTIRMA'ya dayanarak 4 ÖZGÜN video fikri üret (haber başlığını KOPYALAMA, site adı ve yıl yazma; kendi kanca başlığını kur). "
                       'Her fikir: {"baslik":"...","format":"uzun|shorts","neden":"...","kaynak_no":"A3"} (kaynak_no ARAŞTIRMA listesinden). '
                       'Ayrıca bu turdan bir "ders" (1 cümle) yaz. JSON: {"fikirler":[...],"ders":"..."}.\nVERİ: '
                       + json.dumps(ctx, ensure_ascii=False) + "\nARAŞTIRMA: " + json.dumps(found, ensure_ascii=False),
                       temp=0.6, timeout=900, keep="10m")
        ideas = out.get("fikirler", []) if isinstance(out, dict) else []
        src = re.sub(r"[.,]", "", json.dumps(ctx, ensure_ascii=False) + json.dumps(found, ensure_ascii=False))
        for it in ideas:
            it["puan"], it["gerekce"] = score(it, src, ours, eksik, [r['title'] for r in found] + news)
            k = str(it.get("kaynak_no", ""))
            it["kaynak"] = next((r["url"] for r in found if r["no"] == k), "")
        avg = round(sum(i["puan"] for i in ideas) / len(ideas), 1) if ideas else 0
        # 3) evrim: aday kural setini değerlendir / yeni aday öner
        hist = st.setdefault("history", [])
        base = [h["avg"] for h in hist if h.get("set") == "ana"][-3:]
        base_avg = sum(base) / len(base) if base else avg
        if st.get("candidate"):
            c = st["candidate"]
            keep = avg > base_avg
            remember({"at": now.isoformat(timespec="minutes"), "tip": "evrim", "degisiklik": c["change"], "aday_puan": avg,
                      "ana_ort": round(base_avg, 1), "sonuc": "TUTULDU" if keep else "GERİ ALINDI"})
            if keep:
                st["rules"] = c["rules"]
            st["candidate"] = None
            hist.append({"at": now.isoformat(timespec="minutes"), "set": "aday", "avg": avg})
        else:
            hist.append({"at": now.isoformat(timespec="minutes"), "set": "ana", "avg": avg})
            weak = [w for i in ideas for w in i["gerekce"] if w != "eksik konuyu dolduruyor"]
            prop = llm_json(MODEL, "Kural listen:\n- " + "\n- ".join(st["rules"]) + f"\nBu turda fikirlerin zayıf yanları (kod ölçtü): {weak}. "
                            "Puanı yükseltecek TEK değişiklik öner: yeni kural ekle ya da bir kuralı değiştir/sil. En çok 8 kural. "
                            'JSON: {"degisiklik":"ne yaptın","kurallar":["tam yeni liste"]}', temp=0.5, timeout=600, keep="1m")
            nr = prop.get("kurallar") if isinstance(prop, dict) else None
            if isinstance(nr, list) and 1 <= len(nr) <= 8 and all(isinstance(x, str) and 5 < len(x) < 200 for x in nr):
                st["candidate"] = {"rules": nr, "change": str(prop.get("degisiklik", ""))[:200]}
        st["history"] = hist[-60:]
        write_json(RULES, st)
    except Exception as e:  # noqa: BLE001
        log(AGENT, f"tur başarısız: {str(e)[:150]}")
        return 1
    finally:
        unload(MODEL)
    remember({"at": now.isoformat(timespec="minutes"), "tip": "tur", "sorgular": plan.get("sorgular") if isinstance(plan, dict) else [],
              "ort_puan": avg, "ders": str(out.get("ders", ""))[:300] if isinstance(out, dict) else ""})
    # fikir havuzu: günün en iyileri (aynı başlık tekrar etmesin)
    pool = [i for i in read_json(IDEAS, []) if i.get("at", "")[:10] >= now.strftime("%Y-%m-%d")]
    seen = {i["baslik"].lower() for i in pool}
    for it in ideas:
        if it.get("baslik") and it["baslik"].lower() not in seen:
            pool.append({**it, "at": now.isoformat(timespec="minutes")})
    pool.sort(key=lambda i: -i.get("puan", 0))
    write_json(IDEAS, pool[:30])
    evo = [m for m in memory(40) if m.get("tip") == "evrim"][-5:]
    md = [f"# Beyin — {now:%Y-%m-%d %H:%M} (yerel model; puanlar KODDAN; YALNIZ İLHAM, rakamları doğrula)", "",
          "## En iyi fikirler (bugün)"] + [
        f"- **{i['baslik']}** [{i.get('format', '?')}] puan {i['puan']} — {i.get('neden', '')} {('· kaynak ' + i.get('kaynak_no', '')) if i.get('kaynak') else ''}"
        + (f" _⚠ {'; '.join(i['gerekce'])}_" if i.get("gerekce") else "") for i in pool[:6]] + [
        "", "## Şu anki kurallarım"] + [f"- {r}" for r in st["rules"]] + [
        "", "## Evrim (son denemeler)"] + [f"- {m['at']}: {m['degisiklik']} → {m['sonuc']} ({m['aday_puan']} vs {m['ana_ort']})" for m in evo]
    (BRAIN / "brain_brief.md").write_text("\n".join(md), encoding="utf-8")
    log(AGENT, f"tur bitti: {len(ideas)} fikir, ort {avg}, kaynak {len(found)}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    raise SystemExit(main(ap.parse_args().force))
