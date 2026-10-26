"""Görsel denetçi (render'dan ÖNCE): her sahneden kare çeker, iletişim sayfalarına (contact sheet) dizer, kural tabanlı
tempo kontrolleri yapar ve Claude headless'e (prompts/qa_review.md) bakıp DÜZELTMESİNİ ister.

Claude yalnız video.json / reels.json içindeki `scenes` ve `hits` alanlarını düzenleyebilir (metin/segment YOK).
Düzeltme sonrası validate() hata verirse değişiklik geri alınır. Sonuç: _raw/qa/qa.json + günlük log.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REMOTION = ROOT / "remotion"
LEAD = 8
FPS = 30


def _norm(s: str) -> str:
    return re.sub(r"[^\w]", "", s.replace("İ", "i").replace("I", "ı").lower())


def cue_abs(plan: dict, c, lead: int = 4) -> int:
    """remotion/src/core/timing.tsx cueAbs'in birebir Python karşılığı."""
    if c is None or c == "":
        return 0
    m = re.match(r"^(\d+)(?::(.+?))?([+-]\d+)?$", str(c).strip())
    if not m:
        return 0
    off = int(m.group(3)) if m.group(3) else 0
    key = m.group(2)
    segs = plan["segments"]
    seg = segs[max(0, min(int(m.group(1)), len(segs) - 1))]
    if not key:
        return seg["s"] - lead + off
    if key == "end":
        return seg["e"] + off
    if re.fullmatch(r"\d{1,2}", key):
        w = seg["words"][min(int(key), len(seg["words"]) - 1)] if seg["words"] else None
        return (w["s"] if w else seg["s"]) - 3 + off
    word, _, nth = key.partition("#")
    want, count = _norm(word), 0
    exact = any(_norm(w["w"]) == want for w in seg["words"])  # timing.tsx ile aynı: önce tam eşleşme
    for w in seg["words"]:
        if (_norm(w["w"]) == want) if exact else _norm(w["w"]).startswith(want):
            count += 1
            if count >= (int(nth) if nth.isdigit() else 1):
                return w["s"] - 3 + off
    return seg["s"] - lead + off


def timed_scenes(plan: dict) -> list[dict]:
    sc = plan["scenes"]
    starts = [s["from"] if s.get("from") is not None else (0 if i == 0 and not s.get("cue") else cue_abs(plan, s.get("cue", "0"), LEAD))
              for i, s in enumerate(sc)]
    out = []
    for i, s in enumerate(sc):
        st = max(0, starts[i])
        nxt = starts[i + 1] if i < len(sc) - 1 else plan["total"]
        out.append({**s, "i": i, "start": st, "len": max(nxt - st, 12)})
    return out


def spoken(plan: dict, a: int, b: int) -> str:
    return " ".join(w["w"] for seg in plan["segments"] for w in seg["words"] if a <= w["s"] < b)


def rule_checks(ts: list[dict], plan: dict, where: str) -> list[str]:
    notes = []
    for k, s in enumerate(ts):
        sec = s["len"] / FPS
        if sec < 1.8 and s.get("t") != "Chapter":
            notes.append(f"{where} sahne {s['i']} ({s['t']}): yalnız {sec:.1f} sn ekranda — okunamaz, cue'yu kaydır ya da birleştir")
        if sec > 22 and s.get("t") not in ("Outro",):
            notes.append(f"{where} sahne {s['i']} ({s['t']}): {sec:.0f} sn tek sahne — tempo düşer, araya sahne ekle")
        if k and ts[k - 1]["t"] == s["t"] and s["t"] not in ("Chart",):
            notes.append(f"{where} sahne {s['i']}: '{s['t']}' art arda")
        if s["start"] >= plan.get("outroStart", plan["total"]) and s.get("t") != "Outro":
            notes.append(f"{where} sahne {s['i']} ({s['t']}): outro'dan sonra başlıyor")
        if k and s["start"] < ts[k - 1]["start"]:
            notes.append(f"{where} sahne {s['i']} ({s['t']}): önceki sahneden ÖNCE başlıyor (cue sırası bozuk)")
    hits = plan.get("hits") or []
    if len(hits) > 10:
        notes.append(f"{where}: {len(hits)} ses efekti — fazla (en fazla 8); en zayıf vurguları çıkar")
    short = sum(1 for s in ts if s["len"] < 4 * FPS and s.get("t") != "Chapter")
    if len(ts) > 8 and short / len(ts) > 0.3:
        notes.append(f"{where}: sahnelerin %{100 * short // len(ts)}'i 4 sn'den kısa — tempo fazla hızlı/yorucu")
    return notes


def _sheet(shots: list[dict], out: Path, cols: int):
    from PIL import Image, ImageDraw, ImageFont
    ims = [Image.open(s["out"]).convert("RGB") for s in shots]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    try:
        font = ImageFont.truetype("arialbd.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for k, (im, s) in enumerate(zip(ims, shots)):
        x, y = (k % cols) * w, (k // cols) * h
        sheet.paste(im, (x, y))
        lab = s["label"]
        d.rectangle([x, y, x + 12 * len(lab) + 16, y + 32], fill=(255, 220, 0))
        d.text((x + 8, y + 4), lab, fill=(0, 0, 0), font=font)
        d.rectangle([x, y, x + w - 1, y + h - 1], outline=(255, 220, 0), width=2)
    sheet.save(out, quality=85)


def run(job: Path, raw: Path, reels: int, log=print, claude_fn=None, strict: bool = True) -> dict:
    job, raw = job.resolve(), raw.resolve()  # node remotion/ klasöründen çalışır -> mutlak yol şart
    qa = raw / "qa"
    if qa.exists():
        shutil.rmtree(qa)
    qa.mkdir(parents=True)
    targets = [("video", "AutoShowreel", raw / "props_long.json", "long")] + \
              [(f"reel{r + 1}", "AutoReel", raw / f"props_reel{r + 1}.json", f"reel{r + 1}") for r in range(reels)]
    jobs, notes, scene_index = [], [], {}
    for where, comp, props, tag in targets:
        plan = json.loads(props.read_text(encoding="utf-8"))["plan"]
        ts = timed_scenes(plan)
        notes += rule_checks(ts, plan, where)
        shots = []
        for s in ts:
            # animasyon oturduktan sonra: sahnenin ~%60'ı (en az 20 kare içeri, en az 12 kare önce çık)
            fr = s["start"] + int(min(max(s["len"] * 0.6, 20), s["len"] - 12))
            out = qa / f"{tag}_{s['i']:02d}.jpg"
            shots.append({"frame": fr, "out": str(out), "label": f"{where} #{s['i']} {s['t']} {fr / FPS:.0f}s"})
            scene_index.setdefault(where, []).append({"scene": s["i"], "t": s["t"], "layout": s.get("layout"), "at_s": round(s["start"] / FPS, 1),
                                                      "dur_s": round(s["len"] / FPS, 1), "shot_s": round(fr / FPS, 1),
                                                      "spoken": spoken(plan, s["start"], s["start"] + s["len"])[:400], "p": s.get("p", {})})
        jobs.append({"props": str(props), "comp": comp, "shots": shots, "where": where})
    jf = qa / "jobs.json"
    jf.write_text(json.dumps([{k: v for k, v in j.items() if k != "where"} for j in jobs], ensure_ascii=False), encoding="utf-8")
    npx = "node.exe" if sys.platform == "win32" else "node"
    with open(qa / "stills.log", "w", encoding="utf-8") as lf:
        from pipeline.daily.build import clean_render_tmp, render_env
        r = subprocess.run([npx, "scripts/qa_stills.mjs", str(jf)], cwd=str(REMOTION), stdout=lf, stderr=subprocess.STDOUT, timeout=3600, env=render_env())
    clean_render_tmp()
    if r.returncode != 0:
        raise RuntimeError(f"QA kareleri çekilemedi: {qa / 'stills.log'}")
    sheets = []
    for j in jobs:
        per, cols = (6, 2) if j["comp"] == "AutoShowreel" else (8, 4)
        for k in range(0, len(j["shots"]), per):
            sh = qa / f"sheet_{j['where']}_{k // per:02d}.jpg"
            _sheet(j["shots"][k:k + per], sh, cols)
            sheets.append(sh.name)
    (qa / "scenes.json").write_text(json.dumps(scene_index, ensure_ascii=False, indent=1), encoding="utf-8")
    (qa / "rule_notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"QA: {sum(len(j['shots']) for j in jobs)} kare, {len(sheets)} sayfa, {len(notes)} kural notu")

    if claude_fn is None:
        return {"shots": sum(len(j["shots"]) for j in jobs), "notes": notes, "changed": False}
    backups = {n: (job / n).read_text(encoding="utf-8") for n in ("video.json", "reels.json")}
    rel = lambda p: p.relative_to(ROOT).as_posix()  # noqa: E731
    prompt = ((ROOT / "prompts" / "qa_review.md").read_text(encoding="utf-8")
              .replace("{{JOB_DIR}}", rel(job)).replace("{{QA_DIR}}", rel(qa)).replace("{{SHEETS}}", "\n".join(f"- `{rel(qa)}/{s}`" for s in sheets)))
    claude_fn(prompt)
    changed = any((job / n).read_text(encoding="utf-8") != b for n, b in backups.items())
    if changed:
        # metin/segment değişmemeli; şema ve cue'lar geçerli olmalı — değilse geri al
        from pipeline.daily.validate import validate
        bad = []
        for n, b in backups.items():
            old, new = json.loads(b), json.loads((job / n).read_text(encoding="utf-8"))
            segs = lambda d: [s.get("segments") for s in d] if isinstance(d, list) else d.get("segments")  # noqa: E731
            if segs(old) != segs(new):
                bad.append(f"{n}: segmentler değişmiş")
        v = validate(job) if strict else {"ok": True}
        if bad or not v["ok"]:
            for n, b in backups.items():
                (job / n).write_text(b, encoding="utf-8")
            log(f"QA düzeltmesi GERİ ALINDI: {(bad + v.get('errors', []))[:3]}")
            changed = False
    res = json.loads((qa / "qa.json").read_text(encoding="utf-8")) if (qa / "qa.json").exists() else {}
    issues = res.get("issues", [])
    # kütüphane geliştirme turu için birikim: denetçinin eksik gördüğü şablon/özellik fikirleri
    if res.get("library_ideas"):
        bl = ROOT / "output" / "_brain" / "library_backlog.jsonl"
        bl.parent.mkdir(parents=True, exist_ok=True)
        with open(bl, "a", encoding="utf-8") as f:
            for idea in res["library_ideas"]:
                f.write(json.dumps({"job": job.name, "idea": idea}, ensure_ascii=False) + "\n")
    log(f"QA: {len(issues)} sorun, {'düzeltildi' if changed else 'değişiklik yok'}"
        + "".join(f"\n   - [{i.get('severity', '?')}] {i.get('where', '')} #{i.get('scene', '')}: {i.get('problem', '')[:120]}" for i in issues[:8]))
    return {"issues": issues, "notes": notes, "changed": changed}
