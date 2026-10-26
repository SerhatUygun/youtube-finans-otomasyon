"""8 Ağu: TTS OKUMA NORMALİZASYONU — sayı/yüzde ifadelerini Türkçe okunuşa çevirir.
17 Eyl: para birimi sembolleri, sıra sayıları ve "S&P" gibi özel kısaltmalar eklendi
(izleyicinin "bu bir AI sesi" diye fark edip videoyu bırakmaması için).

Kök neden: CosyVoice/XTTS gibi TTS motorları rakamları (özellikle virgüllü/binlik
noktalı finans rakamlarını: "47,69", "%1,9", "6.170") ve $/₺/& gibi sembolleri
tutarsız/anlaşılmaz okuyor. Bu modül script'teki RAKAMLARI/SEMBOLLERİ DEĞİŞTİRMEZ —
sadece TTS'e giden metinde aynı ifadeyi Türkçe kelimelerle yazar (script.json,
altyazı, fact-check hep orijinal metinle kalır). Deterministik (LLM YOK) — bu yüzden
hiçbir sayıyı hatalı/başka bir değere çeviremez, sadece BİÇİMİNİ okunur hale getirir.

Desteklenen kalıplar: %N, yüzde N, binlik nokta ("7.745"), ondalık virgül ("47,69",
lider sıfırlı "78,05" -> "yetmiş sekiz virgül sıfır beş" ondalık anlamı korunur),
düz tamsayılar, tarihlerdeki gün/yıl (ay adı Türkçe kelime olduğu için dokunulmaz),
para birimi sembolleri (₺/$/€/£, önek ya da soneki fark etmez), sıra sayıları
("20." -> "yirminci"; sadece SONDAKİ bileşen çekimlenir, "21." -> "yirmi birinci"),
market_data.py'nin SYMBOLS sözlüğünden gelen "&" içeren özel isimler (_TERM_MAP).

Desteklenmeyen (bilinen sınırlama): saat/tarih formatı "20.09.2026" gibi noktalı
tam tarihler (bu pipeline'da tarihler zaten "20 Eylül 2026" -- ay adı kelime --
biçiminde üretiliyor, bu yüzden pratikte nadiren karşılaşılır).
"""
import re

_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
_SCALES = ["", "bin", "milyon", "milyar", "trilyon"]
_DIGIT_WORDS = ["sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]


def _spell_hundreds(n: int) -> str:
    parts = []
    h, r = divmod(n, 100)
    if h:
        parts.append("yüz" if h == 1 else f"{_ONES[h]} yüz")
    t, o = divmod(r, 10)
    if t:
        parts.append(_TENS[t])
    if o:
        parts.append(_ONES[o])
    return " ".join(parts)


def spell_int_tr(n: int) -> str:
    if n == 0:
        return "sıfır"
    sign = "eksi " if n < 0 else ""
    n = abs(n)
    chunks = []
    while n > 0:
        chunks.append(n % 1000)
        n //= 1000
    words = []
    for i in range(len(chunks) - 1, -1, -1):
        c = chunks[i]
        if c == 0:
            continue
        if i == 1 and c == 1:
            words.append("bin")  # "bir bin" değil, sadece "bin"
        else:
            words.append((_spell_hundreds(c) + " " + _SCALES[i]).strip())
    return sign + " ".join(words)


def _spell_frac(frac: str) -> str:
    # Baştaki sıfır ondalık basamak sayısını (ve dolayısıyla değeri) korumak için
    # tek tek okunur: "78,05" -> "sıfır beş" (aksi halde "beş" olup 78,5 ile
    # karışırdı). Baştaki sıfır yoksa doğal tam sayı okunuşu kullanılır.
    if len(frac) > 1 and frac[0] == "0":
        return " ".join(_DIGIT_WORDS[int(d)] for d in frac)
    return spell_int_tr(int(frac))


def _spell_token(token: str) -> str:
    if "," in token:
        int_part, frac_part = token.split(",", 1)
    else:
        int_part, frac_part = token, ""
    int_part = int_part.replace(".", "")
    out = spell_int_tr(int(int_part)) if int_part else "sıfır"
    if frac_part:
        out += " virgül " + _spell_frac(frac_part)
    return out


# Sıra önemli: binlik-nokta(+ondalık) -> düz ondalık -> düz tamsayı (alternation
# soldan sağa denenir; en spesifik/uzun kalıp önce olmalı).
_NUM_CORE = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+"
_NUM_TOKEN_RE = re.compile(_NUM_CORE)
_PERCENT_RE = re.compile(r"%\s*(\d{1,3}(?:\.\d{3})*(?:,\d+)?)")

# Para birimi sembolleri önek ("$47,69") ya da sonek ("47,69₺") olarak gelebilir;
# ikisi de aynı birim kelimesine (sayıdan SONRA, Türkçe'nin doğal söyleyişiyle) çevrilir.
_CURRENCY_WORDS = {"₺": "lira", "$": "dolar", "€": "euro", "£": "sterlin"}
_CURRENCY_RE = re.compile(
    rf"(?:([₺$€£])\s*({_NUM_CORE}))|(?:({_NUM_CORE})\s*([₺$€£]))"
)


def _spell_currency(m: re.Match) -> str:
    if m.group(1):
        sym, num = m.group(1), m.group(2)
    else:
        num, sym = m.group(3), m.group(4)
    return _spell_token(num) + " " + _CURRENCY_WORDS[sym]


# Sıra sayıları: "20." -> "yirminci". Sadece rakamdan hemen sonra nokta gelip
# ardından BAŞKA bir rakam gelmeyen durumlarda tetiklenir -- böylece "7.745" gibi
# binlik-nokta ayracı olan sayılarla (nokta hemen ardından 3 rakam) karışmaz.
_ORDINAL_RE = re.compile(r"\b(\d{1,3})\.(?!\d)")

# Türkçe'de bileşik sayıların sıra sayısı SADECE SON kelimeden çekimlenir
# ("yirmi birinci", "yirminci" değil) -- bu yüzden kardinal okunuşu üretip yalnızca
# son kelimeyi bu tablodan değiştiriyoruz.
_ORDINAL_WORD_MAP = {
    "sıfır": "sıfırıncı", "bir": "birinci", "iki": "ikinci", "üç": "üçüncü",
    "dört": "dördüncü", "beş": "beşinci", "altı": "altıncı", "yedi": "yedinci",
    "sekiz": "sekizinci", "dokuz": "dokuzuncu",
    "on": "onuncu", "yirmi": "yirminci", "otuz": "otuzuncu", "kırk": "kırkıncı",
    "elli": "ellinci", "altmış": "altmışıncı", "yetmiş": "yetmişinci",
    "seksen": "sekseninci", "doksan": "doksanıncı",
    "yüz": "yüzüncü", "bin": "bininci", "milyon": "milyonuncu", "milyar": "milyarıncı",
}


def _spell_ordinal_tr(n: int) -> str:
    words = spell_int_tr(n).split(" ")
    words[-1] = _ORDINAL_WORD_MAP.get(words[-1], words[-1] + "ıncı")
    return " ".join(words)


# market_data.py'nin SYMBOLS sözlüğünden gelen, "&" gibi TTS'i bozan özel isimler.
# SYMBOLS'a "&" içeren yeni bir isim eklenirse burada da karşılığı eklenmeli.
_TERM_MAP = [
    ("S&P 500", "es end pi beş yüz"),
]


def _apply_term_map(text: str) -> str:
    for term, spoken in _TERM_MAP:
        text = text.replace(term, spoken)
    # Tabloda olmayan herhangi bir "X & Y" kalıbı için genel yedek kural.
    return text.replace("&", " ve ")


def normalize_for_tts(text: str) -> str:
    """TTS'e gönderilecek metni döner; script.json'daki orijinal metne dokunma,
    bu fonksiyonun çıktısını SADECE ses sentezine ver."""
    if not text:
        return text
    text = _apply_term_map(text)
    text = _CURRENCY_RE.sub(_spell_currency, text)
    text = _ORDINAL_RE.sub(lambda m: _spell_ordinal_tr(int(m.group(1))), text)
    text = _PERCENT_RE.sub(lambda m: "yüzde " + _spell_token(m.group(1)), text)
    text = _NUM_TOKEN_RE.sub(lambda m: _spell_token(m.group(0)), text)
    return text


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    samples = [
        "Dolar bugün 47,69 Türk lirası seviyesinden işlem gördü.",
        "Bu rakam son bir ay içinde yaklaşık %1,9 oranında artışa işaret ediyor.",
        "7 Ağustos 2026 itibarıyla derlenen doğrulanmış verilerle.",
        "Gram altının o dönemde 6.170 lira bandında dengelendiği belirtilmişti.",
        "S&P 500 endeksi bugün 7.745 dolar seviyesinden işlem gördü.",
        "WTI türü petrol bugün 78,05 dolar seviyesinden işlem gördü.",
        "14 günlük göreceli güç endeksi yani RSI 14,95 seviyesinde bulunuyor.",
        "yıl sonu enflasyonunun yüzde 30 civarında olması bekleniyor.",
        "Dolar bugün $47,69 seviyesinden işlem gördü.",
        "Gram altın ₺6.170 bandında dengelendi.",
        "S&P 500 endeksi bugün 7.745 dolar seviyesinden işlem gördü.",
        "Bu ayın 20. günü açıklanan veriler beklentileri aştı.",
        "21. yüzyılın en büyük faiz artışı olarak kayıtlara geçti.",
        "Kar ve zarar (P&L) tablosunda 3. çeyrek verileri paylaşıldı.",
    ]
    for s in samples:
        print(f"{s}\n  -> {normalize_for_tts(s)}\n")
