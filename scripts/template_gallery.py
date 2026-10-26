"""Şablon galerisi: seçilen şablonları örnek veriyle tek plana dizer, her birinden kare çeker, iletişim sayfası üretir.
Yeni şablon geliştirirken ve kütüphane turlarında görsel kontrol için.

  python scripts/template_gallery.py            # templatesC + D (yeni şablonlar)
  python scripts/template_gallery.py --all      # + mevcut örnek plan (bugünkü işin sahneleri)
Çıktı: output/_gallery/sheet_*.jpg
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.market_snapshot import snapshot  # noqa: E402
from pipeline.daily.qa import _sheet  # noqa: E402

OUT = ROOT / "output" / "_gallery"
SCENE = 150  # her sahne 5 sn

SAMPLES = [
    {"t": "Candles", "p": {"symbol": "XU100", "last": 35, "title": "BIST 100 · günlük mum", "change": {"text": "Zirveden −%14,7", "color": "down"},
                          "hlines": [{"value": 12400, "label": "Destek 12.400", "color": "up"}, {"value": 12900, "label": "Direnç 12.900", "color": "hawk"}]}},
    {"t": "Heatmap", "p": {"title": "Sektörler · bugün", "source": "Kaynak: Borsa İstanbul",
                          "items": [{"label": "Bankacılık", "value": -2.4, "weight": 30}, {"label": "Sanayi", "value": -1.1, "weight": 22},
                                    {"label": "Holding", "value": -1.8, "weight": 16}, {"label": "Teknoloji", "value": 0.9, "weight": 9},
                                    {"label": "Enerji", "value": 1.6, "weight": 8}, {"label": "Ulaştırma", "value": -3.2, "weight": 7},
                                    {"label": "GYO", "value": -0.4, "weight": 5}, {"label": "Gıda", "value": 0.3, "weight": 3}]}},
    {"t": "WorldMap", "p": {"title": "Petrol nereden geçiyor?",
                           "highlight": [{"name": "Iran", "color": "hawk"}, {"name": "Saudi Arabia", "color": "oil"}, {"name": "Turkey", "color": "hero"}],
                           "flows": [{"from": [50.0, 26.5], "to": [121.5, 31.2], "label": "Hürmüz → Çin", "color": "oil"},
                                     {"from": [50.0, 26.5], "to": [4.9, 52.4], "label": "→ Avrupa", "color": "oil"}],
                           "markers": [{"at": [56.3, 26.6], "label": "Hürmüz", "color": "hawk"}]}},
    {"t": "YieldCurve", "p": {"title": "ABD verim eğrisi", "nowLabel": "bugün", "prevLabel": "1 ay önce",
                             "items": [{"m": "3A", "v": 4.95, "prev": 4.9}, {"m": "2Y", "v": 4.71, "prev": 4.52}, {"m": "5Y", "v": 4.86, "prev": 4.6},
                                       {"m": "10Y", "v": 5.23, "prev": 4.94}, {"m": "30Y", "v": 5.41, "prev": 5.12}]}},
    {"t": "Breaking", "p": {"time": "14:05", "headline": "SPK 131 fonu tasfiyeye gönderdi", "highlight": ["131"], "sub": "455.758 yatırımcı ödeme takvimini bekliyor",
                           "source": "SPK duyurusu"}},
    {"t": "Countdown", "p": {"kicker": "KRİTİK VERİ", "title": "ABD enflasyonu (PCE)", "days": 1, "hours": 15, "date": "30 Eylül · 15:30 TSİ"}},
    {"t": "Headline", "p": {"outlet": "Ekonomi Gazetesi", "date": "29.09.2026", "text": "Borsa 3 ayın dibinde: fon krizi derinleşiyor", "highlight": "fon krizi",
                           "sub": "BIST 100 zirveden %14,7 geriledi"}},
    {"t": "Metal3D", "p": {"symbol": "XAUUSD", "sub": "Dünkü sert düşüşün ardından tepki alımı"}},
    {"t": "Metal3D", "p": {"symbol": "XAGUSD", "shape": "coin"}},
    {"t": "Globe3D", "p": {"kicker": "KÜRESEL", "title": "Petrol arzı ve Hürmüz", "focus": [50, 26],
                          "markers": [{"at": [56.3, 26.6], "label": "Hürmüz Boğazı", "color": "hawk"}, {"at": [28.9, 41.0], "label": "İstanbul", "color": "hero"}],
                          "flows": [{"from": [50.0, 26.5], "to": [28.9, 41.0], "color": "oil"}]}},
    {"t": "AssetCards", "p": {"title": "Hisse · kur · tahvil", "items": [{"symbol": "XU100", "name": "BIST 100"}, {"symbol": "USDTRY", "name": "Dolar/TL"},
                                                                          {"symbol": "TR10Y", "name": "TR 10 yıllık"}]}},
]


# 30 Eyl düzeltmelerinin regresyon örnekleri (sahne indeksi i ise o sahnedeki kelime tetikleri k{i*10+n})
FIXES = [
    ("Stamp", lambda i: {"kicker": "GEÇ GELEN RAKAM", "big": "+25", "unit": "baz puan", "label": "hayalet → slam", "bigCue": f"0:k{i * 10 + 6}"}),
    ("Compare", lambda i: {"title": "Uzun rozet metni", "items": [{"label": "Beklenti", "value": 30, "color": "dim"}, {"label": "Gerçekleşen", "value": 45, "color": "down"}],
                           "big": {"text": "Açığın kaynağı: enerji", "sub": "Kaynak: TCMB ödemeler dengesi", "color": "down"}}),
    ("Normalized", lambda i: {"title": "Negatif yüzde biçimi", "since": "2026-08-01", "lines": [{"symbol": "XU100", "label": "BIST 100", "color": "down"},
                                                                                               {"symbol": "USDTRY", "label": "Dolar/TL", "color": "accent"}]}),
    ("Chart", lambda i: {"symbol": "XAUUSD", "last": 40, "title": "Tek uç etiketi", "markers": [{"at": "last"}, {"at": "max", "label": "zirve {v}"}]}),
    ("Chapter", lambda i: {"title": "Dolar, Gram Altın ve Cari Açık", "n": 3, "of": 4, "kind": "gold"}),
    ("DateQuestion", lambda i: {"month": "EKİM", "day": "1", "weekday": "ÇARŞAMBA", "question": "Benzin ve motorine ÖTV zammı gelirse fatura kime kalır",
                                "note": {"label": "BUGÜN", "text": "Enflasyon · Faiz · Altın · Türkiye"}}),
    ("Quote", lambda i: {"who": "Jerome Powell", "initials": "JP", "role": "Fed Başkanı", "text": "Enflasyon hedefe dönene kadar sabırlı olacağız.",
                         "cue": f"0:k{i * 10 + 7}"}),
    ("Poll", lambda i: {"question": "Zam pompaya nasıl yansıyacak?", "options": [{"text": "Tek seferde, bu gece"}, {"text": "Kademeli, birkaç parçada"},
                                                                                  {"text": "Petrol düşerse kısmen dengelenir"}]}),
    ("Bars", lambda i: {"kicker": "TÜFE'YE KATKI", "title": "Kalem kalem", "big": {"text": "Asıl yük benzinlide", "sub": "tahmini", "color": "down"},
                        "items": [{"label": "Benzin", "value": 0.31}, {"label": "Motorin", "value": 0.07}, {"label": "LPG", "value": 0.02}]}),
    ("Scenario", lambda i: {"asset": "BENZİN · İSTANBUL", "tone": "consumer", "left": {"label": "Senaryo 1", "cond": "Kademeli geçiş", "target": "≈86 TL"},
                            "right": {"label": "Senaryo 2", "cond": "Tek seferde + Brent > 100$", "target": "≈93 TL"}}),
    ("PumpBoard", lambda i: {"title": "AKARYAKIT", "place": "İstanbul Avrupa", "note": "Vergi farkı tek seferde yansırsa (hesap)",
                             "items": [{"name": "Benzin", "from": 80.40, "to": 92.87}, {"name": "Motorin", "from": 93.50, "to": 97.10}, {"name": "LPG", "from": 34.99, "to": 36.47}]}),
    ("Timeline", lambda i: {"kicker": "BU HAFTA · TÜRKİYE SAATİ", "items": [
        {"date": "1 EKİM", "time": "00:00", "title": "Eşel mobil biter", "cue": f"0:k{i * 10 + 1}"},
        {"date": "2 EKİM CUMA", "time": "15:30", "title": "ABD istihdamı", "cue": f"0:k{i * 10 + 4}"},
        {"date": "5 EKİM", "time": "10:00", "title": "TÜİK enflasyonu", "cue": f"0:k{i * 10 + 7}"}]}),
    ("DominoChain", lambda i: {"title": "Borsayı düşüren zincir", "items": [
        {"title": "SPK kuralı", "sub": "yoğunlaşma sınırı", "cue": f"0:k{i * 10 + 1}"}, {"title": "Temerrütler", "sub": "15–16 Eylül", "cue": f"0:k{i * 10 + 3}"},
        {"title": "131 fon tasfiye", "sub": "455 bin yatırımcı", "cue": f"0:k{i * 10 + 5}"}, {"title": "BIST −%14,7", "sub": "3 ayın dibi", "cue": f"0:k{i * 10 + 7}"}]}),
    ("Waterfall", lambda i: {"title": "Benzindeki vergi farkı", "items": [{"label": "ÖTV", "value": 10.39}, {"label": "KDV", "value": 2.08}],
                             "totalText": "12,47 TL", "totalLabel": "TOPLAM", "source": "Kaynak: hesaplama, 30.09.2026"}),
]


def main():
    base = len(SAMPLES)
    for k, (t, fn) in enumerate(FIXES):
        SAMPLES.append({"t": t, "p": fn(base + k)})
    OUT.mkdir(parents=True, exist_ok=True)
    snap = snapshot(["XU100", "XAUUSD", "XAGUSD", "USDTRY", "TR10Y"])
    series = {k: v["series"] for k, v in snap.items() if "series" in v}
    n = len(SAMPLES)
    total = n * SCENE
    words = [{"w": f"k{i}", "s": i * 15, "e": i * 15 + 14} for i in range(total // 15)]
    V = "--v" in sys.argv  # dikey (Shorts) kontrolü: aynı örnekler 1080x1920'de
    plan = {"fps": 30, "total": total, "outroStart": total, "layout": "v" if V else "h", "series": series, "captions": False,
            "segments": [{"i": 0, "s": 0, "e": total, "text": "galeri", "words": words}],
            "scenes": [{**s, "from": i * SCENE} for i, s in enumerate(SAMPLES)], "hud": {"date": "GALERİ"}}
    props = OUT / "props.json"
    props.write_text(json.dumps({"plan": plan}, ensure_ascii=False), encoding="utf-8")
    shots = [{"frame": i * SCENE + 110, "out": str(OUT / f"{"v" if V else "g"}_{i:02d}.jpg"), "label": f"#{i} {s['t']}"} for i, s in enumerate(SAMPLES)]
    jobs = OUT / "jobs.json"
    jobs.write_text(json.dumps([{"props": str(props), "comp": "AutoReel" if V else "AutoShowreel", "scale": 0.4 if V else 0.5,
                                 "shots": [{k: v for k, v in s.items() if k != 'label'} for s in shots]}]), encoding="utf-8")
    from pipeline.daily.build import clean_render_tmp, render_env
    r = subprocess.run(["node", "scripts/qa_stills.mjs", str(jobs)], cwd=str(ROOT / "remotion"), capture_output=True, text=True, env=render_env())
    clean_render_tmp()
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        sys.exit(1)
    per, cols, pre = (8, 4, "vsheet") if V else (6, 2, "sheet")
    for k in range(0, n, per):
        _sheet(shots[k:k + per], OUT / f"{pre}_{k // per}.jpg", cols)
    print("ok", [f"{pre}_{k // per}.jpg" for k in range(0, n, per)])


if __name__ == "__main__":
    main()
