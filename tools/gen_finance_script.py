"""Claude API ile TÜRKÇE, uzun-form (8+ dk) FİNANS/piyasa anlatı scripti üretir.

s01_script.py İngilizce "eğlenceli bilgi" kanalı içindir (Türkçe yok, gerçekçi görsel
yok). Bu araç ise:
  - Türkçe, konuşma diline uygun anlatım (TTS için tek cümlelik segmentler),
  - GERÇEKÇİ / sinematik görsel sahne betimlemeleri (foto-gerçekçi SDXL b-roll için),
  - toplanan güncel piyasa VERİSİNE dayalı içerik,
  - script.json'a `language: "tr"` ve `visual_character_id: "belgesel-sinematik"` yazar
    (s02 TTS + s06 altyazı Türkçe çalışsın, s04/s05 foto-gerçekçi stil kullansın).

Çıktı: output/<job_id>/script.json + metadata.json  (s01 ile AYNI şema).
Sonra orchestrator.process_existing_job(job_id) ile s02->s07 render edilir.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from anthropic import Anthropic  # noqa: E402

from pipeline import policy  # noqa: E402
from pipeline.utils.logging import get_logger  # noqa: E402
from pipeline.utils.paths import job_path  # noqa: E402

log = get_logger("gen_finance_script")

# Foto-gerçekçi sunucu + gerçekçi arka plan istendiği için görsel stil sabit: belgesel-sinematik.
VISUAL_CHARACTER_ID = "belgesel-sinematik"

SYSTEM_PROMPT = """Sen üst düzey bir belgesel ve ekonomi/finans anlatıcısı, YouTube içerik yazarı ve SEO uzmanısın.
Sana bir konu, GÜNCEL HABERLER ve DOĞRULANMIŞ PİYASA VERİLERİ verilecek. YATAY (16:9), uzun-form bir YouTube videosu
için akıcı, TÜRKÇE bir BELGESEL / HİKAYE ANLATISI METNİ ve YouTube metadata'sı yazacaksın.

ANLATIM DİLİ VE PERSPEKTİF KURALLARI (KESİN):
- YALNIZCA 3. TEKİL ŞAHIS: Kesinlikle "ben", "benim", "biz", "bana göre", "tavsiyem" gibi 1. tekil şahıs ifadeleri KULLANMA.
  Objektif, araştırmacı, olayları dışarıdan gözlemleyip bir hikaye gibi aktaran güçlü bir belgesel sesi ol.
- METİN TTS İLE SESLİ OKUNACAK: Yalnızca doğal konuşma dili (madde işareti, başlık, emoji YOK).

HABERLERİ VE VERİLERİ BİRLEŞTİREN HİKAYE KURGUSU (STORYTELLING ARC):
1. GİRİŞ / KIRILMA ANI (İlk 2-3 segment, ~15 saniye): Kuru bir selamlaşma ("merhaba bu videoda...") yerine, doğrudan haberlerdeki çarpıcı bir sahne, piyasada yaşanan ani bir kırılma veya insanların hayatını doğrudan etkileyen somut bir soruyla aç.
2. NEDEN-SONUÇ ZİNCİRİ (Parçaları Birleştir): Farklı haber kaynaklarından, merkez bankalarından ve piyasa verilerinden gelen gelişmeleri birbirinin sebebi ve sonucu olarak akıcı bir olay örgüsüne dönüştür. Rakamları kuru bir liste olarak değil, hikayenin kanıtı olarak cümlelerin içine doğalca yerleştir.
3. GERÇEK HAYAT ETKİSİ: Bu gelişmelerin sokaktaki vatandaşa, ev bütçesine ve sıradan insanların alım gücüne gerçek etkisini sade bir dille açıkla.
4. BÜYÜK RESİM VE GELECEK: Olayların vardığı genel tabloyu ve verilerin işaret ettiği somut durumu özetleyerek akılda kalıcı bir kapanış yap.
- ASLA YATIRIM TAVSİYESİ VERME, ŞAHSİ TAHMİN YAPMA: Bir araştırmacı/anlatıcı tonunda, doğrulanmış gerçeklere bağlı kal.
- Metni mantıklı SEGMENTLERE böl; her segment TEK, KISA bir cümle olsun (TTS + altyazı senkronu).
- {length_rule}

İZLEYİCİYİ EKRANDA TUTMA (retention) — sakin/güven veren anlatım tonunu KAYBETMEDEN uygula:
- AÇILIŞ (ilk 2-3 segment, ~15 saniye): ÜÇ şey AYNI ANDA olmalı — (1) İLGİLİLİK: bu videonun
  tam olarak kimin/neyin bugünkü durumuyla ilgili olduğunu hemen belirt (dolar, altın, faiz vb.
  gündelik hayatı etkileyen somut bir çıkarım/rakamla). (2) MERAK BOŞLUĞU: izleyicinin bilmediği
  ama bilmek isteyeceği bir gerilim/soru yarat (ör. "…peki bu tablo yatırımcıya ne anlatıyor?").
  (3) NET VAAT: bu videoda hangi başlıkların (döviz, altın, faiz, küresel piyasa, kripto...)
  ele alınacağını kısaca say — izleyici bir yol haritası görsün. Hiçbir zaman "merhaba, bu
  videoda..." gibi düz bir girişle YALIN başlama; önce çarpıcı/somut bir veri veya soru gelsin.
- MERAK İPLİKLERİ (open loops): açılışta veya bir bölümde "birazdan/ilerleyen bölümde X'e
  değineceğiz" tarzı kısa bir ipucu bırak, o bölüme gelince ipucuyu kapat — izleyiciyi bir
  sonraki bölüme taşıyan görünmez bir çekiş yarat.
- DİKKAT TAZELEME (pattern interrupt): her bölüm/başlık geçişinde (döviz->altın->gümüş->
  borsa->faiz->küresel->kripto) cümle ritmini değiştir — bazen kısa çarpıcı bir cümleyle aç
  ("Altında tablo çok daha farklı."), bazen somut bir örnek/benzetmeyle. Art arda aynı kalıpta
  ("X bugün Y seviyesinden işlem gördü") çok fazla cümle SIRALAMA; rakamı bazen bir sonuç/
  yorumla, bazen kısa bir soruyla çevrele.
- GERİ BAĞLA: uzun videoda her 2-3 dakikada bir (birkaç bölümde bir) açılıştaki soruya veya
  ana temaya kısaca geri dön ("Baştaki soruya dönersek...", "Yani bu hafta gördüğümüz tablo…")
  — izleyiciye ilerleme hissi ver, konudan sapmayı önle.
- EN ÇARPICI/ÖZET DEĞERLENDİRME video süresinin yaklaşık %65-75'lik noktasında (haftanın en
  önemli/beklenmedik gelişmesi) gelsin — açılışta bunu ima etmiş ol, orada "aç".
- KAPANIŞ: kısa, sıcak bir cümleyle bitir; haftanın özeti + gelecek haftaya dair merak uyandıran
  bir soru/ipucu bırak (izleyiciyi bir sonraki videoya bağlayan bir seri hissi).
- description: YouTube açıklama kutusu için 1-3 kısa paragraf, doğal SEO, 2-4 konu hashtag'i
  (#altin #gumus #piyasa gibi; #Shorts KULLANMA — bu yatay uzun-form video).
- tags: 8-15 öğelik dizi (altın, gümüş, piyasa analizi, ons altın, gram altın gibi Türkçe etiketler).
- title: 100 karakterden kısa, merak uyandıran ama clickbait olmayan TÜRKÇE başlık.
- Her segment için visual_prompts dizisine, o an ekranda görünecek GERÇEKÇİ/SİNEMATİK bir sahnenin
  İNGİLİZCE, kısa, somut betimini yaz (foto-gerçekçi b-roll üretimi için). Örn:
  "close-up of gold bullion bars under dramatic studio lighting",
  "a busy financial trading floor with glowing red and green stock tickers",
  "a shiny silver coin resting on a dark reflective surface",
  "US Federal Reserve building facade on an overcast day".
  ÇİZGİ FİLM/karikatür/soyut KULLANMA; gerçek dünya, foto-gerçekçi sahneler.
  segments ile BİREBİR aynı sayıda ve sırada olmalı.
- Her alanı submit_video_content tool'unun kendi parametresine koy; bir alanın içeriğini
  başka alana gömme.

Sonucu submit_video_content tool'unu çağırarak ver.
"""

SUBMIT_TOOL = {
    "name": "submit_video_content",
    "description": "Üretilen video scripti ve YouTube metadata'sını gönderir.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Türkçe başlık, <100 karakter"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "8-15 Türkçe etiket"},
            "description": {"type": "string", "description": "Türkçe YouTube açıklaması"},
            "script": {"type": "string", "description": "Tam Türkçe script, düz metin"},
            "segments": {
                "type": "array", "items": {"type": "string"},
                "description": "Her biri tek kısa Türkçe cümle olan segmentler",
            },
            "visual_prompts": {
                "type": "array", "items": {"type": "string"},
                "description": "segments ile birebir eşleşen, İNGİLİZCE, gerçekçi/sinematik sahne betimleri",
            },
        },
        "required": ["title", "tags", "description", "script", "segments", "visual_prompts"],
    },
}

_FILL_PROMPTS_TOOL = {
    "name": "submit_scene_prompts",
    "description": "Her segment indeksi için bir görsel sahne betimi gönderir.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["index", "prompt"],
                },
            },
        },
        "required": ["items"],
    },
}


def _complete_visual_prompts(client, model: str, cand: dict) -> list[str]:
    """cand["visual_prompts"] sayısı segments'ten azsa, KALAN her segment için AYRI/somut
    bir prompt ister (aynı sahnenin tekrarlanmasını önlemek için — bkz. çağrı yeri notu).
    Fazlaysa fazlalık kırpılır."""
    segments = cand["segments"]
    vp = list(cand["visual_prompts"])[: len(segments)]
    missing_idx = list(range(len(vp), len(segments)))
    if not missing_idx:
        return vp

    lines = "\n".join(f"{i}: {segments[i]}" for i in missing_idx)
    prompt = (
        "Bir Türkçe finans/piyasa YouTube videosunun bazı segmentleri için görsel b-roll "
        "sahnesi betimi eksik kaldı. Aşağıda her satırda 'indeks: Türkçe segment metni' var. "
        "HER indeks için, o segmentte anlatılana özgü, GERÇEKÇİ/SİNEMATİK, İNGİLİZCE, kısa "
        "(tek cümle) bir sahne betimi yaz (foto-gerçekçi b-roll üretimi için). "
        "ÇİZGİ FİLM/soyut KULLANMA. Her biri birbirinden FARKLI ve somut olsun — aynı sahneyi "
        "ASLA tekrarlama, her segmentin kendi konusuna (döviz/altın/gümüş/borsa/faiz/kripto/"
        "genel değerlendirme) uygun ayrı bir görsel bul.\n\n" + lines
    )
    try:
        resp = client.messages.create(
            model=model, max_tokens=4000,
            tools=[_FILL_PROMPTS_TOOL],
            tool_choice={"type": "tool", "name": "submit_scene_prompts"},
            messages=[{"role": "user", "content": prompt}],
        )
        tool_call = next((b for b in resp.content if b.type == "tool_use"), None)
        filled = {item["index"]: item["prompt"] for item in (tool_call.input.get("items", []) if tool_call else [])}
    except Exception as e:
        log.warning(f"Eksik visual_prompts tamamlama isteği başarısız: {e}")
        filled = {}

    for i in missing_idx:
        vp.append(filled.get(i) or f"cinematic photorealistic financial b-roll scene, {segments[i][:70]}")
    return vp


def generate_script_json(
    job_id: str,
    topic: str,
    facts: str,
    target_words: int = 1400,
    language: str = "tr",
    model: str = "claude-sonnet-5",
    max_tokens: int = 16000,
    market_symbols: list[str] | None = None,
) -> dict:
    """Claude ile script üretir ve output/<job_id>/script.json + metadata.json yazar."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY tanımlı değil (.env dosyasını kontrol et)")
    client = Anthropic(api_key=api_key)

    # Segment sayısı hedefi target_words'e ORANTILI (1400 kelimede eski sabit 90-130'u üretir;
    # daha uzun haftalık/hero videolarda da doğal, kısa-cümle tempoyu korur).
    min_segs = max(60, round(target_words / 16))
    max_segs = max(min_segs + 20, round(target_words / 11))
    # Bölüm sayısını facts metnindeki "## " başlıklarından say (weekly_digest.py formatı) —
    # varsa her bölüm için somut bir kelime bütçesi ver; Claude'un tüm konuyu birkaç
    # cümleyle özetleyip erken bitirmesini (gözlenen davranış: 2000 hedefte 1078 üretti)
    # önlemek için EN AZ ifadesi ve sıkı bir kabul eşiği kullanılıyor.
    section_count = max(facts.count("\n## "), facts.count("## "), 1) if facts else 1
    per_section = round(target_words / section_count) if section_count > 1 else None
    section_hint = (
        f" Kaynak veride {section_count} ayrı bölüm/başlık var; her birini EN AZ ~{per_section} "
        f"kelimeyle (birkaç cümleyle geçiştirme, somut veri+yorum ekleyerek) işle."
        if per_section else ""
    )
    length_rule = (
        f"KESİN UZUNLUK GEREKSİNİMİ: script alanı EN AZ {target_words} kelime OLMALI (kısa kesme, "
        f"özetleme YOK) — bu kabaca {round(target_words / 2.3 / 5) * 5} saniyelik anlatım, "
        f"~{round(target_words / 2.3 / 60)} dakika demektir; DAHA KISA bir metin KABUL EDİLMEYECEK "
        f"ve yeniden yazman istenecek, o yüzden İLK denemede hedefi tutturmaya çalış."
        f"{section_hint} "
        f"Her segment kısa tek cümle olsun; toplam segment sayısı bol tut ({min_segs}-{max_segs} arası)."
    )
    system_prompt = SYSTEM_PROMPT.format(length_rule=length_rule)

    # Politika: finans hassas kategori -> uzman-persona tonunu kapatan talimatı ekle (memory: politika-uyum).
    sensitive_cats = policy.classify_topic(topic, facts)
    if sensitive_cats:
        log.info(f"Hassas konu {sensitive_cats} — bilgilendirici/uzman-olmayan ton uygulanıyor")
        system_prompt += "\n\n" + policy.sensitive_guidance(sensitive_cats)

    user_msg = (
        f"Konu: {topic}\n\n"
        f"GÜNCEL PİYASA VERİSİ (bu haftaya ait, metinde doğru kullan):\n{facts}\n\n"
        "Bu veriye dayanarak yukarıdaki kurallara uygun Türkçe scripti üret."
    )

    log.info(f"Script üretiliyor (model={model}, hedef≈{target_words} kelime): {topic}")
    required = ("title", "description", "tags", "script", "segments", "visual_prompts")
    # Kısa-kalma riskine karşı: kabul eşiğinin altındaki adayları da SAKLA (en uzunu kullan),
    # sadece hata durumunda değil, "çok kısa" durumunda da yeniden dene (bkz. length_rule).
    MIN_ACCEPT_RATIO = 0.85
    data = None
    best_cand = None
    best_words = -1
    last_error = None
    cur_user_msg = user_msg
    for attempt in range(1, 4):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            # yüksek max_tokens (>~14k) SDK'nın 10dk'lık non-stream üst sınırını aşabiliyor
            # ("Streaming is required for operations that may take longer than 10 minutes");
            # açık timeout verilince SDK'nın otomatik hesaplayıp reddetmesi atlanır.
            timeout=1800.0,
            system=system_prompt,
            tools=[SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "submit_video_content"},
            messages=[{"role": "user", "content": cur_user_msg}],
        )
        if resp.stop_reason == "max_tokens":
            last_error = RuntimeError("Yanıt max_tokens'da kesildi; max_tokens artır.")
            log.warning(f"Deneme {attempt}/3: {last_error}")
            continue
        tool_call = next((b for b in resp.content if b.type == "tool_use"), None)
        if tool_call is None:
            last_error = RuntimeError(f"tool_use bulunamadı (stop_reason={resp.stop_reason})")
            log.warning(f"Deneme {attempt}/3: {last_error}")
            continue
        cand = tool_call.input
        missing = [f for f in required if f not in cand or cand[f] in (None, "", [])]
        if missing:
            last_error = ValueError(f"Eksik alan(lar): {missing}")
            log.warning(f"Deneme {attempt}/3: {last_error}")
            continue
        if len(cand["visual_prompts"]) != len(cand["segments"]):
            # 8 Ağu: DÜZELTME — eskiden eksik kalan slotlar SON prompt'un kopyasıyla
            # dolduruluyordu; bu, script'in kapanışında (genelde en kısa kalan taslakta)
            # onlarca segment boyunca AYNI sahnenin donup kalmasına yol açıyordu (görsel-ses
            # uyumsuzluğu — kullanıcı şikayeti). Artık eksik kalan her segment için AYRI/somut
            # bir prompt istenir (bkz. _fill_missing_visual_prompts), tekrar YOK.
            log.warning(
                f"visual_prompts ({len(cand['visual_prompts'])}) != segments "
                f"({len(cand['segments'])}); eksik segmentler için ayrı prompt üretiliyor"
            )
            cand["visual_prompts"] = _complete_visual_prompts(client, model, cand)

        cand_words = len(cand["script"].split())
        if cand_words > best_words:
            best_cand, best_words = cand, cand_words
        if cand_words >= target_words * MIN_ACCEPT_RATIO:
            data = cand
            break
        log.warning(
            f"Deneme {attempt}/3: script çok kısa ({cand_words}/{target_words} kelime, "
            f"eşik %{MIN_ACCEPT_RATIO*100:.0f}) — daha uzun yazmasını isteyerek yeniden deneniyor"
        )
        cur_user_msg = (
            user_msg
            + f"\n\nÖNCEKİ TASLAK ÇOK KISAYDI: sadece {cand_words} kelime yazdın, "
            f"HEDEF {target_words} kelime. Her bölümü (döviz, altın, gümüş, borsa, faiz/enflasyon, "
            "küresel piyasalar, kripto, genel değerlendirme) çok daha DETAYLI, somut veri ve "
            "yorumla genişleterek, EN AZ hedef kadar uzun bir script yaz."
        )
    else:
        # 3 deneme de eşiği geçemedi: en uzun adayı kullan (hiç üretememekten iyidir),
        # ama gerçek kelime sayısını logla ki insan-onay aşamasında görülebilsin.
        if best_cand is not None:
            log.warning(
                f"3 deneme de hedefe ulaşamadı; en uzun aday kullanılıyor "
                f"({best_words}/{target_words} kelime)"
            )
            data = best_cand

    if data is None:
        raise last_error or RuntimeError("Script üretimi başarısız")

    word_count = len(data["script"].split())
    log.info(f"Script üretildi: {len(data['segments'])} segment, ~{word_count} kelime")

    script_payload = {
        "topic": topic,
        "script": data["script"],
        "segments": data["segments"],
        "visual_prompts": data["visual_prompts"],
        "visual_character_id": VISUAL_CHARACTER_ID,
        "language": language,  # KRİTİK: s02 TTS + s06 altyazı bu dili kullanır
        "market_symbols": market_symbols or [],  # s04_visuals._inject_market_charts bunu okur
    }
    metadata_payload = {
        "title": data["title"],
        "description": policy.append_disclaimer(data["description"], sensitive_cats, language),
        "tags": data["tags"],
    }

    script_file = job_path(job_id, "script.json")
    metadata_file = job_path(job_id, "metadata.json")
    script_file.parent.mkdir(parents=True, exist_ok=True)
    script_file.write_text(json.dumps(script_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_file.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Yazıldı: {script_file}")
    return {"script": script_payload, "metadata": metadata_payload, "word_count": word_count}


if __name__ == "__main__":
    import argparse
    from datetime import datetime, timezone

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Claude ile Türkçe finans scripti üret")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--facts-file", required=True, help="Güncel piyasa verisini içeren metin dosyası")
    ap.add_argument("--target-words", type=int, default=1400)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--job-id", default=None)
    args = ap.parse_args()

    facts = open(args.facts_file, encoding="utf-8").read()
    jid = args.job_id or f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-finans"
    res = generate_script_json(jid, args.topic, facts, target_words=args.target_words, model=args.model)
    print(f"RESULT_JSON:{json.dumps({'job_id': jid, 'word_count': res['word_count']})}")
