"""HAFTALIK ekonomi özeti toplayıcı — sabit konu seti üzerinden research.py + market_data.py'yi
tek bir birleşik "facts" bloğunda toplar. gen_finance_script.py'nin girdisi olan
data/altin_gumus_facts.txt gibi elle-yazılmış dosyaların OTOMATİK, haftalık, çoklu-konu karşılığıdır.

Kullanım:
    from pipeline import weekly_digest
    d = weekly_digest.gather_weekly_digest(out_dir="output/_weeklytest")
    print(d["facts"])       # gen_finance_script.generate_script_json'a `facts` olarak verilir
    print(d["symbols"])     # gen_finance_script.generate_script_json'a `market_symbols` olarak verilir
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from pipeline import market_data, research
from pipeline.utils.logging import get_logger

log = get_logger("weekly_digest")

# (bölüm başlığı, araştırma sorgusu, market_data.SYMBOLS anahtarları)
WEEKLY_SECTIONS: list[tuple[str, str, list[str]]] = [
    ("DÖVİZ (DOLAR/TL, EURO/TL)", "dolar euro kuru bu hafta Türkiye", ["dolar", "euro"]),
    ("ALTIN", "altın fiyatları ons gram bu hafta", ["altın"]),
    ("GÜMÜŞ", "gümüş fiyatları bu hafta", ["gümüş"]),
    ("BORSA İSTANBUL (BIST 100)", "Borsa İstanbul BIST 100 bu hafta", ["bist100"]),
    ("FAİZ VE ENFLASYON", "TCMB faiz kararı enflasyon TÜFE bu hafta", []),
    ("KÜRESEL PİYASALAR", "Fed faiz kararı küresel piyasalar S&P 500 Nasdaq petrol bu hafta",
     ["sp500", "nasdaq", "petrol"]),
    ("KRİPTO PARA", "bitcoin ethereum kripto para piyasası bu hafta", ["bitcoin", "ethereum"]),
]

# Tek bir konuya bağlı olmayan, haftanın genel makro hikayesini yakalamak için ek sorgu.
_MACRO_QUERY = "Türkiye ekonomisi bu hafta Fed TCMB faiz enflasyon piyasa"


def gather_weekly_digest(
    out_dir=None,
    news_timespan: str = "1w",
    range_: str = "1mo",
    max_sources: int = 3,
    max_news: int = 8,
) -> dict:
    """Sabit haftalık bölüm seti için research.gather_facts + market_data.topic_data toplar,
    kaynakları tekilleştirir, tek bir başlıklı facts metni + sembol listesi döner.

    Döner: {"facts": str, "sources": [...], "symbols": [...], "sections": [...], "charts": [...]}
    """
    seen_url: set[str] = set()
    all_sources: list[str] = []
    all_symbols: list[str] = []
    all_charts: list[str] = []
    section_blocks: list[str] = []
    sections_raw: list[dict] = []

    def _add_sources(urls: list[str]) -> None:
        for u in urls:
            key = u.split("?")[0]
            if key in seen_url:
                continue
            seen_url.add(key)
            all_sources.append(u)

    for title, query, symbol_keys in WEEKLY_SECTIONS:
        parts: list[str] = []

        # Canlı piyasa verisi (varsa) önce — sayısal gerçekler en üstte.
        if symbol_keys:
            try:
                md = market_data.topic_data(query, out_dir=out_dir, range_=range_)
            except Exception as e:
                log.warning(f"market_data başarısız ({title}): {e}")
                md = {"facts": "", "charts": [], "sources": [], "symbols": []}
            if md.get("facts"):
                parts.append(md["facts"])
            all_charts.extend(md.get("charts", []))
            for k in md.get("symbols", []):
                if k not in all_symbols:
                    all_symbols.append(k)
            _add_sources(md.get("sources", []))

        # Haber/araştırma katmanı (o bölüme özel sorgu, son 1 hafta).
        try:
            rf = research.gather_facts(
                query, language="tr", max_sources=max_sources,
                include_news=True, news_timespan=news_timespan, max_news=max_news,
            )
        except Exception as e:
            log.warning(f"research.gather_facts başarısız ({title}): {e}")
            rf = {"facts": "", "sources": []}
        if rf.get("facts"):
            parts.append(rf["facts"])
        _add_sources(rf.get("sources", []))

        sections_raw.append({"title": title, "query": query, "market": bool(symbol_keys),
                              "has_content": bool(parts)})
        if parts:
            section_blocks.append(f"## {title}\n" + "\n\n".join(parts))

    # Kesişen makro haberler (tek bir sembole bağlı olmayan) — ayrı, kapsayıcı bölüm.
    try:
        macro = research.gather_facts(
            _MACRO_QUERY, language="tr", max_sources=max_sources,
            include_news=True, news_timespan=news_timespan, max_news=max_news,
        )
    except Exception as e:
        log.warning(f"Makro araştırma başarısız: {e}")
        macro = {"facts": "", "sources": []}
    if macro.get("facts"):
        section_blocks.append("## HAFTANIN ANA ETKENLERİ\n" + macro["facts"])
    _add_sources(macro.get("sources", []))

    stamp = datetime.now().strftime("%d.%m.%Y")
    header = f"HAFTALIK EKONOMİ ÖZETİ — {stamp} itibarıyla toplanan doğrulanmış veri ve haberler.\n"
    facts = header + "\n\n---\n\n".join(section_blocks)

    log.info(
        f"Haftalık özet toplandı: {len(section_blocks)} bölüm, {len(all_sources)} kaynak, "
        f"{len(all_symbols)} sembol, {len(facts)} karakter"
    )
    return {
        "facts": facts,
        "sources": all_sources,
        "symbols": all_symbols,
        "charts": all_charts,
        "sections": sections_raw,
    }


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    ap = argparse.ArgumentParser(description="Haftalık ekonomi özeti araştırması (dry-run)")
    ap.add_argument("--out", default=None, help="facts metnini yazacağı dosya (opsiyonel)")
    ap.add_argument("--out-dir", default="output/_weeklytest", help="grafiklerin yazılacağı klasör")
    args = ap.parse_args()

    d = gather_weekly_digest(out_dir=args.out_dir)
    print(f"\n=== {len(d['sources'])} KAYNAK / {len(d['symbols'])} SEMBOL: {d['symbols']} ===")
    for s in d["sources"]:
        print(" -", s)
    print("\n=== FACTS ===\n")
    print(d["facts"])

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(d["facts"], encoding="utf-8")
        print(f"\nYazıldı: {out_path}")
