"""Ajan 5 — Sistem bekçisi (10 dakikada bir; model YOK, saniyeler sürer).

Kontroller -> output/_agents/system.json + sorun varsa alerts.jsonl:
  - C:/E: boş alan (C: 2 kez dolup render'ı öldürdü), Remotion temp birikmesi (.tmp)
  - günlük kilit: sahibi ölü / 4 saatten eski
  - yeni HATA dosyası (output/_daily/*_HATA.txt)
  - Ollama ayakta mı, RAM
  - diğer ajanların son çalışma zamanı (haber > 3 saat, performans > 14 saat sessizse uyarı)
  - Google yetki tokenı (Test modunda 7 günde düşer)
Aynı uyarı 6 saatte bir tekrarlanır (spam yok).
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timedelta

from common import OUT, ROOT, alert, log, ollama_up, read_json, write_json

AGENT = "sistem"
STATE = OUT / "system.json"
GB = 1024 ** 3


def dir_size(p) -> int:
    tot = 0
    try:
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    tot += f.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return tot


def main() -> int:
    import psutil
    st = read_json(STATE, {})
    last_alert: dict = st.get("last_alert", {})
    issues: list[tuple[str, str, str]] = []  # (anahtar, seviye, mesaj)
    now = datetime.now()

    disks = {}
    for d, warn, crit in (("C:\\", 15, 6), ("E:\\", 25, 10)):
        free = shutil.disk_usage(d).free / GB
        disks[d[0]] = round(free, 1)
        if free < crit:
            issues.append((f"disk{d[0]}", "kritik", f"{d[0]}: diskinde yalnız {free:.1f} GB boş — render çökebilir"))
        elif free < warn:
            issues.append((f"disk{d[0]}", "uyarı", f"{d[0]}: diskinde {free:.1f} GB boş"))

    tmp = ROOT / ".tmp"
    tmp_gb = dir_size(tmp) / GB if tmp.exists() else 0
    if tmp_gb > 15:
        issues.append(("tmp", "uyarı", f".tmp klasörü {tmp_gb:.1f} GB (Remotion artıkları?)"))

    lock = ROOT / "output" / "_daily" / ".lock"
    lock_info = None
    if lock.exists():
        age_h = (time.time() - lock.stat().st_mtime) / 3600
        try:
            pid = int(lock.read_text(encoding="utf-8").strip() or 0)
        except ValueError:
            pid = 0
        alive = bool(pid) and psutil.pid_exists(pid)
        lock_info = {"pid": pid, "age_h": round(age_h, 1), "alive": alive}
        if not alive:
            issues.append(("lock", "uyarı", f"günlük kilit sahipsiz (pid {pid} yaşamıyor) — sonraki koşu temizler"))
        elif age_h > 4:
            issues.append(("lock", "uyarı", f"günlük koşu {age_h:.1f} saattir sürüyor — takılmış olabilir"))

    seen = set(st.get("seen_errors", []))
    errs = sorted((ROOT / "output" / "_daily").glob("*_HATA.txt"))
    for e in errs:
        if e.name not in seen and e.stat().st_mtime > time.time() - 2 * 86400:
            first = e.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:] or [""]
            alert(AGENT, "hata", f"yeni hata dosyası {e.name}: {first[0][:160]}")
        seen.add(e.name)

    ram = psutil.virtual_memory()
    up = ollama_up()
    if not up:
        issues.append(("ollama", "uyarı", "Ollama çalışmıyor — haber/performans ajanları modelsiz çalışır"))

    # diğer ajanların nabzı
    beats = {}
    logf = OUT / "agents.log"
    if logf.exists():
        for ln in logf.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]:
            try:
                ts, rest = ln[:19], ln[20:]
                name = rest[1:rest.index("]")]
                beats[name] = ts
            except ValueError:
                continue
    for name, max_h in (("haber", 3), ("performans", 14)):
        ts = beats.get(name)
        if ts and now - datetime.fromisoformat(ts) > timedelta(hours=max_h):
            issues.append((f"beat-{name}", "uyarı", f"{name} ajanı {max_h} saatten uzun süredir çalışmadı (Görev Zamanlayıcı?)"))

    tok = ROOT / "secrets" / "youtube_token.json"
    if tok.exists():
        age_d = (time.time() - tok.stat().st_mtime) / 86400
        if age_d > 6:
            issues.append(("token", "uyarı", f"Google yetki tokenı {age_d:.0f} günlük — Test modunda 7. günde düşer: tools/reauth_google.py"))

    for key, lvl, msg in issues:
        prev = last_alert.get(key)
        if not prev or now - datetime.fromisoformat(prev) > timedelta(hours=6):
            alert(AGENT, lvl, msg)
            last_alert[key] = now.isoformat(timespec="seconds")
    active = {k for k, _, _ in issues}
    last_alert = {k: v for k, v in last_alert.items() if k in active}  # düzelen sorun tekrar olursa hemen uyarsın

    write_json(STATE, {"at": now.isoformat(timespec="seconds"), "disk_free_gb": disks, "tmp_gb": round(tmp_gb, 1), "lock": lock_info,
                       "ram_free_gb": round(ram.available / GB, 1), "ollama": up, "agents_last": beats,
                       "issues": [m for _, _, m in issues], "last_alert": last_alert, "seen_errors": sorted(seen)[-300:]})
    log(AGENT, f"kontrol: {len(issues)} sorun · C {disks.get('C')} GB · E {disks.get('E')} GB boş")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
