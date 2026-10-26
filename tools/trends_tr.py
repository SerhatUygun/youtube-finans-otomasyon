"""Google Trends — Türkiye günlük yükselen aramalar (ücretsiz RSS). Günlük hat Claude'dan önce çağırır;
Claude konu seçerken bugün Türkiye'de patlayan finans/ekonomi aramalarına bakar (zamanlama = algoritmada öne çıkma).

  python tools/trends_tr.py
Çıktı: output/_brain/trends_tr.json  [{title, traffic, news: [başlık...]}]
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "_brain" / "trends_tr.json"
NS = {"ht": "https://trends.google.com/trending/rss"}
# kısa kökler ("zam", "kur", "fon") "zaman", "kanal", "fonksiyon"a takılıyordu -> kelime başı + izinli Türkçe ekler
FIN = re.compile(r"(?<![\wçğıöşü])(altın|dolar|euro|borsa|bist|faiz|enflasyon|tüfe|merkez bankası|tcmb|fed|bitcoin|kripto|petrol|benzin|"
                 r"motorin|akaryakıt|asgari ücret|maaş|zamm|emekli|vergi|ötv|döviz|hisse|yatırım fonu|spk|ekonomi|konut|kira|kredi|mevduat|"
                 r"gümüş|brent|ons altın)", re.IGNORECASE)


def main():
    r = requests.get("https://trends.google.com/trending/rss", params={"geo": "TR"}, timeout=15,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        traffic = (it.findtext("ht:approx_traffic", namespaces=NS) or "").strip()
        news = [n.findtext("ht:news_item_title", namespaces=NS) or "" for n in it.findall("ht:news_item", NS)]
        blob = " ".join([title] + news)
        items.append({"title": title, "traffic": traffic, "finance": bool(FIN.search(blob)), "news": [x for x in news if x][:3]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    fin = [i for i in items if i["finance"]]
    print(f"{len(items)} trend ({len(fin)} finans/ekonomi) -> {OUT}")
    for i in fin[:10]:
        print(f"  {i['traffic']:>6}  {i['title']}  | {(i['news'] or [''])[0][:70]}")
    return items


if __name__ == "__main__":
    main()
