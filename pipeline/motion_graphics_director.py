"""Veri-görselleştirme yönetmeni -- ollama (qwen3) ile script segmentlerinden hangisinin
ANİMASYONLU istatistik/karşılaştırma grafiğine dönüştürüleceğini seçer.

visual_director.py'nin GÖRSEL karakter seçimindeki aynı yerel-LLM deseni (persona._ollama +
_extract_json) burada VERİ grafiği seçimi için kullanılır. Tamamen savunmacı: Ollama
kapalıysa/timeout olursa/geçersiz JSON dönerse BOŞ liste döner -> çağıran taraf
(s05b_motion_graphics) segmenti bugünkü statik görseliyle bırakır, hiçbir şey bozulmaz.
"""
import re

from pipeline.persona import DEFAULT_MODEL, _extract_json, _ollama
from pipeline.utils.logging import get_logger

log = get_logger("motion_graphics_director")

_VALID_TRENDS = {"up", "down", "neutral"}

_HOOK_RE = re.compile(r"\d|%|\$|₺|dolar|yüzde|milyon|milyar", re.IGNORECASE)


def _deterministic_highlights(segments: list[str], exclude_idx: set[int],
                               max_highlights: int) -> list[dict]:
    """17 Eyl eklendi -- Ollama TAMAMEN erişilemez/timeout olduğunda (canlı testte
    gözlendi: 180s timeout -> pick_highlights [] döndü -> videoda TEK animasyon
    (TitleCard) kaldı) kullanılan SIFIR-LLM yedek seçici. Sayı/yüzde/para birimi
    içeren segmentleri KeyQuote (BİREBİR alıntı, hiçbir sayı ayrıştırma/uydurma riski
    yok -- s05b_motion_graphics zaten quote'un segment metninde birebir geçtiğini
    kontrol eder) olarak işaretler. Motion graphics'in Ollama'nın o anki durumundan
    BAĞIMSIZ olarak her zaman birkaç segmenti kapsamasını garanti eder -- kullanıcı
    isteği: video monoton kalmasın, animasyon eksik olmasın."""
    out = []
    for i, s in enumerate(segments):
        if not s or i in exclude_idx:
            continue
        n_words = len(s.split())
        if not (4 <= n_words <= 22):
            continue
        if not _HOOK_RE.search(s):
            continue
        out.append({"type": "quote", "segment_index": i, "quote": s.strip()[:140], "attribution": ""})
        if len(out) >= max_highlights:
            break
    return out


def _clean_stat(item: dict) -> dict | None:
    try:
        return {
            "type": "stat",
            "segment_index": int(item["segment_index"]),
            "label": str(item.get("label") or "").strip()[:60] or "İlgi çekici veri",
            "value": float(item["value"]),
            "prefix": str(item.get("prefix") or "")[:4],
            "suffix": str(item.get("suffix") or "")[:6],
            "trend": item.get("trend") if item.get("trend") in _VALID_TRENDS else "neutral",
        }
    except (KeyError, TypeError, ValueError):
        return None


def _clean_compare(item: dict) -> dict | None:
    try:
        items = []
        for it in (item.get("items") or []):
            items.append({"label": str(it["label"]).strip()[:40], "value": float(it["value"])})
        if len(items) < 2:
            return None
        return {
            "type": "compare",
            "segment_index": int(item["segment_index"]),
            "title": str(item.get("title") or "").strip()[:60] or "Karşılaştırma",
            "unit": str(item.get("unit") or "")[:4],
            "items": items[:3],
        }
    except (KeyError, TypeError, ValueError):
        return None


def _clean_report(item: dict, segment_text: str) -> dict | None:
    """18 Eyl eklendi (SIFIR_MALIYET rehberi Modul 2) -- 'report' tipi NewspaperHighlight
    kartına gider. _clean_quote ile AYNI 'asla uydurma' ilkesi: headline segmentin GERÇEK
    metninde birebir geçmiyorsa reddedilir."""
    try:
        headline = str(item["headline"]).strip()
        if not headline or headline not in segment_text:
            return None
        return {
            "type": "report",
            "segment_index": int(item["segment_index"]),
            "headline": headline[:140],
            "sourceLabel": str(item.get("sourceLabel") or "Rapor").strip()[:40],
        }
    except (KeyError, TypeError, ValueError):
        return None


def _clean_quote(item: dict, segment_text: str) -> dict | None:
    """'stat'/'compare' için 'asla sayı uydurma' ilkesinin alıntı karşılığı: seçilen
    alıntı segmentin GERÇEK metninde birebir geçmiyorsa reddedilir (LLM'in cümleyi
    kısaltıp/parafraze edip uydurmasını engeller)."""
    try:
        quote = str(item["quote"]).strip()
        if not quote or quote not in segment_text:
            return None
        return {
            "type": "quote",
            "segment_index": int(item["segment_index"]),
            "quote": quote[:140],
            "attribution": str(item.get("attribution") or "").strip()[:40],
        }
    except (KeyError, TypeError, ValueError):
        return None


def pick_highlights(segments: list[str], exclude_idx: set[int], max_highlights: int = 2,
                     model: str | None = None) -> list[dict]:
    """segments listesinden (exclude_idx hariç) en fazla max_highlights adet animasyonlu
    grafik adayı döner. Her aday {"type": "stat"|"compare", "segment_index": int, ...}.
    Hata/timeout/boş sonuçta [] döner (çağıran taraf statik görsele düşer)."""
    if max_highlights <= 0:
        return []
    candidates = [(i, s) for i, s in enumerate(segments) if s and i not in exclude_idx]
    if not candidates:
        return []

    listing = "\n".join(f"{i}: {s}" for i, s in candidates)
    prompt = (
        "You are a DATA VISUALIZATION DIRECTOR for a financial news video. Given the "
        f"numbered script segments below (Turkish), find UP TO {max_highlights} segments "
        "worth turning into an animated on-screen graphic: a percentage, a price level, "
        "a count, 2-3 comparable named values in the SAME sentence, a sentence that cites "
        "an OFFICIAL report/institution (TCMB, Fed, TÜİK, a bank, an official statement/"
        "haber başlığı) worth a newspaper-style highlight card, or (if nothing else "
        "qualifies) one short striking verbatim sentence worth a big pulled-quote card.\n\n"
        "Prefer numbers that are SURPRISING: a record, a sharp change, a rare/extreme "
        "value, or a meaningful comparison across time -- over routine/expected figures. "
        "Do not pick a number just because it is the first one you see; scan all segments "
        "and rank by how striking the number is. Prefer picks spread across different "
        "parts of the video rather than several from the same few consecutive segments. "
        "Skip vague/general segments with no concrete number or notable claim.\n\n"
        f"Segments:\n{listing}\n\n"
        "For each chosen segment output ONE of three shapes:\n"
        '- stat: {"type":"stat","segment_index":N,"label":"<short Turkish label, max 5 '
        'words>","value":<number>,"prefix":"<e.g. $ or empty>","suffix":"<e.g. % or '
        'empty>","trend":"up"|"down"|"neutral"}\n'
        '- compare (2-3 named values in one sentence): {"type":"compare","segment_index":N,'
        '"title":"<short Turkish title>","unit":"<optional symbol>","items":['
        '{"label":"<name>","value":<number>}, ...]}\n'
        '- report (cites an official report/institution/haber, newspaper-style card): '
        '{"type":"report","segment_index":N,"headline":"<the key sentence copied VERBATIM '
        'from the segment, max ~16 words>","sourceLabel":"<short Turkish source label, e.g. '
        '\'TCMB Raporu\' or \'Fed Açıklaması\', max 4 words>"}\n'
        '- quote (only when no number/report qualifies but the sentence is a striking '
        'standalone claim): {"type":"quote","segment_index":N,"quote":"<the sentence copied '
        'VERBATIM from the segment, max ~16 words>","attribution":""}\n\n'
        'Reply ONLY as JSON: {"highlights": [...]}. Use [] if nothing qualifies. '
        "NEVER invent a number that is not present in the segment text. NEVER invent or "
        "paraphrase a quote/headline -- it must be copied exactly as it appears in the segment."
    )
    try:
        raw = _ollama(prompt, model or DEFAULT_MODEL, timeout=240)
        data = _extract_json(raw)
    except Exception as e:
        log.warning(f"Grafik önerisi alınamadı (Ollama), sıfır-LLM yedek seçiciye düşülüyor: {e}")
        fallback = _deterministic_highlights(segments, exclude_idx, max_highlights)
        if fallback:
            log.info(f"Yedek seçici {len(fallback)} segmenti KeyQuote'a işaretledi (Ollama'sız)")
        return fallback

    by_idx = dict(candidates)
    out = []
    seen = set()
    for item in (data.get("highlights") or [])[: max_highlights * 2]:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "stat":
            cleaned = _clean_stat(item)
        elif item_type == "compare":
            cleaned = _clean_compare(item)
        elif item_type == "report":
            try:
                seg_text = by_idx.get(int(item.get("segment_index", -1)), "")
            except (TypeError, ValueError):
                seg_text = ""
            cleaned = _clean_report(item, seg_text)
        elif item_type == "quote":
            try:
                seg_text = by_idx.get(int(item.get("segment_index", -1)), "")
            except (TypeError, ValueError):
                seg_text = ""
            cleaned = _clean_quote(item, seg_text)
        else:
            cleaned = None
        if not cleaned:
            continue
        idx = cleaned["segment_index"]
        if idx in exclude_idx or idx in seen or idx >= len(segments):
            continue
        seen.add(idx)
        out.append(cleaned)
        if len(out) >= max_highlights:
            break
    return out
