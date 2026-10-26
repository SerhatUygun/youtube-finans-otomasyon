#!/usr/bin/env python3
"""hookscore_tr.py — Türkçe kanca puanlayıcı (yt-script/hookscore.py'nin Türkçe uyarlaması).

Beş özellik 0-100; karar = %60 ortalama + %40 en zayıf (zayıf halka kancayı sızdırır).
Düşük puan "tekrar bak" demektir; yüksek puan garanti değildir.

    python tools/hookscore_tr.py --hook "tek cümle"
    python tools/hookscore_tr.py kancalar.txt          # satır başına bir kanca, sıralı
    python tools/hookscore_tr.py --daily output/daily-20261021   # props_long.json ilk segmenti + varyantlar
    ... --json                                         # makine okunur
"""
import json, re, sys
from pathlib import Path

LOW = str.maketrans("İIÇĞÖŞÜ", "iıçğöşü")
def low(t): return t.translate(LOW).lower()

def words(t): return re.findall(r"[a-zçğıöşü0-9'%$.,]+", low(t))

# Seslendirme metni rakamları yazıyla yazar ("yüzde yetmiş"), ikisini de say
SAYI = r"(sıfır|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|on|yirmi|otuz|kırk|elli|altmış|yetmiş|seksen|doksan|yüz|bin|milyon|milyar|trilyon)"
CONCRETE = re.compile(r"(\d[\d.,]*\s?%?|%\s?\d+|\byüzde\s+" + SAYI + r"|\b" + SAYI + r"\s+(lira|dolar|kuruş|gram|ons|puan|baz|yıl|ay|gün|hafta|saat|dakika|kat)\w*"
                      r"|\b(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\b|\b(19|20)\d\d\b)")
YOU = re.compile(r"\b(sen|seni|sana|senin|siz|sizin|size|(kazanc|kazan|para|altın|birikim|yatırım|maaş|kredi|ceb|cep|bütçe|kira|hesab|borc|evin|araban)\w*(ın|in|un|ün|n|ndeki|ndaki)\b|\w+(ının|inin|unun|ünün|nın|nin|nun|nün)\b(?=\s)|\w+(sın|sin|sun|sün|sınız|siniz)\b)")
STAKE = re.compile(r"\b(kayb\w*|kaybet\w*|eri\w*|yedi|yiyor|maliyet\w*|zarar\w*|batt?\w*|düş\w*|çök\w*|önce\w*|dur\w*|asla|tehlike\w*|risk\w*|kaçır\w*|enflasyon\w*|pahal\w*|sınav\w*)")
CURIOSITY = re.compile(r"\b(neden|niye|nasıl|ne\b|hangi\w*|kim\w*|ama|fakat|oysa|aslında|kimse|hiç|bile|meğer|sanıldığı|değil\s+mi|\w+\s+mı\b|\w+\s+mi\b)")
CLOSED = re.compile(r"\b(çünkü|bu yüzden|yani|demek ki|bu nedenle)\b")
FILLER = {"merhaba","selam","arkadaşlar","hoş","geldiniz","bugün","videoda","abone","kanal","kanalımıza","işte","şimdi","evet","aslında"}
VAGUE = {"inanılmaz","müthiş","çılgın","şok","şoke","dev","muazzam","büyük","efsane","olağanüstü","gizli","sır","kesin","mutlaka"}

def specificity(t):
    w = words(t)
    if not w: return 0
    s = 34 + len(CONCRETE.findall(low(t))) * 22 - sum(x in VAGUE for x in w) * 16 - sum(x in FILLER for x in w) * 5
    s += min(18, 6 * sum(1 for x in t.split()[1:] if x[:1].isupper()))   # özel isimler (TCMB, Fed, Merkez Bankası)
    return max(0, min(100, s))

def address(t):
    l = low(t); n = len(YOU.findall(l))
    first = 30 if YOU.search(" ".join(l.split()[:6])) else 0
    return max(0, min(100, 26 + n * 20 + first))

def stakes(t):
    l = low(t)
    return max(0, min(100, 22 + len(STAKE.findall(l)) * 26 + (14 if CONCRETE.search(l) else 0)))

def curiosity(t):
    l = low(t)
    q = 18 if "?" in t else 0
    closed = -18 if CLOSED.search(l) else 0
    return max(0, min(100, 24 + len(CURIOSITY.findall(l)) * 17 + q + closed))

def brevity(t):
    n = len(t.split())
    if n == 0: return 0
    if 9 <= n <= 24: return 100
    if n < 9: return max(30, 100 - (9 - n) * 11)
    return max(10, 100 - (n - 24) * 7)

PROPS = [("SOMUTLUK", specificity), ("HİTAP", address), ("RİSK", stakes), ("MERAK", curiosity), ("KISALIK", brevity)]
FIX = {"SOMUTLUK": "bir sıfatı rakam, isim ya da tarihle değiştir",
       "HİTAP": "ilk 6 kelimede 'sen/paran/cebindeki' de",
       "RİSK": "izleyicinin bunu bilmezse ne kaybedeceğini söyle",
       "MERAK": "cümlenin kendi kendine cevap veren yarısını sil",
       "KISALIK": "9–24 kelime; sesli oku, nefesin bittiği yerde kes"}

def band(v): return "GÜÇLÜ" if v >= 72 else "İDARE EDER" if v >= 55 else "ZAYIF"

def score(t):
    p = {n: fn(t) for n, fn in PROPS}
    v = list(p.values())
    verdict = round(0.6 * sum(v) / len(v) + 0.4 * min(v))
    return {"hook": t.strip(), "properties": p, "verdict": verdict, "band": band(verdict),
            "weakest": min(p, key=p.get), "fix": FIX[min(p, key=p.get)]}

def first_sentences(text, maxw=30):
    """Segmentin kanca kısmı: ilk 1-2 cümle, en fazla ~30 kelime."""
    sents = re.split(r"(?<=[.?!])\s+", text.strip())
    out = sents[0]
    if len(out.split()) < 9 and len(sents) > 1: out += " " + sents[1]
    return " ".join(out.split()[:maxw])

def from_daily(d):
    d = Path(d); hooks = []
    for name in ("video.json", "props_long.json", "script.json"):
        f = d / name
        if not f.exists(): continue
        j = json.loads(f.read_text(encoding="utf-8-sig"))
        segs = j.get("segments") or j.get("video", {}).get("segments") or []
        if segs:
            t = segs[0].get("tts") or segs[0].get("text") or ""
            if t: hooks.append(("A", first_sentences(t)))
        for i, hv in enumerate(j.get("hook_variants") or [], 1):
            if isinstance(hv, dict) and hv.get("segments"): hv = hv["segments"][0]
            t = (hv.get("tts") or hv.get("text") or "") if isinstance(hv, dict) else str(hv)
            if t: hooks.append(("BC"[i - 1] if i <= 2 else str(i), first_sentences(t)))
        if hooks: break
    return hooks

def main():
    a = sys.argv[1:]; as_json = "--json" in a; a = [x for x in a if x != "--json"]
    if "--hook" in a: items = [("", a[a.index("--hook") + 1])]
    elif "--daily" in a: items = from_daily(a[a.index("--daily") + 1])
    elif a and Path(a[0]).exists(): items = [("", l) for l in Path(a[0]).read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    else: print(__doc__); sys.exit(1)
    out = [dict(score(t), label=lab) for lab, t in items]
    if as_json: print(json.dumps(out, ensure_ascii=False, indent=1)); return
    for r in sorted(out, key=lambda r: -r["verdict"]):
        print(f"\n  {('['+r['label']+'] ') if r['label'] else ''}{r['hook']}")
        for k, v in r["properties"].items(): print(f"    {k:<10} {v:3d}  {'#' * (v // 5)}")
        print(f"    {'KARAR':<10} {r['verdict']:3d}  {r['band']}\n    en zayıf   {r['weakest']} — {r['fix']}")

if __name__ == "__main__":
    main()
