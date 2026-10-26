"""Yerel (Ollama) sürekli ajanların ortak altyapısı (2 Eki 2026).

- busy(): video üretimi sürüyorsa (günlük kilit / Remotion render / TTS / whisper / LatentSync) True -> LLM'li ajan beklemeye geçer.
  16 GB RAM + tek GPU: render sırasında 9-18 GB'lık model yüklemek render'ı çökertir.
- llm_json(): Ollama /api/chat, JSON çıktı; tur içinde model 3 dk bellekte kalır, tur sonunda unload() ile ATILIR.
- alert(): output/_agents/alerts.jsonl (günlük hat ve Claude oturumu buradan okur).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "output" / "_agents"
OUT.mkdir(parents=True, exist_ok=True)
OLLAMA = "http://localhost:11434"

# komut satırında bunlardan biri geçen süreç = GPU/RAM ağır iş sürüyor
HEAVY = ("daily_run.py", "edit_footage.py", "remotion render", "remotion still", "run_voxcpm", "run_latentsync", "make_shorts",
         "template_gallery", "run_test_", "run_2026", "gen_one.py")


def busy() -> str | None:
    """Ağır iş varsa nedenini döndürür, yoksa None."""
    lock = ROOT / "output" / "_daily" / ".lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < 4 * 3600:
        return "günlük kilit"
    try:
        import psutil
        for p in psutil.process_iter(["name", "cmdline"]):
            name = (p.info.get("name") or "").lower()
            if not name.startswith(("python", "node")):
                continue
            cmd = " ".join(p.info.get("cmdline") or [])
            for h in HEAVY:
                if h in cmd:
                    return h
    except Exception:  # noqa: BLE001
        pass
    return None


def log(agent: str, msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} [{agent}] {msg}"
    print(line, flush=True)
    with open(OUT / "agents.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def alert(agent: str, level: str, msg: str) -> None:
    rec = {"at": datetime.now().isoformat(timespec="seconds"), "agent": agent, "level": level, "msg": msg}
    with open(OUT / "alerts.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(agent, f"UYARI[{level}] {msg}")


def ollama_up() -> bool:
    import requests
    try:
        return requests.get(f"{OLLAMA}/api/tags", timeout=3).ok
    except Exception:  # noqa: BLE001
        return False


def unload(model: str) -> None:
    """Modeli bellekten at (render'a yer aç)."""
    import requests
    try:
        requests.post(f"{OLLAMA}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    except Exception:  # noqa: BLE001
        pass


def llm_json(model: str, prompt: str, *, system: str = "", ctx: int = 8192, temp: float = 0.2, timeout: int = 900,
             keep: str = "3m") -> dict:
    import requests
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "stream": False, "format": "json", "keep_alive": keep, "messages": msgs,
            "options": {"num_ctx": ctx, "temperature": temp}}
    if model.startswith("qwen3"):
        body["think"] = False
    r = requests.post(f"{OLLAMA}/api/chat", json=body, timeout=timeout)
    r.raise_for_status()
    txt = r.json()["message"]["content"].strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        a, b = txt.find("{"), txt.rfind("}")
        return json.loads(txt[a:b + 1])


def wait_free(agent: str, max_wait_s: int = 0) -> bool:
    """Ağır iş yoksa True. max_wait_s>0 ise o kadar bekler (60 sn aralıkla)."""
    t0 = time.time()
    while True:
        why = busy()
        if not why:
            return True
        if time.time() - t0 >= max_wait_s:
            log(agent, f"atlandı: video üretimi sürüyor ({why})")
            return False
        time.sleep(60)


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def write_json(p: Path, data) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
