"""YouTube arama önerileri (otomatik tamamlama) — izleyicinin GERÇEKTEN yazdığı Türkçe sorgular.
Günlük hat Claude'dan önce çağırır; Claude başlık/etiket/açıklamada bu ifadeleri kullanır (arama trafiği = kanalın 2. kaynağı).

  python tools/yt_suggest.py                 # varsayılan tohumlar
  python tools/yt_suggest.py "gram altın"    # tek tohum
Çıktı: output/_brain/yt_suggest.json  {tohum: [öneri, ...]}
"""
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "_brain" / "yt_suggest.json"
SEEDS = ["altın", "gram altın", "dolar", "borsa", "bist 100", "bitcoin", "gümüş", "petrol", "faiz", "enflasyon",
         "altın neden", "dolar neden", "borsa neden", "ekonomi", "yatırım"]
SUFFIX = ["", " ne olacak", " yorum", " düştü", " yükseldi"]


def suggest(q: str) -> list[str]:
    r = requests.get("https://suggestqueries.google.com/complete/search",
                     params={"client": "firefox", "ds": "yt", "hl": "tr", "gl": "TR", "q": q}, timeout=10)
    r.raise_for_status()
    data = json.loads(r.content.decode("utf-8", errors="replace"))
    return [s for s in data[1] if isinstance(s, str)]


def main(seeds: list[str]):
    res = {}
    for s in seeds:
        seen = []
        for suf in SUFFIX if len(seeds) > 1 else [""] + SUFFIX[1:]:
            try:
                for x in suggest(s + suf):
                    if x not in seen:
                        seen.append(x)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {s + suf}: {e}")
            time.sleep(0.25)
        res[s] = seen[:25]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), "suggestions": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sum(len(v) for v in res.values())} öneri -> {OUT}")
    return res


if __name__ == "__main__":
    main(sys.argv[1:] or SEEDS)
