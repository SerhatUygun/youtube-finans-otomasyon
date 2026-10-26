"""Kanalın 'beyni' — yerel (Ollama) çalışan kişilik + içerik üretici.

Bir YouTube kanalına tutarlı bir KİŞİLİK verir: niş, ton, hedef kitle, hook tarzı
ve kurallar `channel_persona.json`'da tanımlanır (web panelinden düzenlenir). Bu
kişilik doğrultusunda, tamamen YEREL olarak (Ollama qwen3 — sıfır API maliyeti):
  - video FİKİRLERİ üretir (kanalı besleyen konu akışı),
  - bir konudan tam SCRIPT + metadata üretir (s01_script/Claude'un yerel muadili;
    aynı script.json sözleşmesini döndürür: title, description, tags, script,
    segments, visual_prompts).

Not: qwen3 'düşünen' bir model; think=false + format=json ile temiz JSON alınır,
yine de güvenlik için <think> blokları temizlenip ilk JSON gövdesi ayıklanır.
"""
import json
import re
import time

import requests

from pipeline import policy
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT

log = get_logger("persona")

PERSONA_FILE = ROOT / "channel_persona.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
# 5 Ağu: qwen3:30b-a3b (18GB) DENENDİ ama bu makinede (16GB VRAM + 16GB RAM) yüklenirken
# takılıyor/500 veriyor (küçük promptta bile 2dk+ timeout) — donanıma AĞIR. qwen3:14b'de
# kalındı: 9.3GB, VRAM'e rahat sığar, hızlı yüklenir, güçlü akıl. Kalite sıçraması asıl
# research (dünya haberleri) + market (teknik analiz) katmanlarından geliyor.
DEFAULT_MODEL = "qwen3:14b"
PREFERRED_MODELS = [
    "qwen3:14b", "qwen2.5:14b", "qwen2.5:7b", "qwen3:8b",
    "llama3.1:8b", "deepseek-r1:8b", "deepseek-r1:14b", "mistral:7b"
]
# 17 Eyl eklendi -- KULLANICI İSTEĞİ: "araştırmacı ruh", bu makinenin kaldırabileceği
# (16GB VRAM) daha güçlü bir yerel model. gpt-oss:20b (OpenAI'nin açık ağırlıklı MoE
# modeli, native mxfp4 ile ~13GB) qwen3:30b-a3b'nin aksine (5 Ağu'da bu makinede
# takıldığı doğrulandı, bkz. memory) gerçekten çalışıyor -- research.py'nin takip-sorgu
# muhakemesi ve script üretiminin ana "beyni" burada kullanılır. resolve_best_model
# ile aynı güvenli düşüş deseni: kurulu değilse otomatik DEFAULT_MODEL'e düşer.
RESEARCH_MODEL = "gpt-oss:20b"

DEFAULT_PERSONA = {
    "name": "The Curious Mind",
    "niche": "Fascinating science and everyday 'why' questions explained simply",
    "audience": "Curious people of all ages who love quick, surprising facts",
    "language": "en",
    "tone": (
        "Warm, energetic and genuinely excited; like a smart friend who can't wait "
        "to share a cool fact. Simple words, short punchy sentences, zero jargon."
    ),
    "hook_style": (
        "Open with a surprising question or a bold 'did you know' that makes people "
        "stop scrolling in the first 2 seconds. Vary it every time."
    ),
    "rules": (
        "100% family-safe. Always original, never copy sources. One genuinely "
        "surprising specific detail per video. End with a warm, curiosity-sparking line."
    ),
    "signature": "Stay curious!",
    "model": DEFAULT_MODEL,
}


def is_ollama_online() -> bool:
    """Ollama servisinin çalışıp çalışmadığını kontrol eder."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def list_ollama_models() -> list[str]:
    """Ollama'da yüklü yerel modelleri listeler."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            return [m["name"] for m in models if "name" in m]
    except Exception as e:
        log.warning(f"Ollama modelleri listelenemedi: {e}")
    return []


def resolve_best_model(preferred: str | None = None) -> str:
    """Belirtilen model yüklüyse onu, değilse mevcut en iyi yüklü modeli seçer."""
    installed = list_ollama_models()
    if not installed:
        return preferred or DEFAULT_MODEL

    if preferred and any(preferred == m or preferred == m.split(":")[0] for m in installed):
        return preferred

    # Tercih edilen model listesinde ilk bulunanı seç
    for pm in PREFERRED_MODELS:
        for im in installed:
            if pm == im or pm.split(":")[0] == im.split(":")[0]:
                return im

    return installed[0]


def load_persona() -> dict:
    persona = dict(DEFAULT_PERSONA)
    if PERSONA_FILE.exists():
        try:
            persona.update(json.loads(PERSONA_FILE.read_text(encoding="utf-8-sig")))  # Not Defteri BOM ekleyebilir
        except Exception:
            log.warning("channel_persona.json okunamadı, varsayılan kişilik kullanılıyor")
    return persona


def save_persona(persona: dict) -> dict:
    current = load_persona()
    allowed = set(DEFAULT_PERSONA.keys())
    merged = {**current, **{k: v for k, v in persona.items() if k in allowed}}
    PERSONA_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def _extract_json(text: str):
    """qwen çıktısından ilk geçerli JSON gövdesini ayıklar (<think> bloklarını atar)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # ilk { ... } dengeli bloğu bul
    start = text.find("{")
    if start == -1:
        raise ValueError("Yanıtta JSON bulunamadı")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("JSON gövdesi kapanmadı")


def _ollama(prompt: str, model: str, timeout: int = 900, keep_alive: str = "20m") -> str:
    active_model = resolve_best_model(model)
    last_err = None
    for attempt, wait_s in enumerate((0, 10, 30, 60), start=1):
        if wait_s:
            log.warning(f"Ollama isteği başarısız oldu, {wait_s}s bekleyip yeniden denenecek "
                        f"(deneme {attempt}/4): {last_err}")
            time.sleep(wait_s)
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": active_model, "format": "json", "think": False, "stream": False,
                      "keep_alive": keep_alive, "prompt": prompt},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            last_err = e
            continue
    raise last_err or RuntimeError(f"Ollama servisine bağlanılamadı ({active_model})")


def unload_model(model: str | None = None):
    """Ollama modelini VRAM'den boşaltır (keep_alive=0)."""
    m = model or load_persona().get("model", DEFAULT_MODEL)
    try:
        requests.post(OLLAMA_URL, json={"model": m, "prompt": "", "keep_alive": 0, "stream": False}, timeout=30)
        log.info(f"Ollama modeli boşaltıldı (VRAM serbest): {m}")
    except Exception as e:
        log.warning(f"Ollama modeli boşaltılamadı: {e}")


def generate_story_outline(topic: str, facts: str, language: str = "tr") -> dict:
    """Verilen konu ve gerçeklerden 5 aşamalı makro döngü taslağı çıkarır."""
    p = load_persona()
    lang_name = {"en": "English", "tr": "Turkish"}.get(language, language)
    model = resolve_best_model(p.get("model", DEFAULT_MODEL))
    
    prompt = (
        f"You are a master macroeconomist and documentary story architect (data-driven macro documentary style). Language: {lang_name}.\n"
        f"Topic: \"{topic}\"\n"
        f"Verified Facts & Market Data:\n{facts[:3500]}\n\n"
        "Create a 5-part deep-dive documentary story outline in JSON with the following keys:\n"
        "{\n"
        "  \"hook_scene\": \"The dramatic opening or multi-decade cycle anomaly (1-2 sentences). MUST include a concrete verified number (price, percent change, or historic level) in the very first sentence — zero generic greetings.\",\n"
        "  \"historical_rhyme\": \"The historical parallel or origin (e.g. 1873 Crime of '73, 1971 Nixon Shock, 1980 Hunt Brothers, 2008 Lehman) connecting past monetary cycles to today\",\n"
        "  \"mechanism_and_data\": \"The hidden underlying mechanism (physical inventory depletion vs paper contracts, central bank reserves, liquidity faucets, institutional flows)\",\n"
        "  \"opposing_view_risks\": \"Objective balance: What do the bears/critics argue? Where are the downside risks and technical correction zones? Why is this NOT a guaranteed straight line?\",\n"
        "  \"big_picture\": \"The concluding systemic synthesis on the currency order and macro reality (strictly educational, NO financial advice)\"\n"
        "}\n"
        "Return ONLY JSON."
    )
    try:
        raw = _ollama(prompt, model, timeout=120)
        return _extract_json(raw)
    except Exception as e:
        log.warning(f"Story outline çıkarılamadı (varsayılana düşülüyor): {e}")
        return {
            "hook_scene": topic,
            "historical_rhyme": "Geçmiş makroekonomik döngüler ve tarihsel benzerlikler",
            "mechanism_and_data": "Piyasanın arkasındaki kurumsal akış ve likidite mekanizmaları",
            "opposing_view_risks": "Piyasadaki karşıt görüşler, düzeltme riskleri ve kritik eşikler",
            "big_picture": "Büyük resim ve küresel para sisteminin seyri"
        }



def _persona_block(p: dict) -> str:
    return (
        f"You ARE the personality of a YouTube channel. Stay 100% in character.\n"
        f"- Channel name: {p.get('name')}\n"
        f"- Niche: {p.get('niche')}\n"
        f"- Target audience: {p.get('audience')}\n"
        f"- Voice/tone: {p.get('tone')}\n"
        f"- Hook style: {p.get('hook_style')}\n"
        f"- Rules: {p.get('rules')}\n"
        f"- Signature closing vibe: {p.get('signature')}\n"
    )


def _learning_context() -> str:
    """Öğrenilmiş yönlendirme + en iyi örnek (few-shot) bloğu. _brain/ boşsa '' (no-op).
    Gecikmeli import: brain_learn -> paths; döngüsel import ve gereksiz yük olmasın."""
    try:
        from pipeline import brain_learn
        from pipeline.utils.config import load_config
        k = int((load_config().get("brain") or {}).get("fewshot_k", 1))
        return brain_learn.prompt_context(k=k)
    except Exception as e:
        log.warning(f"öğrenme bağlamı yüklenemedi ({type(e).__name__}) — atlanıyor")
        return ""


def _skill_context(topic: str) -> str:
    """Konuya eşleşen alan SKILL'inin rehberliğini prompt'a ekler. Eşleşme yoksa '' (no-op).
    Gecikmeli import: skill_router hafif ama döngüsel bağımlılığı önlemek için içeride."""
    try:
        from pipeline import skill_router
        return skill_router.skill_guidance(topic)
    except Exception as e:
        log.warning(f"skill bağlamı yüklenemedi ({type(e).__name__}) — atlanıyor")
        return ""


def _feedback_block(feedback: str | None) -> str:
    """Critic'in bir önceki denemedeki bulgularını yeniden-üretim prompt'una iliştirir."""
    if not feedback:
        return ""
    return (
        "\n\nPREVIOUS ATTEMPT — ISSUES TO FIX (a stricter editor rejected the last draft; "
        "rewrite so these are clearly resolved):\n" + feedback.strip() + "\n"
    )


def generate_ideas(persona: dict | None = None, n: int = 8,
                   avoid: list[str] | None = None, language: str | None = None) -> list[str]:
    """Kanalın nişine uygun n adet video KONUSU (kısa başlık) üretir.

    avoid: daha önce üretilmiş başlıklar (brain_memory.recent_titles) — beyin bunları
    tekrar etmesin diye prompt'a enjekte edilir (çeşitlilik).
    language: verilirse KONULAR bu dilde üretilir (ör. 'tr' -> Türkçe başlıklar, böylece
    araştırma da o dilde daha iyi sonuç verir)."""
    p = persona or load_persona()
    lang = language or p.get("language", "en")
    lang_block = ""
    if lang and lang != "en":
        lang_name = {"tr": "Turkish"}.get(lang, lang)
        lang_block = f"\nWrite EVERY topic in {lang_name} (native, natural phrasing)."
    avoid_block = ""
    if avoid:
        lst = "\n".join(f"- {t}" for t in avoid[:40])
        avoid_block = (
            "\n\nYou have ALREADY made videos on these — do NOT repeat them or trivial "
            "rewordings; propose DIFFERENT subtopics, angles or newer developments:\n" + lst
        )
    prompt = (
        _persona_block(p)
        + f"\nPropose {n} fresh, specific, high-curiosity video TOPICS that fit this channel. "
        "Each topic must be a short phrase (a video subject), not a full sentence. "
        "Avoid repeats and generic phrasing."
        + lang_block
        + avoid_block
        + "\nReturn ONLY JSON: "
        '{"ideas": ["topic 1", "topic 2", ...]}'
    )
    data = _extract_json(_ollama(prompt, p.get("model", DEFAULT_MODEL)))
    ideas = [str(x).strip() for x in (data.get("ideas") or []) if str(x).strip()]
    return ideas[:n]


def generate_grounded_script(topic: str, facts: str, language: str = "tr",
                             target_words: int = 150, tone: str | None = None,
                             feedback: str | None = None, outline: dict | None = None) -> dict:
    """GERÇEK verilerle temellendirilmiş script üretir (haber/finans videoları için).
    qwen'e SADECE verilen gerçekleri kullanması, sayı/olay UYDURMAMASI söylenir.
    segments hedef dilde, visual_prompts İngilizce döner (SDXL için)."""
    p = load_persona()
    lang_name = {"en": "English", "tr": "Turkish"}.get(language, language)
    cats = policy.classify_topic(topic, facts)
    tone = tone or (
        "3rd-person documentary narrator: captivating, objective, analytical, immersive storytelling. "
        "Synthesize real news, events, and market facts into an unfolding narrative arc — NO 1st-person pronouns ('I', 'me', 'my', 'ben', 'biz')."
    )
    from datetime import date
    today = date.today().isoformat()

    outline_block = ""
    if outline and isinstance(outline, dict):
        outline_block = (
            f"\n\nTHE HIDDEN ECONOMY 5-STAGE STORY BLUEPRINT TO FOLLOW:\n"
            f"- 1. Multi-Decade Hook / Catalyst: {outline.get('hook_scene', '')}\n"
            f"- 2. Historical Parallel & Monetary Origin: {outline.get('historical_rhyme', '')}\n"
            f"- 3. Underlying Mechanism & Hard Data: {outline.get('mechanism_and_data', '')}\n"
            f"- 4. Objective Balance & Bear/Risk Arguments: {outline.get('opposing_view_risks', '')}\n"
            f"- 5. Big Picture Synthesis on Currency System: {outline.get('big_picture', '')}\n"
        )

    prompt = (
        f"You are a world-class senior macroeconomist and investigative video narrator (data-driven explainer documentary style). Tone: {tone}\n"
        f"Today's date is {today}. Uncover the TRUE macro story and historical rhyme behind this topic using the verified facts below.\n\n"
        "PERSPECTIVE & VOICE RULES (STRICT):\n"
        "- Pure THIRD-PERSON narration ONLY. Never say 'I', 'me', 'my', 'we', 'ben', 'bana göre', 'benim tavsiyem'.\n"
        "- Speak as an objective, authoritative economic historian tracking tectonic monetary shifts.\n"
        "- NO FINANCIAL ADVICE. Always present both sides neutrally: why bulls believe it's a breakout, and where bears/critics warn of risks.\n\n"
        "5-PART MACRO DOCUMENTARY ARC:\n"
        "1. THE HOOK & CYCLE ANOMALY (First 2-3 sentences): Open immediately with a multi-decade cycle, a massive breakout or historic milestone. First sentence MUST contain a verified number, date, or percentage. Zero generic greetings.\n"
        "2. THE HISTORICAL RHYME (Why the past matters): Connect today's setup to a pivotal historical event (1873, 1971 Nixon Shock, 1980 Hunt Brothers, 2008 crash). History rhymes; show how the setup played out before.\n"
        "3. THE HIDDEN MECHANISM & HARD DATA: Explain the real plumbing (physical supply vs paper derivatives, COMEX inventories, central bank reserves, M2 money supply, industrial demand).\n"
        "4. WHAT THE CRITICS / BEARS GET RIGHT: Dedicate a clear section to the counter-thesis. Where are the risks? What could go wrong? What technical correction level threatens this trend? (Builds immense credibility).\n"
        "5. THE BIG PICTURE & SYSTEMIC VERDICT: Conclude with a thought-provoking synthesis on the global monetary order and what it signals for the future of purchasing power."
        f"{outline_block}\n\n"
        "VERIFIED FACTS & NEWS — the ONLY source of truth:\n"
        f"{facts}\n\n"
        "DATA ACCURACY & REALISM (critical):\n"
        "1. Every specific figure, price, percentage, date, institution and named event MUST be 100% accurate from the verified facts above. Never invent, guess or exaggerate figures.\n"
        "2. Weave the verified numbers smoothly into the storytelling prose rather than listing them as a dry bulletin.\n"
        "3. Explain financial/technical concepts with intuitive real-world metaphors.\n\n"
        "WRITING FORMAT:\n"
        f"- Target length: about {target_words} words. Language of 'script' and 'segments': {lang_name}.\n"
        "- EACH segment MUST be ONE short, punchy spoken sentence (for TTS and subtitle sync).\n"
        "- visual_prompts: For EVERY segment, write ONE English cinematic scene description for photorealistic SDXL b-roll (cinematic lighting, real-world objects/places, NO cartoon, NO text overlay, NO fake human faces). Exact same count as segments.\n"
        "- Metadata: title (<100 chars, high curiosity, not clickbait), 8-15 tags, and 1-2 paragraph description.\n\n"
        "Return ONLY JSON: {\"title\": str, \"description\": str, \"tags\": [str], \"script\": str, "
        "\"segments\": [str], \"visual_prompts\": [str]}."
    )
    prompt += policy.sensitive_guidance(cats)
    prompt += _skill_context(topic)
    prompt += _learning_context()
    prompt += _feedback_block(feedback)
    data = _extract_json(_ollama(prompt, p.get("model", DEFAULT_MODEL)))
    segments = [str(s).strip() for s in (data.get("segments") or []) if str(s).strip()]
    vps = [str(v).strip() for v in (data.get("visual_prompts") or [])]
    if not segments:
        raise ValueError("Grounded script üretilemedi (segment yok)")
    vps = (vps + [""] * len(segments))[: len(segments)]
    return {
        "topic": topic,
        "script": str(data.get("script", "")).strip() or " ".join(segments),
        "segments": segments,
        "visual_prompts": vps,
        "language": language,
        "metadata": {
            "title": (str(data.get("title", "")).strip() or topic)[:100],
            "description": policy.build_full_description(
                str(data.get("description", "")).strip(),
                categories=cats,
                language=language,
            ),
            "tags": [str(t).strip() for t in (data.get("tags") or []) if str(t).strip()],
            "pinned_comment": policy.generate_pinned_comment(topic, language),
        },
    }


def discover_trending_topics(language: str = "tr") -> list[dict]:
    """İnternetteki güncel haberleri tarayarak YouTube için en sıcak konu önerilerini döner."""
    from pipeline import research
    return research.discover_trending_financial_topics(language=language)


def generate_researched_script(topic: str, language: str | None = None,
                               target_words: int = 288, tone: str | None = None,
                               max_sources: int = 6, feedback: str | None = None) -> dict:
    """BEYNİN İNTERNETE BAĞLI HALİ: konuyu önce internette ÇOK AÇILI DERİN ARAŞTIRIR,
    topladığı gerçeklerle temellendirilmiş 3. kişi belgesel scripti üretir.

    Akış: research.deep_research (Çoklu sorgu + Google News + DuckDuckGo + Wikipedia)
          -> market_data.topic_data (Canlı piyasa grafiği ve fiyatı)
          -> generate_story_outline (4 aşamalı olay örgüsü)
          -> generate_grounded_script (3. kişi belgesel anlatısı).
    """
    from pipeline import research  # gecikmeli import

    p = load_persona()
    lang = language or p.get("language", "tr")
    log.info(f"Beyin derin araştırma yapıyor: {topic!r} (dil={lang})")
    r = research.deep_research(topic, language=lang, max_sources=max_sources)
    facts = r.get("facts", "").strip()

    # CANLI PİYASA VERİSİ (sıfır maliyet, anahtarsız)
    market_facts, market_sources, market_charts = "", [], []
    try:
        from pipeline import market_data
        md = market_data.topic_data(topic)
        market_facts = md.get("facts", "").strip()
        market_sources = md.get("sources", [])
        market_charts = md.get("charts", [])
        if market_facts:
            log.info(f"Canlı piyasa verisi eklendi: {md.get('symbols')}")
    except Exception as e:
        log.warning(f"Canlı piyasa verisi alınamadı (atlanıyor): {e}")

    combined_facts = ("\n\n".join(x for x in (market_facts, facts) if x)).strip()

    if not combined_facts:
        log.warning("Araştırma boş döndü (ağ yok/sonuç yok) — araştırmasız üretime düşülüyor")
        out = generate_script(topic, target_words=target_words, language=lang, feedback=feedback)
        out["sources"] = []
        out["researched"] = False
        return out

    # Çok aşamalı yerel beyin: Önce taslak (outline) çıkar, sonra metni ör
    outline = generate_story_outline(topic, combined_facts, language=lang)

    out = generate_grounded_script(
        topic, combined_facts, language=lang, target_words=target_words, tone=tone, feedback=feedback, outline=outline
    )
    all_sources = list(dict.fromkeys(market_sources + r.get("sources", [])))
    out["sources"] = all_sources
    out["market_symbols"] = market_data.detect_symbols(topic) if market_facts else []
    out["facts"] = combined_facts
    out["researched"] = True
    out["outline"] = outline
    
    # Metadata'yı tam şeffaf ve kaynaklı hale getir
    meta = out.setdefault("metadata", {})
    # combined_facts YERİNE üretilen NİHAİ script metni sınıflandırılır: ham araştırma/piyasa
    # verisi dökümü (ör. "RSI aşırı satım" gibi teknik ifadeler) kategori sınıflandırmasında
    # gürültüye yol açıp alakasız disclaimer'ların (sağlık/hukuk) eklenmesine sebep olabiliyordu;
    # gerçekte YAYINLANAN metin script'tir, disclaimer kararı ona göre verilmeli.
    cats = policy.classify_topic(topic, out.get("script", ""))
    meta["description"] = policy.build_full_description(
        meta.get("description", ""),
        sources=all_sources,
        categories=cats,
        language=lang,
    )
    meta["pinned_comment"] = policy.generate_pinned_comment(topic, lang)
    meta["sources"] = all_sources
    return out


def generate_script(topic: str, persona: dict | None = None,
                    target_words: int = 140, language: str | None = None,
                    feedback: str | None = None) -> dict:
    """Konudan, kişiliğin sesiyle tam script + metadata üretir (script.json sözleşmesi)."""
    p = persona or load_persona()
    lang = language or p.get("language", "en")
    lang_name = {"en": "English", "tr": "Turkish"}.get(lang, lang)
    cats = policy.classify_topic(topic)  # hassas konu -> uzman-olmayan/bilgilendirici ton

    prompt = (
        _persona_block(p)
        + f"\nWrite a horizontal (16:9) YouTube video narration in {lang_name}, about {target_words} words "
        f"(~{max(round(target_words / 2.4), 10)} seconds). Topic: \"{topic}\".\n"
        "Split the narration into logical segments; EACH segment is ONE short spoken sentence "
        "(used for TTS + subtitle sync). For EVERY segment add ONE short ENGLISH visual scene "
        "description to visual_prompts (for cartoon/storybook b-roll image generation; concrete, "
        "visualizable, no realistic human faces) — same count and order as segments. "
        "Also write YouTube metadata. "
        f"The 'script' and 'segments' MUST be in {lang_name}; 'visual_prompts' MUST be in English. "
        "Return ONLY JSON with keys: "
        '{"title": str, "description": str, "tags": [str], "script": str, '
        '"segments": [str], "visual_prompts": [str]}. '
        "title < 100 chars; tags 8-15 items; description 1-2 short paragraphs with #Shorts and 2-3 hashtags."
    )
    prompt += policy.sensitive_guidance(cats)
    prompt += _skill_context(topic)
    prompt += _learning_context()
    prompt += _feedback_block(feedback)
    data = _extract_json(_ollama(prompt, p.get("model", DEFAULT_MODEL)))

    segments = [str(s).strip() for s in (data.get("segments") or []) if str(s).strip()]
    vps = [str(v).strip() for v in (data.get("visual_prompts") or [])]
    if not segments:
        raise ValueError("Beyin script üretemedi (segment yok)")
    vps = (vps + [""] * len(segments))[: len(segments)]

    return {
        "topic": topic,
        "script": str(data.get("script", "")).strip() or " ".join(segments),
        "segments": segments,
        "visual_prompts": vps,
        "language": lang,
        "metadata": {
            "title": (str(data.get("title", "")).strip() or topic)[:100],
            "description": policy.append_disclaimer(
                str(data.get("description", "")).strip(), cats, lang
            ),
            "tags": [str(t).strip() for t in (data.get("tags") or []) if str(t).strip()],
        },
    }
