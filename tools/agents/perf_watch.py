"""Ajan 3 — Performans izleyicisi (günde 2 kez: 10:30 ve 22:30; yerel gpt-oss:20b).

tools/perf_report.py (Data+Analytics API) -> output/_brain/perf.json; önceki anlık görüntüyle karşılaştırır:
  - izlenme hızı (son ölçümden bu yana saatlik izlenme), yaşına göre beklenen izlenme (kategori ortalamasıyla)
  - beklenenden çok iyi/kötü giden video -> uyarı
Yerel model notları + yarın için konu/açı önerisi -> output/_agents/perf_notes.json (günlük hat okur).
Kanala hiçbir şey YAZMAZ (yalnız okuma).

  python tools/agents/perf_watch.py
"""
from __future__ import annotations

from datetime import datetime

from common import OUT, ROOT, alert, llm_json, log, ollama_up, read_json, unload, wait_free, write_json

AGENT = "performans"
MODEL = "gpt-oss:20b"
SNAP = OUT / "perf_snapshots.json"
NOTES = OUT / "perf_notes.json"


def main() -> int:
    from tools import perf_report
    try:
        perf_report.main()
    except Exception as e:  # noqa: BLE001
        alert(AGENT, "hata", f"perf_report çalışmadı (Google yetkisi düşmüş olabilir: tools/reauth_google.py): {str(e)[:150]}")
        return 1
    perf = read_json(ROOT / "output" / "_brain" / "perf.json", {})
    vids = perf.get("videos", {})
    now = datetime.now()
    snaps = read_json(SNAP, {})
    prev = snaps.get("last", {})
    prev_at = snaps.get("last_at")
    hours = max((now - datetime.fromisoformat(prev_at)).total_seconds() / 3600, 0.1) if prev_at else None

    rows = []
    for vid, v in vids.items():
        age_d = max((now - datetime.fromisoformat(v["date"])).days, 0)
        cat_avg = perf.get("summary", {}).get(v["type"], {}).get(v["cat"], {}).get("avg_views")
        rate = round((v["views"] - prev[vid]) / hours, 1) if hours and vid in prev else None
        rows.append({"id": vid, "title": v["title"], "type": v["type"], "cat": v["cat"], "age_d": age_d, "views": v["views"],
                     "views_per_h": rate, "avg_view_pct": v.get("avg_view_pct"), "subs": v.get("subs"), "cat_avg_views": cat_avg})
    rows.sort(key=lambda r: r["age_d"])

    # kural tabanlı uyarılar (model gerekmez): son 3 günün videoları kategori ortalamasına göre
    for r in rows:
        if r["age_d"] <= 3 and r["cat_avg_views"]:
            ratio = r["views"] / max(r["cat_avg_views"], 1)
            key = f"{r['id']}:{'iyi' if ratio >= 1.8 else 'kotu' if ratio <= 0.35 and r['age_d'] >= 2 else ''}"
            if key.endswith(":") or key in snaps.get("alerted", []):
                continue
            alert(AGENT, "performans", f"{'BEKLENENDEN İYİ' if ratio >= 1.8 else 'ZAYIF'}: {r['title'][:70]} — {r['views']} izlenme "
                                       f"(kategori ort. {r['cat_avg_views']}, {r['age_d']} gün)")
            snaps.setdefault("alerted", []).append(key)

    notes = read_json(NOTES, {})
    notes.update(at=now.isoformat(timespec="minutes"), videos=rows[:20], summary=perf.get("summary", {}))
    if ollama_up() and wait_free(AGENT):
        # 2 Eki: model hesap yapınca yanılıyordu (ortalama uydurma, 1 günlük videoya "kaçın" hükmü) -> tabloyu kod hesaplar;
        # 3 günden genç videolar kıyasa girmez, "erken" diye ayrı listelenir
        mature = [r for r in rows if r["age_d"] >= 3]
        table = {}
        for r in mature:
            table.setdefault((r["type"], r["cat"]), []).append(r)
        tab = "\n".join(f"- {t} / {c}: {len(xs)} video, ort. {round(sum(x['views'] for x in xs) / len(xs))} izlenme, "
                        f"ort. izlenme oranı %{round(sum(x.get('avg_view_pct') or 0 for x in xs) / len(xs), 1)}"
                        for (t, c), xs in sorted(table.items(), key=lambda kv: -sum(x['views'] for x in kv[1]) / len(kv[1])))
        lines = "OLGUN VİDEOLAR (≥3 gün; kıyas bunlarla):\n" + "\n".join(
            f"- [{r['type']}/{r['cat']}] {r['title'][:80]} | {r['age_d']} gün | {r['views']} izl | izlenme oranı %{r['avg_view_pct']} | +{r['subs']} abone"
            for r in mature[:15]) + "\n\nKATEGORİ TABLOSU (hazır hesaplandı, yeniden hesaplama):\n" + tab + \
            "\n\nYENİ VİDEOLAR (<3 gün; HÜKÜM VERME, yalnız 'izlenmeli' de):\n" + "\n".join(
            f"- [{r['type']}/{r['cat']}] {r['title'][:80]} | {r['age_d']} gün | {r['views']} izl | saatlik {r['views_per_h']}"
            for r in rows if r["age_d"] < 3)
        brief = read_json(OUT / "morning_brief.json", {})
        news = "\n".join(f"- {x.get('ozet') or x.get('title')}" for x in brief.get("top", [])[:8])
        prompt = ("Finans Kanalı (Türk finans YouTube kanalı) son videolarının verisi aşağıda. Kanal hedefi: kitleyi büyütmek. "
                  "SABİT STRATEJİ (sorgulama): gelir UZUN videodan gelir; Shorts keşif içindir ve izleyiciyi uzun videoya taşımalıdır. "
                  "Bu yüzden 'uzun videoyu bırak / yalnız Shorts yap' önerisi VERME; hangi KONU ve AÇININ uzun videoda daha iyi gittiğine bak. "
                  "Sadece hazır tablodaki sayılara dayan; sayı UYDURMA, ortalama HESAPLAMA, aynı gözlemi tekrarlama. JSON döndür: "
                  "{\"notlar\": [\"en fazla 5 FARKLI kısa gözlem\"], \"yarin_onerisi\": {\"kategori\": \"uzun video konusu\", \"aci\": \"...\", \"neden\": \"tablodan sayı ile\"}}"
                  "\n\n" + lines + ("\n\nGÜNÜN HABERLERİ (doğrulanmamış ipucu):\n" + news if news else ""))
        try:
            out = llm_json(MODEL, prompt, ctx=8192, temp=0.3)
            notes.pop("kacinilacak", None)
            notes.update(notlar=list(dict.fromkeys(out.get("notlar", [])))[:5], yarin_onerisi=out.get("yarin_onerisi", {}),
                         note="Yerel model (gpt-oss:20b) yorumu; sayılar perf.json'dan.")
        except Exception as e:  # noqa: BLE001
            log(AGENT, f"model yorumu alınamadı: {str(e)[:120]}")
        unload(MODEL)
    write_json(NOTES, notes)
    snaps.update(last={vid: v["views"] for vid, v in vids.items()}, last_at=now.isoformat(timespec="seconds"))
    snaps["alerted"] = snaps.get("alerted", [])[-200:]
    write_json(SNAP, snaps)
    log(AGENT, f"{len(rows)} video izlendi -> {NOTES.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
