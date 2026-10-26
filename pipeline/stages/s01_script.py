"""Aşama 01: Script + metadata üretimi (Claude API).

Girdi: konu başlığı (str)
Çıktı: output/<job_id>/script.json, output/<job_id>/metadata.json
"""
import json
import os

from anthropic import Anthropic

from pipeline import policy
from pipeline import visual_director
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import job_path

log = get_logger("s01_script")

# Kanal yönü: İngilizce, aile dostu GENEL İZLEYİCİ — YATAY (16:9) uzun-form içerik.
# (28 Tem 2026: dikey Shorts formatı tamamen bırakıldı; test 2 dk, real 8-10 dk yatay.)
# Bilinçli karar: içerik "her yaşa hitap eden eğlenceli bilgi" olarak konumlanıyor
# (madeForKids=False beyanıyla tutarlı olması için metadata/etiketlerde doğrudan
# "çocuklara yönelik" hedefleme YAPILMAZ; ton yine de tamamen çocuk-güvenli kalır).
# Prompt İngilizce tutuluyor: çıktı dili İngilizce olduğu için model daha tutarlı uyuyor.
SYSTEM_PROMPT = """You are an expert documentary scriptwriter and YouTube SEO specialist.
You will be given a topic (and optionally news/facts). Write an original, compelling 3rd-person documentary spoken-narration script for a
horizontal (16:9) YouTube video, plus the YouTube metadata.

PERSPECTIVE & VOICE RULES:
- Pure THIRD-PERSON narration ONLY. Never say 'I', 'me', 'my', 'in my opinion', 'we', 'ben', 'bana göre'.
- Speak as a captivating, objective documentary narrator unfolding a true story.
- Spoken language only: natural pacing, short sentences, NO bullet points, headings or emojis.

STORYTELLING ARC:
1. THE HOOK (Opening 1-2 sentences): Grab attention immediately with a concrete scene, breaking turning point, or high-stakes question. Never start with dry greetings ("Hello, in this video...").
2. NARRATIVE PROGRESSION (Connecting the dots): Unfold the causes, events, and discoveries in a clear cause-and-effect storyline.
3. PRACTICAL / HUMAN IMPACT: Explain what this means in real life for everyday people with clear, intuitive analogies.
4. RESOLUTION: Conclude with a thought-provoking takeaway summarizing the big picture.

RULES:
- Split the script into logical segments; each segment is ONE short sentence (used for TTS and subtitle sync).
- {length_rule}
- Avoid template feel: vary sentence rhythm and structure between videos; never reuse stock phrasing.
- title: curiosity-driven, under 70 characters (fits fully in search/suggested-video UI without truncation), leads with the single strongest keyword phrase for this topic. No clickbait that the video doesn't deliver on.
- description: structured as (a) one keyword-rich hook sentence restating the topic in plain language (shown before the "more" fold, so it must stand alone and contain the main search term), (b) 1-2 short body paragraphs with supporting context, (c) 3-5 hashtags on their own line at the very end (do NOT use #Shorts), (d) do not put the AI-disclosure or legal disclaimer inside this field — those are appended separately by the pipeline.
- tags: 8-15 items, ALL directly relevant to this specific topic (no generic filler like "gelişmeler", "haberler" alone, no unrelated sectors/topics that merely sound plausible). Mix: 2-3 broad category tags, remainder specific long-tail phrases a viewer would actually search (include realistic keyword variants and, where natural, numbers/entities from the story).
- visual_prompts: For EVERY segment, write ONE short English cinematic scene description for photorealistic b-roll generation. Must match the exact count and order of segments.
- Deliver all fields using the submit_video_content tool.
"""

SUBMIT_TOOL = {
    "name": "submit_video_content",
    "description": "Üretilen video scripti ve YouTube metadata'sını gönderir.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "8-15 adet etiket"},
            "description": {"type": "string"},
            "script": {"type": "string", "description": "Tam script, düz metin"},
            "segments": {"type": "array", "items": {"type": "string"}},
            "visual_prompts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "segments ile birebir eşleşen, İngilizce, kısa sahne betimlemeleri",
            },
        },
        "required": ["title", "tags", "description", "script", "segments", "visual_prompts"],
    },
}


def run(job_id: str, topic: str) -> dict:
    cfg = load_config()["llm"]

    # OmniRoute (varsa) tercih edilir: ücretsiz model havuzu + otomatik fallback,
    # hiçbir Anthropic kredisi harcamadan çalışır. OMNIROUTE_API_KEY boşsa davranış
    # eskisi gibi doğrudan Anthropic API'ye gider (geriye dönük uyumlu).
    omniroute_key = os.environ.get("OMNIROUTE_API_KEY")
    if omniroute_key:
        base_url = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128/v1")
        client = Anthropic(api_key=omniroute_key, base_url=base_url)
        model_name = cfg.get("omniroute_model", "auto")
        log.info(f"OmniRoute üzerinden yönlendiriliyor (model={model_name}, base_url={base_url})")
    else:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Ne OMNIROUTE_API_KEY ne de ANTHROPIC_API_KEY tanımlı (.env dosyasını kontrol et)"
            )
        client = Anthropic(api_key=api_key)
        model_name = cfg["model"]

    # Hedef uzunluk config'den ayarlanabilir (llm.target_words) — kısa testlerde
    # ("30 saniyelik video") tam metraj script üretip boşa token/TTS/GPU harcamamak için.
    target_words = cfg.get("target_words")
    if target_words:
        length_rule = (
            f"Write a script of about {target_words} words "
            f"(roughly {max(round(target_words / 2.4 / 5) * 5, 15)} seconds of narration). "
            "Keep every segment short (one sentence each)."
        )
    else:
        length_rule = "Aim for a 1150-1440 word script (about 8-10 minutes of narration)."
    system_prompt = SYSTEM_PROMPT.format(length_rule=length_rule)

    # Politika koruması: konu hassas (sağlık/finans/hukuk/siyaset) ise anlatıcının "uzman
    # persona" gibi konuşmasını engelleyen talimatı enjekte et (YouTube AI-persona politikası).
    sensitive_cats = policy.classify_topic(topic)
    if sensitive_cats:
        log.info(f"Hassas konu tespit edildi {sensitive_cats} — uzman-olmayan/bilgilendirici ton uygulanıyor")
        system_prompt += policy.sensitive_guidance(sensitive_cats)

    # Görsel karakter (sanat yönetmeni): "claude" seçim modunda, script'le birlikte hangi görsel
    # stil karakterinin kullanılacağını da Claude seçsin diye tool'a opsiyonel bir alan ve system
    # prompt'a karakter listesi ekleriz. Diğer modlarda (preset/ollama) bu alan yok sayılır ve
    # seçim resolve_character içinde yapılır.
    vcfg = visual_director.load_visual_config()
    char_ids = [c["id"] for c in vcfg["characters"]]
    char_lines = "\n".join(
        f"  - {c['id']}: {c.get('name')} — {c.get('description')}" for c in vcfg["characters"]
    )
    system_prompt += (
        "\n\nVISUAL STYLE CHARACTER:\n"
        "Also pick the SINGLE best visual style character for this topic and return its id in "
        "the visual_character_id field. Choose from:\n" + char_lines + "\n"
    )
    submit_tool = json.loads(json.dumps(SUBMIT_TOOL))  # derin kopya (modül sabitini bozmadan)
    submit_tool["input_schema"]["properties"]["visual_character_id"] = {
        "type": "string",
        "enum": char_ids,
        "description": "Bu videoya en uygun görsel stil karakterinin id'si",
    }

    log.info(f"Script üretiliyor: '{topic}' (model={model_name}, hedef={target_words or '500-900'} kelime)")

    required_fields = ("title", "description", "tags", "script", "segments", "visual_prompts")
    max_attempts = 3
    data = None
    last_error = None

    for attempt in range(1, max_attempts + 1):
        response = client.messages.create(
            model=model_name,
            max_tokens=cfg.get("max_tokens", 8000),
            system=system_prompt,
            tools=[submit_tool],
            tool_choice={"type": "tool", "name": "submit_video_content"},
            messages=[{"role": "user", "content": f"Konu: {topic}"}],
        )

        if response.stop_reason == "max_tokens":
            last_error = RuntimeError(
                "Claude yanıtı max_tokens sınırında kesildi; config.yaml içinde llm.max_tokens değerini artır."
            )
            log.warning(f"Deneme {attempt}/{max_attempts}: {last_error}")
            continue

        tool_call = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_call is None:
            last_error = RuntimeError(f"Beklenen tool_use bloğu bulunamadı (stop_reason={response.stop_reason})")
            log.warning(f"Deneme {attempt}/{max_attempts}: {last_error}")
            continue

        candidate = tool_call.input
        missing = [f for f in required_fields if f not in candidate or candidate[f] in (None, "", [])]
        if missing:
            last_error = ValueError(f"LLM yanıtında eksik/boş alan(lar): {missing}")
            log.warning(f"Deneme {attempt}/{max_attempts}: {last_error}, yeniden deneniyor")
            continue

        data = candidate
        break

    if data is None:
        raise last_error or RuntimeError("Script üretimi başarısız oldu")

    # Görsel karakteri seçim moduna göre çöz (claude modunda Claude'un seçtiği id kullanılır);
    # sonuç script.json'a yazılır ki s04 (görsel) ve s05 (video b-roll) aynı karakteri kullansın.
    char = visual_director.resolve_character(
        topic, data["segments"], claude_pick=data.get("visual_character_id")
    )

    script_payload = {
        "topic": topic,
        "script": data["script"],
        "segments": data["segments"],
        "visual_prompts": data["visual_prompts"],
        "visual_character_id": char["id"],
    }
    metadata_payload = {
        "title": data["title"],
        # Hassas konularda açıklamaya standart sorumluluk reddi ve AI beyanı eklenir.
        "description": policy.build_full_description(
            data["description"],
            sources=[],
            categories=sensitive_cats,
            language=cfg.get("language", "tr"),
        ),
        "tags": data["tags"],
        "pinned_comment": policy.generate_pinned_comment(topic, cfg.get("language", "tr")),
    }

    script_file = job_path(job_id, "script.json")
    metadata_file = job_path(job_id, "metadata.json")
    script_file.write_text(json.dumps(script_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_file.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(f"Script yazıldı: {script_file}")
    log.info(f"Metadata yazıldı: {metadata_file}")
    return {"script": script_payload, "metadata": metadata_payload}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    topic_arg = sys.argv[1] if len(sys.argv) > 1 else "Why do cats purr?"
    run("manual-test", topic_arg)
