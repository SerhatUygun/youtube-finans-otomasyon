"""Günlük iş klasöründen (Claude'un yazdığı brief/video/reels/thumb/series.json) bitmiş çıktılar üretir:
ses (tek VoxCPM çağrısı + ses kapısı) -> zaman çizelgeleri -> Remotion planları -> render (uzun + 2 Reels + 3 kapak)
-> süre kontrolü -> YouTube PRIVATE yükleme (+ kapak A) -> Drive (Reels + metinler + B/C kapak) -> geçmiş kaydı.

Her adım `_raw/status.json`'a yazılır; `--resume` ile tamamlanan adımlar atlanır.
"""
from __future__ import annotations

import json
import os
import zlib
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.daily import timeline as tlmod  # noqa: E402
from pipeline.daily import voice  # noqa: E402
from pipeline.utils.config import load_config  # noqa: E402


def _tr_up(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def _hook_big(reel: dict) -> str:
    """Shorts 0. kare damgası: reels.json hook_big; yoksa ilk cümledeki ilk rakam ifadesi, o da yoksa başlığın ilk 3 kelimesi."""
    import re
    if reel.get("hook_big"):
        return _tr_up(str(reel["hook_big"])[:24])
    first = (reel.get("segments") or [{}])[0].get("text", "")
    m = re.search(r"(?:%\s?)?\d[\d.,]*(?:\s?(?:bin|milyon|milyar))?(?:\s?(?:TL|dolar|\$|lira|puan))?", first, re.I)
    if m and len(m.group(0)) >= 2:
        return _tr_up(m.group(0).strip())
    return _tr_up(" ".join(str(reel.get("title", "")).split()[:3]).rstrip(",:?"))


_VIS = {**{c: "A" for c in "aâı"}, **{c: "E" for c in "eiî"}, **{c: "O" for c in "oöuüû"}, **{c: "M" for c in "mbp"}, **{c: "F" for c in "fv"}}


def _presenter_track(wav: Path, segments: list[dict], total: int, fps: int = 30) -> dict:
    """2D sunucu için kare başına ağız enerjisi (0..1, 2 ondalık) + ağız şekli (X/M/A/E/O/F).
    Şekil: kelimenin harfleri kelime süresine eşit yayılır; ünsüzde önceki ünlü şekli sürer, m/b/p dudak kapatır."""
    import numpy as np
    import soundfile as sf
    a, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    hop = sr / fps
    rms = np.array([np.sqrt(np.mean(a[int(i * hop):int((i + 1) * hop)] ** 2)) if int(i * hop) < len(a) else 0.0 for i in range(total)])
    ref = np.percentile(rms[rms > 0], 95) if (rms > 0).any() else 1.0
    m = np.clip(rms / (ref + 1e-6), 0, 1)
    m[m < 0.12] = 0
    m = m ** 0.8
    vis = ["X"] * total
    for seg in segments:
        for w in seg.get("words", []):
            s, e = int(w["s"]), int(w.get("e", w["s"] + 8))
            txt = [c for c in w["w"].lower() if c.isalpha()]
            if not txt or e <= s:
                continue
            cur = "E"
            for k in range(s, min(e, total)):
                c = txt[min(int((k - s) / (e - s) * len(txt)), len(txt) - 1)]
                v = _VIS.get(c)
                if v in ("A", "E", "O"):
                    cur = v
                vis[k] = v if v in ("M", "F") else cur
    return {"mouth": [round(float(x), 2) for x in m], "vis": "".join(vis)}


def _emphasis(wav: Path, segments: list[dict], fps: int = 30, gap: int = 240) -> list[int]:
    """Kelime bazında ses enerjisi: çevresine göre en güçlü vurgulanan kelimelerin başlangıç karesi.
    Aralarında en az `gap` kare; ilk 2 sn ve son segment hariç. Kamera yakınlaşması bu karelerde olur."""
    import numpy as np
    import soundfile as sf
    a, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    a = a.mean(axis=1)
    words = [w for seg in segments[:-1] for w in seg.get("words", []) if w.get("s", 0) > 2 * fps]
    if len(words) < 8:
        return []
    def rms(s, e):
        x = a[int(s / fps * sr):max(int(e / fps * sr), int(s / fps * sr) + 1)]
        return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
    en = np.array([rms(w["s"], w.get("e", w["s"] + 8)) for w in words])
    # yerel ortalamaya göre (±10 kelime) göreli vurgu; kısa kelimeler ("ve", "bu") elenir
    rel = np.array([en[i] / (np.mean(en[max(0, i - 10):i + 11]) + 1e-6) for i in range(len(en))])
    rel[[len(w["w"].strip(".,!?;:")) < 4 for w in words]] = 0
    picked: list[int] = []
    for i in np.argsort(-rel):
        if rel[i] < 1.25:
            break
        f = int(words[i]["s"])
        if all(abs(f - p) >= gap for p in picked):
            picked.append(f)
    return sorted(picked)

REMOTION = ROOT / "remotion"
NPX = "npx.cmd" if sys.platform == "win32" else "npx"


# 30 Eyl OLAYI: Remotion her render'da %TEMP%'e ~0,4 GB önbellek bırakıyor (yarıda kesilenler silinmiyor) -> C: 0 GB'a
# düştü, render ENOSPC ile çöktü. Geçici dosyalar E:'ye yönlendirilir ve her render sonrası temizlenir.
RENDER_TMP = ROOT / ".tmp"


def render_env() -> dict:
    import os
    RENDER_TMP.mkdir(exist_ok=True)
    env = dict(os.environ)
    env["TEMP"] = env["TMP"] = str(RENDER_TMP)
    return env


def clean_render_tmp(max_age_s: float = 60):
    """E: .tmp klasöründeki Remotion önbelleklerini ve (yönlendirmesiz çalışan elle komutlardan kalan) sistem %TEMP% kopyalarını siler.
    30 Eyl'de C: iki kez 0 GB'a düştü (bir seferinde 16 klasör = 29 GB)."""
    import os
    import shutil
    now = time.time()
    dirs = list(RENDER_TMP.glob("*"))
    sys_tmp = Path(os.environ.get("TEMP", "")) if os.environ.get("TEMP") else None
    max_sys = 1800  # sistem TEMP'te yalnız 30 dk'dan eski olanlar (başka bir render sürüyor olabilir)
    if sys_tmp and sys_tmp.exists() and sys_tmp.resolve() != RENDER_TMP.resolve():
        dirs += [d for d in sys_tmp.glob("remotion-*")] + [d for d in sys_tmp.glob("react-motion*")]
    for d in dirs:
        # 30 Eyl HATASI: Remotion'un kısa ömürlü .tmp dosyaları glob ile stat arasında silinince FileNotFoundError
        # tüm render'ı düşürdü -> yalnız klasörler, her hata yutulur (temizlik asla işi durdurmaz)
        try:
            if not (d.is_dir() and d.name.startswith(("remotion-", "react-motion"))):
                continue
            age = now - d.stat().st_mtime
            lim = max_age_s if d.parent.resolve() == RENDER_TMP.resolve() else max_sys
            if age > lim:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            continue


class Build:
    def __init__(self, job_dir: Path, log=print, twin: bool = False):
        self.job = job_dir
        self.job_id = job_dir.name
        self.raw = job_dir / "_raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.cfg = load_config().get("daily", {})
        self.cfg_yt = load_config().get("youtube", {})
        self.status_file = self.raw / "status.json"
        self.status = json.loads(self.status_file.read_text(encoding="utf-8")) if self.status_file.exists() else {}
        rd = lambda n: json.loads((job_dir / n).read_text(encoding="utf-8"))
        # 9 Eki: haftada 3 uzun video — diğer günler yalnız Shorts (video.json/thumb.json yazılmaz)
        self.shorts_only = not (job_dir / "video.json").exists()
        self.reels, self.brief = rd("reels.json"), rd("brief.json")
        self.video = rd("video.json") if not self.shorts_only else {"title": self.reels[0].get("title", ""), "segments": [], "scenes": []}
        self.thumb = rd("thumb.json") if not self.shorts_only else {}
        snap = rd("series.json")
        self.series = {k: v["series"] for k, v in snap.items() if isinstance(v, dict) and "series" in v}
        self.snap = snap
        self.pub = REMOTION / "public" / "auto" / self.job_id
        self.pub.mkdir(parents=True, exist_ok=True)
        # Çekim modu (tools/edit_footage.py): ses/zaman çizelgesi çekimden gelir, TTS yok; kamera taban katman.
        ff = self.raw / "footage.json"
        self.footage = json.loads(ff.read_text(encoding="utf-8")) if ff.exists() else None
        # Dijital ikiz modu: TTS sesi (voice.wav) kanal sahibinin taban çekimine dudak-senkronlanır -> kamera katmanı olur.
        self.twin = twin and not self.footage
        self.lang = (self.footage or {}).get("lang", "tr")

    # ---------------------------------------------------------------- yardımcılar
    def _done(self, step: str, **info):
        self.status[step] = {"at": datetime.now().isoformat(timespec="seconds"), **info}
        self.status_file.write_text(json.dumps(self.status, ensure_ascii=False, indent=1), encoding="utf-8")

    def _skip(self, step: str) -> bool:
        return step in self.status

    def _npx(self, args: list[str], log_name: str, timeout: int = 3 * 3600):
        for attempt in range(3):
            with open(self.raw / log_name, "w", encoding="utf-8") as lf:
                r = subprocess.run([NPX, "remotion", *args], cwd=str(REMOTION), stdout=lf, stderr=subprocess.STDOUT, timeout=timeout, env=render_env())
            clean_render_tmp()
            # 3-5 Eki: geçici Chrome sorunları ("connect to the browser" zaman aşımı, "Page crashed") -> bekle, yeniden dene
            txt = (self.raw / log_name).read_text(encoding="utf-8", errors="ignore")[-4000:]
            if r.returncode == 0 or not ("connect to the browser" in txt or "Page crashed" in txt):
                break
            self.log(f"remotion {args[0]} geçici tarayıcı hatası, {attempt + 1}. yeniden deneme")
            time.sleep(30)
        if r.returncode != 0:
            raise RuntimeError(f"remotion {args[0]} başarısız, log: {self.raw / log_name}")

    # ---------------------------------------------------------------- 1) ses
    def tts(self):
        if self._skip("tts") or self.footage:
            return
        items = []
        for i, s in enumerate(self.video["segments"]):
            items.append({"text": s["tts"], "out": str(self.raw / "tts_long" / f"seg_{i:03d}.wav")})
        for r_i, r in enumerate(self.reels):
            for i, s in enumerate(r["segments"]):
                items.append({"text": s["tts"], "out": str(self.raw / f"tts_reel{r_i + 1}" / f"seg_{i:03d}.wav")})
        for L, hv in self._hooks():
            items.append({"text": hv["segments"][0]["tts"], "out": str(self.raw / f"tts_hook{L}" / "seg_000.wav")})
        t0 = time.time()
        rep = voice.synth(items, self.raw / "tts.log", self.raw / "voice_gate.json")
        retried = sum(1 for x in rep["items"] if x.get("tries", 1) > 1)
        bad = [x["i"] for x in rep["items"] if x.get("score", 0) > 1.0]
        self.log(f"ses: {len(items)} segment, {retried} yeniden denendi, tolerans dışı kalan {len(bad)} ({time.time() - t0:.0f}s)")
        self._done("tts", segments=len(items), retried=retried, out_of_tolerance=bad)

    # ---------------------------------------------------------------- 2) zaman çizelgesi
    def timelines(self):
        if self._skip("timelines") or self.footage:
            return
        from faster_whisper import WhisperModel
        wm = WhisperModel("large-v3", device="cuda", compute_type="int8")
        tl = {"seconds": 0}
        if not self.shorts_only:
            before = {sc["before"] for sc in self.video["scenes"] if sc.get("t") == "Chapter"}
            segs = self.video["segments"]
            tl = tlmod.build(segs, [self.raw / "tts_long" / f"seg_{i:03d}.wav" for i in range(len(segs))], self.pub / "voice.wav",
                             chapter_before=before, intro_s=1.0, whisper_model=wm, log=self.log)  # 30 Eyl: sessiz giriş 3,2→1 sn (kanca hemen)
            (self.raw / "timeline_long.json").write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
            self.log(f"uzun video sesi: {tl['seconds'] / 60:.2f} dk")
        for r_i, r in enumerate(self.reels):
            rs = r["segments"]
            rtl = tlmod.build(rs, [self.raw / f"tts_reel{r_i + 1}" / f"seg_{i:03d}.wav" for i in range(len(rs))], self.pub / f"reel{r_i + 1}.wav",
                              intro_s=0.35, sent_pause=0.18, tail_s=1.6, whisper_model=wm, log=self.log)
            (self.raw / f"timeline_reel{r_i + 1}.json").write_text(json.dumps(rtl, ensure_ascii=False), encoding="utf-8")
            self.log(f"reel{r_i + 1} sesi: {rtl['seconds']:.1f} sn")
        for L, hv in self._hooks():
            wav = self.raw / f"tts_hook{L}" / "seg_000.wav"
            if not wav.exists():
                continue
            htl = tlmod.build(hv["segments"], [wav], self.pub / f"hook{L}.wav", intro_s=1.0, tail_s=0.04, whisper_model=wm, log=self.log)
            (self.raw / f"timeline_hook{L}.json").write_text(json.dumps(htl, ensure_ascii=False), encoding="utf-8")
            self.log(f"açılış {L} sesi: {htl['seconds']:.1f} sn")
        del wm
        self._done("timelines", seconds=tl["seconds"])

    # ---------------------------------------------------------------- 2b) dijital ikiz
    def twin_video(self):
        if not self.twin or self._skip("twin"):
            return
        from pipeline import twin
        t0 = time.time()
        twin.lipsync(self.pub / "voice.wav", self.pub / "twin.mp4", self.raw / "twin", log=self.log)
        self._done("twin", sec=round(time.time() - t0))
        self.log(f"dijital ikiz: {time.time() - t0:.0f}s")

    # ---------------------------------------------------------------- 3) planlar
    def _plan(self, tl: dict, spec: dict, layout: str, voice_file: str, music_file: str) -> dict:
        scenes = []
        for sc in spec["scenes"]:
            sc = dict(sc)
            if sc.get("t") == "Chapter":
                sc["from"] = tl["chapterFrom"].get(str(sc["before"]), tl["chapterFrom"].get(sc["before"]))
                if sc["from"] is None:
                    sc["from"] = tl["segments"][sc["before"]]["s"] - 70
            scenes.append(sc)
        plan = {k: tl[k] for k in ("fps", "total", "outroStart", "segments")}
        plan.update(layout=layout, scenes=scenes, series=self.series, hits=[h for h in spec.get("hits", []) if h.get("sfx")],
                    audio={"voice": voice_file, "music": music_file})
        if self.footage and layout == "h":
            plan["footage"] = {"src": self.footage["src"], "volume": self.footage.get("volume", 1)}
            if self.footage.get("faceX") is not None:
                plan["footage"]["faceX"] = self.footage["faceX"]
        if self.footage and self.footage.get("brand"):  # 1 Eki: başka kanal kurgusu (ör. Other Channel, İngilizce)
            plan["brand"] = self.footage["brand"]
        bj = (ROOT / "remotion" / "public" / music_file).with_suffix(".beat.json")
        if bj.exists():  # 9 Eki: sahne kesmeleri müzik vuruşuna hizalanır (AutoVideo timedScenes)
            plan["beat"] = round(json.loads(bj.read_text(encoding="utf-8"))["beat_s"] * tl["fps"], 3)
        if not self.footage and not self.twin and self.cfg.get("presenter", {}).get("enabled", True):
            try:  # 9 Eki: 2D çizim sunucu — ağız enerjisi + ağız şekli izi (AutoVideo PresenterLayer)
                plan["presenter"] = _presenter_track(ROOT / "remotion" / "public" / voice_file, tl["segments"], tl["total"])
            except Exception as e:  # noqa: BLE001
                self.log(f"!! sunucu ağız izi atlandı: {str(e)[:120]}")
            if layout == "h" and self.cfg.get("presenter", {}).get("pip"):  # 13 Eki: referans düzeni — sol altta sabit kutu
                plan["presenterPip"] = True
                if self.cfg.get("presenter", {}).get("style") == "3d":  # 18 Eki: takım elbiseli 3D çizgi sunucu
                    plan["presenter3d"] = True
                    plan["presenterVariant"] = self.cfg.get("presenter", {}).get("variant", "sade")
        try:  # 9 Eki: seste vurgulu anlar -> hafif kamera yakınlaşması (AutoVideo Punch)
            plan["emph"] = _emphasis(ROOT / "remotion" / "public" / voice_file, tl["segments"], gap=240 if layout == "h" else 150)
        except Exception as e:  # noqa: BLE001
            self.log(f"!! vurgu analizi atlandı: {str(e)[:120]}")
        if self.lang != "tr":
            plan["lang"] = self.lang
        elif self.twin and layout == "h":
            plan["footage"] = {"src": f"auto/{self.job_id}/twin.mp4", "volume": 1}
            # günlük sahnelerde layout yok: grafik ağırlıklı kalsın, bölüm kartı/sonuç tam ekran, sebep/rakam sahneleri split
            for i, sc in enumerate(plan["scenes"]):
                sc.setdefault("layout", "cam" if i == 0 or sc.get("t") in ("Intro", "Outro") else
                              "full" if sc.get("t") in ("Chapter", "Chart", "Ladder", "Scenario", "Timeline", "Disclaimer") else
                              "corner" if sc.get("t") in ("Stamp", "StatCards", "Gauge") else "split")
        if layout == "h":
            plan["hud"] = {"date": self.video.get("hud_date", ""), "label": "LAST CLOSE" if self.lang == "en" else "SON KAPANIŞ",
                           "chapters": [{"name": c["name"], "cue": str(c.get("seg", 0))} for c in self.video.get("chapters_hud", [])]}
            plan["ticker"] = self._ticker(self.video.get("ticker", []))
        else:
            plan["hud"] = {"date": self.video.get("hud_date", "").split("·")[0].strip()}
            plan["hookBig"], plan["hookSub"] = _hook_big(spec), spec.get("hook_sub", "")
        plan.update(self._style_pack())
        return {"plan": plan}

    THEMES = ("navy", "carbon", "crimson", "violet", "steel", "terminal", "sunset")  # 15 Eki: zümrüt kullanıcı isteğiyle çıkarıldı
    CAPTION_STYLES = ("yellow", "yellow", "yellow", "hormozi", "box", "minimal", "pill", "karaoke")  # 15 Eki: kullanıcı sarı stili en çok beğendi -> ağırlıklı

    def _style_pack(self) -> dict:
        """15 Eki: video başına tema paketi + altyazı stili + geçiş tohumu (uzun video ve Shorts aynı paketi paylaşır).
        Son 3 günde kullanılmayanlar seçilir; geçmiş output/_brain/style_history.json. config daily.style_pack.enabled=false -> eski görünüm."""
        import random
        if not self.cfg.get("style_pack", {}).get("enabled", True):
            return {}
        f = ROOT / "output" / "_brain" / "style_history.json"
        try:
            hist = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except Exception:  # noqa: BLE001
            hist = {}
        if self.job_id in hist:
            return hist[self.job_id]
        rnd = random.Random(self.job_id)
        recent = [v for jid, v in sorted(hist.items())][-3:]

        def pick(options, key):
            used = {r.get(key) for r in (recent[-1:] if key == "captionStyle" else recent)}
            pool = [o for o in options if o not in used] or list(options)
            return rnd.choice(pool)
        pack = {"theme": pick(self.THEMES, "theme"), "captionStyle": pick(self.CAPTION_STYLES, "captionStyle"), "transSeed": rnd.randint(1, 12)}
        hist[self.job_id] = pack
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        self.log(f"görünüm paketi: tema={pack['theme']}, altyazı={pack['captionStyle']}, geçiş tohumu={pack['transSeed']}")
        return pack

    def _ticker(self, syms: list[str]) -> list[dict]:
        names = {"XAUUSD": "ALTIN", "XAGUSD": "GÜMÜŞ", "BRENT": "BRENT", "WTI": "WTI", "USDTRY": "USD/TRY", "EURTRY": "EUR/TRY",
                 "GAUTRY": "GRAM ALTIN", "BTCUSD": "BITCOIN", "ETHUSD": "ETHEREUM", "XU100": "BIST 100", "DXY": "DXY", "US10Y": "ABD 10Y",
                 "TR10Y": "TR 10Y", "SPX": "S&P 500", "NDX": "NASDAQ 100", "VIX": "VIX",
                 "GC=F": "ALTIN", "SI=F": "GÜMÜŞ", "BTC-USD": "BITCOIN", "ETH-USD": "ETHEREUM", "BZ=F": "BRENT", "CL=F": "WTI", "^TNX": "ABD 10Y",
                 "DX-Y.NYB": "DXY", "XU100.IS": "BIST 100", "USDTRY=X": "USD/TRY", "EURTRY=X": "EUR/TRY", "^GSPC": "S&P 500", "^IXIC": "NASDAQ"}
        out = []
        for s in syms:
            v = self.snap.get(s)
            if not v or "last" not in v:
                continue
            last = v["last"]
            txt = (f"%{last:.2f}" if s in ("^TNX", "US10Y", "US02Y", "TR10Y") else f"{last:,.2f}" if last < 1000 else f"{last:,.0f}").replace(",", "X").replace(".", ",").replace("X", ".")
            if self.lang == "en":  # İngilizce kurgu: 4,219.50 / 4.62% biçimi + İngilizce adlar
                txt = f"{last:.2f}%" if s in ("^TNX", "US10Y", "US02Y", "TR10Y") else f"{last:,.2f}" if last < 1000 else f"{last:,.0f}"
                names.update({"XAUUSD": "GOLD", "XAGUSD": "SILVER", "GC=F": "GOLD", "SI=F": "SILVER", "US10Y": "US 10Y", "^TNX": "US 10Y"})
            if s in ("XAUUSD", "XAGUSD", "BRENT", "WTI", "BTCUSD", "ETHUSD", "GC=F", "SI=F", "BTC-USD", "ETH-USD", "BZ=F", "CL=F"):
                txt = "$" + txt
            elif s in ("GAUTRY", "USDTRY", "EURTRY"):
                txt = txt + " ₺"
            out.append({"n": names.get(s, s), "v": txt, "ch": v.get("chg_1d_pct", v.get("chg_5d_pct"))})  # 8 Eki: etiket "SON KAPANIŞ" -> günlük değişim (5g, seste söylenen "bugün" ile çelişiyordu)
        return out

    LAYOUTS = ("classic", "hero", "split", "banner", "marker", "center", "stack", "poster", "tilt", "hazard", "duo")

    def _vary_thumb(self, k: str, spec: dict):
        """15 Eki: kapaklar hep aynı taslak olmasın — foto kapaklara son günlerde kullanılmamış yerleşim + yazı rengi ata.
        Claude thumb.json'da `layout`/`accent2` verdiyse ona dokunmaz. Geçmiş: output/_brain/thumb_layouts.json."""
        import random
        if spec.get("style") != "object" or "layout" in spec:
            return
        f = ROOT / "output" / "_brain" / "thumb_layouts.json"
        try:
            hist = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except Exception:  # noqa: BLE001
            hist = {}
        today = hist.get(self.job_id, {})
        recent = [v for jid, v in sorted(hist.items()) if jid != self.job_id][-3:]
        used_recent = {x for d in recent for x in d.get("layouts", {}).values()}
        used_now = set(today.get("layouts", {}).values())
        pool = [x for x in self.LAYOUTS if x not in used_recent and x not in used_now] or [x for x in self.LAYOUTS if x not in used_now] or list(self.LAYOUTS)
        rnd = random.Random(f"{self.job_id}-{k}")
        lay = rnd.choice(pool)
        acc = rnd.choice(["gold", "white", "gold", "blue"])
        spec["layout"], spec["accent2"] = lay, acc
        today.setdefault("layouts", {})[k] = lay
        hist[self.job_id] = today
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        self.log(f"kapak {k}: yerleşim={lay}, yazı rengi={acc}")

    def plans(self):
        if self._skip("plans"):
            return
        if not self.shorts_only:
            tl = json.loads((self.raw / "timeline_long.json").read_text(encoding="utf-8"))
            self._music(tl["total"] / 30 + 1, self.pub / "music.wav")
            p = self._plan(tl, self.video, "h", f"auto/{self.job_id}/voice.wav", f"auto/{self.job_id}/music.wav")
            (self.raw / "props_long.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        for r_i, r in enumerate(self.reels):
            rtl = json.loads((self.raw / f"timeline_reel{r_i + 1}.json").read_text(encoding="utf-8"))
            self._music(rtl["total"] / 30 + 1, self.pub / f"music_reel{r_i + 1}.wav")
            rp = self._plan(rtl, r, "v", f"auto/{self.job_id}/reel{r_i + 1}.wav", f"auto/{self.job_id}/music_reel{r_i + 1}.wav")
            (self.raw / f"props_reel{r_i + 1}.json").write_text(json.dumps(rp, ensure_ascii=False), encoding="utf-8")
        hooks = {}
        if not self.shorts_only:
            cut = tl["segments"][1]["s"] - 1 if len(tl["segments"]) > 1 else tl["segments"][0]["e"]
            cut = min(cut, tl["segments"][0]["e"] + 9)  # ana videoda 1. segmentin bitişi + kısa duraklama
        for L, hv in self._hooks():
            hf = self.raw / f"timeline_hook{L}.json"
            if not hf.exists():
                continue
            htl = json.loads(hf.read_text(encoding="utf-8"))
            Lv = htl["segments"][0]["e"] + 9
            htl["total"], htl["outroStart"] = Lv, Lv + 300
            hp = self._plan(htl, {"scenes": hv["scenes"], "hits": hv.get("hits", [])}, "h", f"auto/{self.job_id}/hook{L}.wav",
                            f"auto/{self.job_id}/music.wav")
            hp["plan"]["audio"].update(musicFrom=cut - Lv, noFadeOut=True)
            hp["plan"]["progressTotal"] = tl["total"] - cut + Lv
            # açılışta yalnız ilk bölüm etkin görünsün (diğer bölüm cue'ları tek segmentlik planda 0'a sıkışıp sonuncuyu yakıyordu)
            hp["plan"]["hud"]["chapters"] = hp["plan"]["hud"].get("chapters", [])[:1]
            (self.raw / f"props_hook{L}.json").write_text(json.dumps(hp, ensure_ascii=False), encoding="utf-8")
            hooks[L] = {"cut": cut, "len": Lv, "label": hv.get("label", L)}
        (self.raw / "hooks.json").write_text(json.dumps(hooks, ensure_ascii=False), encoding="utf-8")
        for k, spec in self.thumb.items():
            spec = {**spec, "variant": spec.get("variant", k)}
            self._vary_thumb(k, spec)
            if spec.get("style"):
                # Kapak 2.0: grafik tarzına seri verisi, yüz tarzına gerçek fotoğraf
                if spec["style"] == "chart" and spec.get("symbol") in self.series:
                    spec["data"] = self.series[spec["symbol"]]["c"][-60:]
                # çekim modunda yüz kapağı videonun KENDİ karesinden (kıyafet/mekân tutarlı olsun)
                if spec["style"] == "face" and self.footage and "image" not in spec:
                    face = self._footage_face()
                    if face:
                        spec["image"] = face
                # 30 Eyl kullanıcı kararı: taban çekimden çıkarılan yüz fotoğrafı (host_real) SİLİNDİ, bir daha kullanılmaz.
                # Gerçek çekim karesi yoksa yüz kapağı yüzsüz 'object' tarzına döner.
                if spec["style"] == "face" and "image" not in spec:
                    spec["style"] = "object"
                    spec.setdefault("object", "gold")
            else:
                spec["image"] = "auto/host_cut.png"
            if self.footage and self.footage.get("brand"):
                spec["noBrand"] = True
            (self.raw / f"props_thumb_{k}.json").write_text(json.dumps({"spec": spec}, ensure_ascii=False), encoding="utf-8")
        self._done("plans")

    # ---------------------------------------------------------------- 3b) görsel denetçi
    def qa(self):
        """Render'dan önce her sahnenin karesine Claude bakar, scenes düzeyinde düzeltir (pipeline/daily/qa.py)."""
        if not self.cfg.get("qa", {}).get("enabled", True) or self._skip("qa"):
            return
        from pipeline.daily import qa as qamod
        from tools.daily_run import claude_resilient
        t0 = time.time()
        res = qamod.run(self.job, self.raw, len(self.reels), log=self.log, strict=not self.footage,
                        claude_fn=lambda prompt: claude_resilient(prompt, self.job, self.log))
        if res["changed"]:
            rd = lambda n: json.loads((self.job / n).read_text(encoding="utf-8"))  # noqa: E731
            self.video, self.reels = rd("video.json"), rd("reels.json")
            self.status.pop("plans", None)
            self.plans()
        self._done("qa", issues=len(res.get("issues", [])), changed=res["changed"], sec=round(time.time() - t0))

    def _footage_face(self) -> str | None:
        """Çekimden kapak için yüz kesiti: birkaç aday kare, en keskin olan (Laplace varyansı), rembg ile arka plansız PNG."""
        out = self.pub / "face_cut.png"
        if out.exists():
            return f"auto/{self.job_id}/face_cut.png"
        try:
            import numpy as np
            from PIL import Image, ImageFilter
            from rembg import remove
            cam = REMOTION / "public" / self.footage["src"]
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(cam)],
                                       capture_output=True, text=True, check=True).stdout.strip())
            best, score = None, -1.0
            for q in (0.18, 0.32, 0.47, 0.61, 0.76):
                fp = self.raw / f"_face_{int(q * 100)}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{dur * q:.2f}", "-i", str(cam), "-frames:v", "1", str(fp)], check=True)
                im = Image.open(fp).convert("RGB")
                s = float(np.asarray(im.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32).var())  # keskinlik
                if s > score:
                    best, score = im, s
            if best is None:
                return None
            w, h = best.size
            crop = best.crop((int(w * 0.22), 0, int(w * 0.78), h))  # konuşmacı ortada
            img = remove(crop)
            img = img.crop(img.getbbox())
            img.save(out)
            return f"auto/{self.job_id}/face_cut.png"
        except Exception as e:  # noqa: BLE001
            self.log(f"  kapak yüzü çıkarılamadı: {e}")
            return None

    def _music(self, seconds: float, dst: Path):
        maker = ROOT / "scripts" / "fed_motion" / "make_music.py"
        if not maker.exists():  # public kopyada müzik üreteci yok -> sessiz yatak, render müziksiz sürer
            self.log(f"  müzik üreteci yok ({maker.relative_to(ROOT)}), sessiz müzik yatağı yazılıyor")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{seconds:.1f}", str(dst)], check=True)
            return
        seed = int(datetime.now().strftime("%Y%m%d")) + (zlib.crc32(dst.name.encode()) % 97)
        mood = str(self.video.get("mood", "neutral")) if hasattr(self, "video") else "neutral"
        subprocess.run([sys.executable, str(maker), f"{seconds:.1f}", str(dst), str(seed), mood], check=True,
                       cwd=str(ROOT), stdout=subprocess.DEVNULL)

    def thumb_photos(self):
        """3 Eki: object kapaklara foto-gerçekçi RealVisXL arka plan (tools/thumb_photo.py, ayrı süreç -> VRAM boşalır).
        Hata olursa eski 3D/sembol kapak kalır."""
        if self._skip("thumb_photos") or not self.cfg.get("thumb_photo", {}).get("enabled", True):
            return
        keys = [k for k, s in self.thumb.items() if s.get("style") in ("object", "face", "photo")]
        if not keys:
            return
        try:
            subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools" / "thumb_photo.py"), str(self.job), "--keys", ",".join(keys)],
                           check=True, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1200)
            bgs = json.loads((self.raw / "thumb_bg.json").read_text(encoding="utf-8"))
            for k, bg in bgs.items():
                p = self.raw / f"props_thumb_{k}.json"
                props = json.loads(p.read_text(encoding="utf-8"))
                props["spec"].update(bg=bg, focusX=self.thumb[k].get("focusX", 0.62), focusY=self.thumb[k].get("focusY", 0.55))
                p.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
            self.log(f"foto-gerçekçi kapak arka planı: {', '.join(bgs)}")
        except Exception as e:  # noqa: BLE001
            self.log(f"!! foto kapak üretilemedi, 3D kapakla devam: {str(e)[:150]}")
        self._done("thumb_photos")

    # ---------------------------------------------------------------- 4) render
    def render(self):
        r = self.cfg.get("render", {})
        conc, crf = str(r.get("concurrency", 8)), str(r.get("crf", 17))
        self.thumb_photos()
        for k in self.thumb:
            if not self._skip(f"thumb_{k}"):
                self._npx(["still", "src/auto/index.ts", "AutoThumb", str(self.job / f"thumb_{k}.png"), f"--props={self.raw / f'props_thumb_{k}.json'}", "--gl=angle", "--scale=1.5", "--overwrite"], f"thumb_{k}.log")  # 8 Eki: 1920x1080 (API kapak sınırı 2->50MB)
                self._done(f"thumb_{k}")
        for r_i in range(len(self.reels)):
            key = f"reel{r_i + 1}"
            if not self._skip(f"render_{key}"):
                t0 = time.time()
                self._npx(["render", "src/auto/index.ts", "AutoReel", str(self.job / f"reel_{r_i + 1}.mp4"), f"--props={self.raw / f'props_{key}.json'}",
                           "--codec", "h264", "--crf", crf, "--concurrency", conc, "--audio-bitrate", "320k", "--gl=angle", "--overwrite"], f"render_{key}.log")
                self._done(f"render_{key}", sec=round(time.time() - t0))
                self.log(f"{key} render: {time.time() - t0:.0f}s")
        if not self._skip("render_long") and not self.shorts_only:
            t0 = time.time()
            self._npx(["render", "src/auto/index.ts", "AutoShowreel", str(self.job / "video.mp4"), f"--props={self.raw / 'props_long.json'}",
                       "--codec", "h264", "--crf", crf, "--concurrency", conc, "--audio-bitrate", "320k", "--gl=angle", "--overwrite"], "render_long.log")
            self._done("render_long", sec=round(time.time() - t0))
            self.log(f"uzun video render: {time.time() - t0:.0f}s")
        self.render_hooks(conc, crf)

    def _hooks(self):
        """Açılış A/B varyantları (YouTube video testi): ana video = A, bunlar B ve C."""
        return [(chr(66 + i), hv) for i, hv in enumerate((self.video.get("hook_variants") or [])[:2]) if len(hv.get("segments", [])) == 1]

    def render_hooks(self, conc: str, crf: str):
        hf = self.raw / "hooks.json"
        hooks = json.loads(hf.read_text(encoding="utf-8")) if hf.exists() else {}
        for L, h in hooks.items():
            if self._skip(f"render_hook{L}"):
                continue
            t0 = time.time()
            intro = self.raw / f"hook{L}_intro.mp4"
            self._npx(["render", "src/auto/index.ts", "AutoShowreel", str(intro), f"--props={self.raw / f'props_hook{L}.json'}",
                       "--codec", "h264", "--crf", crf, "--concurrency", conc, "--audio-bitrate", "320k", "--gl=angle", "--overwrite"], f"render_hook{L}.log")
            Lv, cut = h["len"], h["cut"]
            fc = (f"[0:v]trim=end_frame={Lv},setpts=PTS-STARTPTS[v0];[0:a]atrim=end={Lv / 30:.4f},asetpts=PTS-STARTPTS[a0];"
                  f"[1:v]trim=start_frame={cut},setpts=PTS-STARTPTS[v1];[1:a]atrim=start={cut / 30:.4f},asetpts=PTS-STARTPTS[a1];"
                  f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(intro), "-i", str(self.job / "video.mp4"), "-filter_complex", fc,
                            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", crf, "-preset", "fast", "-c:a", "aac", "-b:a", "320k",
                            str(self.job / f"video_{L}.mp4")], check=True)
            self._done(f"render_hook{L}", sec=round(time.time() - t0))
            self.log(f"açılış {L} ({h['label']}): video_{L}.mp4 ({time.time() - t0:.0f}s)")

    # ---------------------------------------------------------------- 5) kontrol
    def check(self) -> float:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(self.job / "video.mp4")],
                                   capture_output=True, text=True, check=True).stdout.strip())
        if dur < (20 if self.footage else self.cfg.get("min_seconds", 480)):
            raise RuntimeError(f"video {dur:.0f} sn — {self.cfg.get('min_seconds', 480)} sn altında, YÜKLENMEDİ")
        for r_i in range(len(self.reels)):
            rd = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(self.job / f"reel_{r_i + 1}.mp4")],
                                      capture_output=True, text=True, check=True).stdout.strip())
            if rd > 60:
                self.log(f"UYARI: reel{r_i + 1} {rd:.0f} sn (>60, Shorts sayılmayabilir)")
        self.contact_sheets()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.job / "thumb_A.png"), "-q:v", "2", str(self.job / "thumbnail.jpg")], check=True)
        for k in ("B", "C"):
            if (self.job / f"thumb_{k}.png").exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.job / f"thumb_{k}.png"), "-q:v", "2", str(self.job / f"thumb_{k}.jpg")], check=True)
        return dur

    def contact_sheets(self):
        """18 Eki (skill: 'render, contact sheet temiz olmadan bitmiş sayılmaz'): render SONRASI her mp4'ten 60 karelik iletişim
        sayfası (_raw/qa/contact_*.jpg) + kare sayısı plan süresiyle eşleşiyor mu. Engellemez; sorunları loglar, gece editörü/denetçi okur."""
        qa = self.raw / "qa"
        qa.mkdir(parents=True, exist_ok=True)
        report = {}
        for name, props in [("video", "props_long.json")] + [(f"reel_{i + 1}", f"props_reel{i + 1}.json") for i in range(len(self.reels))]:
            mp4 = self.job / f"{name}.mp4"
            if not mp4.exists():
                continue
            try:
                probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                                        "stream=nb_read_packets,width", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True, timeout=300).stdout.strip()
                w, n = (int(x) for x in probe.split(",")[:2])
                pf = self.raw / props
                want = json.loads(pf.read_text(encoding="utf-8"))["plan"]["total"] if pf.exists() else None
                dur = n / 30
                cols, rows = (10, 6) if w > 1500 else (12, 5)
                fps = max(cols * rows / max(dur, 1), 0.05)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf",
                                f"fps={fps:.4f},scale={240 if w > 1500 else 140}:-1,tile={cols}x{rows}:padding=4:color=black",
                                "-frames:v", "1", "-q:v", "3", str(qa / f"contact_{name}.jpg")], check=True, timeout=600)
                ok = want is None or abs(n - int(want)) <= 2
                report[name] = {"frames": n, "plan_frames": want, "frames_ok": ok, "sheet": str(qa / f"contact_{name}.jpg")}
                if not ok:
                    self.log(f"UYARI: {name}.mp4 {n} kare, plan {want} — render eksik/fazla")
            except Exception as e:  # noqa: BLE001
                report[name] = {"error": str(e)[:200]}
                self.log(f"UYARI: contact sheet {name}: {str(e)[:120]}")
        (qa / "contact.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        return report

    # ---------------------------------------------------------------- 6) metadata + yükleme
    def metadata(self, seconds: float):
        from pipeline import policy
        tl = json.loads((self.raw / "timeline_long.json").read_text(encoding="utf-8"))
        marks = [(0, "Giriş")]
        for c in self.video.get("chapters_hud", [])[1:]:
            marks.append((tl["segments"][c["seg"]]["s"] / 30, c["name"]))
        for sc in self.video["scenes"]:
            if sc.get("t") == "Chapter":
                marks.append((tl["chapterFrom"].get(str(sc["before"]), tl["segments"][sc["before"]]["s"]) / 30, sc.get("p", {}).get("title", "").title()))
        # HUD bölümü ile Chapter kartı ~2 sn arayla aynı yere düşüyor; YouTube <10 sn aralıklı bölümlerde TÜM bölümleri yok sayar
        # -> 10 sn'den yakın işaretleri birleştir (ilk zaman, Chapter kartının adı)
        merged: list[list] = []
        for t, n in sorted({round(t): n for t, n in marks}.items()):
            if merged and t - merged[-1][0] < 10:
                merged[-1][1] = n or merged[-1][1]
            else:
                merged.append([t, n])
        marks = merged
        chapters = "\n".join(f"{int(t // 60):02d}:{int(t % 60):02d} {n}" for t, n in marks if n)
        desc = f"{self.video['description'].strip()}\n\n⏱️ Bölümler\n{chapters}"
        full = policy.build_full_description(desc, sources=self.brief.get("sources", []), categories=["finance"], language="tr")
        if self.lang == "en":  # 1 Eki: başka kanal kurgusu -> Türkçe politika/AI şablonu eklenmez
            full = f"{self.video['description'].strip()}\n\n⏱️ Chapters\n{chapters}"
        meta = {"title": self.video["title"][:100], "description": full[:4900], "tags": self.video.get("tags", [])[:25],
                "pinned_comment": self.video.get("pinned_comment", ""), "language": self.lang, "seconds": round(seconds),
                "title_variants": [t[:100] for t in (self.video.get("titles") or [])],
                "hook_variants": {L: hv.get("label", L) for L, hv in self._hooks()}}
        (self.job / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    def upload(self):
        if self._skip("upload"):
            return self.status["upload"]
        from tools import make_thumbnail
        from pipeline.stages import s09_upload
        make_thumbnail.make = lambda job_id, top, bottom: self.job / "thumbnail.jpg"
        ap = self.cfg_yt.get("auto_publish") or {}
        when = None
        if ap.get("enabled"):
            when = s09_upload.publish_time(os.environ.get("SP_PUBLISH_LONG") or ap.get("long", "15:00"))
        res = s09_upload.run(self.job_id, publish_at=when)
        if res.get("skipped"):
            raise RuntimeError(f"YouTube yüklemesi atlandı: {res}")
        self._done("upload", video_id=res["video_id"], url=res["url"], privacy=res["privacy_status"], thumbnail=res["thumbnail_set"],
                   publish_at=res.get("publish_at"))
        self.log(f"YouTube: {res['url']}" + (f" · otomatik yayın {when:%d.%m %H:%M}" if when else " (private)"))
        if ap.get("enabled") and ap.get("shorts", True):
            self.upload_shorts(res, ap)
        return self.status["upload"]

    def upload_shorts(self, long_res: dict, ap: dict):
        """2 Eki: Shorts'lar da otomatik; açıklamada uzun videoya köprü (Shorts->uzun geçişi zayıftı)."""
        from pipeline.stages import s09_upload
        times = ap.get("reels", ["19:30", "+1d 10:00"])
        for i, r in enumerate(self.reels):
            key = f"short{i + 1}"
            if self._skip(key) or not (self.job / f"reel_{i + 1}.mp4").exists():
                continue
            tags = [h.lstrip("#") for h in r.get("hashtags", [])]
            desc = "\n\n".join(x for x in [(r.get("caption") or "").strip(), f"▶ Uzun analiz: {long_res['url']}" if long_res.get("url") else "",
                                             " ".join(r.get("hashtags", [])), "Yatırım tavsiyesi değildir."] if x)
            try:
                when = s09_upload.publish_time(times[min(i, len(times) - 1)])
                out = s09_upload.upload_short(self.job_id, i + 1, r.get("title") or self.video["title"], desc, tags, when, long_url=long_res.get("url"))
                self._done(key, video_id=out["video_id"], url=out["url"], publish_at=out["publish_at"])
            except Exception as e:  # noqa: BLE001
                self.log(f"Shorts {i + 1} yüklenemedi (uzun video etkilenmez): {str(e)[:160]}")

    def drive(self, meta: dict, up: dict):
        if self._skip("drive"):
            return
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from pipeline.stages import s10_drive_upload as s10
        txt = self.texts(meta, up)
        try:  # 17 Eki: token yoksa tarayıcı yetkisinde sonsuza dek takılıyordu (12 saat) -> atla, geçmişi yine yaz
            creds = s10._get_credentials(interactive=False)
        except Exception as e:  # noqa: BLE001
            self.log(f"Drive atlandı: {str(e)[:140]}")
            return
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        parent = load_config().get("drive", {}).get("parent_folder_id") or None
        folder = s10._get_or_create_folder(drive, f"{datetime.now():%Y-%m-%d} — Finans Kanalı günlük", parent)
        files = [txt] + [self.job / f"reel_{i + 1}.mp4" for i in range(len(self.reels))] + [self.job / f"thumb_{k}.jpg" for k in ("B", "C")]
        ids = {}
        for f in files:
            if not f.exists():
                continue
            mt = "text/plain" if f.suffix == ".txt" else "image/jpeg" if f.suffix == ".jpg" else "video/mp4"
            media = MediaFileUpload(str(f), mimetype=mt, resumable=f.suffix == ".mp4")
            ids[f.name] = drive.files().create(body={"name": f.name, "parents": [folder]}, media_body=media, fields="id").execute()["id"]
        self._done("drive", folder_id=folder, files=ids)
        self.log(f"Drive: {len(ids)} dosya -> https://drive.google.com/drive/folders/{folder}")

    def texts(self, meta: dict, up: dict) -> Path:
        """Elle yükleme için tüm metinler tek dosyada (yüklemesiz koşuda da yazılır): başlık varyantları, açıklama, etiketler,
        sabit yorum, topluluk gönderisi, A/B açılışlar, Reels metinleri, Shorts→uzun video bağlama adımı."""
        lines = [f"FİNANS KANALI · {datetime.now():%d.%m.%Y} · günlük paket", "",
                 f"UZUN VİDEO: {up.get('url') or 'video.mp4 (elle yüklenecek)'}", f"Başlık: {meta['title']}", "",
                 "AÇIKLAMA:", meta.get("description", ""), "", "ETİKETLER:", ", ".join(meta.get("tags", [])), "",
                 "Sabitlenecek yorum (yayına aldıktan sonra yapıştır + sabitle):", meta.get("pinned_comment", ""), ""]
        cp = self.video.get("community_post") or {}
        if cp.get("text"):
            lines += ["TOPLULUK GÖNDERİSİ (ertesi gün paylaş — geri dönen izleyici):", cp["text"]] + [f"  ◯ {o}" for o in cp.get("poll", [])][:4] + [""]
        if meta.get("title_variants"):
            lines += ["BAŞLIK TESTİ (Studio > Test & Compare, 3 başlık):"] + [f"  {i + 1}) {t}" for i, t in enumerate(meta["title_variants"])] + [""]
        if meta.get("hook_variants"):
            lines += ["VİDEO A/B TESTİ (3 açılış): A = video.mp4 (ana)"] + [f"  {L} = video_{L}.mp4 — {lab}" for L, lab in meta["hook_variants"].items()] + [""]
        for r_i, r in enumerate(self.reels):
            lines += [f"─── REELS {r_i + 1}  (reel_{r_i + 1}.mp4) ───", f"Başlık: {r['title']}", "Açıklama:", r["caption"],
                      " ".join(r.get("hashtags", [])), ""]
        lines += ["🔗 SHORTS → UZUN VİDEO (en çok izlenen içerik Shorts; izleyiciyi kanala taşı): her Reels'i yükledikten sonra",
                  "   Studio > İçerik > Shorts > videoyu aç > 'İlgili video' alanına bugünkü UZUN videoyu seç. Shorts'un altında tıklanabilir bağlantı çıkar.",
                  "⚠️ Telefondan yüklerken: 'Değiştirilmiş veya yapay içerik' (altered/synthetic) kutusunu İŞARETLE — ses yapay zekâ klonu.",
                  "Kapak: thumbnail.jpg (A) + thumb_B.jpg + thumb_C.jpg -> Studio > Test & Compare (3 kapak).",
                  "Oynatma listesi: 'Finans Kanalı · Günlük Piyasa Analizi' (elle yüklemede listeye ekle)."]
        txt = self.job / "YUKLEME_METINLERI.txt"
        txt.write_text("\n".join(lines), encoding="utf-8")
        return txt

    def history(self, meta: dict, up: dict, seconds: float):
        if self._skip("history"):
            return
        h = ROOT / "output" / "_brain" / "daily_history.jsonl"
        h.parent.mkdir(parents=True, exist_ok=True)
        rec = {"date": datetime.now().strftime("%Y-%m-%d"), "job": self.job_id, "topic": self.brief.get("topic"), "title": meta["title"],
               "experiment": self.video.get("experiment"), "video_id": up.get("video_id"), "seconds": round(seconds),
               "reels": [r["title"] for r in self.reels], "voice": self.status.get("tts", {}),
               # CTR öğrenmesi için: hangi kapak tarzı/yazısı, hangi başlık varyantları
               "thumbs": {k: {"style": v.get("style", v.get("variant")), "text": v.get("text") or " ".join(v.get("headline", []))} for k, v in self.thumb.items()},
               "titles": self.video.get("titles", [])}
        with open(h, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._done("history")

    # ---------------------------------------------------------------- 9 Eki: yalnız-Shorts günü
    @staticmethod
    def latest_long() -> dict:
        """En son yüklenen günlük uzun video (Shorts köprüsü için)."""
        best = {}
        for f in (ROOT / "output").glob("daily-*/upload_result.json"):
            try:
                r = json.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if r.get("url") and r.get("uploaded_at", "") > best.get("uploaded_at", ""):
                best = r
        return best

    def run_shorts(self, upload: bool) -> dict:
        self.render()  # thumb={} ve shorts_only -> yalnız reel render
        self.contact_sheets()
        for r_i in range(len(self.reels)):
            rd = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(self.job / f"reel_{r_i + 1}.mp4")],
                                      capture_output=True, text=True, check=True).stdout.strip())
            if rd > 60:
                self.log(f"UYARI: reel{r_i + 1} {rd:.0f} sn (>60, Shorts sayılmayabilir)")
        long = self.latest_long()
        ap = self.cfg_yt.get("auto_publish") or {}
        if upload and ap.get("enabled") and ap.get("shorts", True):
            from pipeline.daily import packaging_audit  # 15 Eki: Shorts başlık denetimi (yüklemeden hemen önce)
            packaging_audit.audit(self, reels_only=True)
            if not long:
                self.log("!! köprü kurulacak uzun video bulunamadı — Shorts açıklamasında uzun video linki olmayacak")
            self.upload_shorts({"url": long.get("url", "")} if long else {"url": ""}, ap)
        meta = {"title": self.video["title"], "description": "", "tags": [], "pinned_comment": ""}
        self.texts(meta, {"url": long.get("url")} if long else {})
        if upload or self.job_id.startswith("daily-"):
            self.history(meta, {}, 0)
        shorts = {k: v.get("url") for k, v in self.status.items() if k.startswith("short")}
        self.log(f"yalnız-Shorts günü: {len(shorts)} Shorts yüklendi" + (f" · köprü: {long.get('url')}" if long else ""))
        return {"seconds": 0, "upload": {"url": ", ".join(u for u in shorts.values() if u) or "yüklenmedi"}, "title": self.video["title"], "shorts": shorts}

    # ---------------------------------------------------------------- hepsi
    def run(self, upload: bool = True) -> dict:
        self.tts()
        self.timelines()
        self.twin_video()
        self.plans()
        if self.shorts_only:
            return self.run_shorts(upload)
        try:
            self.qa()
        except Exception as e:  # noqa: BLE001
            # 30 Eyl: Claude kotası denetçide doldu ve TÜM iş durdu -> denetçi isteğe bağlı: atla, render sürsün
            self.log(f"görsel denetçi atlandı ({str(e)[:140]}) — render denetimsiz sürüyor")
        self.render()
        seconds = self.check()
        meta = self.metadata(seconds)
        if upload:  # 15 Eki: SON adım — Claude başlık/kapak denetimi (zayıfsa düzeltir), sonra yükleme
            from pipeline.daily import packaging_audit
            packaging_audit.audit(self)
            meta = json.loads((self.job / "metadata.json").read_text(encoding="utf-8"))
        up = self.upload() if upload else {}
        self.texts(meta, up)
        if upload:
            self.drive(meta, up)
        # geçmiş (konu tekrarı önleme + CTR öğrenmesi): elle yüklenen günlük videolar da kaydedilir; test işleri kaydedilmez
        if upload or self.job_id.startswith("daily-"):
            self.history(meta, up, seconds)
        return {"seconds": seconds, "upload": up, "title": meta["title"]}
