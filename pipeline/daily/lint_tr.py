"""10 Eki: Türkçe başlık/kapak çifti ve Shorts kancası denetimi (yt-package / yt-script fikirlerinin Türkçe uyarlaması).

Orijinal İngilizce araçlar `you/why/how` arar ve [a-z] regex'i Türkçe harfleri atar; Türkçede yanlış puan verirler.
Bu modül ek kökleri (öneki karşılaştırma) ve Türkçe küçük harf kurallarını (İ/I) bilir. Yalnız UYARI üretir, hiçbir şeyi bloklamaz.

    from pipeline.daily.lint_tr import title_lint, hook_lint
"""
from __future__ import annotations

import re

DESKTOP, MOBILE = 60, 40
_STOP = {"bir", "bu", "şu", "ve", "ile", "için", "mi", "mı", "mu", "mü", "ne", "neden", "nasıl", "de", "da", "ki", "en", "çok", "daha",
         "gibi", "ama", "veya", "ya", "o", "ben", "sen", "biz", "siz", "hangi", "kim", "her", "hiç"}
_VAGUE = {"inanılmaz", "muhteşem", "şok", "efsane", "mükemmel", "olağanüstü", "korkunç", "büyük", "dev", "kesin", "garanti", "sır", "sırrı"}
_ACRONYM_OK = {"FED", "TCMB", "ABD", "TÜİK", "BIST", "ONS", "TL", "USD", "EUR", "BTC", "ETH", "AB", "KAP", "SPK", "BDDK"}
# kanalın konu sözcükleri: başlık ve kapakta birlikte geçmesi doğal, "tekrar" sayılmaz
_TOPIC = {"altın", "gram", "fed", "faiz", "dolar", "borsa", "bitco", "ethe", "gümüş", "euro", "kripto", "enfla", "merke", "banka", "tcmb", "abd", "lira", "tl"}
_GREETING = ("merhaba", "selam", "hoş geldin", "hoşgeldin", "arkadaşlar", "herkese")
_ADDRESS = re.compile(r"\b(sen|senin|sana|seni|paran\w*|cebin\w*|birikim\w*|tasarruf\w*|maaş\w*|liran\w*)\b")
_STAKES = re.compile(r"\b(kayb\w*|eri\w*|risk\w*|tehlik\w*|düş\w*|kriz\w*|tuzak\w*|dikkat|uyarı\w*|batı\w*|kaybet\w*|zarar\w*|çök\w*|son)\b")
_CURIOSITY = re.compile(r"\b(neden|nasıl|ne|hangi\w*|kimse|aslında|peki|ama|gerçek\w*|sebep\w*|cevap\w*|nereden|nerede)\b")
_NUM = re.compile(r"\d[\d.,]*\s?(%|bin|milyon|milyar|tl|lira|dolar)?|%\s?\d+", re.I)


def tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _words(s: str) -> list[str]:
    return re.findall(r"[a-zçğıöşü0-9%']+", tr_lower(s))


def _stem(w: str) -> str:
    return w[:5]  # Türkçe ek çeşitliliği: "altın/altına/altının" -> "altın"/"altın"/"altın"


def title_lint(title: str, thumb_text: str | None = None) -> dict:
    """{'score','issues':[(kod,mesaj)],'good':[...]} — başlık+kapak yazısı BİR ÇİFT olarak."""
    t = title.strip()
    n = len(t)
    issues: list[tuple[str, str]] = []
    good: list[str] = []
    if n > 100:
        issues.append(("length", f"{n} karakter — YouTube sınırı 100"))
    elif n > 70:
        issues.append(("length", f"{n} karakter — masaüstü aramada ~{DESKTOP}'tan sonrası kesilir"))
    else:
        good.append(f"{n} karakter")
    if n > MOBILE:
        head = t[:MOBILE].rsplit(" ", 1)[0]
        issues.append(("mobile", f'mobil akışta "{head}…" görünür — konu bu kısımda mı?'))
    caps = [w for w in re.findall(r"[A-ZÇĞİÖŞÜ]{4,}", t) if w not in _ACRONYM_OK]
    if len(caps) > 2:
        issues.append(("shouting", f"{len(caps)} BÜYÜK HARFLİ kelime ({', '.join(caps[:3])}) — spam gibi okunur"))
    vague = [w for w in _words(t) if w in _VAGUE]
    if vague:
        issues.append(("vague", f"{', '.join(sorted(set(vague)))} — rakam, isim ya da tarihle değiştir"))
    if _NUM.search(t):
        good.append("somut rakam var")
    else:
        issues.append(("no-number", "başlıkta rakam/tarih/isim yok — en güvenilir tek iyileştirme"))
    if thumb_text:
        tw = {_stem(w) for w in _words(t) if w not in _STOP and len(w) > 2}
        hw = {_stem(w) for w in _words(thumb_text) if w not in _STOP and len(w) > 2}
        shared = {x for x in (tw & hw) if x not in _TOPIC}
        if shared:
            issues.append(("duplicate", f"kapak yazısı başlığı tekrar ediyor ({', '.join(sorted(shared))}) — kapak başlığın söylemediğini söylemeli"))
        else:
            good.append("başlık ve kapak farklı şey söylüyor")
        if len(_words(thumb_text)) > 4:
            issues.append(("thumb-length", f"kapakta {len(_words(thumb_text))} kelime — küçük boyutta 3-4 yeter"))
    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return {"title": t, "score": score, "issues": issues, "good": good}


def hook_lint(text: str) -> dict:
    """İlk cümle (kanca) 5 özellikte 0-100: somutluk, hitap, risk, merak, kısalık. Karar = %60 ortalama + %40 en zayıf halka."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip()) if text.strip() else [""]
    first = parts[0]
    if len(_words(first)) < 5 and len(parts) > 1:  # "%17!" gibi damga cümlesi: kanca bir sonraki cümleyle birlikte
        first = f"{first} {parts[1]}"
    low = tr_lower(first)
    w = _words(first)
    nums = len(_NUM.findall(first))
    spec = 30 + nums * 25 - 12 * sum(1 for x in w if x in _VAGUE)
    addr = 26 + 22 * len(_ADDRESS.findall(low))
    stakes = 22 + 26 * len(_STAKES.findall(low)) + (12 if nums else 0)
    cur = 24 + 17 * len(_CURIOSITY.findall(low)) + (18 if first.rstrip().endswith("?") else 0)
    n = len(w)
    brev = 90 if n <= 14 else 70 if n <= 20 else 45 if n <= 26 else 20
    greet = low.startswith(_GREETING)
    props = {"specificity": spec, "address": addr, "stakes": stakes, "curiosity": cur, "brevity": brev}
    props = {k: max(0, min(100, v)) for k, v in props.items()}
    mean = sum(props.values()) / len(props)
    score = round(0.6 * mean + 0.4 * min(props.values()))
    if greet:
        score = max(0, score - 25)
    return {"hook": first, "score": score, "props": props, "greeting": greet, "words": n}


def lint_messages(title: str | None = None, thumb_text: str | None = None, hook_text: str | None = None, where: str = "") -> list[str]:
    """validate.py için: yalnız eyleme dönük UYARI metinleri."""
    out: list[str] = []
    if title:
        r = title_lint(title, thumb_text)
        for code, msg in r["issues"]:
            if code in ("duplicate", "vague", "no-number", "shouting", "thumb-length"):
                out.append(f"{where}başlık '{title[:50]}': {msg}")
    if hook_text:
        h = hook_lint(hook_text)
        if h["greeting"]:
            out.append(f"{where}kanca selamla başlıyor — ilk cümle kanca olmalı")
        weakest = min(h["props"], key=h["props"].get)
        if h["score"] < 32:
            names = {"specificity": "rakam/somutluk", "address": "izleyiciye hitap", "stakes": "risk/kayıp", "curiosity": "merak boşluğu", "brevity": "kısalık"}
            out.append(f"{where}kanca zayıf ({h['score']}/100, en zayıf: {names[weakest]}): \"{h['hook'][:70]}\"")
    return out
