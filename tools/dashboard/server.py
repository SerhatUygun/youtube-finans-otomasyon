"""Finans Kanalı kontrol paneli (17 Eki) — yerel (127.0.0.1) masaüstü arayüzü: günlük koşu, ajanlar, döngü, zamanlanmış görevler, videolar.

  pythonw tools/dashboard/server.py --open     # sunucuyu başlatır (çalışıyorsa yalnız pencereyi açar), uygulama penceresi açar
Salt-okunur + güvenli düğmeler (ajan çalıştır / döngüyü başlat-durdur). Günlük üretimi/yüklemeyi buradan BAŞLATMAZ.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output"
AG = OUT / "_agents"
HERE = Path(__file__).resolve().parent
PORT = 8765
PY = ROOT / ".venv" / "Scripts" / "python.exe"
CACHE: dict[str, tuple[float, object]] = {}
RUN_NOW = {  # düğme -> komut (hepsi güvenli: yükleme/yayın yapmaz)
    "trend": ["tools/agents/trend_scout.py"], "haber": ["tools/agents/news_hunter.py"], "editor": ["tools/agents/night_editor.py"],
    "sistem": ["tools/agents/sys_watch.py"], "referans": ["tools/ref_watch.py"],
    "denetci": ["tools/agents/qa_auditor.py"], "bosluk": ["tools/agents/gap_analyst.py"],
    "beyin": ["tools/agents/brain.py"],
}
NO_WIN = 0x08000000 if os.name == "nt" else 0


def cached(key: str, ttl: float, fn):
    t = CACHE.get(key)
    if t and time.time() - t[0] < ttl:
        return t[1]
    try:
        v = fn()
    except Exception as e:  # noqa: BLE001
        v = {"hata": str(e)[:200]}
    CACHE[key] = (time.time(), v)
    return v


def rj(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def tail(p: Path, n: int = 14, width: int = 220) -> list[str]:
    try:
        raw = p.read_bytes()[-40000:]
        for enc in ("utf-8", "cp1254"):
            try:
                txt = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            txt = raw.decode("utf-8", "replace")
        if "Ã" in txt or "Ä" in txt:  # utf-8 yazılmış, cp1252 okunmuş log
            try:
                txt = txt.encode("cp1252", "ignore").decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                pass
        return [x[:width] for x in txt.splitlines()[-n:]]
    except OSError:
        return []


def pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001
        return False


def sched() -> list[dict]:
    ps = ("Get-ScheduledTask | Where-Object {$_.TaskName -like 'YTBot*'} | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; "
          "[pscustomobject]@{ad=$_.TaskName; durum=[string]$_.State; sonraki=$i.NextRunTime; son=$i.LastRunTime; sonuc=$i.LastTaskResult} } | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=40, creationflags=NO_WIN)
    d = json.loads(r.stdout or "[]")
    d = d if isinstance(d, list) else [d]
    for x in d:
        for k in ("sonraki", "son"):
            v = x.get(k)
            if isinstance(v, str) and v.startswith("/Date("):
                ms = int(v[6:v.index(")")].split("+")[0].split("-")[0])
                x[k] = datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")
    return d


def youtube_status(ids: list[str]) -> dict:
    sys.path.insert(0, str(ROOT))
    from googleapiclient.discovery import build
    from pipeline.stages import s09_upload as u
    yt = build("youtube", "v3", credentials=u._get_credentials(), cache_discovery=False)
    out = {}
    for i in yt.videos().list(part="snippet,status,statistics", id=",".join(ids[:40])).execute().get("items", []):
        st = i["status"]
        out[i["id"]] = {"gizlilik": st.get("privacyStatus"), "yayin": st.get("publishAt"), "izlenme": i.get("statistics", {}).get("viewCount"),
                        "baslik": i["snippet"]["title"]}
    return out


def videos() -> list[dict]:
    jobs = sorted(OUT.glob("daily-2*"), key=lambda p: p.name, reverse=True)[:3]
    rows, ids = [], []
    for j in jobs:
        up = rj(j / "upload_result.json", {}) or {}
        md = rj(j / "metadata.json", {}) or {}
        if up.get("video_id"):
            ids.append(up["video_id"])
            rows.append({"job": j.name, "tur": "uzun", "id": up["video_id"], "baslik": md.get("title", "")})
        for f in sorted((j / "_raw").glob("reel_*_upload.json")):
            r = rj(f, {}) or {}
            if r.get("video_id"):
                ids.append(r["video_id"])
                rows.append({"job": j.name, "tur": "short", "id": r["video_id"], "baslik": r.get("title", ""), "plan": r.get("publish_at")})
    live = cached("yt", 240, lambda: youtube_status(ids)) if ids else {}
    for r in rows:
        r["canli"] = live.get(r["id"]) if isinstance(live, dict) else None
    return rows


def daily() -> dict:
    lock = OUT / "_daily" / ".lock"
    d: dict = {"kilit": False}
    if lock.exists():
        try:
            pid = int(lock.read_text().strip().split()[0])
        except Exception:  # noqa: BLE001
            pid = 0
        d.update(kilit=True, pid=pid, canli=pid_alive(pid) if pid else False, yas_dk=round((time.time() - lock.stat().st_mtime) / 60))
    jobs = sorted(OUT.glob("daily-2*"), key=lambda p: p.name, reverse=True)
    if jobs:
        j = jobs[0]
        st = rj(j / "_raw" / "status.json", {}) or {}
        d["is"] = j.name
        d["adimlar"] = [{"ad": k, "saat": (v.get("at") or "")[11:16], "sn": v.get("sec") or v.get("seconds")} for k, v in st.items() if isinstance(v, dict)][-18:]
    d["log"] = tail(OUT / "_logs" / "daily_manual_out.log", 12)
    return d


def agents() -> dict:
    sysj = rj(AG / "system.json", {}) or {}
    news = rj(AG / "morning_brief.json", {}) or {}
    loop = rj(AG / "loop_state.json", {}) or {}
    if loop.get("pid") and not pid_alive(loop["pid"]):
        loop["calismiyor"] = True
    alerts = []
    try:
        for line in (AG / "alerts.jsonl").read_text(encoding="utf-8").splitlines()[-12:]:
            alerts.append(json.loads(line))
    except Exception:  # noqa: BLE001
        pass
    notes = sorted((AG / "editor_notes").glob("*.md"))
    trend = (OUT / "_brain" / "trend_brief.md")
    return {
        "sistem": sysj, "dongu": loop, "uyarilar": alerts[::-1],
        "haber": [{"puan": t.get("score"), "kat": t.get("cat"), "ozet": t.get("ozet"), "kaynak": t.get("outlet")} for t in (news.get("top") or [])[:6]],
        "haber_zaman": news.get("at"),
        "editor": notes[-1].read_text(encoding="utf-8")[:2500] if notes else "",
        "editor_dosya": notes[-1].name if notes else "",
        "trend": trend.read_text(encoding="utf-8")[:3500] if trend.exists() else "",
        "log": tail(AG / "agents.log", 14),
        "denetim": rj(AG / "audit.json", {}),
        "bosluk": (OUT / "_brain" / "gap_brief.md").read_text(encoding="utf-8")[:2500] if (OUT / "_brain" / "gap_brief.md").exists() else "",
    }


def system() -> dict:
    try:
        import psutil
        ram = psutil.virtual_memory()
        r = {"ram_bos_gb": round(ram.available / 1024 ** 3, 1), "ram_yuzde": ram.percent}
    except Exception:  # noqa: BLE001
        r = {}
    r["disk"] = {d: round(shutil.disk_usage(d + ":\\").free / 1024 ** 3, 1) for d in "CE"}
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=2) as f:
            r["ollama"] = [m["name"] for m in json.load(f).get("models", [])]
            r["ollama_acik"] = True
    except Exception:  # noqa: BLE001
        r["ollama_acik"] = False
    return r


def state() -> dict:
    return {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "gunluk": daily(), "ajanlar": agents(), "sistem": system(),
            "gorevler": cached("sched", 45, sched), "videolar": videos()}


def start(cmd: list[str]) -> None:
    subprocess.Popen([str(PY), "-X", "utf8", *cmd], cwd=str(ROOT), creationflags=NO_WIN | 0x00000200,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # sessiz
        pass

    def send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/state":
            self.send(200, json.dumps(state(), ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")
        elif u.path in ("/", "/index.html"):
            self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        else:
            self.send(404, b"yok", "text/plain")

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return self.send(403, b"{}", "application/json")
        msg = "?"
        if u.path == "/api/run":
            a = (q.get("ajan") or [""])[0]
            if a in RUN_NOW:
                start(RUN_NOW[a])
                msg = f"{a} başlatıldı"
        elif u.path == "/api/loop":
            if (q.get("islem") or [""])[0] == "baslat":
                start(["tools/agents/agent_loop.py"])
                msg = "döngü başlatıldı"
            else:
                pid = (rj(AG / "loop_state.json", {}) or {}).get("pid")
                if pid:
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NO_WIN)
                    (AG / "loop.pid").unlink(missing_ok=True)
                msg = "döngü durduruldu"
        self.send(200, json.dumps({"mesaj": msg}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")


def port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def open_window() -> None:
    url = f"http://127.0.0.1:{PORT}/"
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if Path(c).exists():
            subprocess.Popen([c, f"--app={url}", "--window-size=1500,950"])
            return
    webbrowser.open(url)


def main() -> None:
    if port_open():
        if "--open" in sys.argv:
            open_window()
        return
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    if "--open" in sys.argv:
        threading.Timer(1.0, open_window).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
