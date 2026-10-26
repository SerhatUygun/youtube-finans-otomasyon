"""Ajan 5 — Trend/format avcısı (17 Eki; döngü ajanı, yerel qwen3:14b).

İnternetten (API anahtarsız): YouTube'da TR + global ekonomi/altın/borsa aramaları (yt-dlp) -> hangi videolar patlıyor
(izlenme/gün), hangi başlık/süre kalıpları çalışıyor + global makro başlıklar (Google News EN) ->
yerel model "bizim kanal için ne yapmalı" sentezi -> output/_agents/trend_brief.json + output/_brain/trend_brief.md
(günlük prompt ve gece editörü okur; İLHAM — kopyalama yok, rakamlar yeniden doğrulanır).

  python tools/agents/trend_scout.py            # tek tur
  python tools/agents/trend_scout.py --no-llm   # yalnız topla
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from common import OUT, ROOT, alert, llm_json, log, ollama_up, unload, wait_free, write_json

AGENT = "trend"
MODEL = "qwen3:14b"
BRAIN = ROOT / "output" / "_brain"
JSON_OUT = OUT / "trend_brief.json"
MD_OUT = BRAIN / "trend_brief.md"
HIST = OUT / "trend_history.jsonl"

QUERIES = {
    "tr": ["gram altın yorum", "borsa istanbul analiz", "dolar altın faiz kararı", "ekonomi haftalık değerlendirme", "enflasyon ne olacak",
           "gümüş yatırım", "merkez bankası faiz kararı", "dolar kuru tahmin", "emekli maaş ekonomi", "kira konut fiyatları ekonomi",
           "petrol fiyatları türkiye", "birikim nasıl yapılır", "altın mı dolar mı", "kripto bitcoin türkçe", "ekonomi belgesel türkçe"],
    "global": ["gold price analysis", "global economy explained", "Fed rate decision explained", "stock market crash explained",
               "silver gold ratio", "economy documentary finance", "recession warning", "central banks buying gold",
               "oil price Hormuz", "dollar collapse explained", "inflation explained animation", "emerging markets crisis"],
    "shorts": ["altın shorts", "ekonomi shorts", "gold shorts", "finance shorts"],
}
NEWS_EN = ["global economy outlook", "gold price central banks", "Fed Warsh rates", "oil price OPEC", "emerging markets currency crisis"]


def ytdlp() -> list[str]:
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    for py in (sys.executable, r"python"):
        try:
            if subprocess.run([py, "-m", "yt_dlp", "--version"], capture_output=True, timeout=30).returncode == 0:
                return [py, "-m", "yt_dlp"]
        except Exception:  # noqa: BLE001
            continue
    return []


def run(cmd: list[str], timeout: int = 120) -> str:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    return r.stdout


def search(yt: list[str], q: str, n: int = 12) -> list[dict]:
    out = run(yt + ["--flat-playlist", "--print", "%(id)s|%(view_count)s|%(duration)s|%(channel)s|%(title)s", f"ytsearch{n}:{q}"])
    rows = []
    for line in out.splitlines():
        p = line.split("|", 4)
        if len(p) < 5:
            continue
        try:
            rows.append({"id": p[0], "views": int(p[1]) if p[1].isdigit() else 0, "dur": int(float(p[2])) if p[2] not in ("NA", "") else 0,
                         "channel": p[3], "title": p[4], "q": q})
        except ValueError:
            continue
    return rows


def age_days(yt: list[str], vid: str) -> int | None:
    out = run(yt + ["--skip-download", "--print", "%(upload_date)s", f"https://www.youtube.com/watch?v={vid}"], timeout=90).strip()
    try:
        return max((datetime.now() - datetime.strptime(out[:8], "%Y%m%d")).days, 1)
    except ValueError:
        return None


def news_en() -> list[str]:
    heads: list[str] = []
    for q in NEWS_EN:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}+when:2d&hl=en-US&gl=US&ceid=US:en"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
                root = ET.fromstring(r.read())
            heads += [(i.findtext("title") or "").strip() for i in root.iter("item")][:5]
        except Exception as e:  # noqa: BLE001
            log(AGENT, f"haber {q} alınamadı: {str(e)[:80]}")
    seen, out = set(), []
    for h in heads:
        k = h.lower()[:60]
        if h and k not in seen:
            seen.add(k)
            out.append(h)
    return out[:25]


def collect() -> dict:
    yt = ytdlp()
    if not yt:
        alert(AGENT, "hata", "yt-dlp bulunamadı")
        return {}
    cands: dict[str, dict] = {}
    from concurrent.futures import ThreadPoolExecutor
    jobs = [(scope, q) for scope, qs in QUERIES.items() for q in qs]
    with ThreadPoolExecutor(4) as ex:
        for (scope, q), rows in zip(jobs, ex.map(lambda j: search(yt, j[1]), jobs)):
            for r in rows:
                r["scope"] = scope
                cands.setdefault(r["id"], r)
    pool = sorted([r for r in cands.values() if r["views"] >= 2000], key=lambda r: -r["views"])[:90]
    with ThreadPoolExecutor(6) as ex:  # raw izlenmeye göre değil, YAŞA göre bakmak için hepsinin tarihi gerekir
        ages = list(ex.map(lambda r: age_days(yt, r["id"]), pool))
    top = []
    for r, d in zip(pool, ages):
        if d and d <= 30:
            r["age_d"], r["views_per_day"] = d, round(r["views"] / d)
            top.append(r)
    top.sort(key=lambda r: r["views_per_day"], reverse=True)
    for i, r in enumerate(top[:25], 1):
        r["no"] = f"V{i}"
    own = []
    hp = ROOT / "output" / "_brain" / "daily_history.jsonl"
    if hp.exists():
        for ln in hp.read_text(encoding="utf-8").splitlines()[-14:]:
            try:
                own.append(json.loads(ln).get("title") or "")
            except ValueError:
                pass
    return {"videos": top[:25], "haberler_en": news_en(), "bizim_son_basliklar": [t for t in own if t]}


SYSTEM = (
    "Sen 'Finans Kanalı' adlı Türkçe finans YouTube kanalının araştırma analistisin. Kanal: gram altın/gümüş, BIST, dolar, Fed/TCMB; "
    "TL perspektifi, rakam odaklı, hareketli grafik videolar (10-11 dk uzun + 2 kısa/gün). SADECE verilen veriye dayan; "
    "uydurma rakam/izlenme/yıl yazma; videolara YALNIZ 'no' koduyla (V1, V2...) atıf yap, izlenme sayısı yazma (kod ekler); "
    "veride olmayan gelecek yıl tahmini (2027 vb.) ve hedef fiyat UYDURMA; veri yoksa 'VARSAYIM' de. Başkasının anlatısını kopyalama önerisi verme — format ve açı öğren."
)


def synth(data: dict) -> dict:
    prompt = (
        "Aşağıda bugün YouTube'da (TR + global) öne çıkan ekonomi videoları (izlenme/gün sıralı) ve global makro başlıklar var.\n"
        "ÇIKTI tek JSON:\n"
        '{"ozet":"2 cümle: şu an ne çalışıyor",'
        '"calisan_formatlar":[{"kalip":"başlık/süre/anlatı kalıbı","kanit":["V1","V3"]}],'
        '"baslik_kaliplari":["başlıklardaki ortak yapılar (en çok 5)"],'
        '"global_gundem":[{"tema":"...","kanala_baglanti":"TL/gram altın/BIST kitlesine nasıl bağlanır"}],'
        '"bizde_olmayan":["bizim_son_basliklar ile karşılaştır: rakiplerde çalışan ama bizde olmayan konu/format (en çok 4)"],'
        '"video_fikirleri":[{"aci":"...","neden":"veri dayanağı","kanit":["V2"],"baslik_ornegi":"merak uyandıran, uydurma rakamsız","format":"uzun|short"}],'
        '"uyarilar":["tuzaklar: kopya riski, doğrulanması gereken rakamlar"]}\n\nVERİ:\n'
        + json.dumps(data, ensure_ascii=False)[:20000]
    )
    return llm_json(MODEL, prompt, system=SYSTEM, ctx=16384, temp=0.3, timeout=1200, keep="2m")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    data = collect()
    if not data.get("videos"):
        log(AGENT, "veri toplanamadı (internet/yt-dlp?)")
        return 1
    log(AGENT, f"{len(data['videos'])} video, {len(data['haberler_en'])} global başlık toplandı")
    res: dict = {}
    if not a.no_llm:
        if not ollama_up():
            log(AGENT, "Ollama kapalı — yalnız ham veri yazıldı")
        elif wait_free(AGENT, max_wait_s=2 * 3600):
            try:
                res = synth(data)
            except Exception as e:  # noqa: BLE001
                alert(AGENT, "hata", f"sentez üretilemedi: {str(e)[:160]}")
            finally:
                unload(MODEL)
    now = datetime.now().isoformat(timespec="seconds")
    write_json(JSON_OUT, {"at": now, "ham": data, "sentez": res})
    with open(HIST, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": now, "top": [(v["title"][:70], v.get("views_per_day")) for v in data["videos"][:5]]}, ensure_ascii=False) + "\n")
    byno = {v["no"]: v for v in data["videos"] if v.get("no")}

    def ev(k) -> str:  # kanıt = koddan gerçek veri; listede olmayan kod -> 'doğrulanamadı'
        ks = k if isinstance(k, list) else re.findall(r"V\d+", str(k or ""))
        got = [f"{byno[x]['channel']} {byno[x]['views_per_day']}/gün" for x in ks if x in byno]
        return "; ".join(got) if got else "kanıt doğrulanamadı"

    for x in res.get("video_fikirleri", []):  # uydurma gelecek yılı ele
        if re.search(r"20(2[7-9]|3\d)", str(x.get("baslik_ornegi", ""))):
            x["baslik_ornegi"] = "(uydurma yıl içeriyordu, silindi)"
    BRAIN.mkdir(parents=True, exist_ok=True)
    md = [f"# Trend özeti — {now[:16]} (yerel model; İLHAM — kopyalama, rakamları doğrula)", "", res.get("ozet", "(sentez yok)"), "", "## Öne çıkan videolar (izlenme/gün)"]
    md += [f"- {v.get('no')} · {v.get('views_per_day')}/gün · {v['views']:,} · {v['dur'] // 60} dk · {v['channel']} — {v['title']}" for v in data["videos"][:15]]
    md += ["", "## Çalışan formatlar"] + [f"- {x.get('kalip')} _({ev(x.get('kanit'))})_" for x in res.get("calisan_formatlar", [])]
    md += ["", "## Başlık kalıpları"] + [f"- {x}" for x in res.get("baslik_kaliplari", [])]
    md += ["", "## Global gündem → bizim kitle"] + [f"- **{x.get('tema')}**: {x.get('kanala_baglanti')}" for x in res.get("global_gundem", [])]
    md += ["", "## Bizde olmayan"] + [f"- {x}" for x in res.get("bizde_olmayan", [])]
    md += ["", "## Video fikirleri"] + [f"- **{x.get('aci')}** ({x.get('format')}) — {x.get('neden')} [{ev(x.get('kanit'))}] · örnek: {x.get('baslik_ornegi')}" for x in res.get("video_fikirleri", [])]
    md += ["", "## Uyarılar"] + [f"- {x}" for x in res.get("uyarilar", [])]
    MD_OUT.write_text("\n".join(md), encoding="utf-8")
    log(AGENT, f"yazıldı: {MD_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
