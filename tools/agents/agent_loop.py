"""Ajan döngüsü (17 Eki): araştırma/editör ajanlarını gece boyu tekrar tekrar çalıştırır; günlük koşuda kendini geri çeker.

Görevler (aralık dakika): trend_scout 180 · night_editor 240 · ref_watch 360 · news_hunter 60.
Ağır iş (günlük koşu/render) sürerken LLM'li görev başlatılmaz; --until saatinde (varsayılan 11:45) çıkar, 12:00 koşusuna yer bırakır.
Durum: output/_agents/loop_state.json (arayüz bunu okur). Tek kopya: loop.pid.

  python tools/agents/agent_loop.py [--until 11:45] [--once]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

from common import OUT, ROOT, busy, log, read_json, write_json

AGENT = "dongu"
STATE = OUT / "loop_state.json"
PID = OUT / "loop.pid"
PY = sys.executable
TASKS = {  # ad: (komut, aralık dk, zaman aşımı sn)
    "trend_scout": (["tools/agents/trend_scout.py"], 180, 2400),
    "night_editor": (["tools/agents/night_editor.py"], 240, 3600),
    "ref_watch": (["tools/ref_watch.py"], 360, 1200),
    "news_hunter": (["tools/agents/news_hunter.py"], 60, 1500),
    "gap_analyst": (["tools/agents/gap_analyst.py"], 240, 900),
    "brain": (["tools/agents/brain.py"], 45, 1800),
    "qa_auditor": (["tools/agents/qa_auditor.py"], 30, 120),  # en sonda: diğerlerinin çıktısını denetler
}


def alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001
        return False


def save(state: dict) -> None:
    state["heartbeat"] = datetime.now().isoformat(timespec="seconds")
    write_json(STATE, state)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default="11:45")
    ap.add_argument("--once", action="store_true", help="her görevi bir kez çalıştırıp çık")
    a = ap.parse_args()
    if PID.exists():
        try:
            old = int(PID.read_text().strip())
            if old != os.getpid() and alive(old):
                log(AGENT, f"zaten çalışıyor (pid {old})")
                return 0
        except ValueError:
            pass
    PID.write_text(str(os.getpid()))
    h, m = map(int, a.until.split(":"))
    deadline = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    if deadline <= datetime.now():
        deadline += timedelta(days=1)
    prev = read_json(STATE, {})
    state = {"pid": os.getpid(), "started": datetime.now().isoformat(timespec="seconds"), "until": deadline.isoformat(timespec="minutes"),
             "tasks": {k: {"interval_min": v[1], **(prev.get("tasks", {}).get(k, {}))} for k, v in TASKS.items()}, "current": None}
    log(AGENT, f"döngü başladı, bitiş {deadline:%H:%M}")
    save(state)
    try:
        while datetime.now() < deadline:
            ran = False
            for name, (cmd, every, tmo) in TASKS.items():
                t = state["tasks"][name]
                last = t.get("last_end")
                gap = 20 if t.get("last_code") not in (0, None) else every  # hata/kesinti -> 20 dk sonra yeniden dene
                due = (not last) or datetime.now() - datetime.fromisoformat(last) >= timedelta(minutes=gap)
                if not due or datetime.now() >= deadline:
                    continue
                why = busy()
                if why:
                    t["skipped"] = f"{datetime.now():%H:%M} meşgul: {why}"
                    continue
                state["current"] = name
                t["last_start"] = datetime.now().isoformat(timespec="seconds")
                save(state)
                log(AGENT, f"başlıyor: {name}")
                code, tail = -1, ""
                try:
                    r = subprocess.run([PY, "-X", "utf8", str(ROOT / cmd[0])], cwd=str(ROOT), capture_output=True, text=True,
                                       encoding="utf-8", errors="replace", timeout=tmo,
                                       creationflags=0x08000000 if os.name == "nt" else 0)  # konsol penceresi açma
                    code, tail = r.returncode, (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
                    tail = tail[0][:200]
                except subprocess.TimeoutExpired:
                    tail = f"zaman aşımı ({tmo}s)"
                t.update(last_end=datetime.now().isoformat(timespec="seconds"), last_code=code, last_msg=tail, runs=t.get("runs", 0) + 1)
                t.pop("skipped", None)
                state["current"] = None
                save(state)
                log(AGENT, f"bitti: {name} kod {code}")
                ran = True
            if a.once:
                break
            save(state)
            if not ran:
                time.sleep(60)
    finally:
        state["current"] = None
        state["stopped"] = datetime.now().isoformat(timespec="seconds")
        save(state)
        try:
            PID.unlink()
        except OSError:
            pass
        log(AGENT, "döngü bitti")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
