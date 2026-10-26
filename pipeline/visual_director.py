"""Kanalın 'sanat yönetmeni' — görsel KARAKTER (tema + stil + palet + mood + hareket) sistemi.

`persona.py` metni/kişiliği yönetir; bu modül ise GÖRSELİ yönetir. Kanalın aralarından seçim
yapabileceği birden fazla **görsel karakter** tanımlar. Her karakter, o videonun görsellerinin
(s04) ve hareketli b-roll'lerinin (s05) NASIL görüneceğini belirleyen bir paket:
  - style_suffix      : SDXL pozitif prompt'una eklenen stil (eski sabit STYLE_SUFFIX'in yerine)
  - negative_prompt   : (opsiyonel) o karaktere özel negatif prompt; yoksa s04'ün varsayılanı
  - palette, mood     : insan/panel için açıklayıcı; ayrıca style_suffix'e harmanlanabilir
  - wan/ltx_motion_suffix : s05'te statik görseli canlandırırken kullanılan hareket ipucu

Karakterler `visual_characters.json`'da saklanır (web panelinden düzenlenir), dosya yoksa
buradaki DEFAULT_CHARACTERS kullanılır — böylece hiçbir kurulum olmadan bugünkü davranış
(varsayılan 'cocuk-storybook' karakteri) birebir korunur.

Bir videoya karakter SEÇİMİ üç modda yapılabilir (selection_mode):
  - "preset" : basit anahtar-kelime kuralı; eşleşme yoksa default_id
  - "ollama" : yerel qwen3, konuya göre en uygun karakteri seçer (sıfır API maliyeti)
  - "claude" : s01_script'te Claude script'le birlikte karakteri de seçer (claude_pick)
"""
import json

from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT
# _ollama / _extract_json persona ile ortak (tekrar yazmamak için yeniden kullanılır)
from pipeline.persona import _ollama, _extract_json, load_persona, DEFAULT_MODEL

log = get_logger("visual_director")

VISUAL_FILE = ROOT / "visual_characters.json"

# NOT: 'cocuk-storybook' style_suffix + negative_prompt + hareket ekleri, s04_visuals.py ve
# s05_video_broll.py'deki ESKİ sabitlerle birebir aynıdır (geriye dönük uyum: karakter
# seçilmezse çıktı bugünküyle aynı kalır). Değiştirirken iki yeri de birlikte düşün.
DEFAULT_CHARACTERS = [
    {
        "id": "cocuk-storybook",
        "name": "Çocuk Storybook",
        "description": (
            "Renkli, sıcak, çocuk dostu 3D karikatür / masal kitabı stili. Bilim, doğa, "
            "hayvanlar, 'neden' soruları, eğlenceli genel bilgi konuları için."
        ),
        "keywords": ["cocuk", "kids", "science", "bilim", "hayvan", "animal", "doga",
                     "nature", "eglenceli", "masal", "story", "fun"],
        "style_suffix": (
            ", vibrant colorful 3d cartoon style, pixar style render, storybook illustration, "
            "soft rounded shapes, cheerful bright lighting, kid-friendly, "
            "highest quality RealVisXL 8k rendering, "
            "8k resolution, highly detailed textures, Unreal Engine 5 render, cinematic"
        ),
        "negative_prompt": (
            "text, watermark, logo, signature, caption, subtitles, letters, numbers, "
            "collage, grid, tiled, split screen, multiple panels, frame, border, "
            "photorealistic human face, photo portrait, person looking at camera, "
            "scary, creepy, horror, nightmare, dark and gloomy, violent, blood, weapon, "
            "deformed, distorted, disfigured, mutated, extra limbs, extra fingers, poorly drawn, "
            "bad anatomy, visual glitches, noise, artifacts, lowres, "
            "low quality, worst quality, blurry, jpeg artifacts, oversaturated, messy"
        ),
        "palette": "canlı, doygun, sıcak renkler",
        "mood": "neşeli, meraklı, davetkâr",
        "wan_motion_suffix": (
            ", gentle smooth animation, soft playful natural movement, "
            "calm slow camera motion, bright cheerful consistent lighting, high quality"
        ),
        "ltx_motion_suffix": (
            ", slow gentle camera drift, subtle natural motion in the scene, "
            "smooth cinematic movement, consistent lighting"
        ),
    },
    {
        "id": "belgesel-sinematik",
        "name": "Belgesel Sinematik",
        "description": (
            "Fotogerçekçi, sinematik belgesel estetiği; dramatik ışık, sığ alan derinliği. "
            "Tarih, uzay, bilim-teknik, ciddi/haber ve gerçek dünya konuları için."
        ),
        # 31 Tem: FİNANS artık foto-gerçekçi bu karaktere yönlendirilir (minimal-flat'ten taşındı).
        "keywords": ["tarih", "history", "historical", "uzay", "space", "belgesel",
                     "documentary", "haber", "news", "gercek", "savas", "war", "dogal",
                     "cinematic", "gold", "altin", "oil", "petrol", "recession",
                     "market crash", "housing market", "central bank", "world economy",
                     # Finans (TR+EN) — foto-gerçekçi sunum için:
                     "finance", "financial", "para", "money", "ekonomi", "economy", "economic",
                     "enflasyon", "inflation", "faiz", "interest", "tasarruf", "savings", "saving",
                     "yatirim", "invest", "investing", "investment", "borsa", "stock", "hisse",
                     "kredi", "credit", "loan", "mortgage", "banka", "bank", "banking",
                     "butce", "budget", "vergi", "tax", "taxes", "emeklilik", "retirement", "pension",
                     "kripto", "crypto", "bitcoin", "bilesik", "compound", "gelir", "income",
                     "fon", "fund", "etf", "bond", "gdp", "dividend", "fintech", "exchange rate"],
        "style_suffix": (
            ", cinematic photograph, photorealistic, dramatic natural lighting, "
            "shallow depth of field, film grain, high dynamic range, epic wide shot, "
            "professional color grading, highest quality RealVisXL 8k rendering, "
            "8k resolution, highly detailed textures, Unreal Engine 5 render"
        ),
        # Fotogerçekçi karakter olduğu için 'photorealistic face' YASAKLANMAZ.
        "negative_prompt": (
            "text, watermark, logo, signature, caption, subtitles, letters, numbers, "
            "collage, grid, tiled, split screen, multiple panels, frame, border, "
            "cartoon, anime, 3d render, cgi, illustration, painting, "
            "deformed, distorted, disfigured, mutated, extra limbs, extra fingers, poorly drawn, "
            "bad anatomy, visual glitches, noise, artifacts, lowres, "
            "low quality, worst quality, blurry, jpeg artifacts, oversaturated, messy"
        ),
        "palette": "doğal, kontrastlı, hafif desatüre sinematik tonlar",
        "mood": "epik, ciddi, etkileyici",
        "wan_motion_suffix": (
            ", slow cinematic camera push-in, subtle atmospheric motion, "
            "realistic natural movement, dramatic consistent lighting, high quality"
        ),
        "ltx_motion_suffix": (
            ", slow cinematic dolly movement, subtle realistic motion, "
            "atmospheric depth, consistent dramatic lighting"
        ),
    },
    {
        "id": "retro-vintage",
        "name": "Retro Vintage",
        "description": (
            "Retro/vintage poster estetiği; sıcak nostaljik renkler, hafif doku ve grain. "
            "Nostalji, geçmiş on yıllar, müzik, pop kültür konuları için."
        ),
        "keywords": ["retro", "vintage", "nostalji", "nostalgia", "muzik", "music",
                     "80s", "70s", "90s", "eski", "pop", "klasik", "classic"],
        "style_suffix": (
            ", retro vintage illustration, 1970s poster art style, warm nostalgic colors, "
            "muted tones, subtle paper texture and grain, screen-print look, halftone shading, "
            "highest quality RealVisXL 8k rendering, "
            "8k resolution, highly detailed textures, Unreal Engine 5 render, cinematic"
        ),
        "negative_prompt": (
            "text, watermark, logo, signature, caption, subtitles, letters, numbers, "
            "collage, grid, tiled, split screen, multiple panels, frame, border, "
            "modern, hyperrealistic, neon, oversaturated, deformed, distorted, disfigured, mutated, "
            "bad anatomy, visual glitches, noise, artifacts, lowres, "
            "low quality, worst quality, blurry, jpeg artifacts, messy"
        ),
        "palette": "sıcak, hardal/turuncu/kahve nostaljik tonlar",
        "mood": "nostaljik, sıcak, sakin",
        "wan_motion_suffix": (
            ", gentle vintage camera drift, soft nostalgic motion, "
            "warm consistent retro lighting, subtle film grain, high quality"
        ),
        "ltx_motion_suffix": (
            ", slow nostalgic camera pan, subtle grainy motion, "
            "warm retro lighting, consistent vintage tone"
        ),
    },
    {
        "id": "minimal-flat",
        "name": "Minimal Flat / İnfografik",
        "description": (
            "Temiz, minimal düz (flat) vektör / infografik stili; geometrik şekiller, geniş "
            "boşluk. Ekonomi, veri, açıklayıcı/kavramsal ve teknik konular için."
        ),
        # 31 Tem: finans kelimeleri belgesel-sinematik'e (foto-gerçekçi) taşındı.
        # Burada yalnızca SAF infografik/şema/veri konuları kalır (nadiren tercih edilir).
        "keywords": ["veri", "data", "infografik", "infographic", "sema", "chart", "diagram",
                     "istatistik", "statistics", "minimal", "flat", "vector"],
        "style_suffix": (
            ", clean minimal flat vector illustration, infographic style, simple geometric shapes, "
            "bold flat colors, generous negative space, smooth gradients, modern design, "
            "highest quality RealVisXL 8k rendering, "
            "8k resolution, highly detailed textures, Unreal Engine 5 render, cinematic"
        ),
        "negative_prompt": (
            "text, watermark, logo, signature, caption, subtitles, letters, numbers, "
            "collage, grid, tiled, split screen, multiple panels, frame, border, "
            "photorealistic, 3d render, cluttered, busy background, noisy, "
            "deformed, distorted, disfigured, mutated, bad anatomy, visual glitches, artifacts, lowres, "
            "low quality, worst quality, blurry, jpeg artifacts, messy"
        ),
        "palette": "sınırlı, canlı ama temiz düz renkler",
        "mood": "temiz, modern, net",
        "wan_motion_suffix": (
            ", smooth clean animation, simple flat shapes gently moving, "
            "minimal consistent lighting, high quality"
        ),
        "ltx_motion_suffix": (
            ", smooth minimal motion, gentle geometric movement, "
            "clean flat consistent lighting"
        ),
    },
    {
        "id": "epik-fantastik",
        "name": "Epik Fantastik",
        "description": (
            "Sinematik dijital konsept sanatı; destansı, atmosferik, resimsel fantezi. "
            "Efsane, mitoloji, gizem, hayal gücü ve destansı hikâye konuları için."
        ),
        "keywords": ["efsane", "legend", "mitoloji", "myth", "fantezi", "fantasy",
                     "gizem", "mystery", "destan", "epic", "hayal", "masalsi", "kahraman",
                     "hero", "ejder", "dragon"],
        "style_suffix": (
            ", epic fantasy digital painting, cinematic concept art, dramatic volumetric lighting, "
            "rich atmospheric detail, painterly brushwork, majestic composition, artstation trending, "
            "highest quality RealVisXL 8k rendering, "
            "8k resolution, highly detailed textures, Unreal Engine 5 render, cinematic"
        ),
        "negative_prompt": (
            "text, watermark, logo, signature, caption, subtitles, letters, numbers, "
            "collage, grid, tiled, split screen, multiple panels, frame, border, "
            "flat, cartoon, low detail, deformed, distorted, disfigured, mutated, "
            "extra limbs, extra fingers, poorly drawn, bad anatomy, visual glitches, noise, artifacts, lowres, "
            "low quality, worst quality, blurry, jpeg artifacts, messy"
        ),
        "palette": "derin, zengin, atmosferik kontrastlı renkler",
        "mood": "destansı, gizemli, görkemli",
        "wan_motion_suffix": (
            ", sweeping epic camera movement, atmospheric drifting particles, "
            "dramatic volumetric lighting, majestic motion, high quality"
        ),
        "ltx_motion_suffix": (
            ", grand cinematic camera sweep, atmospheric motion, "
            "dramatic volumetric lighting, epic consistent tone"
        ),
    },
]

DEFAULT_CONFIG = {
    "characters": DEFAULT_CHARACTERS,
    # 31 Tem: FOTO-GERÇEKÇİ öncelik -> eşleşme olmayan konularda bile foto-gerçekçi
    # belgesel-sinematik'e düş ("sulu boya"/flat görünümden kurtul). Kullanıcı kararı.
    "default_id": "belgesel-sinematik",
    "selection_mode": "preset",  # preset | ollama | claude
}

_VALID_MODES = {"preset", "ollama", "claude"}
# Bir karakterde bulunması beklenen alanlar (panelden gelen eksik alanları tamamlamak için).
_CHAR_KEYS = ["id", "name", "description", "keywords", "style_suffix",
              "negative_prompt", "palette", "mood", "wan_motion_suffix", "ltx_motion_suffix"]


def load_visual_config() -> dict:
    """visual_characters.json'u okur; yoksa/bozuksa varsayılan kütüphaneye düşer."""
    cfg = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_CONFIG.items()}
    if VISUAL_FILE.exists():
        try:
            data = json.loads(VISUAL_FILE.read_text(encoding="utf-8"))
            if isinstance(data.get("characters"), list) and data["characters"]:
                cfg["characters"] = data["characters"]
            if data.get("default_id"):
                cfg["default_id"] = data["default_id"]
            if data.get("selection_mode") in _VALID_MODES:
                cfg["selection_mode"] = data["selection_mode"]
        except Exception:
            log.warning("visual_characters.json okunamadı, varsayılan karakterler kullanılıyor")
    # default_id gerçekten listede var mı? Yoksa ilk karaktere düş.
    ids = {c.get("id") for c in cfg["characters"]}
    if cfg["default_id"] not in ids and cfg["characters"]:
        cfg["default_id"] = cfg["characters"][0]["id"]
    return cfg


def save_visual_config(payload: dict) -> dict:
    """Paneldan gelen kütüphaneyi doğrulayıp diske yazar."""
    current = load_visual_config()
    chars = payload.get("characters")
    if isinstance(chars, list) and chars:
        cleaned = []
        for c in chars:
            if not isinstance(c, dict) or not c.get("id"):
                continue
            cleaned.append({k: c.get(k, "" if k != "keywords" else []) for k in _CHAR_KEYS})
        if cleaned:
            current["characters"] = cleaned
    if payload.get("default_id"):
        current["default_id"] = payload["default_id"]
    if payload.get("selection_mode") in _VALID_MODES:
        current["selection_mode"] = payload["selection_mode"]
    ids = {c["id"] for c in current["characters"]}
    if current["default_id"] not in ids:
        current["default_id"] = current["characters"][0]["id"]
    VISUAL_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def list_characters() -> list[dict]:
    return load_visual_config()["characters"]


def get_character(char_id: str | None, cfg: dict | None = None) -> dict:
    """Verilen id'nin karakterini döndürür; bulunamazsa default karaktere düşer."""
    cfg = cfg or load_visual_config()
    chars = cfg["characters"]
    by_id = {c["id"]: c for c in chars}
    if char_id and char_id in by_id:
        return by_id[char_id]
    return by_id.get(cfg["default_id"], chars[0])


def _preset_pick(topic: str, cfg: dict) -> str:
    """Basit anahtar-kelime skoru: konu metniyle en çok örtüşen karakterin id'si."""
    t = (topic or "").lower()
    best_id, best_score = cfg["default_id"], 0
    for c in cfg["characters"]:
        score = 0
        for kw in (c.get("keywords") or []):
            if kw and kw.lower() in t:
                score += 1
        if score > best_score:
            best_id, best_score = c["id"], score
    return best_id


def _ollama_pick(topic: str, cfg: dict) -> str:
    """qwen'e karakter listesini verip konuya en uygun tek id'yi seçtirir."""
    lines = [f"- {c['id']}: {c.get('name')} — {c.get('description')}" for c in cfg["characters"]]
    valid_ids = [c["id"] for c in cfg["characters"]]
    prompt = (
        "You are the ART DIRECTOR of a video channel. Choose the SINGLE best visual style "
        "character for the given video topic. Consider mood, subject and audience.\n\n"
        "Available characters:\n" + "\n".join(lines) + "\n\n"
        f'Video topic: "{topic}"\n\n'
        'Respond ONLY with JSON: {"character_id": "<one id from the list above>"}'
    )
    model = load_persona().get("model", DEFAULT_MODEL)
    raw = _ollama(prompt, model)
    data = _extract_json(raw)
    picked = (data.get("character_id") or "").strip()
    if picked in valid_ids:
        return picked
    log.warning(f"Ollama geçersiz karakter döndürdü ({picked!r}), default kullanılıyor")
    return cfg["default_id"]


def suggest_character(topic: str) -> dict:
    """qwen'e verilen konuya uygun YENİ bir görsel karakter taslağı ürettirir (panelde
    'öner' için). Kaydetmez; eksik alanları güvenli varsayılanlarla tamamlar."""
    prompt = (
        "You are an ART DIRECTOR. Invent a NEW visual style CHARACTER tailored to the given "
        "video topic, for AI image/video generation. Reply ONLY as JSON with these keys:\n"
        '{"id","name","description","keywords",'
        '"style_suffix","negative_prompt","palette","mood",'
        '"wan_motion_suffix","ltx_motion_suffix"}\n'
        "- id: short kebab-case ascii slug.\n"
        "- style_suffix and motion suffixes: English, comma-separated phrases, START WITH A COMMA "
        "(they are appended to an image/motion prompt).\n"
        "- keywords: array of lowercase topic words that should trigger this character.\n"
        f'Video topic: "{topic}"'
    )
    model = load_persona().get("model", DEFAULT_MODEL)
    data = _extract_json(_ollama(prompt, model))
    # Şemaya sabitle: eksik alanları default karakterden doldur, fazlalıkları at.
    base = {k: v for k, v in DEFAULT_CHARACTERS[0].items()}
    draft = {k: data.get(k, base[k]) for k in _CHAR_KEYS}
    if not isinstance(draft.get("keywords"), list):
        draft["keywords"] = []
    if not draft.get("id"):
        draft["id"] = "yeni-karakter"
    return draft


def resolve_character(topic: str, segments: list[str] | None = None,
                      claude_pick: str | None = None) -> dict:
    """selection_mode'a göre bir videoya görsel karakter seçer ve tam karakter dict'i döndürür.
    Seçim script üretim anında (GPU aşamalarından önce) bir kez yapılmalı; sonuç script.json'a
    visual_character_id olarak yazılır ki s04 ve s05 aynı karakteri kullansın."""
    cfg = load_visual_config()
    mode = cfg["selection_mode"]
    try:
        if mode == "claude":
            char_id = claude_pick or cfg["default_id"]
        elif mode == "ollama":
            char_id = _ollama_pick(topic, cfg)
        else:  # preset
            char_id = _preset_pick(topic, cfg)
    except Exception as e:
        log.warning(f"Karakter seçimi başarısız ({mode}): {e} — default kullanılıyor")
        char_id = cfg["default_id"]
    char = get_character(char_id, cfg)
    log.info(f"Görsel karakter seçildi (mod={mode}): {char['id']} — {char.get('name')}")
    return char
