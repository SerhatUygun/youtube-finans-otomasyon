"""TradingView (OANDA spot vb.) günlük fiyat serisi — kullanıcı isteği (28 Eyl): vadeli kontrat (GC=F, BZ=F…) yerine
TradingView'daki OANDA spot fiyatları (XAUUSD, XAGUSD…) daha gerçek; vadeli seriler vade devrinde sıçrıyordu
(BZ=F 25 Eyl: 97,44 — uzlaşma 104,32).

Kaynak: tvdatafeed (TradingView grafik veri akışı, girişsiz). Kısa adlar aşağıdaki haritadan; "BORSA:SEMBOL" da verilebilir.
"""
from __future__ import annotations

import logging

# Kanonik ad -> (borsa, sembol, görünen ad)
TV_SYMBOLS: dict[str, tuple[str, str, str]] = {
    "XAUUSD": ("OANDA", "XAUUSD", "Altın (ons/$)"),
    "XAGUSD": ("OANDA", "XAGUSD", "Gümüş (ons/$)"),
    "XPTUSD": ("OANDA", "XPTUSD", "Platin (ons/$)"),
    "BRENT": ("OANDA", "BCOUSD", "Brent petrol ($/varil)"),
    "WTI": ("OANDA", "WTICOUSD", "WTI petrol ($/varil)"),
    "NATGAS": ("OANDA", "NATGASUSD", "Doğalgaz"),
    "USDTRY": ("OANDA", "USDTRY", "Dolar/TL"),
    "EURTRY": ("OANDA", "EURTRY", "Euro/TL"),
    "EURUSD": ("OANDA", "EURUSD", "Euro/Dolar"),
    "GAUTRY": ("FX_IDC", "XAUTRYG", "Gram altın (TL)"),
    "BTCUSD": ("BITSTAMP", "BTCUSD", "Bitcoin ($)"),
    "ETHUSD": ("BITSTAMP", "ETHUSD", "Ethereum ($)"),
    "XU100": ("BIST", "XU100", "BIST 100"),
    "DXY": ("TVC", "DXY", "Dolar endeksi"),
    "US10Y": ("TVC", "US10Y", "ABD 10 yıllık tahvil faizi (%)"),
    "US02Y": ("TVC", "US02Y", "ABD 2 yıllık tahvil faizi (%)"),
    "TR10Y": ("TVC", "TR10Y", "Türkiye 10 yıllık tahvil faizi (%)"),
    "SPX": ("SP", "SPX", "S&P 500"),
    "NDX": ("NASDAQ", "NDX", "Nasdaq 100"),
    "VIX": ("TVC", "VIX", "VIX oynaklık endeksi"),
}

_tv = None


def _client():
    global _tv
    if _tv is None:
        logging.getLogger("tvDatafeed").setLevel(logging.ERROR)
        from tvDatafeed import TvDatafeed
        _tv = TvDatafeed()
    return _tv


def resolve(name: str) -> tuple[str, str, str] | None:
    n = name.strip().upper()
    if n in TV_SYMBOLS:
        return TV_SYMBOLS[n]
    if ":" in n:
        ex, sym = n.split(":", 1)
        return ex, sym, n
    return None


def fetch_series(name: str, n_bars: int = 70) -> dict | None:
    """{'name', 'dates': ['YYYY-MM-DD'...], 'closes': [...], 'source': 'TradingView EX:SYM'} ya da None."""
    r = resolve(name)
    if not r:
        return None
    ex, sym, label = r
    from tvDatafeed import Interval
    for attempt in range(2):
        try:
            df = _client().get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=n_bars)
            if df is not None and len(df) >= 2:
                dates = [str(i)[:10] for i in df.index]
                closes = [float(x) for x in df["close"]]
                opens, highs, lows = ([float(x) for x in df[k]] for k in ("open", "high", "low"))
                # aynı güne düşen çift satırları (seans saat farkı) tekille
                seen, d2, c2, o2, h2, l2 = set(), [], [], [], [], []
                for d, c, o, h, lo in zip(dates, closes, opens, highs, lows):
                    if d in seen:
                        c2[-1], h2[-1], l2[-1] = c, max(h2[-1], h), min(l2[-1], lo)
                        continue
                    seen.add(d)
                    d2.append(d)
                    c2.append(c)
                    o2.append(o)
                    h2.append(h)
                    l2.append(lo)
                return {"name": label, "dates": d2, "closes": c2, "opens": o2, "highs": h2, "lows": l2, "source": f"TradingView {ex}:{sym}"}
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning(f"TradingView {ex}:{sym} deneme {attempt + 1}: {e}")
            global _tv
            _tv = None
    return None
