"""Canlı finansal veri + otomatik grafik — sıfır API maliyeti (anahtarsız uçlar).

Kanalın videolarına GÜNCEL, GERÇEK sayılar ve profesyonel grafikler katar. Bu, YouTube'un
"inauthentic/şablon içerik" filtresine karşı en güçlü savunmadır: her video, o gün çekilmiş
benzersiz verilerle farklılaşır (bkz. research.py — bu onun sayısal/görsel tamamlayıcısı).

Kaynaklar (hiçbiri API anahtarı istemez):
  - Yahoo Finance chart API: hisse, endeks, döviz, emtia, kripto (zaman serisi)
  - CoinGecko: kripto anlık fiyat yedeği

Kullanım:
    from pipeline import market_data as md
    s = md.fetch_series("altın", range_="6mo")      # {dates, closes, last, change_pct, ...}
    md.render_chart(s, "output/<job>/charts/altin.png")
    d = md.topic_data("altın ve gümüş piyasası")    # {facts, charts, sources, symbols}
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import requests

from pipeline.utils.logging import get_logger

log = get_logger("market_data")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36"}
_YF_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_CG_PRICE = "https://api.coingecko.com/api/v3/simple/price"

# Kullanıcı-dostu ad (TR/EN) -> Yahoo sembolü + görünen ad + para birimi ipucu.
# Konudan otomatik sembol tespiti için anahtar kelimeler de burada.
SYMBOLS: dict[str, dict] = {
    "altın":    {"yf": "GC=F",     "name": "Altın (ons/USD)",   "kw": ["altın", "gold", "xau", "ons altın"]},
    "gümüş":    {"yf": "SI=F",     "name": "Gümüş (ons/USD)",   "kw": ["gümüş", "silver", "xag"]},
    "petrol":   {"yf": "CL=F",     "name": "Ham Petrol (WTI)",  "kw": ["petrol", "oil", "wti", "ham petrol"]},
    "dolar":    {"yf": "TRY=X",    "name": "Dolar/TL",          "kw": ["dolar", "usd/try", "usdtry", "dolar kuru"]},
    "euro":     {"yf": "EURTRY=X", "name": "Euro/TL",           "kw": ["euro", "eur/try", "eurtry"]},
    "bitcoin":  {"yf": "BTC-USD",  "name": "Bitcoin (USD)",     "kw": ["bitcoin", "btc", "kripto"], "cg": "bitcoin"},
    "ethereum": {"yf": "ETH-USD",  "name": "Ethereum (USD)",    "kw": ["ethereum", "eth"], "cg": "ethereum"},
    "bist100":  {"yf": "XU100.IS", "name": "BIST 100",          "kw": ["bist", "borsa istanbul", "bist100"]},
    "sp500":    {"yf": "^GSPC",    "name": "S&P 500",           "kw": ["s&p", "sp500", "s and p"]},
    "nasdaq":   {"yf": "^IXIC",    "name": "Nasdaq",            "kw": ["nasdaq"]},
}


def _fmt_num(v: float) -> str:
    """İnsan-okur sayı: büyükse binlik ayırıcı, küçükse ondalık."""
    if v >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    if v >= 1:
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{v:.4f}".replace(".", ",")


def resolve_symbol(name_or_kw: str) -> tuple[str, dict] | None:
    """Serbest metinden ('altın', 'gold', 'BTC') SYMBOLS anahtarını bulur."""
    q = name_or_kw.strip().lower()
    if q in SYMBOLS:
        return q, SYMBOLS[q]
    for key, meta in SYMBOLS.items():
        if q == key or any(k in q for k in meta["kw"]):
            return key, meta
    return None


def fetch_series(name_or_symbol: str, range_: str = "6mo", interval: str = "1d") -> dict | None:
    """Yahoo chart API'den zaman serisi çeker. Döner:
    {key, symbol, name, dates:[...], closes:[...], last, first, change_pct, currency}
    Bulunamazsa None (çağıran grafiksiz devam eder)."""
    resolved = resolve_symbol(name_or_symbol)
    if resolved:
        key, meta = resolved
        symbol, name = meta["yf"], meta["name"]
    else:
        key, symbol, name = name_or_symbol, name_or_symbol, name_or_symbol

    try:
        r = requests.get(
            _YF_CHART.format(symbol=symbol),
            params={"range": range_, "interval": interval},
            headers=_UA, timeout=15,
        )
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        closes_raw = res["indicators"]["quote"][0]["close"]
        currency = res.get("meta", {}).get("currency", "")
    except Exception as e:
        log.warning(f"Yahoo serisi alınamadı ({symbol}): {e}")
        return None

    # None (tatil/eksik) noktaları temizle
    dates, closes = [], []
    for t, c in zip(ts, closes_raw):
        if c is None:
            continue
        dates.append(datetime.fromtimestamp(t, tz=timezone.utc))
        closes.append(float(c))
    if len(closes) < 2:
        return None

    first, last = closes[0], closes[-1]
    change_pct = (last - first) / first * 100.0 if first else 0.0
    return {
        "key": key, "symbol": symbol, "name": name,
        "dates": dates, "closes": closes,
        "first": first, "last": last, "change_pct": change_pct,
        "currency": currency, "range": range_,
    }


def latest_price_coingecko(cg_id: str, vs: str = "usd") -> float | None:
    try:
        r = requests.get(_CG_PRICE, params={"ids": cg_id, "vs_currencies": vs}, headers=_UA, timeout=12)
        r.raise_for_status()
        return float(r.json()[cg_id][vs])
    except Exception as e:
        log.warning(f"CoinGecko fiyatı alınamadı ({cg_id}): {e}")
        return None


# --- Teknik analiz (ücretsiz — Yahoo zaman serisinden hesaplanır) --------------
_TROY_OUNCE_G = 31.1034768   # 1 ons = 31.1035 gram (gram altın/gümüş dönüşümü için)


def _sma_series(closes: list[float], n: int) -> list[float | None]:
    """Kayan basit hareketli ortalama (grafik overlay için tarihlerle hizalı)."""
    out: list[float | None] = []
    for i in range(len(closes)):
        out.append(sum(closes[i - n + 1:i + 1]) / n if i >= n - 1 else None)
    return out


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder RSI (0-100). >=70 aşırı alım, <=30 aşırı satım kabul edilir."""
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    avg_g, avg_l = gains / period, losses / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def technical_analysis(series: dict) -> dict:
    """Zaman serisinden teknik göstergeler: SMA20/50, RSI14, trend, momentum,
    dönem zirve/dip ve zirveye uzaklık. Hepsi ücretsiz (seriden hesaplanır)."""
    closes, last = series["closes"], series["last"]
    sma20_s, sma50_s = _sma_series(closes, 20), _sma_series(closes, 50)
    sma20 = sma20_s[-1] if sma20_s else None
    sma50 = sma50_s[-1] if sma50_s else None
    rsi = _rsi(closes, 14)
    hi, lo = max(closes), min(closes)

    if sma20 and sma50:
        if last > sma20 > sma50:
            trend = "yükseliş trendi"
        elif last < sma20 < sma50:
            trend = "düşüş trendi"
        else:
            trend = "yatay/kararsız"
    else:
        trend = "yükseliş" if series["change_pct"] >= 0 else "düşüş"

    if rsi is None:
        momentum = "nötr"
    elif rsi >= 70:
        momentum = "aşırı alım"
    elif rsi <= 30:
        momentum = "aşırı satım"
    else:
        momentum = "nötr"

    from_high = (last - hi) / hi * 100.0 if hi else 0.0
    return {
        "sma20": sma20, "sma50": sma50, "rsi": rsi, "high": hi, "low": lo,
        "trend": trend, "momentum": momentum, "from_high_pct": from_high,
        "sma20_series": sma20_s, "sma50_series": sma50_s,
    }


def _ta_summary_tr(series: dict, ta: dict) -> str:
    """Teknik analizi tek satır Türkçe özete çevirir (script'e enjekte edilir)."""
    cur = series["currency"]
    parts = [f"trend {ta['trend']}"]
    if ta["rsi"] is not None:
        parts.append(f"RSI14 {ta['rsi']:.0f} ({ta['momentum']})")
    if ta["sma20"]:
        parts.append(f"20 günlük ort. {_fmt_num(ta['sma20'])} {cur}")
    if ta["sma50"]:
        parts.append(f"50 günlük ort. {_fmt_num(ta['sma50'])} {cur}")
    parts.append(
        f"dönem aralığı {_fmt_num(ta['low'])}–{_fmt_num(ta['high'])} {cur} "
        f"(zirveden %{abs(ta['from_high_pct']):.1f} uzak)"
    )
    return "  Teknik görünüm: " + "; ".join(parts) + "."


def _asof_label(series: dict) -> str:
    """Serinin GERÇEK son veri noktasının tarihini dürüst şekilde ifade eder. Yahoo'nun günlük
    barı piyasa kapalıyken (hafta sonu/resmi tatil) ya da endpoint gecikmesinde 1-2 gün eski
    kalabilir -- script bunu körü körüne 'bugün' diye sunarsa YANLIŞ/yanıltıcı olur (finans
    içeriğinde doğruluk kritik). Son veri bugünse 'bugün', değilse gerçek tarihi söyler."""
    last_date = series["dates"][-1].date()
    today = datetime.now(timezone.utc).date()
    if last_date == today:
        return "bugün"
    return f"{last_date.strftime('%d.%m.%Y')} kapanışı itibarıyla"


def gram_gold_silver_try() -> list[str]:
    """Gram altın/gümüş TL — ons USD (GC=F/SI=F) × USDTRY / 31.1035.
    Türk izleyici için en anlamlı metrik. Boş liste = veri alınamadı."""
    lines: list[str] = []
    usdtry = fetch_series("dolar", range_="5d")
    if not usdtry:
        return lines
    rate = usdtry["last"]
    for key, label in (("altın", "Gram altın"), ("gümüş", "Gram gümüş")):
        s = fetch_series(key, range_="5d")
        if not s:
            continue
        gram_try = s["last"] / _TROY_OUNCE_G * rate
        lines.append(f"- {label}: yaklaşık {_fmt_num(gram_try)} TL "
                     f"(ons {_fmt_num(s['last'])} USD × {_fmt_num(rate)} USDTRY / 31,1 g).")
    return lines


# --- Grafik (video için: koyu zemin, tek vurgu, büyük okunaklı font) ---
# dataviz ilkeleri: zaman-serisi -> çizgi; tek seri -> efsane yok (başlık adlandırır);
# yön'e göre tek vurgu (yükseliş yeşil / düşüş kırmızı); metin ink token'da, çizgi vurguda;
# silik ızgara/eksen. Renkler koyu zeminde eri­şilebilir kontrastta.
_BG = "#0d1117"
_INK = "#e6edf3"        # ana metin
_MUTED = "#8b949e"      # eksen/silik metin
_GRID = "#21262d"
_UP = "#3fb950"         # yükseliş (erişilebilir yeşil)
_DOWN = "#f85149"       # düşüş (erişilebilir kırmızı)


def render_chart(series: dict, out_path, title: str | None = None, source: str = "Yahoo Finance",
                 ta: dict | None = None) -> str:
    """Zaman serisini video-dostu bir PNG grafiğe çizer (1920x1080). out_path döner.
    `ta` verilirse SMA20/50 hareketli ortalamalar silik overlay olarak eklenir."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from pathlib import Path

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    up = series["change_pct"] >= 0
    accent = _UP if up else _DOWN
    dates, closes = series["dates"], series["closes"]

    fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)

    ax.plot(dates, closes, color=accent, linewidth=3.0, solid_capstyle="round", zorder=4)
    ax.fill_between(dates, closes, min(closes), color=accent, alpha=0.10)

    # Teknik overlay: SMA20 (sarı) + SMA50 (mavi), silik ve ince — fiyat çizgisini ezmesin.
    if ta:
        for s_key, color, lbl in (("sma20_series", "#d29922", "20g"),
                                  ("sma50_series", "#58a6ff", "50g")):
            vals = ta.get(s_key)
            if vals:
                pts = [(d, v) for d, v in zip(dates, vals) if v is not None]
                if len(pts) > 1:
                    xs, ys = zip(*pts)
                    ax.plot(xs, ys, color=color, linewidth=1.6, alpha=0.85, zorder=3, label=lbl)
        ax.legend(loc="upper left", frameon=False, labelcolor=_MUTED, fontsize=16)

    # Son değeri doğrudan etiketle (efsane yerine) — dataviz: seçili doğrudan etiket
    last, cur = series["last"], series["currency"]
    ax.scatter([dates[-1]], [last], color=accent, s=90, zorder=5)
    ax.annotate(
        f"  {_fmt_num(last)} {cur}",
        xy=(dates[-1], last), color=_INK, fontsize=26, fontweight="bold",
        va="center", ha="left", xytext=(8, 0), textcoords="offset points",
    )

    # Başlık (sol) + değişim yüzdesi (SAĞ) — aynı satırda, çakışmadan.
    head = title or series["name"]
    sign = "▲" if up else "▼"
    ax.text(0.0, 1.04, head, transform=ax.transAxes, color=_INK,
            fontsize=38, fontweight="bold", va="bottom", ha="left")
    ax.text(1.0, 1.04, f"{sign} %{abs(series['change_pct']):.1f}  ({series['range']})",
            transform=ax.transAxes, color=accent, fontsize=28, fontweight="bold",
            va="bottom", ha="right")

    # Silik ızgara/eksen (recessive)
    ax.grid(True, color=_GRID, linewidth=1.0, alpha=0.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=_MUTED, labelsize=18, length=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    for lbl in ax.get_yticklabels():
        lbl.set_color(_MUTED)

    # Kaynak + tarih dipnotu (şeffaflık/güven)
    stamp = datetime.now().strftime("%d.%m.%Y")
    fig.text(0.01, 0.02, f"Kaynak: {source} · {stamp}", color=_MUTED, fontsize=16)

    fig.subplots_adjust(left=0.06, right=0.90, top=0.86, bottom=0.10)
    fig.savefig(out, facecolor=_BG)
    plt.close(fig)
    log.info(f"Grafik yazıldı: {out} ({head}, %{series['change_pct']:.1f})")
    return str(out)


def detect_symbols(topic: str, max_symbols: int = 3) -> list[str]:
    """Konu metninden ilgili SYMBOLS anahtarlarını çıkarır (sıra korunur, tekrarsız)."""
    q = topic.lower()
    found = []
    for key, meta in SYMBOLS.items():
        if key in q or any(k in q for k in meta["kw"]):
            if key not in found:
                found.append(key)
    return found[:max_symbols]


def topic_data(topic: str, out_dir=None, range_: str | None = None) -> dict:
    """Konuyla ilgili sembolleri tespit eder, canlı veri + grafik üretir. Döner:
    {facts: <script'e enjekte edilecek güncel rakamlar>, charts: [png...], sources: [...], symbols: [...]}
    range_ verilmezse: makro döngü / tarihsel konularda otomatik '5y', aksi halde '6mo' seçilir."""
    from pathlib import Path

    if range_ is None:
        q = topic.lower()
        if any(w in q for w in ("döngü", "tarih", "yıllık", "büyük resim", "rekor", "nixon", "makro", "cycle", "kırılım", "50 yıl")):
            range_ = "5y"
        else:
            range_ = "6mo"

    keys = detect_symbols(topic)
    if not keys:
        return {"facts": "", "charts": [], "sources": [], "symbols": []}

    lines, charts, sources, used = [], [], [], []
    stamp = datetime.now().strftime("%d.%m.%Y")
    for key in keys:
        s = fetch_series(key, range_=range_)
        if not s:
            continue
        used.append(key)
        sign = "arttı" if s["change_pct"] >= 0 else "düştü"
        asof = _asof_label(s)
        lines.append(
            f"- {s['name']}: {asof} {_fmt_num(s['last'])} {s['currency']} "
            f"(son {range_} içinde %{abs(s['change_pct']):.1f} {sign})."
        )
        # Teknik analiz satırı (SMA/RSI/trend) — "teknik yorum" için script'e girer.
        ta = None
        try:
            ta = technical_analysis(s)
            lines.append(_ta_summary_tr(s, ta))
        except Exception as e:
            log.warning(f"Teknik analiz üretilemedi ({key}): {e}")
        sources.append(f"https://finance.yahoo.com/quote/{s['symbol']}")
        if out_dir:
            png = Path(out_dir) / f"chart_{key}.png"
            try:
                charts.append(render_chart(s, png, ta=ta))
            except Exception as e:
                log.warning(f"Grafik üretilemedi ({key}): {e}")

    # Gram altın/gümüş TL — Türk izleyici için en anlamlı metrik (altın/gümüş konusundaysa).
    gram_lines = gram_gold_silver_try() if any(k in ("altın", "gümüş") for k in used) else []

    facts = ""
    if lines:
        facts = (
            f"PİYASA VERİLERİ (script {stamp} tarihinde üretiliyor — her satırdaki tarih ifadesini "
            f"[bugün / X kapanışı itibarıyla] AYNEN kullan; veri o satırda YOKSA 'bugün' UYDURMA):\n"
            + "\n".join(lines)
        )
        if gram_lines:
            facts += "\n\nTÜRKİYE'DE GRAM FİYATLARI (yaklaşık):\n" + "\n".join(gram_lines)
    log.info(f"topic_data: {len(used)} sembol, {len(charts)} grafik — konu: {topic!r}")
    return {"facts": facts, "charts": charts, "sources": sources, "symbols": used}


if __name__ == "__main__":
    import sys

    topic = " ".join(sys.argv[1:]) or "altın ve gümüş piyasası bugün"
    d = topic_data(topic, out_dir="output/_marketdata_test")
    print(f"\n=== SEMBOLLER: {d['symbols']} ===")
    print(d["facts"] or "(veri yok)")
    print("\nGrafikler:", d["charts"])
    print("Kaynaklar:", d["sources"])
