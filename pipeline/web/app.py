"""Yerel web arayüzü — pipeline'ı tarayıcıdan izlemek/tetiklemek için.

Kullanım:
    .venv\\Scripts\\python.exe -m pipeline.web.app
    -> http://127.0.0.1:8000
"""
import json
import re
import subprocess
import sys
import threading
import traceback
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import pipeline  # noqa: F401 -- symlink/DLL PATH patch'lerini uygular
from pipeline.orchestrator import _slugify
from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import OUTPUT_DIR, ROOT, job_path, make_job_id

load_dotenv(ROOT / ".env")
log = get_logger("web")

app = FastAPI(title="YouTube Otomasyon Hattı")

_cfg = load_config()
TOPICS_FILE = ROOT / _cfg["paths"]["topics_file"]
LOG_DIR = OUTPUT_DIR / "_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_job_lock = threading.Lock()
_state = {"running": False, "topic_id": None}


class TopicIn(BaseModel):
    topic: str
    notes: str = ""


class RunIn(BaseModel):
    skip_upload: bool = True


def _read_topics():
    if not TOPICS_FILE.exists():
        return []
    return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))


def _write_topics(topics):
    TOPICS_FILE.write_text(json.dumps(topics, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_if_exists(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ---------------------------------------------------------------- konular --

@app.get("/api/topics")
def list_topics():
    return _read_topics()


@app.post("/api/topics")
def add_topic(payload: TopicIn):
    if not payload.topic.strip():
        raise HTTPException(400, "Konu boş olamaz")
    topics = _read_topics()
    new_id = f"{_slugify(payload.topic)}-{uuid.uuid4().hex[:6]}"
    entry = {"id": new_id, "topic": payload.topic.strip(), "status": "pending", "notes": payload.notes}
    topics.append(entry)
    _write_topics(topics)
    return entry


@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: str):
    topics = _read_topics()
    remaining = [t for t in topics if t.get("id") != topic_id]
    if len(remaining) == len(topics):
        raise HTTPException(404, "Konu bulunamadı")
    _write_topics(remaining)
    return {"ok": True}


@app.get("/api/status")
def status():
    return _state


# ------------------------------------------------------------- iş çalıştır --

def _run_job(topic_id: str, skip_upload: bool, log_path: Path):
    """orchestrator.py'yi AYRI BİR PROCESS olarak çalıştırır.

    Kritik: pipeline aşamaları (XTTS, SDXL, faster-whisper) her model yüklemesinde
    GPU belleğini biriktirir ve PyTorch bu belleği process kapanana kadar iade etmez.
    Web sunucusu uzun ömürlü tek bir process olduğu için, işi in-process çalıştırmak
    (eski davranış) art arda birkaç iş sonrası VRAM'i tüketip pipeline'ı yavaşlatır/
    OOM'a sürükler. Alt process kapandığında GPU belleği tamamen serbest kalır.
    """
    cmd = [sys.executable, "-m", "pipeline.orchestrator", "--topic-id", topic_id]
    if not skip_upload:
        cmd.append("--auto-upload")

    with open(log_path, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        for line in proc.stdout:
            f.write(line)
            f.flush()
        proc.wait()

    if proc.returncode != 0:
        log.error(f"orchestrator alt process'i hata kodu {proc.returncode} ile bitti (topic={topic_id})")

    _state["running"] = False
    _state["topic_id"] = None


@app.post("/api/topics/{topic_id}/run")
def run_topic(topic_id: str, payload: RunIn):
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "Şu anda başka bir iş çalışıyor, önce onun bitmesini bekle")

    try:
        topics = _read_topics()
        entry = next((t for t in topics if t.get("id") == topic_id), None)
        if entry is None:
            raise HTTPException(404, "Konu bulunamadı")
        if entry.get("status") == "processing":
            raise HTTPException(409, "Bu konu zaten işleniyor")

        log_path = LOG_DIR / f"{topic_id}.log"
        log_path.write_text("", encoding="utf-8")

        _state["running"] = True
        _state["topic_id"] = topic_id

        def worker():
            try:
                _run_job(topic_id, payload.skip_upload, log_path)
            finally:
                _job_lock.release()

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True}
    except HTTPException:
        _job_lock.release()
        raise


# --------------------------------------------------- manuel metin -> video --
# Kullanıcının verdiği metni (kendi yazdığı) TTS okur; s01 (Claude) ATLANIR. Metin
# cümlelere bölünür (TTS + altyazı senkronu), her segment için opsiyonel İngilizce
# görsel prompt panelden girilebilir (boşsa s04 yerel fallback ile türetir).

class ManualJobIn(BaseModel):
    text: str
    title: str = ""
    description: str = ""
    tags: list[str] = []
    visual_prompts: list[str] = []
    language: str | None = None


def _split_segments(text: str) -> list[str]:
    """Metni cümlelere böler. Satır sonları da segment sınırı sayılır (kullanıcı
    her satıra bir segment yazabilir). Hem İngilizce hem Türkçe için çalışır."""
    text = text.replace("\r\n", "\n").strip()
    segs = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for part in re.findall(r"[^.!?…]+[.!?…]*", line):
            part = part.strip()
            if part:
                segs.append(part)
    return segs or ([text] if text else [])


def _run_manual(job_id: str, log_path: Path):
    """orchestrator'ı --existing-job-id ile AYRI PROCESS olarak çalıştırır (VRAM izolasyonu)."""
    cmd = [sys.executable, "-m", "pipeline.orchestrator", "--existing-job-id", job_id]
    with open(log_path, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        for line in proc.stdout:
            f.write(line)
            f.flush()
        proc.wait()
    if proc.returncode != 0:
        log.error(f"Manuel iş alt process'i hata kodu {proc.returncode} ile bitti (job={job_id})")
    _state["running"] = False
    _state["topic_id"] = None


@app.post("/api/manual-job")
def create_manual_job(payload: ManualJobIn):
    if not payload.text.strip():
        raise HTTPException(400, "Metin boş olamaz")
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "Şu anda başka bir iş çalışıyor, önce onun bitmesini bekle")
    try:
        segments = _split_segments(payload.text)
        if not segments:
            raise HTTPException(400, "Metinden segment çıkarılamadı")
        base = payload.title.strip() or segments[0]
        job_id = make_job_id(base)

        vps = list(payload.visual_prompts or [])
        vps = (vps + [""] * len(segments))[: len(segments)]  # segment sayısına hizala
        script = {
            "topic": base,
            "script": payload.text.strip(),
            "segments": segments,
            "visual_prompts": vps,
        }
        if payload.language:
            script["language"] = payload.language
        job_path(job_id, "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        job_path(job_id, "metadata.json").write_text(json.dumps({
            "title": (payload.title.strip() or base)[:100],
            "description": payload.description.strip(),
            "tags": payload.tags,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        log_path = LOG_DIR / f"{job_id}.log"
        log_path.write_text("", encoding="utf-8")
        _state["running"] = True
        _state["topic_id"] = job_id

        def worker():
            try:
                _run_manual(job_id, log_path)
            finally:
                _job_lock.release()

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "job_id": job_id, "segments": len(segments)}
    except HTTPException:
        _job_lock.release()
        raise
    except Exception:
        _job_lock.release()
        raise


# -------------------------------------------------- kanal beyni / kişilik --
# Yerel (Ollama) çalışan kişilik: fikir üretir, konudan script üretir. Sıfır API maliyeti.

from pipeline import persona as _persona  # noqa: E402
from pipeline import visual_director as _vdir  # noqa: E402
from pipeline import policy as _policy  # noqa: E402
from pipeline import critic as _critic  # noqa: E402
from pipeline import brain_memory as _brain_memory  # noqa: E402
from pipeline import skill_router as _skills  # noqa: E402


@app.get("/api/persona")
def get_persona():
    return _persona.load_persona()


@app.put("/api/persona")
def put_persona(payload: dict = Body(...)):
    return _persona.save_persona(payload)


# -------------------------------------------------- görsel karakter / sanat yönetmeni --
# Kanalın görsel KİMLİĞİ: birden fazla görsel karakter (stil/palet/mood/hareket) + seçim modu.

@app.get("/api/visual-characters")
def get_visual_characters():
    return _vdir.load_visual_config()


@app.put("/api/visual-characters")
def put_visual_characters(payload: dict = Body(...)):
    return _vdir.save_visual_config(payload)


@app.post("/api/visual-characters/suggest")
def suggest_visual_character(payload: dict = Body(default={})):
    """qwen'e verilen konuya uygun yeni bir görsel karakter TASLAĞI ürettirir (panelden
    'öner' butonu için). Kaydetmez; kullanıcı isterse düzenleyip kaydeder."""
    topic = (payload.get("topic") or "").strip()
    if not topic:
        raise HTTPException(400, "Konu boş olamaz")
    try:
        return _vdir.suggest_character(topic)
    except Exception as e:
        raise HTTPException(500, f"Karakter taslağı üretilemedi (Ollama çalışıyor mu?): {e}")


@app.get("/api/skills")
def get_skills():
    """Beyin skill'leri (alan uzmanlık paketleri) — kullanıcı panelden ekler/düzenler."""
    return {"skills": _skills.load_skills()}


@app.put("/api/skills")
def put_skills(payload: dict = Body(...)):
    try:
        return {"skills": _skills.save_skills(payload)}
    except Exception as e:
        raise HTTPException(400, f"Skill kaydedilemedi: {e}")


@app.get("/api/brain/reflections")
def brain_reflections():
    """Beynin ne öğrendiğini gösterir (salt-okunur): learned_guidance + reflections günlüğü
    + bekleyen persona önerileri (insan onayı için). Veri yoksa boş döner."""
    bdir = OUTPUT_DIR / "_brain"
    def _read(p, default=""):
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return default
    suggestions = []
    sp = bdir / "persona_suggestions.json"
    if sp.exists():
        try:
            suggestions = [s for s in json.loads(sp.read_text(encoding="utf-8"))
                           if not s.get("applied")]
        except Exception:
            suggestions = []
    return {
        "learned_guidance": _read(bdir / "learned_guidance.txt"),
        "reflections": _read(bdir / "reflections.md"),
        "pending_suggestions": suggestions,
    }


@app.post("/api/brain/ideas")
def brain_ideas(payload: dict = Body(default={})):
    try:
        # Hafıza-farkında: daha önce üretilen başlıkları 'avoid' olarak ver (tekrar önleme).
        ideas = _persona.generate_ideas(
            n=int(payload.get("n", 8)), avoid=_brain_memory.recent_titles())
        return {"ideas": ideas}
    except Exception as e:
        raise HTTPException(500, f"Beyin fikir üretemedi (Ollama çalışıyor mu?): {e}")


def _default_target_words() -> int:
    try:
        return int(load_config().get("llm", {}).get("target_words") or 288)
    except Exception:
        return 288


@app.post("/api/brain/preview")
def brain_preview(payload: dict = Body(...)):
    topic = (payload.get("topic") or "").strip()
    if not topic:
        raise HTTPException(400, "Konu boş olamaz")
    tw = int(payload.get("target_words") or _default_target_words())
    research = bool(payload.get("research"))
    try:
        if research:
            # Beyin önce internette araştırır, sonra gerçeklerle temellendirilmiş script yazar.
            result = _persona.generate_researched_script(
                topic, target_words=tw, language=payload.get("language"),
            )
        else:
            result = _persona.generate_script(
                topic, target_words=tw, language=payload.get("language"),
            )
        # Politika uyarısı: konu hassas mı? (panelde gösterilir — uzman-olmayan ton zaten uygulandı)
        result["policy"] = {"sensitive": _policy.classify_topic(topic)}
        # ÖZ-DEĞERLENDİRME: script'i puanla (panelde skor + sorunlar rozeti gösterilir).
        try:
            result["critic"] = _critic.score_script(result, topic)
        except Exception as e:
            log.warning(f"önizleme critic puanlaması atlandı: {e}")
        return result
    except Exception as e:
        raise HTTPException(500, f"Beyin script üretemedi: {e}")


@app.post("/api/brain/create-job")
def brain_create_job(payload: dict = Body(...)):
    """Konudan (veya önceden üretilmiş script alanlarından) yerel beyinle iş oluşturup
    pipeline'ı başlatır."""
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "Şu anda başka bir iş çalışıyor, önce onun bitmesini bekle")
    try:
        gen = payload.get("script")  # önizlemeden düzenlenmiş script gelebilir
        if not gen:
            topic = (payload.get("topic") or "").strip()
            if not topic:
                raise HTTPException(400, "Konu boş olamaz")
            tw = int(payload.get("target_words") or _default_target_words())
            if payload.get("research"):
                gen = _persona.generate_researched_script(
                    topic, target_words=tw, language=payload.get("language"),
                )
            else:
                gen = _persona.generate_script(
                    topic, target_words=tw, language=payload.get("language"),
                )
        meta = gen.get("metadata") or {}
        base = meta.get("title") or gen.get("topic") or (gen.get("segments") or ["job"])[0]
        job_id = make_job_id(base)

        # Görsel karakteri seçim moduna göre çöz (beyin yolunda Claude yok; preset/ollama karar
        # verir) ve script.json'a yaz -> s04/s05 aynı karakteri kullanır.
        _char = _vdir.resolve_character(gen.get("topic", base), gen.get("segments", []))
        script_payload = {
            "topic": gen.get("topic", base),
            "script": gen.get("script", ""),
            "segments": gen.get("segments", []),
            "visual_prompts": gen.get("visual_prompts", []),
            "visual_character_id": _char["id"],
        }
        if gen.get("language"):
            script_payload["language"] = gen["language"]
        if gen.get("sources"):  # araştırma kaynakları (şeffaflık — script.json'da saklanır)
            script_payload["sources"] = gen["sources"]
        job_path(job_id, "script.json").write_text(json.dumps(script_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        job_path(job_id, "metadata.json").write_text(json.dumps({
            "title": (meta.get("title") or base)[:100],
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        # Hafıza: panelden başlatılan iş de geçmişe işlenir (tekrar önleme tutarlı olsun).
        try:
            _brain_memory.record(gen.get("topic", base), meta.get("title") or base,
                                 job_id, gen.get("language", "en"))
        except Exception as e:
            log.warning(f"hafıza kaydı atlandı: {e}")

        # 16 Eyl: beyin (Ollama qwen3:14b, ~9.6GB) varsayılan keep_alive=20m ile VRAM'de
        # kalıyordu -- hemen ardından başlayan orchestrator subprocess'i (XTTS/SDXL/vb.)
        # aynı 16GB VRAM'i onunla paylaşmak zorunda kalıp zorlanıyordu. Script/karakter
        # seçimi bitti, beyne artık ihtiyaç yok -> GPU aşamaları başlamadan hemen boşalt.
        try:
            _persona.unload_model()
        except Exception as e:
            log.warning(f"Ollama modeli boşaltılamadı (devam ediliyor): {e}")

        log_path = LOG_DIR / f"{job_id}.log"
        log_path.write_text("", encoding="utf-8")
        _state["running"] = True
        _state["topic_id"] = job_id

        def worker():
            try:
                _run_manual(job_id, log_path)
            finally:
                _job_lock.release()

        threading.Thread(target=worker, daemon=True).start()
        return {"ok": True, "job_id": job_id, "segments": len(script_payload["segments"])}
    except HTTPException:
        _job_lock.release()
        raise
    except Exception as e:
        _job_lock.release()
        raise HTTPException(500, str(e))


@app.post("/api/split-preview")
def split_preview(payload: dict = Body(...)):
    """Metni segmentlere böler ve tahmini süre döner (panelde canlı gösterim için).
    GPU/TTS çalıştırmaz; süre ~2.4 kelime/sn kabaca."""
    segs = _split_segments(payload.get("text", ""))
    words = sum(len(s.split()) for s in segs)
    return {"segments": segs, "count": len(segs), "est_seconds": round(words / 2.4, 1) if words else 0}


@app.get("/api/topics/{topic_id}/log", response_class=PlainTextResponse)
def topic_log(topic_id: str):
    log_path = LOG_DIR / f"{topic_id}.log"
    if not log_path.exists():
        return ""
    return log_path.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ işler --

@app.get("/api/jobs")
def list_jobs():
    jobs = []
    if OUTPUT_DIR.exists():
        for d in sorted(OUTPUT_DIR.iterdir(), reverse=True):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            meta = _read_json_if_exists(d / "metadata.json") or {}
            upload = _read_json_if_exists(d / "upload_result.json")
            jobs.append({
                "job_id": d.name,
                "title": meta.get("title"),
                "has_video": (d / "video.mp4").exists(),
                "has_short": (d / "short.mp4").exists(),
                "has_subtitles": job_path(d.name, "subtitles.srt").exists(),
                "has_upload": upload is not None,
                "has_drive_upload": (d / "drive_upload_result.json").exists(),
                # Yarı-otomatik onay akışı: yüklendi ama hâlâ private/unlisted -> "Onay Bekleyenler".
                "pending_publish": bool(upload) and upload.get("privacy_status") != "public",
            })
    return jobs


@app.get("/api/videos")
def list_videos():
    """Toplu video galerisi — output/_videos/*.mp4 (s07_edit her bitmiş videoyu buraya kopyalar)."""
    vdir = OUTPUT_DIR / "_videos"
    out = []
    if vdir.exists():
        for p in sorted(vdir.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
            out.append({"name": p.name, "job_id": p.stem,
                        "size_mb": round(p.stat().st_size / 1_048_576, 2),
                        "mtime": p.stat().st_mtime})
    return out


@app.get("/api/videos/{name}")
def get_collected_video(name: str):
    p = OUTPUT_DIR / "_videos" / name
    # Yol geçişi koruması: sadece _videos altındaki .mp4'ler.
    if p.suffix != ".mp4" or p.parent != (OUTPUT_DIR / "_videos") or not p.exists():
        raise HTTPException(404, "Video yok")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    d = OUTPUT_DIR / job_id
    if not d.is_dir():
        raise HTTPException(404, "İş bulunamadı")
    return {
        "job_id": job_id,
        "script": _read_json_if_exists(job_path(job_id, "script.json")),
        "metadata": _read_json_if_exists(d / "metadata.json"),
        "upload": _read_json_if_exists(d / "upload_result.json"),
        "drive_upload": _read_json_if_exists(d / "drive_upload_result.json"),
        "critic": _read_json_if_exists(d / "critic.json"),
        "factcheck": _read_json_if_exists(d / "factcheck.json"),
        "has_video": (d / "video.mp4").exists(),
        "has_short": (d / "short.mp4").exists(),
        "has_subtitles": job_path(job_id, "subtitles.srt").exists(),
    }


@app.get("/api/jobs/{job_id}/video")
def job_video(job_id: str):
    p = OUTPUT_DIR / job_id / "video.mp4"
    if not p.exists():
        raise HTTPException(404, "Video yok")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/jobs/{job_id}/short")
def job_short(job_id: str):
    p = OUTPUT_DIR / job_id / "short.mp4"
    if not p.exists():
        raise HTTPException(404, "Shorts klibi yok")
    return FileResponse(p, media_type="video/mp4")


@app.post("/api/jobs/{job_id}/make-short")
def job_make_short(job_id: str, payload: dict = Body(default={})):
    d = OUTPUT_DIR / job_id
    if not d.is_dir() or not (d / "video.mp4").exists():
        raise HTTPException(404, "İş veya ana video bulunamadı")
    from tools import make_shorts
    duration = float(payload.get("duration", 45))
    try:
        out = make_shorts.generate_short_for_job(job_id, duration=duration)
        if not out:
            raise RuntimeError("Shorts oluşturulamadı")
        return {"ok": True, "short_file": out}
    except Exception as e:
        log.error(traceback.format_exc())
        raise HTTPException(500, f"Shorts hatası: {e}")


@app.get("/api/jobs/{job_id}/subtitles")
def job_subtitles(job_id: str):
    p = job_path(job_id, "subtitles.srt")
    if not p.exists():
        raise HTTPException(404, "Altyazı yok")
    return FileResponse(p, media_type="text/plain; charset=utf-8")


@app.post("/api/jobs/{job_id}/upload")
def job_upload(job_id: str):
    from pipeline.stages import s09_upload
    try:
        return s09_upload.run(job_id)
    except Exception as e:
        log.error(traceback.format_exc())
        raise HTTPException(500, str(e))


@app.post("/api/jobs/{job_id}/publish")
def job_publish(job_id: str):
    """Yarı-otomatik onay akışı: private/unlisted yüklenmiş bir videoyu public'e çeker."""
    from pipeline.stages import s09_upload
    try:
        return s09_upload.publish(job_id)
    except Exception as e:
        log.error(traceback.format_exc())
        raise HTTPException(500, str(e))


@app.post("/api/jobs/{job_id}/drive-upload")
def job_drive_upload(job_id: str):
    from pipeline.stages import s10_drive_upload
    try:
        return s10_drive_upload.run(job_id)
    except Exception as e:
        log.error(traceback.format_exc())
        raise HTTPException(500, str(e))


# -------------------------------------------------------- yerel beyin & şablonlar --

@app.get("/api/ollama/status")
def get_ollama_status():
    from pipeline import persona
    online = persona.is_ollama_online()
    models = persona.list_ollama_models() if online else []
    p = persona.load_persona()
    active_model = persona.resolve_best_model(p.get("model"))
    return {
        "online": online,
        "models": models,
        "active_model": active_model,
        "configured_model": p.get("model")
    }


@app.get("/api/presets")
def get_topic_presets():
    return [
        {
            "id": "market_summary",
            "icon": "📈",
            "title": "Haftalık Piyasa & Borsa Özeti",
            "topic": "Haftalık piyasa özeti: Borsa İstanbul, Dolar Kuru, Faiz ve Şirket Bilançoları",
            "badge": "Piyasa",
            "description": "BIST 100, döviz kurları ve TCMB faiz dinamiklerinin haftalık genel değerlendirmesi."
        },
        {
            "id": "gold_forex",
            "icon": "🥇",
            "title": "Altın & Döviz Analizi",
            "topic": "Altın ve Dolar Analizi: Gram altın, Ons ve Dolar/TL'de son gelişmeler",
            "badge": "Emtia / Döviz",
            "description": "Fed sinyalleri, jeopolitik riskler ve döviz kurunun altın fiyatlarına etkisi."
        },
        {
            "id": "inflation_budget",
            "icon": "💡",
            "title": "Tasarruf & Enflasyon Rehberi",
            "topic": "Enflasyona karşı bütçe koruma ve akıllı tasarruf yöntemleri",
            "badge": "Kişisel Finans",
            "description": "Alım gücünü korumak, gereksiz harcamaları kısmak ve birikim yapmanın temelleri."
        },
        {
            "id": "crypto_global",
            "icon": "⚡",
            "title": "Kripto & Küresel Piyasalar",
            "topic": "Kripto para piyasaları ve küresel teknoloji hisselerinde son durum",
            "badge": "Küresel / Kripto",
            "description": "Bitcoin, Ethereum ve ABD borsalarındaki güncel trendler ve gelişmeler."
        }
    ]


@app.get("/api/trends")
def get_trends(language: str = "tr"):
    from pipeline import persona
    try:
        topics = persona.discover_trending_topics(language=language)
        return {"ok": True, "trends": topics}
    except Exception as e:
        log.error(f"Trendler alınamadı: {e}")
        return {"ok": False, "trends": [], "error": str(e)}


@app.post("/api/brain/outline")
def get_brain_outline(payload: dict = Body(...)):
    topic = payload.get("topic", "").strip()
    language = payload.get("language", "tr")
    if not topic:
        raise HTTPException(400, "Konu boş olamaz")
    from pipeline import research, market_data, persona
    
    r = research.deep_research(topic, language=language, max_sources=4)
    facts = r.get("facts", "")
    try:
        md = market_data.topic_data(topic)
        if md.get("facts"):
            facts = md["facts"] + "\n\n" + facts
    except Exception:
        pass
        
    outline = persona.generate_story_outline(topic, facts, language=language)
    return {
        "ok": True,
        "topic": topic,
        "outline": outline,
        "facts": facts,
        "sources": r.get("sources", []),
        "queries": r.get("queries", [])
    }


@app.post("/api/brain/generate-script")
def get_brain_script(payload: dict = Body(...)):
    topic = payload.get("topic", "").strip()
    language = payload.get("language", "tr")
    target_words = int(payload.get("target_words", 288))
    tone = payload.get("tone")
    if not topic:
        raise HTTPException(400, "Konu boş olamaz")
    from pipeline import persona
    try:
        script_data = persona.generate_researched_script(
            topic=topic,
            language=language,
            target_words=target_words,
            tone=tone
        )
        return {"ok": True, "data": script_data}
    except Exception as e:
        log.error(f"Yerel senaryo üretilemedi: {e}")
        raise HTTPException(500, f"Senaryo üretim hatası: {e}")


# ------------------------------------------------ araştırma / sohbet sayfası --
# 22 Eyl eklendi: yapılandırılmış brain endpoint'lerinden farklı olarak SERBEST sohbet.
# Kullanıcı bir soru/konu yazar -> research.py (deep_research + ek kaynaklar) + market_data
# canlı verisiyle beslenir -> yerel Ollama (persona._ollama) yanıtı üretir -> kaynaklar +
# basit çapraz-doğrulama etiketiyle birlikte döner. Ücretsiz kalır (Ollama + anahtarsız
# kaynaklar); Claude/GPT gibi ücretli bir sohbet API'si KULLANILMAZ.

class ChatIn(BaseModel):
    message: str
    language: str = "tr"


@app.post("/api/chat")
def chat(payload: ChatIn):
    msg = payload.message.strip()
    if not msg:
        raise HTTPException(400, "Mesaj boş olamaz")
    from pipeline import research, market_data, persona

    r = research.deep_research(msg, language=payload.language, max_sources=5)
    extra = research.gather_extra_sources(msg, language=payload.language)
    facts = r.get("facts", "")

    market_facts = ""
    try:
        md = market_data.topic_data(msg)
        market_facts = md.get("facts", "")
    except Exception as e:
        log.warning(f"Chat: piyasa verisi alınamadı: {e}")

    extra_block = "\n".join(f"- {e['title']} [{e.get('source', '')}]" for e in extra[:10])
    combined_facts = "\n\n".join(x for x in (market_facts, facts, extra_block) if x).strip()

    lang_name = "Turkish" if payload.language == "tr" else "English"
    prompt = (
        f"You are a research assistant helping a YouTube finance/news channel (write in {lang_name}). "
        f"User question/topic: \"{msg}\".\n\nGATHERED FACTS (from live web search, treat as ground truth "
        f"-- do not invent numbers not present here):\n{combined_facts[:4000] or '(hiçbir kaynak bulunamadı)'}"
        "\n\nWrite a concise, well-organized answer grounded ONLY in the facts above. If facts are thin, say so "
        "honestly instead of guessing. Also produce a short version of the answer already edited for natural "
        "Turkish text-to-speech narration (short sentences, no abbreviations/symbols that a TTS engine would "
        "mispronounce, e.g. spell out '%' as 'yüzde', write numbers in words where natural)."
        '\n\nReply ONLY as JSON: {"answer": "<full answer>", "tts_ready_text": "<TTS-friendly version>"}'
    )
    try:
        raw = persona._ollama(prompt, persona.RESEARCH_MODEL, timeout=180)
        data = persona._extract_json(raw)
        answer = data.get("answer", "").strip()
        tts_text = data.get("tts_ready_text", "").strip()
    except Exception as e:
        log.error(f"Chat: yerel model yanıt üretemedi: {e}")
        answer = combined_facts[:1500] or "Yerel model şu anda yanıt veremiyor ve araştırma boş döndü."
        tts_text = ""

    all_sources = extra + r.get("news", [])
    verification = research.verify_claim(answer[:300], all_sources) if answer else None

    return {
        "ok": True,
        "answer": answer,
        "tts_ready_text": tts_text,
        "sources": r.get("sources", []) + [e["url"] for e in extra if e.get("url")],
        "verification": verification,
    }


# -------------------------------------------------------- altyazı tasarımı --
# Altyazı stili web'den düzenlenir; subtitle_style.json'a yazılır ve s07 montajda
# onu kullanır. Canlı önizleme tek bir kareyi ffmpeg ile burn edip PNG döner.

import subprocess as _subprocess  # noqa: E402
import tempfile as _tempfile  # noqa: E402

from fastapi.responses import Response  # noqa: E402

from pipeline.stages.s07_edit import (  # noqa: E402
    EDIT_OVERRIDE_KEYS,
    EDIT_SETTINGS_FILE,
    SUBTITLE_STYLE_FILE,
    build_subtitle_force_style,
    load_edit_settings,
    load_subtitle_style,
    _escape_filter_path,
)

PREVIEW_DIR = OUTPUT_DIR / "_preview"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/subtitle-style")
def get_subtitle_style():
    return load_subtitle_style()


@app.put("/api/subtitle-style")
def put_subtitle_style(style: dict = Body(...)):
    # Sadece bilinen anahtarları, mevcut stilin üzerine yaz (güvenli birleştirme).
    current = load_subtitle_style()
    allowed = set(current.keys())
    merged = {**current, **{k: v for k, v in style.items() if k in allowed}}
    SUBTITLE_STYLE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


def _preview_background(job_id: str | None, w: int, h: int):
    """Önizleme arka planı: iş seçiliyse onun altyazısız temiz görselini, yoksa
    koyu bir gradyan döner. (Nihai video'da altyazı zaten gömülü olduğu için ondan
    değil, temiz visuals/ görselinden alınır.)"""
    if job_id:
        vis_dir = job_path(job_id, "visuals")
        imgs = sorted(vis_dir.glob("*")) if vis_dir.is_dir() else []
        imgs = [p for p in imgs if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
        if imgs:
            return ["-i", str(imgs[0])], (
                f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
            )
    # koyu gradyan (lavfi)
    return (
        ["-f", "lavfi", "-i", f"gradients=s={w}x{h}:c0=0x232733:c1=0x0d0f14:x0=0:y0=0:x1={w}:y1={h}:d=1"],
        "[0:v]setsar=1",
    )


@app.post("/api/subtitle-preview")
def subtitle_preview(payload: dict = Body(...)):
    """Verilen stil + örnek metinle tek kare PNG önizleme üretir."""
    style = {**load_subtitle_style(), **{k: v for k, v in (payload.get("style") or {}).items()}}
    sample = (payload.get("text") or "Örnek altyazı burada\nböyle görünecek").strip()
    job_id = payload.get("job_id")
    # 9:16 önizleme; libass PlayResY'ye göre ölçeklediği için yarım çözünürlük yeterli
    w, h = 540, 960

    tmp = Path(_tempfile.mkdtemp(dir=PREVIEW_DIR))
    srt = tmp / "s.srt"
    lines = sample.replace("\r", "").split("\n")
    srt.write_text("1\n00:00:00,000 --> 00:00:05,000\n" + "\n".join(lines) + "\n", encoding="utf-8")

    bg_input, bg_chain = _preview_background(job_id, w, h)
    force_style = build_subtitle_force_style(style)
    srt_escaped = _escape_filter_path(srt)
    filt = f"{bg_chain}[bg];[bg]subtitles='{srt_escaped}':force_style='{force_style}'[out]"

    out_png = tmp / "preview.png"
    cmd = ["ffmpeg", "-y", *bg_input, "-filter_complex", filt, "-map", "[out]", "-frames:v", "1", str(out_png)]
    res = _subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not out_png.exists():
        log.error(res.stderr[-2000:])
        raise HTTPException(500, "Önizleme üretilemedi")
    data = out_png.read_bytes()
    try:
        import shutil as _shutil
        _shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    return Response(content=data, media_type="image/png")


@app.get("/api/edit-settings")
def get_edit_settings():
    cfg = load_edit_settings()
    out = {k: cfg.get(k) for k in EDIT_OVERRIDE_KEYS}
    # motion_graphics edit.* altında değil (visuals.motion_graphics) -- override yoksa
    # config.yaml varsayılanını göster (yoksa panelde her zaman boş/kapalı görünürdü).
    if out.get("motion_graphics") is None:
        out["motion_graphics"] = load_config().get("visuals", {}).get("motion_graphics", {})
    return out


@app.put("/api/edit-settings")
def put_edit_settings(settings: dict = Body(...)):
    current = {k: load_edit_settings().get(k) for k in EDIT_OVERRIDE_KEYS}
    merged = {**current, **{k: v for k, v in settings.items() if k in EDIT_OVERRIDE_KEYS}}
    EDIT_SETTINGS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged


@app.post("/api/jobs/{job_id}/rerender")
def job_rerender(job_id: str):
    """Mevcut işi (avatar/görseller hazır) yeni altyazı stiliyle yeniden montajlar.
    GPU gerektirmez, hızlıdır."""
    d = OUTPUT_DIR / job_id
    if not d.is_dir():
        raise HTTPException(404, "İş bulunamadı")
    from pipeline.stages import s07_edit
    try:
        return s07_edit.run(job_id)
    except Exception as e:
        log.error(traceback.format_exc())
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------- statik --

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
