"""Politika koruması — YouTube para kazanma + AI beyanı politikalarına uyum.

Kodun bilinçli karar vermesi gereken YÜKSEK riskli iki alan var:

1) HASSAS KONULARDA AI "UZMAN PERSONASI" (Tem 2026'da eklenen ayrı ihlal kategorisi:
   "AI Personas Related to Sensitive Topics"). Sağlık / finans / hukuk / siyaset
   konularında anlatıcının bir uzman/otorite gibi (doktor, finans uzmanı, avukat)
   konuşması ihlaldir. Bu modül konuyu sınıflar ve script üretimine:
     - "uzman değil, KAYNAK AKTARAN bilgilendirici" tonu (sensitive_guidance),
     - çıktı diline uygun kısa SORUMLULUK REDDİ (disclaimer_line)
   enjekte edilmesini sağlar.

2) AI BEYANI (altered/synthetic content disclosure). Gerçekçi sentetik içerik
   Studio/API'de işaretlenmeli. Yükleme (s09_upload) zaten
   status.containsSyntheticMedia=True gönderiyor; bu modül yalnızca şeffaflık
   metni ve politika notu üretir — beyanın kendisi upload aşamasında yapılır.

Kaynaklar (kullanıcı tarafından sağlanan resmi sayfalar):
- Para kazanma politikaları:  https://support.google.com/youtube/answer/1311392
- AI/sentetik içerik beyanı:  https://support.google.com/youtube/answer/14328491
- Yaratıcı sorumlulukları:     https://support.google.com/youtube/answer/7650329

NOT: Politikalar son 12 ayda iki kez yeniden adlandırıldı; strateji kurmadan önce
1. kaynağın en üstündeki "son güncellemeler" bölümü kontrol edilmeli.
"""

# Anahtar kelimeler kabadır ama amaç bir sınıflandırıcı değil, GÜVENLİ TARAFTA kalıp
# hassas olabilecek konularda uzman-persona tonunu kapatmaktır (yanlış pozitif zararsız:
# yalnızca tonu nötrler ve bir disclaimer ekler).
_SENSITIVE_KEYWORDS: dict[str, list[str]] = {
    "health": [
        "sağlık", "saglik", "hastalık", "hastalik", "tedavi", "ilaç", "ilac", "doktor",
        "kanser", "diyet", "kilo", "zayıfla", "zayifla", "vitamin", "aşı", "asi", "hamile",
        "depresyon", "kaygı", "kaygi", "psikoloji", "beslenme", "semptom", "teşhis", "teshis",
        "health", "disease", "illness", "medical", "medicine", "drug", "doctor", "cancer",
        "diet", "weight loss", "vaccine", "symptom", "diagnosis", "mental health", "therapy",
        "nutrition", "supplement", "pregnan",
    ],
    "finance": [
        "finans", "para", "yatırım", "yatirim", "borsa", "hisse", "kripto", "bitcoin",
        "ethereum", "dolar", "euro", "altın", "altin", "gümüş", "gumus", "faiz", "kredi",
        "ekonomi", "enflasyon", "vergi", "emeklilik", "tasarruf", "forex",
        "finance", "money", "invest", "stock", "crypto", "forex", "trading", "trader",
        "inflation", "interest rate", "loan", "mortgage", "retirement", "savings",
        "tax", "profit", "portfolio", "dividend",
    ],
    "law": [
        "hukuk", "yasa", "kanun", "dava", "mahkeme", "avukat", "ceza", "suç", "suc",
        "boşanma", "bosanma", "miras", "sözleşme", "sozlesme", "tazminat", "haklar",
        "law", "legal", "lawyer", "attorney", "court", "lawsuit", "sue", "rights",
        "contract", "divorce", "inheritance", "liability", "regulation",
    ],
    "politics": [
        "siyaset", "politika", "seçim", "secim", "hükümet", "hukumet", "parti",
        "cumhurbaşkanı", "cumhurbaskani", "başkan", "baskan", "milletvekili", "oy",
        "protesto", "savaş", "savas", "çatışma", "catisma", "göçmen", "gocmen",
        "politic", "election", "government", "president", "senate", "parliament",
        "vote", "protest", "war", "conflict", "immigra", "policy maker", "campaign",
    ],
}

# Çıktı diline uygun kısa sorumluluk reddi (advice DEĞİL bilgi). Kategori başına.
_DISCLAIMERS: dict[str, dict[str, str]] = {
    "tr": {
        "health": "Bu içerik yalnızca genel bilgilendirme amaçlıdır, tıbbi tavsiye değildir; bir sağlık uzmanına danışın.",
        "finance": "Bu içerik yalnızca genel bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.",
        "law": "Bu içerik yalnızca genel bilgilendirme amaçlıdır, hukuki tavsiye değildir; bir avukata danışın.",
        "politics": "Bu içerik yalnızca bilgilendirme amaçlıdır; kaynaklara dayanır ve kişisel görüş bildirmez.",
    },
    "en": {
        "health": "This content is for general information only and is not medical advice; consult a qualified professional.",
        "finance": "This content is for general information only and is not financial or investment advice.",
        "law": "This content is for general information only and is not legal advice; consult a qualified professional.",
        "politics": "This content is for information only; it is based on sources and does not express personal opinion.",
    },
}

_CATEGORY_LABEL = {
    "health": "sağlık", "finance": "finans", "law": "hukuk", "politics": "siyaset",
}


import re


def _tr_lower(s: str) -> str:
    """Türkçe-güvenli küçük harfe çevirme. Python'un düz .lower()'ı 'İ' harfini
    'i' + BİRLEŞTİRİCİ NOKTA (U+0307) ikilisine çevirir; bu görünmez işaret \\w
    SAYILMADIĞI için kelime ortasında sahte bir sınır yaratır (ör. 'PİYASA' ->
    'pi̇yasa' -> \\byasa 'piyasa' içindeki 'yasa'ya YANLIŞLIKLA eşleşir -> hukuk
    kategorisi hatalı tetiklenir). Önce İ/I'yı Türkçe karşılığına çevirip SONRA
    .lower() çağırmak bu ikiliyi hiç oluşturmaz.
    """
    return s.replace("İ", "i").replace("I", "ı").lower()


# Kelime-SINIRI eşleşmesi: "yatırım" -> "yatırımı" (ek) yakalanır ama kelime İÇİNDE gömülü
# eşleşmeler (ör. "maaşı" içindeki "aşı", "boyut" içindeki "oy") YANLIŞ pozitif üretmez.
# \b Python re'de Unicode \w kullanır; Türkçe ş/ç/ı harfleri de kelime karakteri sayılır.
#
# KISA/JENERİK köklerin ÖNEK (prefix) eşleşmesi -- finans videolarında sürekli geçen
# sıradan kelimelerin BAŞINDA yanlışlıkla yakalanır: "oy" -> "oynaklık" (volatilite!)/
# "oyuncak"/"oydu"; "asi" -> "asistan"/"asimetrik"/"asit"; "kilo" -> "kilogram"/
# "kilometre"/"kilovat"; "suc" (suç'un ASCII hali) -> "sucuk". Bunlar TAM KELİME
# olmadıkça eşleşmemeli (ek yakalama faydası bu kısa köklerde çakışma riskinden düşük).
_WHOLE_WORD_ONLY = {"oy", "asi", "kilo", "suc"}
# "aşı" (sağlık): "aşırı" ("RSI aşırı satım/alım" -- piyasa teknik analiz metninde
# sürekli geçer) kelimenin kendisi bir sınırdan BAŞLADIĞI için normalde eşleşirdi;
# negatif ileri-bakışla bu spesifik çakışma dışlanır (diğer ek'ler -- aşılar, aşıyı
# vb. -- hâlâ yakalanır).
_SENSITIVE_PATTERNS: dict[str, "re.Pattern"] = {
    cat: re.compile("|".join(
        r"\başı(?!rı)" if w == "aşı"
        else (r"\b" + re.escape(w) + r"\b") if w in _WHOLE_WORD_ONLY
        else r"\b" + re.escape(w)
        for w in words
    ))
    for cat, words in _SENSITIVE_KEYWORDS.items()
}


def classify_topic(*texts: str) -> list[str]:
    """Verilen metin(ler)de eşleşen hassas kategori listesini döndürür (boş = hassas değil)."""
    blob = _tr_lower(" ".join(t for t in texts if t))
    return [cat for cat, pat in _SENSITIVE_PATTERNS.items() if pat.search(blob)]


def is_sensitive(*texts: str) -> bool:
    return bool(classify_topic(*texts))


def sensitive_guidance(categories: list[str]) -> str:
    """Hassas konu tespit edildiğinde script üretim prompt'una eklenecek talimat (İngilizce —
    prompt'lar İngilizce). Anlatıcıyı UZMAN persona olmaktan çıkarır, kaynağa dayandırır."""
    if not categories:
        return ""
    cats = ", ".join(categories)
    return (
        f"\n\nSENSITIVE TOPIC DETECTED ({cats}). YouTube prohibits AI personas that act as "
        "experts on sensitive topics — follow these compliance rules strictly:\n"
        "- Do NOT present the narrator as a personal expert, professional or authority. "
        "Never say or imply 'as a doctor / financial advisor / lawyer / analyst' or use "
        "first-person expert claims.\n"
        "- Attribute factual claims to their source ('according to ...'); present figures as "
        "reported information, never as personal opinion, prediction or recommendation.\n"
        "- Do NOT give personalized medical, financial, legal or investment ADVICE, and do NOT "
        "recommend to buy/sell/treat/vote. Keep it neutral, general and informational.\n"
    )


def disclaimer_line(categories: list[str], language: str = "en") -> str:
    """Açıklamaya eklenecek kısa sorumluluk reddi (çıktı dilinde). Kategori bazlı, tekilleştirilmiş."""
    if not categories:
        # Finans kanalı varsayılanı: boşsa bile genel bilgilendirme disclaimer'ı döndür
        categories = ["finance"]
    lang = language if language in _DISCLAIMERS else "en"
    seen, lines = set(), []
    for c in categories:
        d = _DISCLAIMERS[lang].get(c)
        if d and d not in seen:
            seen.add(d)
            lines.append(d)
    return " ".join(lines)


def get_overlay_disclaimer_text(categories: list[str] | None = None, language: str = "tr") -> str:
    """Video üstünde küçük yazı olarak görünecek kısa disclaimer."""
    if language == "tr":
        return "Bilgilendirme Amaçlıdır • Yatırım Tavsiyesi Değildir"
    return "For Informational Purposes Only • Not Financial Advice"


def append_disclaimer(description: str, categories: list[str], language: str = "en") -> str:
    """Açıklamanın sonuna disclaimer'ı ekler (zaten varsa tekrar etmez)."""
    d = disclaimer_line(categories, language)
    if not d or d in (description or ""):
        return description
    base = (description or "").rstrip()
    return f"{base}\n\n⚠️ {d}".strip()


def build_full_description(
    description: str,
    sources: list[str] | None = None,
    categories: list[str] | None = None,
    language: str = "tr",
) -> str:
    """YouTube açıklaması için politika uyumlu, kaynaklı ve şeffaf tam metin oluşturur."""
    cats = categories or ["finance"]
    desc = (description or "").strip()

    # İDEMPOTENT KORUMA: generate_grounded_script zaten bir kez wrap ediyor, sonra
    # generate_researched_script kaynaklarla birlikte TEKRAR wrap ediyordu -> AI beyanı/
    # yasal uyarı/kaynak bloğu açıklamada İKİ KEZ görünüyordu (18 Ağu'da canlı çıktıda
    # yakalandı). Girdi zaten bu fonksiyonla üretilmişse (AI beyanı imzasını taşıyorsa)
    # tekrar sarmalamak yerine olduğu gibi döndür.
    if "🤖" in desc and ("📌" in desc or "⚠️" in desc):
        return desc

    parts = [desc]
    
    # 1. Kaynaklar
    if sources:
        clean_sources = [s.strip() for s in sources if s and s.strip()]
        if clean_sources:
            header = "📌 Kaynaklar & Veriler:" if language == "tr" else "📌 Sources & Data:"
            source_lines = "\n".join(f"- {s}" for s in clean_sources[:6])
            parts.append(f"{header}\n{source_lines}")
            
    # 2. Şeffaf AI Beyanı
    ai_note = (
        "🤖 Bu içerik, güncel piyasa araştırmaları ve yapay zeka araçları desteğiyle hazırlanmıştır."
        if language == "tr" else
        "🤖 This content was created with the help of current market research and AI tools."
    )
    parts.append(ai_note)
    
    # 3. Yasal Uyarı / Sorumluluk Reddi
    d_text = disclaimer_line(cats, language)
    if d_text:
        warn_hdr = "⚠️ Yasal Uyarı:" if language == "tr" else "⚠️ Disclaimer:"
        parts.append(f"{warn_hdr} {d_text}")
        
    return "\n\n".join(parts).strip()


def generate_pinned_comment(topic: str, language: str = "tr") -> str:
    """İzleyici etkileşimini ve topluluk katılımını artıracak sabitlenmiş yorum metni."""
    if language == "tr":
        return (
            f"👇 Siz '{topic}' konusu hakkında ne düşünüyorsunuz? Kendi gözlemlerinizi ve deneyimlerinizi yorumlarda bizimle paylaşın!\n\n"
            "✨ Yeni videolardan anında haberdar olmak için abone olmayı ve bildirimleri açmayı unutmayın. (Bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.)"
        )
    return (
        f"👇 What are your thoughts on '{topic}'? Share your perspectives and experiences in the comments below!\n\n"
        "✨ Don't forget to subscribe and turn on notifications for future videos! (For general info only, not financial advice.)"
    )

