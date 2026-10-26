"""Referans kanal izleyici (13 Eki): config.yaml -> ref_watch.channel yeni video koyunca konu/tez/yapı özetini çıkarır.

AMAÇ: ilham ve konu tespiti. Çeviri/kopya DEĞİL — günlük prompt bu özeti okur ama cümle, ölçüm ve anlatı
kurgusunu kopyalamaz; rakamlar bizim kaynaklarımızdan (tv_data.py) yeniden doğrulanır, TL perspektifi eklenir.

Kullanım:
  python tools/ref_watch.py            # yeni videoları bul, output/_brain/ref_brief.md yaz
  python tools/ref_watch.py --all 3    # son 3 videoyu (görülmüş olsa da) yeniden işle
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BRAIN = ROOT / "output" / "_brain"
CHANNEL = ((yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}).get("ref_watch") or {}).get("channel") or ""
SEEN = BRAIN / "ref_seen.json"
BRIEF = BRAIN / "ref_brief.md"


def _ytdlp(args: list[str]) -> str:
    r = subprocess.run([sys.executable, "-m", "yt_dlp", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    return r.stdout


def latest(n: int) -> list[dict]:
    out = _ytdlp(["--flat-playlist", "--playlist-end", str(n), "--print", "%(id)s|%(view_count)s|%(duration_string)s|%(title)s", CHANNEL])
    vids = []
    for line in out.splitlines():
        p = line.split("|", 3)
        if len(p) == 4:
            vids.append({"id": p[0], "views": p[1], "dur": p[2], "title": p[3]})
    return vids


def transcript(vid: str) -> list[tuple[int, str]]:
    with tempfile.TemporaryDirectory() as d:
        _ytdlp(["--skip-download", "--write-auto-subs", "--sub-langs", "en-orig,en", "--sub-format", "vtt", "-o", f"{d}/v", f"https://youtu.be/{vid}"])
        files = sorted(Path(d).glob("*.vtt"))
        if not files:
            return []
        rows, last, cur, prev = [], "", 0, ""
        for line in files[0].read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"(\d\d):(\d\d):(\d\d)\.\d+ -->", line)
            if m:
                cur = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
                continue
            t = re.sub(r"<[^>]+>", "", line).strip()
            if not t or t.startswith(("WEBVTT", "Kind", "Language")) or t == last:
                continue
            last = t
            if t in prev:
                continue
            rows.append((cur, t))
            prev = t
        return rows


def nums(text: str) -> list[str]:
    seen, out = set(), []
    for m in re.findall(r"\$?\d[\d,\.]*\s?(?:%|percent|billion|trillion|tonnes|years?)?", text):
        m = m.strip()
        if len(m) >= 3 and m not in seen:
            seen.add(m)
            out.append(m)
    return out[:40]


def brief(v: dict) -> str:
    rows = transcript(v["id"])
    if not rows:
        return f"## {v['title']}\n(altyazı alınamadı)\n"
    words = sum(len(t.split()) for _, t in rows)
    hook = " ".join(t for s, t in rows if s < 80)
    full = " ".join(t for _, t in rows)
    return (
        f"## {v['title']}\n- https://youtu.be/{v['id']} · {v['dur']} · {v['views']} izlenme · ~{words} kelime\n"
        f"- **Açılış (ilk 80 sn, YALNIZ yapıyı anlamak için):** {hook[:900]}\n"
        f"- **Sayılar (bizim kaynaklarımızdan yeniden doğrula, USD→TL çevir):** {', '.join(nums(full))}\n"
        f"- **Bizim için yapılacak:** konuyu/tezi al; kendi ölçümün + tv_data.py + TL perspektifiyle ÖZGÜN anlat. Cümle/ölçüm kopyalama.\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", type=int, metavar="N", help="son N videoyu görülmüş olsa da işle")
    a = ap.parse_args()
    if not CHANNEL:
        print("config.yaml -> ref_watch.channel boş, referans kanal izlenmiyor")
        return
    BRAIN.mkdir(parents=True, exist_ok=True)
    seen = set(json.loads(SEEN.read_text(encoding="utf-8"))) if SEEN.exists() else set()
    vids = latest(a.all or 5)
    new = vids if a.all else [v for v in vids if v["id"] not in seen]
    if not new:
        print("yeni referans video yok")
        return
    head = f"# Referans kanal özeti — {datetime.now():%d.%m.%Y %H:%M}\nKAYNAK: {CHANNEL}. Yalnız konu/tez/yapı ilhamı; kopya ve çeviri YASAK.\n\n"
    BRIEF.write_text(head + "\n".join(brief(v) for v in new[:3]), encoding="utf-8")
    SEEN.write_text(json.dumps(sorted(seen | {v["id"] for v in vids})), encoding="utf-8")
    print(f"{len(new)} yeni video -> {BRIEF}")
    for v in new:
        print(" ", v["id"], v["title"])


if __name__ == "__main__":
    main()
