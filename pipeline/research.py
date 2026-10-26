"""Beynin internet ARAŞTIRMA modülü — sıfır API maliyeti.

Kanalın 'beyni' (persona.py) bir konu hakkında GERÇEK, güncel bilgi toplamak için
bunu kullanır. Ücretli arama API'si YOK: DuckDuckGo'nun anahtar gerektirmeyen HTML
uç noktasında arar, ilk birkaç sonucu indirir, sayfa metnini temizler ve modele
verilecek kısa bir 'facts' (gerçekler) bloğu üretir. Wikipedia özeti güvenilir bir
temel kaynak olarak her zaman denenir.

Kullanım:
    from pipeline import research
    r = research.gather_facts("2026 altın fiyatı beklentileri")
    print(r["facts"])     # modele verilecek gerçekler bloğu
    print(r["sources"])   # kaynak URL listesi

Bağımlılık: yalnızca `requests` (venv'de zaten var). Ağ engelliyse zarifçe boş döner —
çağıran taraf araştırmasız üretime düşebilir.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote, quote_plus, unquote, urlparse

import requests

from pipeline.utils.logging import get_logger

log = get_logger("research")

# Gerçek bir tarayıcı gibi görünmek bazı sitelerin 403 vermesini önler.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
}

_DDG_HTML = "https://html.duckduckgo.com/html/"
_WIKI_API = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
# Google News RSS — anahtar GEREKTİRMEZ. Google'ın haber dizinini (dünya genelinde,
# yüzlerce kaynak) bir arama sorgusu için taze RSS akışı olarak verir.
_GNEWS_RSS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
# GDELT Doc 2.0 API — anahtar GEREKTİRMEZ. Dünyadaki haberleri 100+ dilde tarayan
# küresel haber veritabanı; "tüm dünya haberlerini bir araya toplama" katmanı budur.
_GDELT_DOC = "https://api.gdeltproject.org/api/v2/doc/doc"

# Dil -> Google News bölge/dil kodları (hl, gl, ceid).
_GNEWS_LOCALE = {
    "en": ("en-US", "US", "US:en"),
    "tr": ("tr", "TR", "TR:tr"),
}

# Metinden atılacak HTML blokları (içerikte işe yaramaz).
_STRIP_BLOCKS = re.compile(r"<(script|style|noscript|template|svg|nav|header|footer|form)[^>]*>.*?</\1>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
# İçerik metni genelde <p>/<li>/<h1-3> içinde; menü/buton gürültüsü değil.
_CONTENT = re.compile(r"<(p|li|h1|h2|h3)[^>]*>(.*?)</\1>", re.I | re.S)


def _http_get(url: str, timeout: int = 15, headers: dict | None = None, **kw) -> requests.Response | None:
    try:
        resp = requests.get(url, headers=headers or _HEADERS, timeout=timeout, **kw)
        resp.raise_for_status()
        return resp
    except Exception as e:
        log.warning(f"İstek başarısız ({url[:60]}...): {e}")
        return None


def _clean_html_to_text(raw: str, max_chars: int) -> str:
    """Ham HTML'yi okunabilir düz metne indirger. Önce paragraf/başlık/madde
    içeriğini toplar (menü, buton, footer gürültüsünü eler); yeterli içerik
    çıkmazsa tüm gövdeyi düz metne indirmeye düşer."""
    raw = _STRIP_BLOCKS.sub(" ", raw)
    # 1) İçerik-öncelikli: <p>/<li>/<h1-3> bloklarını al.
    parts = []
    for m in _CONTENT.finditer(raw):
        frag = _WS.sub(" ", html.unescape(_TAG.sub(" ", m.group(2)))).strip()
        if len(frag) >= 40:  # kısa menü/etiket parçalarını atla
            parts.append(frag)
    content = " ".join(parts).strip()
    if len(content) >= 200:
        return content[:max_chars]
    # 2) Yedek: tüm gövdeyi düz metne çevir.
    text = _WS.sub(" ", html.unescape(_TAG.sub(" ", raw))).strip()
    return text[:max_chars]


def _ddg_unwrap(href: str) -> str:
    """DDG yönlendirme linkini (/l/?uddg=...) gerçek URL'ye çözer."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        q = parse_qs(parsed.query)
        if "uddg" in q:
            return unquote(q["uddg"][0])
    return href


def ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo HTML uç noktasında arar. [{title, url, snippet}] döner (API anahtarı yok)."""
    try:
        resp = requests.post(
            _DDG_HTML, headers=_HEADERS, data={"q": query, "kl": "wt-wt"}, timeout=15
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"DDG araması başarısız: {e}")
        return []

    body = resp.text
    results: list[dict] = []
    # Her sonuç: <a ... class="result__a" href="...">Başlık</a> ... snippet
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S
    ):
        url = _ddg_unwrap(html.unescape(m.group(1)))
        title = _WS.sub(" ", _TAG.sub("", m.group(2))).strip()
        if not url.startswith("http"):
            continue
        # Aynı sonuç bloğundan snippet'i yakala (varsa)
        tail = body[m.end(): m.end() + 900]
        sm = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', tail, re.S)
        snippet = _WS.sub(" ", _TAG.sub("", sm.group(1))).strip() if sm else ""
        results.append({"title": title, "url": url, "snippet": html.unescape(snippet)})
        if len(results) >= max_results:
            break
    return results


def wikipedia_summary(topic: str, lang: str = "en") -> dict | None:
    """Wikipedia REST özeti — güvenilir, temiz bir temel kaynak."""
    title = quote_plus(topic.strip().replace(" ", "_"))
    # Wikipedia REST politikası açıklayıcı, iletişim içeren bir User-Agent ister;
    # tarayıcı taklidi UA'lar 'too many requests' ile engellenebiliyor.
    wiki_headers = {
        "User-Agent": "YoutubeBot-Research/1.0 (local content research; contact: local user)",
        "Accept": "application/json",
    }
    resp = _http_get(_WIKI_API.format(lang=lang, title=title), timeout=12, headers=wiki_headers)
    if not resp:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    extract = (data.get("extract") or "").strip()
    if not extract or data.get("type", "").endswith("not_found"):
        return None
    page = (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")
    return {"title": data.get("title", topic), "url": page, "snippet": extract}


# ============================================================================
# DÜNYA HABERLERİ KATMANI — anahtar gerektirmeyen küresel haber toplama.
# İki bağımsız kaynak (Google News RSS + GDELT) birleştirilir: biri düşerse diğeri
# çalışmaya devam eder. Script'e GÜNCEL olaylar ekler (evergreen bilgiye ek olarak).
# ============================================================================

def google_news_rss(query: str, language: str = "en", max_results: int = 8) -> list[dict]:
    """Google News'in anahtarsız RSS arama akışında haber arar.

    [{title, url, source, date, snippet}] döner. Google, tek bir sorgu için
    dünya çapında yüzlerce yayından taze haberi tek akışta toplar."""
    hl, gl, ceid = _GNEWS_LOCALE.get(language, _GNEWS_LOCALE["en"])
    url = _GNEWS_RSS.format(q=quote_plus(query), hl=hl, gl=gl, ceid=ceid)
    resp = _http_get(url, timeout=12)
    if not resp or not resp.text:
        return []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        log.warning(f"Google News RSS ayrıştırılamadı: {e}")
        return []
    out: list[dict] = []
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        # Google News başlığı genelde "Manşet - Kaynak Adı" biçimindedir.
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        if not source and " - " in title:
            title, source = title.rsplit(" - ", 1)
        date = (item.findtext("pubDate") or "").strip()
        desc = _WS.sub(" ", html.unescape(_TAG.sub(" ", item.findtext("description") or ""))).strip()
        out.append({"title": title.strip(), "url": link, "source": source,
                    "date": date, "snippet": desc[:400]})
        if len(out) >= max_results:
            break
    return out


def gdelt_news(query: str, max_results: int = 8, timespan: str = "1w") -> list[dict]:
    """GDELT Doc 2.0 API — dünyadaki haberleri 100+ dilde tarayan küresel veritabanı.

    [{title, url, source, date, language, country}] döner (API anahtarı yok).
    `timespan`: son X süre (ör. '24h', '3d', '1w')."""
    # GDELT çok kısa sorgularda hata verir; anlamlı hale getirmek için tırnakla sar.
    q = query.strip()
    if len(q.split()) > 1:
        q = f'"{q}"'
    params = {"query": q, "mode": "ArtList", "maxrecords": str(max_results),
              "format": "json", "sort": "DateDesc", "timespan": timespan}
    resp = _http_get(_GDELT_DOC, timeout=15, params=params)
    if not resp or not resp.text.strip():
        return []
    try:
        data = resp.json()
    except Exception:
        # GDELT hata durumunda düz metin döndürebilir; sessizce boş geç.
        return []
    out: list[dict] = []
    for art in (data.get("articles") or []):
        title = (art.get("title") or "").strip()
        url = (art.get("url") or "").strip()
        if not title or not url:
            continue
        out.append({
            "title": title, "url": url, "source": art.get("domain", ""),
            "date": art.get("seendate", ""), "language": art.get("language", ""),
            "country": art.get("sourcecountry", ""), "snippet": "",
        })
        if len(out) >= max_results:
            break
    return out


def gather_news(topic: str, language: str = "en", max_items: int = 12,
                timespan: str = "1w") -> list[dict]:
    """Google News + GDELT'i birleştirir, alan-adına göre tekilleştirir.

    Dünyanın dört bir yanından, konuyla ilgili GÜNCEL haber başlıklarını döner:
    [{title, url, source, date, ...}]. İki kaynak da düşerse boş liste döner."""
    items: list[dict] = []
    for fn in (lambda: google_news_rss(topic, language, max_items),
               lambda: gdelt_news(topic, max_items, timespan)):
        try:
            items.extend(fn())
        except Exception as e:  # bir kaynak çökerse diğeri devam etsin
            log.warning(f"Haber kaynağı hata verdi: {e}")
    # URL/başlık bazında tekilleştir; alan-adı çeşitliliğini koru.
    seen_url: set[str] = set()
    seen_title: set[str] = set()
    out: list[dict] = []
    for it in items:
        u = it["url"].split("?")[0]
        t = re.sub(r"\s+", "", it["title"].lower())[:70]
        if u in seen_url or t in seen_title:
            continue
        seen_url.add(u)
        seen_title.add(t)
        out.append(it)
        if len(out) >= max_items:
            break
    log.info(f"Haber toplama: {len(out)} güncel başlık — konu: {topic!r}")
    return out


def _news_block(items: list[dict], max_chars: int = 1600) -> str:
    """Haber öğelerini modele verilecek 'GÜNCEL HABERLER' metin bloğuna çevirir."""
    if not items:
        return ""
    lines = ["GÜNCEL HABERLER (dünya genelinde, en yeni — güncel olayları buradan al):"]
    for it in items:
        tag = it.get("source") or urlparse(it["url"]).netloc
        date = (it.get("date") or "")[:16]
        snip = it.get("snippet") or ""
        line = f"- {it['title']} [{tag}{(' · ' + date) if date else ''}]"
        if snip:
            line += f" — {snip[:160]}"
        lines.append(line)
    return "\n".join(lines)[:max_chars]


# Sayısal/veri içeren cümleleri yakalamak için sinyaller (fiyat, %, tarih, birim).
_DATA_SIGNAL = re.compile(
    r"%|\byüzde\b|\bpercent\b|₺|\$|€|\bTL\b|\bUSD\b|\bEUR\b|\bdolar\b|\blira\b|"
    r"\bgram\b|\bons\b|\bounce\b|\bkg\b|\bmilyar\b|\bmilyon\b|\bbillion\b|\bmillion\b|"
    r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b",
    re.I,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def extract_data_highlights(text: str, max_items: int = 18) -> list[str]:
    """Ham metinden SAYISAL/veri içeren cümleleri süzer (fiyat, yüzde, tarih, birim).
    Model bunları 'doğrulanmış rakam' olarak kullanır; tekrar/karışıklığı azaltır."""
    seen: set[str] = set()
    out: list[str] = []
    for chunk in _SENT_SPLIT.split(text):
        s = _WS.sub(" ", chunk).strip(" -•\t")
        if not (20 <= len(s) <= 240):
            continue
        if not re.search(r"\d", s):  # sayı yoksa veri değil
            continue
        if not _DATA_SIGNAL.search(s):  # para/yüzde/tarih/birim sinyali yoksa atla
            continue
        key = re.sub(r"\s+", "", s.lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def plan_research_queries(topic: str, language: str = "tr") -> list[str]:
    """Konudan 3-4 farklı açılı hedef arama sorgusu türetir (Olay/Kırılma, Kurum/Veri, Etki)."""
    t = (topic or "").strip()
    if not t:
        return []
    
    if language == "tr":
        queries = [
            t,
            f"{t} son dakika piyasa haberleri",
            f"{t} analiz yorum ve veriler",
        ]
        # Finansal/ekonomik anahtar kelimelere göre hedefli sorgu ekle
        t_low = t.lower()
        if any(k in t_low for k in ["dolar", "kur", "faiz", "tcmb", "enflasyon"]):
            queries.append(f"{t} TCMB faiz ve döviz etkisi")
        elif any(k in t_low for k in ["altin", "altın", "ons", "gram"]):
            queries.append(f"{t} ons gram altın ve Fed beklentileri")
        elif any(k in t_low for k in ["borsa", "bist", "hisse", "hisseler"]):
            queries.append(f"{t} Borsa İstanbul BIST 100 işlem hacmi ve şirketler")
        else:
            queries.append(f"{t} ekonomi ve hanehalkı etkisi")
    else:
        queries = [
            t,
            f"{t} breaking market news",
            f"{t} economic analysis and data",
            f"{t} global impact and trends",
        ]
    return list(dict.fromkeys(queries))[:4]


def _plan_followup_queries(topic: str, facts_so_far: str, language: str,
                            model: str | None = None) -> list[str]:
    """17 Eyl eklendi -- KULLANICI İSTEĞİ: "araştırmacı ruh", sabit şablon sorgular
    yerine yerel LLM'in TOPLANAN BULGULARA bakıp gerçek bir analist gibi hangi
    boşlukların/karşı-görüşlerin/ikincil etkilerin eksik olduğuna karar vermesi.
    plan_research_queries() (sabit 3-4 şablon) HÂLÂ ilk turda çalışır -- bu fonksiyon
    o ilk bulgular üzerine, modelin kendi muhakemesiyle üretilen 1-3 HEDEFLİ takip
    sorgusu ekler (2. tur). Ollama kapalıysa/hata verirse [] döner (çağıran taraf
    sadece ilk turla devam eder, hiçbir şey bozulmaz)."""
    from pipeline.persona import RESEARCH_MODEL, _extract_json, _ollama  # gecikmeli import (döngüsel import riski yok)

    lang_name = "Turkish" if language == "tr" else "English"
    prompt = (
        "You are a senior financial research analyst reviewing what a junior "
        f"researcher already found about this topic (write in {lang_name}): "
        f"\"{topic}\".\n\nFINDINGS SO FAR:\n{facts_so_far[:3000]}\n\n"
        "Identify up to 3 SPECIFIC gaps a rigorous analyst would chase next: a "
        "named institution's official statement, a historical comparison/precedent, "
        "a skeptical/contrarian take, an ordinary person's real-life impact, or a "
        "second-order effect. For each gap, write ONE precise search query (in "
        f"{lang_name}) that would find that missing piece -- NOT a generic "
        "rephrasing of the topic itself.\n\n"
        'Reply ONLY as JSON: {"gaps": ["<query 1>", "<query 2>", "<query 3>"]}. '
        "Use [] if the findings already cover the topic thoroughly."
    )
    try:
        raw = _ollama(prompt, model or RESEARCH_MODEL, timeout=150)
        data = _extract_json(raw)
        queries = [str(q).strip() for q in (data.get("gaps") or []) if str(q).strip()]
        return queries[:3]
    except Exception as e:
        log.warning(f"Takip sorguları üretilemedi (Ollama, araştırmacı-beyni turu atlanıyor): {e}")
        return []


def deep_research(
    topic: str,
    language: str = "tr",
    max_sources: int = 6,
    max_chars_per_source: int = 1200,
    agentic_followup: bool = True,
) -> dict:
    """ÇOK AÇILI DERİN ARAŞTIRMA MOTORU:
    Konuyu birden fazla arama sorgusuna böler, Google News + DuckDuckGo + Wikipedia
    üzerinden kapsamlı haber ve piyasa verilerini toplar, tekilleştirir ve
    kronolojik sebep-sonuç ilişkili bir facts bloğu döner.

    17 Eyl: agentic_followup=True (varsayılan) iken 1. tur (sabit şablon sorgular)
    bittikten sonra yerel LLM bulunanlara bakıp KENDİ BELİRLEDİĞİ 1-3 boşluk-doldurma
    sorgusuyla 2. bir tur daha araştırma yapar -- "araştırmacı ruh" isteği bu şekilde
    karşılanıyor: sabit sorgu listesi değil, bulgulara göre uyarlanan gerçek muhakeme.
    """
    lang = "tr" if language == "tr" else "en"
    queries = plan_research_queries(topic, language=lang)
    log.info(f"Derin Araştırma başlatıldı ({len(queries)} sorgu): {queries}")

    all_sources: list[str] = []
    all_news: list[dict] = []
    all_blocks: list[str] = []
    seen_domains: set[str] = set()
    seen_urls: set[str] = set()

    # 1) Wikipedia Temel Tanımı
    wiki = wikipedia_summary(topic, lang=lang) or (
        wikipedia_summary(topic, lang="en") if lang != "en" else None
    )
    if wiki:
        all_blocks.append(f"[Wikipedia — {wiki['title']}]\n{wiki['snippet'][:max_chars_per_source]}")
        if wiki.get("url"):
            all_sources.append(wiki["url"])
            seen_urls.add(wiki["url"])
            seen_domains.add(urlparse(wiki["url"]).netloc)

    def _run_query(q: str) -> None:
        """Tek bir sorgu için Google News + DuckDuckGo tara, paylaşılan
        all_sources/all_news/all_blocks/seen_* koleksiyonlarına ekle (closure)."""
        # A) Google News RSS
        news_items = google_news_rss(q, language=lang, max_results=4)
        for n in news_items:
            u = n.get("url", "")
            if u and u not in seen_urls:
                seen_urls.add(u)
                all_news.append(n)
                d = urlparse(u).netloc
                if d not in seen_domains and len(all_sources) < max_sources * 2:
                    all_sources.append(u)
                    seen_domains.add(d)

        # B) DuckDuckGo Web Araması
        hits = ddg_search(q, max_results=3)
        for hit in hits:
            u = hit.get("url", "")
            if not u or u in seen_urls:
                continue
            d = urlparse(u).netloc
            if d in seen_domains and len(all_blocks) >= max_sources:
                continue
            seen_urls.add(u)
            seen_domains.add(d)

            text = hit.get("snippet", "")
            page = _http_get(u, timeout=10)
            if page and page.text:
                full = _clean_html_to_text(page.text, max_chars_per_source)
                if len(full) > len(text):
                    text = full
            text = text.strip()
            if len(text) >= 60:
                all_blocks.append(f"[{hit.get('title', d)} — {u}]\n{text}")
                if u not in all_sources:
                    all_sources.append(u)

    # 2) Planlanan tüm sorgular üzerinden haberleri ve web sonuçlarını tara (1. tur)
    for q in queries:
        _run_query(q)

    # 2b) ARAŞTIRMACI BEYNİ -- 2. tur: yerel LLM 1. turun bulgularına bakıp kendi
    # belirlediği boşluk-doldurma sorgularıyla derinleştirir (bkz. _plan_followup_queries).
    followup_queries: list[str] = []
    if agentic_followup:
        prelim_news = _news_block(all_news[:10])
        prelim_body = "\n\n".join(all_blocks[:max_sources]).strip()
        prelim_facts = (prelim_news + "\n\n" + prelim_body).strip()
        if prelim_facts:
            followup_queries = _plan_followup_queries(topic, prelim_facts, lang)
            if followup_queries:
                log.info(f"Araştırmacı beyni {len(followup_queries)} takip sorgusu belirledi: {followup_queries}")
                for q in followup_queries:
                    _run_query(q)

    # 3) Sayısal Doğrulanmış Verileri Ayıkla
    news_text = _news_block(all_news[:15])
    body_text = "\n\n".join(all_blocks[:max_sources]).strip()
    highlight_source = body_text + "\n" + "\n".join(f"{n['title']} {n.get('snippet','')}" for n in all_news)
    highlights = extract_data_highlights(highlight_source, max_items=12)

    parts: list[str] = []
    if highlights:
        parts.append("ÖNE ÇIKAN DOĞRULANMIŞ VERİLER & RAKAMLAR:\n" + "\n".join(f"- {h}" for h in highlights))
    if news_text:
        parts.append(news_text)
    if body_text:
        parts.append("KAYNAK METİNLERİ & DETAYLAR:\n" + body_text)

    facts = "\n\n---\n".join(parts).strip()
    extra = f" + {len(followup_queries)} araştırmacı-beyni sorgusu" if followup_queries else ""
    log.info(f"Derin Araştırma tamamlandı: {len(all_sources)} kaynak, {len(all_news)} haber, "
             f"{len(highlights)} veri cümlesi{extra}")

    return {
        "facts": facts,
        "sources": all_sources[:max_sources * 2],
        "count": len(all_sources),
        "highlights": highlights,
        "news": all_news[:15],
        "queries": queries,
        "followup_queries": followup_queries,
    }


# ============================================================================
# EK ÜCRETSİZ KAYNAKLAR (22 Eyl eklendi) — web sohbet/araştırma sayfası için çeşitlilik.
# Hepsi anahtarsız, savunmacı (hata/timeout -> sessizce [] döner, üretimi bloklamaz).
# ============================================================================

# Sabit ekonomi/finans RSS akışları -- Google News'in kaçırdığı yerel TR haberlerini
# ve resmi kurumsal yayınları (Reuters) yakalamak için.
_RSS_FEEDS = {
    "reuters_business": "https://www.reutersagency.com/feed/?best-topics=business-finance",
    "aa_ekonomi": "https://www.aa.com.tr/tr/rss/default?cat=ekonomi",
    "bloomberght": "https://www.bloomberght.com/rss",
}

_KAP_DISCLOSURES = "https://www.kap.org.tr/tr/api/memberDisclosureQuery"
_TCMB_EVDS = "https://evds2.tcmb.gov.tr/service/evds/series={series}&type=json"
# Halka açık SearxNG örneği -- tek bir DuckDuckGo yerine Google/Bing/Brave sonuçlarını
# birleştirip döner (çoklu-motor metasearch), çapraz-doğrulama için çeşitlilik katar.
_SEARXNG_INSTANCE = "https://searx.be/search"


def rss_feed(name: str, max_results: int = 8) -> list[dict]:
    """`_RSS_FEEDS` içindeki sabit bir akıştan haber çeker.
    [{title, url, source, date, snippet}] döner; akış düşerse [] (savunmacı)."""
    url = _RSS_FEEDS.get(name)
    if not url:
        return []
    resp = _http_get(url, timeout=12)
    if not resp or not resp.text:
        return []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        log.warning(f"RSS ayrıştırılamadı ({name}): {e}")
        return []
    out: list[dict] = []
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        desc = _WS.sub(" ", html.unescape(_TAG.sub(" ", item.findtext("description") or ""))).strip()
        out.append({"title": title, "url": link, "source": name,
                    "date": (item.findtext("pubDate") or "").strip(), "snippet": desc[:400]})
        if len(out) >= max_results:
            break
    return out


def kap_disclosures(max_results: int = 10) -> list[dict]:
    """KAP (Kamuyu Aydınlatma Platformu) -- BIST şirket bildirimleri, resmi/anahtarsız.
    [{title, url, source, date}] döner; API şekli değişmişse/erişilemezse [] (savunmacı)."""
    resp = _http_get(_KAP_DISCLOSURES, timeout=12, headers={**_HEADERS, "Accept": "application/json"})
    if not resp:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    out: list[dict] = []
    for it in (data if isinstance(data, list) else data.get("data", []))[:max_results]:
        title = f"{it.get('stockCodes', it.get('mkkMemberOid', ''))} — {it.get('subject', '')}".strip(" —")
        disclosure_id = it.get("disclosureIndex") or it.get("basicDisclosureIndex") or ""
        if not title:
            continue
        out.append({
            "title": title, "source": "KAP",
            "url": f"https://www.kap.org.tr/tr/Bildirim/{disclosure_id}" if disclosure_id else "https://www.kap.org.tr/",
            "date": it.get("publishDate", ""),
        })
    return out


def tcmb_series(series_code: str) -> dict | None:
    """TCMB EVDS -- resmi döviz kuru/faiz serisi (ör. 'TP.DK.USD.A' USD/TRY alış).
    API anahtarı GEREKTİRMEZ (EVDS2 anonim erişim). Bulunamazsa None (savunmacı)."""
    resp = _http_get(_TCMB_EVDS.format(series=series_code), timeout=12,
                     headers={**_HEADERS, "Accept": "application/json"})
    if not resp:
        return None
    try:
        items = resp.json().get("items", [])
    except Exception:
        return None
    if not items:
        return None
    last = items[-1]
    return {"series": series_code, "date": last.get("Tarih", ""), "value": last.get(series_code, ""),
            "source": "TCMB EVDS (resmi)"}


def searxng_search(query: str, max_results: int = 5) -> list[dict]:
    """Halka açık SearxNG instance'ında arar -- Google/Bing/Brave'i tek sorguda birleştirir,
    DuckDuckGo'ya EK çeşitlilik katar (çapraz-doğrulama için farklı motor sonuçları).
    [{title, url, snippet}] döner; instance düşerse [] (savunmacı, ddg_search yedek kalır)."""
    resp = _http_get(_SEARXNG_INSTANCE, timeout=12,
                     params={"q": query, "format": "json", "language": "tr"})
    if not resp:
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    out: list[dict] = []
    for r in data.get("results", [])[:max_results]:
        out.append({"title": r.get("title", ""), "url": r.get("url", ""),
                    "snippet": (r.get("content") or "")[:300]})
    return out


def verify_claim(claim: str, sources: list[dict]) -> dict:
    """Bir iddianın kaç FARKLI alan adında (kaynak çeşitliliği) geçtiğini sayar.
    Tek kaynaklı iddialar `confidence: "low"` etiketlenir -- sohbet sayfası bunu
    kullanıcıya 'doğrulanmadı/tek kaynak' olarak gösterir. Basit anahtar-kelime
    örtüşmesiyle çalışır (ücretli bir doğrulama API'si yok)."""
    words = {w for w in re.sub(r"[^\w\s]", " ", claim.lower()).split() if len(w) > 3}
    matched_domains: set[str] = set()
    for s in sources:
        text = f"{s.get('title', '')} {s.get('snippet', '')}".lower()
        overlap = sum(1 for w in words if w in text)
        if words and overlap / len(words) >= 0.3:
            matched_domains.add(urlparse(s.get("url", "")).netloc or s.get("source", ""))
    n = len(matched_domains)
    confidence = "high" if n >= 3 else "medium" if n == 2 else "low" if n == 1 else "unverified"
    return {"claim": claim, "matched_sources": n, "domains": sorted(matched_domains), "confidence": confidence}


def gather_extra_sources(topic: str, language: str = "tr", max_results: int = 6) -> list[dict]:
    """Yukarıdaki ek kaynakların HEPSİNİ bir konu için toplar ve tekilleştirir --
    deep_research()'ün (Google News/DuckDuckGo/GDELT/Wikipedia) üzerine ÇEŞİTLİLİK katmanı.
    Her kaynak bağımsız try/except ile korunur (biri düşerse diğerleri devam eder)."""
    out: list[dict] = []
    if language == "tr":
        for name in _RSS_FEEDS:
            try:
                out.extend(rss_feed(name, max_results=4))
            except Exception as e:
                log.warning(f"RSS kaynağı atlandı ({name}): {e}")
        try:
            out.extend(kap_disclosures(max_results=5))
        except Exception as e:
            log.warning(f"KAP bildirimleri atlandı: {e}")
    try:
        out.extend(searxng_search(topic, max_results=max_results))
    except Exception as e:
        log.warning(f"SearxNG atlandı: {e}")

    seen: set[str] = set()
    uniq: list[dict] = []
    for it in out:
        u = (it.get("url") or "").split("?")[0]
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(it)
    return uniq


def discover_trending_financial_topics(language: str = "tr") -> list[dict]:
    """İnternetteki CANLI ekonomi ve finans gündemini tarayarak sıcak konuları listeler."""
    lang = "tr" if language == "tr" else "en"
    search_terms = (
        ["ekonomi", "borsa", "altın dolar", "piyasalar"]
        if lang == "tr"
        else ["business economy", "stock market", "crypto inflation", "interest rates"]
    )
    
    seen_titles: set[str] = set()
    trending: list[dict] = []

    for term in search_terms:
        items = google_news_rss(term, language=lang, max_results=6)
        for it in items:
            title = it.get("title", "").strip()
            if not title:
                continue
            clean_title = re.sub(r"\s+", " ", title)
            key = re.sub(r"[^\w\s]", "", clean_title.lower())[:50]
            if key in seen_titles:
                continue
            seen_titles.add(key)

            source = it.get("source", "Ekonomi Haberleri")
            trending.append({
                "title": clean_title,
                "source": source,
                "url": it.get("url", ""),
                "date": it.get("date", ""),
                "snippet": it.get("snippet", ""),
                "suggested_topic": f"{clean_title} — Piyasa ve Ekonomi Analizi",
            })
            if len(trending) >= 12:
                break
        if len(trending) >= 12:
            break

    return trending


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "altin dolar borsa"
    res = deep_research(q, language="tr")
    print(f"=== DERİN ARAŞTIRMA: {len(res['sources'])} Kaynak, {len(res['news'])} Haber ===")
    print(res["facts"][:1500])

