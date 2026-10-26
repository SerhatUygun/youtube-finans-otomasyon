"""Canlı piyasa özeti — günlük Claude araştırmasının rakam kaynağı (uydurma sayı yerine).

BİRİNCİL KAYNAK TradingView (OANDA spot vb., pipeline/tv_data.py): XAUUSD XAGUSD BRENT WTI USDTRY EURTRY GAUTRY BTCUSD
ETHUSD XU100 DXY US10Y US02Y TR10Y SPX NDX VIX (ya da "BORSA:SEMBOL"). Yahoo sembolleri (GC=F, ^TNX…) yalnızca yedek.
Kullanım: python tools/market_snapshot.py XAUUSD XAGUSD BTCUSD BRENT USDTRY XU100 [--range 3mo] [--json out.json]
Her sembol için: son kapanış + tarihi, 1 gün / 5 gün / 1 ay % değişim, dönem en yüksek/en düşük (tarihli),
ve --json verilirse tam seri ({d:[...], c:[...]}) — Remotion grafikleri bu dosyadan çizilir.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import market_data as md  # noqa: E402
from pipeline import tv_data  # noqa: E402

BARS = {"1mo": 25, "3mo": 70, "6mo": 135, "1y": 260, "2y": 520}


def pct(a: float, b: float) -> float:
    return round((a / b - 1) * 100, 2) if b else 0.0


def snapshot(symbols: list[str], range_: str = "3mo") -> dict:
    out = {}
    for s in symbols:
        r = tv_data.fetch_series(s, BARS.get(range_, 70)) if tv_data.resolve(s) else None
        if not r:
            r = md.fetch_series(s, range_, "1d")
            if r:
                r["source"] = f"Yahoo {s} (yedek)"
        if not r or not r.get("closes"):
            out[s] = {"error": "veri yok"}
            continue
        d = [str(x)[:10] for x in r["dates"]]
        c = [float(x) for x in r["closes"]]
        hi = max(range(len(c)), key=lambda i: c[i])
        lo = min(range(len(c)), key=lambda i: c[i])
        out[s] = {
            "name": r.get("name"), "last": round(c[-1], 4), "last_date": d[-1],
            "chg_1d_pct": pct(c[-1], c[-2]) if len(c) > 1 else None,
            "chg_5d_pct": pct(c[-1], c[-6]) if len(c) > 5 else None,
            "chg_1m_pct": pct(c[-1], c[-22]) if len(c) > 21 else None,
            "high": {"v": round(c[hi], 4), "d": d[hi]}, "low": {"v": round(c[lo], 4), "d": d[lo]},
            "source": r.get("source", "Yahoo"),
            "series": {"d": d, "c": [round(x, 4) for x in c]},
        }
        # mum grafiği (Candles şablonu) için OHLC — yalnız TradingView'dan gelir
        if all(len(r.get(k) or []) == len(c) for k in ("opens", "highs", "lows")):
            out[s]["series"].update({k[0]: [round(float(x), 4) for x in r[k]] for k in ("opens", "highs", "lows")})
    return out


def main():
    args = sys.argv[1:]
    range_ = "3mo"
    jpath = None
    if "--range" in args:
        i = args.index("--range")
        range_ = args[i + 1]
        del args[i:i + 2]
    if "--json" in args:
        i = args.index("--json")
        jpath = Path(args[i + 1])
        del args[i:i + 2]
    snap = snapshot(args, range_)
    for s, v in snap.items():
        if "error" in v:
            print(f"{s}: {v['error']}")
            continue
        print(f"{s} ({v['name']} · {v['source']}): {v['last']} [{v['last_date']}]  1g {v['chg_1d_pct']}%  5g {v['chg_5d_pct']}%  1a {v['chg_1m_pct']}%  "
              f"zirve {v['high']['v']} ({v['high']['d']})  dip {v['low']['v']} ({v['low']['d']})")
        if s.endswith("=F") and v["chg_1d_pct"] is not None and abs(v["chg_1d_pct"]) >= 5:
            print(f"  ⚠️ {s}: son gün %{v['chg_1d_pct']} — VADELİ KONTRAT DEVRİ olabilir (Yahoo sürekli seri). Son değeri haber kaynağındaki "
                  "uzlaşma fiyatıyla karşılaştır; tutmuyorsa bu sembolün son değerini ekranda kullanma.")
    if jpath:
        jpath.parent.mkdir(parents=True, exist_ok=True)
        jpath.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
