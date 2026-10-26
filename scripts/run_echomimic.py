#!/usr/bin/env python
"""EchoMimic V2 avatar sarmalayici - izole venv (vendor/EchoMimicV2/.venv) icinde calisir.

Strateji: reposunun KENDI infer_acc.yaml'ini yukle, girdileri (ref gorsel + ses + poz)
yamalayip infer_acc.py'yi calistir. Boylece config semasini sifirdan uydurmak yerine
gecerli bir tabandan gidilir (semaya dayanikli).

s03_avatar.py bunu subprocess olarak cagirir:
    <venv> scripts/run_echomimic.py --repo vendor/EchoMimicV2 --ref <png> --audio <wav> --out <mp4>

14 Agu DUZELTME (kok neden analizi ile dogrulandi):
  1) infer.py (standart) config'teki "test_cases" anahtarini HIC OKUMUYOR - sadece
     argparse'in --ref_images_dir/--refimg_name/--audio_name/--pose_name varsayilanlarini
     (demo ornekleri!) kullaniyor. Sadece infer_acc.py gercekten config["test_cases"]'i
     okuyor. Bu yuzden infer_acc.py + infer_acc.yaml (acc agirliklari ile eslesen) BIRLIKTE
     secilir; onceki kod infer.yaml (standart agirliklar) ile infer_acc.py'yi (hizlandirilmis
     pipeline sinifi) YANLIS eslestiriyordu.
  2) infer_acc.py'nin argparse'inda "-L" (kare sayisi) varsayilani 240'TIR VE KOMUT SATIRINDAN
     HIC GECILMIYORDU -> ses ne kadar uzun olursa olsun avatar HER ZAMAN ~240 kare (24fps'te
     ~10sn) ile KESILIYORDU. Ayrica poz dizinleri (assets/halfbody_demo/pose/*) sabit kisa
     jest kliplerdir (97-336 kare = ~4-14sn) - ses onlardan uzunsa modelin kendisi de tek
     seferde tum sesi karsilayamaz. Cozum: sesi poz uzunlugunca PARCALARA bol (SadTalker
     motorundaki ayni desen), her parcayi AYNI islemde (model bir kez yuklenir, tekrar
     yuklenmez) ayri bir test_cases girdisi olarak isle, sonra klipleri ffmpeg concat ile
     birlestir.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return float(out.stdout.strip())


def _count_pose_frames(pose_dir: Path) -> int:
    return len(list(pose_dir.glob("*.npy")))


def _split_audio(audio_file: str, n_chunks: int, chunk_len: float, duration: float, out_dir: Path):
    parts = []
    for i in range(n_chunks):
        start = i * chunk_len
        length = chunk_len if i < n_chunks - 1 else max(duration - start + 1.0, chunk_len)
        part = out_dir / f"audio_{i:03d}.wav"
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_file),
            "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
            "-ar", "16000", "-ac", "1", str(part),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or not part.exists():
            raise SystemExit(f"[echomimic] ses parcasi cikarilamadi ({i}):\n{res.stderr[-1000:]}")
        parts.append(part)
    return parts


def _concat_videos(clip_paths, out_file: Path):
    if len(clip_paths) == 1:
        shutil.copy2(clip_paths[0], out_file)
        return
    list_file = out_file.parent / "_echomimic_concat_list.txt"
    lines = []
    for p in clip_paths:
        safe = str(Path(p).resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
        str(out_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not out_file.exists():
        raise SystemExit(f"[echomimic] parcalar birlestirilemedi:\n{res.stderr[-1500:]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", required=True, help="referans gorsel (sunucu)")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pose", default="", help="poz dizini (bos = otomatik secim, bkz --max-chunk-frames)")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=2.5)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument(
        "--max-chunk-frames", type=int, default=100,
        help="18 Agu OLAYI: en uzun poz (336 kare) tek diffusion batch'inde 16GB VRAM'i "
             "asip sisteme swap'letiyor, adim suresi 290s->946s'ye firlayip PC'yi kilitledi. "
             "Otomatik secim artik bu tavani ASMAYAN EN UZUN pozu secer (daha kucuk VRAM "
             "batch'i -> daha fazla ama guvenli parca). --pose ile elle asilabilir.",
    )
    a = ap.parse_args()

    repo = Path(a.repo).resolve()

    # infer_acc.py TERCIH EDILIR: config["test_cases"]'i okuyan TEK varyant budur (bkz. modul
    # docstring'i). infer.py bulunursa VE infer_acc.py YOKSA standart yola geri donulur (test_cases
    # bu durumda islevsiz kalir; sadece demo varsayilanlari calisir - bilinen sinirlama).
    use_acc = (repo / "infer_acc.py").exists()
    infer = "infer_acc.py" if use_acc else "infer.py"
    base_cfg_name = "infer_acc.yaml" if use_acc else "infer.yaml"
    base_cfg = repo / "configs" / "prompts" / base_cfg_name
    if not base_cfg.exists():
        # diger varyanta dus (agirlik yollari genel anahtarlar oldugu icin yine calisir)
        alt_name = "infer.yaml" if use_acc else "infer_acc.yaml"
        base_cfg = repo / "configs" / "prompts" / alt_name
    if not base_cfg.exists():
        raise SystemExit(f"EchoMimic config bulunamadi: {base_cfg}")
    cfg = yaml.safe_load(base_cfg.read_text(encoding="utf-8")) or {}

    if not use_acc:
        print("[echomimic] UYARI: infer_acc.py yok, standart infer.py kullanilacak. "
              "Bu varyant test_cases'i OKUMAZ -> yalnizca repo demo varsayilanlarini render eder.",
              file=sys.stderr)
        cmd = [sys.executable, infer, f"--config=./configs/prompts/{base_cfg_name}",
               "--steps", str(a.steps), "--cfg", str(a.cfg), "--fps", str(a.fps)]
        res = subprocess.run(cmd, cwd=str(repo))
        if res.returncode != 0:
            raise SystemExit(f"EchoMimic inference basarisiz (exit {res.returncode})")
        outs = sorted(repo.glob("**/*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not outs:
            raise SystemExit("EchoMimic hic mp4 uretmedi")
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(outs[0]), str(out))
        print(f"[echomimic] yazildi: {out}")
        return

    # --- poz dizini secimi: verilmemisse en UZUN (en cok .npy kareli) poz kullanilir ---
    pose_root = repo / "assets" / "halfbody_demo" / "pose"
    if a.pose:
        pose_dir = Path(a.pose)
    else:
        cands = [p for p in sorted(pose_root.glob("*")) if p.is_dir()]
        if not cands:
            raise SystemExit(f"Poz dizini bulunamadi: {pose_root}")
        under_cap = [p for p in cands if _count_pose_frames(p) <= a.max_chunk_frames]
        # tavanin altindakilerin EN UZUNU (parca sayisini azaltir); hicbiri tavanin
        # altinda degilse (hepsi cok uzun) EN KISA olani sec (VRAM guvenligi > parca sayisi).
        pose_dir = max(under_cap, key=_count_pose_frames) if under_cap else min(cands, key=_count_pose_frames)
    pose_frames = _count_pose_frames(pose_dir)
    if pose_frames <= 0:
        raise SystemExit(f"Poz dizininde .npy kare yok: {pose_dir}")
    chunk_len = pose_frames / a.fps  # bir parcanin kaplayabilecegi MAKSIMUM ses suresi (sn)

    duration = _ffprobe_duration(a.audio)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work_dir = out.parent / "avatar_echomimic_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)

    import math
    n_chunks = max(1, math.ceil(duration / chunk_len))
    print(f"[echomimic] ses={duration:.1f}s poz={pose_dir.name}({pose_frames}kare={chunk_len:.1f}s/parca) "
          f"-> {n_chunks} parca (model TEK sefer yuklenir)")

    if n_chunks == 1:
        audio_parts = [Path(a.audio)]
        chunk_frame_counts = [min(pose_frames, int(duration * a.fps))]
    else:
        audio_parts = _split_audio(a.audio, n_chunks, chunk_len, duration, work_dir)
        chunk_frame_counts = [pose_frames] * (n_chunks - 1)
        last_len = duration - chunk_len * (n_chunks - 1)
        chunk_frame_counts.append(min(pose_frames, max(1, int(last_len * a.fps))))

    # Her parca icin ref gorseli benzersiz bir isimle kopyala (test_cases dict anahtari
    # ref gorsel YOLUDUR -> ayni yol tekrar kullanilamaz, kopya sart).
    ref_src = Path(a.ref)
    test_cases = {}
    for i, (audio_part, l) in enumerate(zip(audio_parts, chunk_frame_counts)):
        ref_copy = work_dir / f"ref_{i:03d}{ref_src.suffix}"
        if not ref_copy.exists():
            shutil.copy2(ref_src, ref_copy)
        test_cases[str(ref_copy).replace("\\", "/")] = [
            str(audio_part).replace("\\", "/"), str(pose_dir).replace("\\", "/"),
        ]

    cfg["test_cases"] = test_cases
    for k, v in (("cfg", a.cfg), ("guidance_scale", a.cfg), ("fps", a.fps)):
        if k in cfg:
            cfg[k] = v

    tmp_cfg = repo / "configs" / "prompts" / "_auto_infer.yaml"
    tmp_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")

    # -L: infer_acc.py bunu TEK bir baslangic degeri olarak alir ve kendi ic dongusunde
    # `args.L = min(args.L, audio_suresi*fps, poz_kare_sayisi)` ile HER test_case'te KUCULTUR
    # (Namespace uzerinde birikimli -> asla BUYUMEZ). Parcalarimizi kisadan-uzuna DEGIL,
    # sirali (son parca en kisa/esit) ekledigimiz icin bu birikimli kucultme sorun cikarmaz:
    # ilk n-1 parca ayni pose_frames'te sabit kalir, yalnizca SON (kisa) parcada dogru sekilde
    # kirpilir. Baslangic degerini pose_frames vererek varsayilan 240 kare kesmesini onluyoruz.
    cmd = [
        sys.executable, infer, "--config=./configs/prompts/_auto_infer.yaml",
        "-L", str(pose_frames),
        "--steps", str(a.steps), "--cfg", str(a.cfg), "--fps", str(a.fps),
    ]
    print("[echomimic] calistiriliyor:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(repo))
    if res.returncode != 0:
        raise SystemExit(f"EchoMimic inference basarisiz (exit {res.returncode})")

    # infer_acc.py her test_case icin outputs/output/<tarih>/<...>/<ref_name>/<...>_sig.mp4 yazar.
    # ref_NNN klasor adlarina gore sirali topla (kronolojik parca sirasi = ref index sirasi).
    all_sig_mp4s = list(repo.glob("output/**/*_sig.mp4"))
    clips = []
    for i in range(len(test_cases)):
        ref_name = f"ref_{i:03d}"
        matches = sorted(
            (p for p in all_sig_mp4s if ref_name in p.parts),
            key=lambda p: p.stat().st_mtime,
        )
        if not matches:
            raise SystemExit(f"EchoMimic parca {i} icin cikti bulunamadi (ref={ref_name})")
        clips.append(matches[-1])

    _concat_videos(clips, out)
    print(f"[echomimic] yazildi ({len(clips)} parca birlestirildi): {out}")


if __name__ == "__main__":
    main()
