"""Aşama 03: Konuşan karakter — ÜÇ motor (config avatar.engine ile seçilir):

  - musetalk  : (2 Ağu) v1.5 — ağız bölgesini VAE ile foto-gerçekçi INPAINT eder; SadTalker'a
                göre çok daha net ağız + doğal dudak senkronu, O(n) (paste_pic donması YOK),
                16GB'a rahat sığar. İzole Python 3.10 venv (vendor/MuseTalk). Yeşil arka plan
                korunur (yalnızca ağız değişir) -> s07 chroma key'ler. ÖNERİLEN motor.
                NOT: Blackwell (RTX 50xx) için torch cu128 gerekir; mmcv/mmpose kurulumu
                Windows'ta iterasyon isteyebilir (bkz. scripts/setup_musetalk.ps1).
  - sadtalker : tek fotoğraftan konuşan kafa; izole Python 3.10 venv (vendor/SadTalker).
                KALİTELİ ama uzun seslerde paste_pic adımı kare sayısıyla neredeyse kareli
                yavaşlıyor (bkz. README) -> uzun videolarda takılabilir. face_size=256'da ağız
                bulanık; mimik "robotik" -> bu yüzden musetalk'a geçildi.
  - wav2lip   : (31 Tem) O(n), takılma YOK, hareketsiz görselde çalışır; foto-gerçekçi AI
                karaktere ses-tahrikli dudak senkronu uygular. İzole venv (vendor/Wav2Lip).

Girdi: assets/avatar/photo.png (yeşil ekranlı AI karakter) + output/<job_id>/audio.wav
Çıktı: output/<job_id>/avatar.mp4 (yeşil arka plan korunur -> s07 chroma key ile bindirir)
"""
import math
import shutil
import subprocess
import time

from pipeline.utils.config import load_config
from pipeline.utils.logging import get_logger
from pipeline.utils.paths import ROOT, job_path

log = get_logger("s03_avatar")

# preprocess=full modu, GPU render bittikten sonra üretilen yüzü orijinal fotoğrafın
# üzerine CPU'da kare kare (paste_pic, hiçbir ilerleme çubuğunda görünmüyor) geri
# yapıştırıyor. Bu adımın süresi kare başına piksel sayısıyla orantılı; yüksek
# çözünürlüklü bir stüdyo fotoğrafında (ör. 1400x1400) 1700+ kare için bu iş
# "takılmış" gibi görünecek kadar (20-30+ dk) uzun sürebiliyor. Fotoğrafı önceden
# küçültmek bu adımı dramatik şekilde hızlandırıyor, görünür kalite kaybı minimal.
MAX_PHOTO_DIMENSION = 768


def _free_ram_gb() -> float:
    """Windows GlobalMemoryStatusEx ile kullanılabilir fiziksel RAM (GB). ctypes stdlib'de
    olduğu için yeni bir bağımlılık (psutil vb.) gerektirmez."""
    import ctypes

    class _MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = _MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    return stat.ullAvailPhys / (1024 ** 3)


def _free_vram_gb():
    """nvidia-smi ile boş VRAM (GB); komut okunamazsa None döner (o turda VRAM izlemesi atlanır,
    RAM izlemesi yine de çalışmaya devam eder)."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return float(out.stdout.strip().splitlines()[0]) / 1024
    except Exception:
        pass
    return None


def _kill_process_tree(pid: int):
    """proc.kill() yalnızca üst process'i öldürür; CUDA/DataLoader alt process'leri hayatta
    kalıp VRAM/RAM'i tutmaya devam edebilir (izleyici bunu göremez, tıkanma sürer) ->
    taskkill /T ile TÜM alt ağacı öldür."""
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def _wait_render_process(proc, raw_log, engine_label, max_seconds, cfg):
    """18 Ağu OLAYI: EchoMimic render'ı bellek tükenip sistemi swap'a düşürdü, adım süresi
    290s'den 946s'ye fırladı ve PC tamamen kilitlenip donanım seviyesinde yeniden
    başlatılmak zorunda kaldı (bkz. AI_HANDOVER_GUIDE / hafıza notu). Eski kod yalnızca
    TOPLAM süreyi (max_render_minutes) izliyordu; sistem tıkandığında bu döngünün kendisi
    de CPU/disk'e aç kalıp zamanında tepki veremedi. Artık her turda RAM/VRAM'i aktif
    ölçüyoruz ve eşiğin altına inince süre dolmasını BEKLEMEDEN hemen öldürüyoruz —
    tıkanma/donma başlamadan, sistem hâlâ tepki verebilirken."""
    min_free_ram_gb = float(cfg.get("min_free_ram_gb", 2.5))
    min_free_vram_gb = float(cfg.get("min_free_vram_gb", 1.0))
    low_streak = 0
    started = time.monotonic()
    while proc.poll() is None:
        elapsed = time.monotonic() - started
        if elapsed > max_seconds:
            _kill_process_tree(proc.pid)
            proc.wait()
            raise RuntimeError(
                f"{engine_label} {max_seconds // 60} dakikadan uzun sürdü, muhtemelen takıldı; "
                f"sonlandırıldı (bkz. {raw_log})."
            )

        free_ram = _free_ram_gb()
        free_vram = _free_vram_gb()
        low = free_ram < min_free_ram_gb or (free_vram is not None and free_vram < min_free_vram_gb)
        low_streak = low_streak + 1 if low else 0
        # 3 ardışık düşük ölçüm (~6sn) ister -> geçici tek seferlik bir alloc artışını
        # yanlışlıkla öldürmeyi önler, gerçek tükenmeyi yine de erken (saniyeler içinde) yakalar.
        if low_streak >= 3:
            _kill_process_tree(proc.pid)
            proc.wait()
            vram_txt = f"{free_vram:.1f}GB" if free_vram is not None else "?"
            raise RuntimeError(
                f"{engine_label} kaynak güvenliği tetiklendi: boş RAM {free_ram:.1f}GB / boş VRAM "
                f"{vram_txt} eşiğin altına düştü ({elapsed / 60:.0f}dk'da) -> sistem kilitlenmeden "
                f"ÖNCE durduruldu (bkz. {raw_log})."
            )
        time.sleep(2)

    if proc.returncode is None:
        proc.wait()


def _prepare_source_photo(photo):
    from PIL import Image

    with Image.open(photo) as img:
        w, h = img.size
        if max(w, h) <= MAX_PHOTO_DIMENSION:
            return photo

        cache_dir = photo.parent / ".cache"
        cache_dir.mkdir(exist_ok=True)
        src_stat = photo.stat()
        resized_path = cache_dir / f"{photo.stem}_resized_{int(src_stat.st_mtime)}.png"
        if resized_path.exists():
            return resized_path

        scale = MAX_PHOTO_DIMENSION / max(w, h)
        new_size = (round(w * scale), round(h * scale))
        log.info(f"Avatar fotoğrafı {w}x{h} -> {new_size[0]}x{new_size[1]} küçültülüyor (paste_pic hızı için)")
        resized = img.convert("RGB").resize(new_size, Image.LANCZOS)
        resized.save(resized_path)
        return resized_path


def run(job_id: str) -> dict:
    """Motor seçimine göre konuşan karakter üretir (config avatar.engine)."""
    cfg = load_config()["avatar"]
    engine = (cfg.get("engine") or "sadtalker").lower()
    photo = (ROOT / cfg["photo"]).resolve()
    if not photo.exists():
        raise RuntimeError(
            f"Avatar fotoğrafı bulunamadı: {photo}\n"
            "Net, önden çekilmiş bir fotoğrafı assets/avatar/photo.png olarak kaydet."
        )
    audio_file = job_path(job_id, "audio.wav").resolve()
    if not audio_file.exists():
        raise RuntimeError(f"Ses dosyası bulunamadı: {audio_file}")

    if engine == "latentsync":
        # dijital ikiz: fotoğraf değil, kanal sahibinin kendi taban çekimi (config twin.base_video)
        from pipeline import twin
        out = job_path(job_id, "avatar.mp4").resolve()
        twin.lipsync(audio_file, out, job_path(job_id, "_twin").resolve(), log=log.info)
        return {"avatar_file": str(out)}
    if engine == "echomimic":
        return _run_echomimic(job_id, photo, audio_file, cfg)
    if engine == "musetalk":
        return _run_musetalk(job_id, photo, audio_file, cfg)
    if engine == "wav2lip":
        return _run_wav2lip(job_id, photo, audio_file, cfg)
    return _run_sadtalker(job_id, photo, audio_file, cfg)


def _run_echomimic(job_id, photo, audio_file, cfg) -> dict:
    """EchoMimic V2: ses-güdümlü yarım-boy sunucu (izole venv, subprocess).
    scripts/run_echomimic.py reposunun kendi infer config'ini yamalayıp çalıştırır.
    NOT: EchoMimic çıktısı referans görselin arka planını taşır; s07 chroma-key için
    referans görselin yeşil zeminli olması önerilir (bkz. avatar_chroma_key)."""
    venv_python = (ROOT / cfg.get("echomimic_venv_python", "vendor/EchoMimicV2/.venv/Scripts/python.exe")).resolve()
    repo_dir = (ROOT / cfg.get("echomimic_repo_dir", "vendor/EchoMimicV2")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"EchoMimic venv python yok: {venv_python} (scripts/setup_echomimic.ps1 çalıştır)")
    ref_image = (ROOT / cfg.get("echomimic_ref_image", str(photo))).resolve()
    out_mp4 = job_path(job_id, "avatar.mp4").resolve()
    script = (ROOT / "scripts" / "run_echomimic.py").resolve()
    cmd = [
        str(venv_python), str(script),
        "--repo", str(repo_dir),
        "--ref", str(ref_image),
        "--audio", str(audio_file),
        "--out", str(out_mp4),
        "--steps", str(cfg.get("echomimic_steps", 30)),
        "--cfg", str(cfg.get("echomimic_cfg", 2.5)),
        "--fps", str(cfg.get("echomimic_fps", 24)),
        "--max-chunk-frames", str(cfg.get("echomimic_max_chunk_frames", 100)),
    ]
    raw_log = job_path(job_id, "avatar_echomimic.log")
    # ÖNEMLİ: proc.wait() süresiz olamaz — bu venv'te bazı import'lar (mediapipe/decord/
    # onnxruntime) arka planda non-daemon thread bırakıp process'in temiz çıkışını
    # engelleyebiliyor (gözlemlendi: basit bir import-only script bile timeout'a takıldı).
    # _wait_render_process hem toplam süreyi hem RAM/VRAM'i izler -> gerçekten kilitlenirse
    # iş süresiz asılı kalmaz VE sistem tıkanmadan önce müdahale eder (bkz. 18 Ağu olayı).
    max_seconds = cfg.get("max_render_minutes", 40) * 60
    with open(raw_log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, cwd=str(repo_dir), stdout=f, stderr=subprocess.STDOUT)
        _wait_render_process(proc, raw_log, "EchoMimic", max_seconds, cfg)
    if proc.returncode != 0 or not out_mp4.exists():
        tail = raw_log.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"EchoMimic avatar render başarısız (bkz. {raw_log}):\n{tail}")
    log.info(f"EchoMimic avatar üretildi: {out_mp4}")
    return {"avatar_file": str(out_mp4)}


def _run_wav2lip(job_id, photo, audio_file, cfg) -> dict:
    """Wav2Lip: hareketsiz görsele ses-tahrikli dudak senkronu (izole venv, subprocess).
    Yeşil arka plan korunur (Wav2Lip sadece ağız bölgesini değiştirir) -> s07 chroma key'ler."""
    venv_python = (ROOT / cfg.get("wav2lip_venv_python", "vendor/Wav2Lip/.venv/Scripts/python.exe")).resolve()
    repo_dir = (ROOT / cfg.get("wav2lip_repo_dir", "vendor/Wav2Lip")).resolve()
    ckpt = (ROOT / cfg.get("wav2lip_checkpoint", "vendor/Wav2Lip/checkpoints/wav2lip_gan.pth")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"Wav2Lip venv python yok: {venv_python} (scripts/setup_wav2lip.ps1 çalıştır)")
    if not ckpt.exists():
        raise RuntimeError(f"Wav2Lip checkpoint yok: {ckpt} (scripts/setup_wav2lip.ps1 çalıştır)")

    avatar_file = job_path(job_id, "avatar.mp4").resolve()
    cmd = [
        str(venv_python), "inference.py",
        "--checkpoint_path", str(ckpt),
        "--face", str(photo),
        "--audio", str(audio_file),
        "--outfile", str(avatar_file),
        "--pads", "0", "15", "0", "0",   # çene altını biraz genişlet (dudak kırpılmasın)
        "--nosmooth",                     # hareketsiz görselde smooth gerekmez
        "--resize_factor", str(cfg.get("wav2lip_resize_factor", 1)),
    ]
    log.info("Wav2Lip çalıştırılıyor (izole venv) ...")
    max_seconds = cfg.get("max_render_minutes", 40) * 60
    raw_log = job_path(job_id, "avatar_raw_stdout.log")
    with open(raw_log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, cwd=str(repo_dir), stdout=f, stderr=subprocess.STDOUT)
        _wait_render_process(proc, raw_log, "Wav2Lip", max_seconds, cfg)
    if proc.returncode != 0:
        tail = raw_log.read_text(encoding="utf-8", errors="replace")[-1500:]
        raise RuntimeError("Wav2Lip başarısız:\n" + tail)
    if not avatar_file.exists():
        raise RuntimeError(f"Wav2Lip çıktı videosu oluşmadı: {avatar_file}")
    log.info(f"Avatar videosu yazıldı (wav2lip): {avatar_file}")
    return {"avatar_file": str(avatar_file)}


def _run_musetalk(job_id, photo, audio_file, cfg) -> dict:
    """MuseTalk v1.5: statik portrenin AĞIZ BÖLGESİNİ VAE ile foto-gerçekçi inpaint eder.

    SadTalker'dan farkı: tüm yüzü yeniden üretmez, sadece ağzı ses'e göre yeniden çizer ->
    kalan yüz/gövde/arka plan (yeşil ekran) DEĞİŞMEDEN kalır, ağız çok daha net ve doğal olur.
    O(n) çalışır (paste_pic superlineer donması yok), 16GB'a sığar.

    MuseTalk kendi izole venv'inde `python -m scripts.inference --inference_config <yaml>` ile
    çağrılır (SadTalker'ın basit CLI'sinden farklı: girdiyi bir yaml ile verir). Bu fonksiyon
    job'a özel geçici bir yaml üretir, çalıştırır ve üretilen mp4'ü avatar.mp4'e kopyalar.
    """
    venv_python = (ROOT / cfg.get("musetalk_venv_python", "vendor/MuseTalk/.venv/Scripts/python.exe")).resolve()
    repo_dir = (ROOT / cfg.get("musetalk_repo_dir", "vendor/MuseTalk")).resolve()
    unet_model = (ROOT / cfg.get("musetalk_unet_model", "vendor/MuseTalk/models/musetalkV15/unet.pth")).resolve()
    unet_config = (ROOT / cfg.get("musetalk_unet_config", "vendor/MuseTalk/models/musetalkV15/musetalk.json")).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"MuseTalk venv python yok: {venv_python} (scripts/setup_musetalk.ps1 çalıştır)")
    if not unet_model.exists():
        raise RuntimeError(f"MuseTalk model yok: {unet_model} (scripts/setup_musetalk.ps1 çalıştır)")

    # Job'a özel inference yaml — MuseTalk video_path'e bir GÖRSEL kabul eder (statik portre;
    # dahili olarak tek kareyi ses süresince döngüler). Yollar POSIX ayraçlı yazılır (yaml/win uyumu).
    result_dir = job_path(job_id, "avatar_musetalk").resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = result_dir / "inference.yaml"
    face_yaml = str(photo).replace("\\", "/")
    audio_yaml = str(audio_file).replace("\\", "/")
    yaml_path.write_text(
        f"task_0:\n  video_path: \"{face_yaml}\"\n  audio_path: \"{audio_yaml}\"\n",
        encoding="utf-8",
    )

    avatar_file = job_path(job_id, "avatar.mp4").resolve()
    cmd = [
        str(venv_python), "-m", "scripts.inference",
        "--inference_config", str(yaml_path),
        "--result_dir", str(result_dir),
        "--unet_model_path", str(unet_model),
        "--unet_config", str(unet_config),
        "--version", "v15",
        # bbox_shift: ağız/çene kutusunu dikeyde kaydırır -> ağız açıklığını ayarlar (v1.5'te
        # varsayılan 0 iyi; kapalı/az açılan ağız için pozitif değer dene). fps ses'e göre.
        "--bbox_shift", str(cfg.get("musetalk_bbox_shift", 0)),
        "--fps", str(cfg.get("musetalk_fps", 25)),
        "--batch_size", str(cfg.get("musetalk_batch_size", 4)),
    ]
    if cfg.get("musetalk_use_float16", True):
        cmd.append("--use_float16")   # 16GB'da bellek/hız için yarı hassasiyet

    log.info("MuseTalk çalıştırılıyor (izole venv) ...")
    max_seconds = cfg.get("max_render_minutes", 40) * 60
    raw_log = job_path(job_id, "avatar_raw_stdout.log")
    with open(raw_log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, cwd=str(repo_dir), stdout=f, stderr=subprocess.STDOUT)
        _wait_render_process(proc, raw_log, "MuseTalk", max_seconds, cfg)
    if proc.returncode != 0:
        tail = raw_log.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError("MuseTalk başarısız:\n" + tail)

    # MuseTalk çıktıyı result_dir altına (sürüm/görev adına göre) yazar; en yeni mp4'ü al.
    candidates = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError(f"MuseTalk çıktı videosu bulunamadı: {result_dir}")
    shutil.copy2(candidates[0], avatar_file)
    log.info(f"Avatar videosu yazıldı (musetalk): {avatar_file}")
    return {"avatar_file": str(avatar_file)}


def _ffprobe_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return float(out.stdout.strip())


def _sadtalker_one(photo, audio_file, result_dir, venv_python, repo_dir, cfg, raw_log):
    """Tek bir ses parçası (veya tüm ses) için SadTalker çalıştırır ve üretilen
    (enhancer varsa netleştirilmiş) mp4'ün Path'ini döner. Parçalı render'da bu, ses
    parçası başına çağrılır -> her koşu kısa kalır, paste_pic superlineer donması olmaz."""
    preprocess = cfg.get("preprocess", "full")
    cmd = [
        str(venv_python), "inference.py",
        "--driven_audio", str(audio_file),
        "--source_image", str(photo),
        "--result_dir", str(result_dir),
        "--preprocess", preprocess,
        "--size", str(cfg.get("face_size", 256)),
        "--batch_size", str(cfg.get("batch_size", 4)),
        # expression_scale > 1.0: ağız/mimik hareketini büyütür — "yapmacık/donuk"
        # hissi azaltır (1.0 varsayılan; 1.1-1.3 arası doğal, çok yükseği abartılı olur).
        "--expression_scale", str(cfg.get("expression_scale", 1.0)),
        # pose_style (0-45): kafa poz desenini değiştirir (still_mode kapalıyken etkili).
        "--pose_style", str(cfg.get("pose_style", 0)),
    ]
    if cfg.get("still_mode", True):
        cmd.append("--still")
    if cfg.get("enhancer"):
        cmd += ["--enhancer", cfg["enhancer"]]
    # ref_eyeblink/ref_pose: doğal göz kırpma / kafa hareketi için referans video (opsiyonel)
    if cfg.get("ref_eyeblink") and (ROOT / cfg["ref_eyeblink"]).exists():
        cmd += ["--ref_eyeblink", str((ROOT / cfg["ref_eyeblink"]).resolve())]
    if cfg.get("ref_pose") and (ROOT / cfg["ref_pose"]).exists():
        cmd += ["--ref_pose", str((ROOT / cfg["ref_pose"]).resolve())]

    # ÖNEMLİ: stdout'u subprocess.PIPE ile YAKALAMIYORUZ. SadTalker kendi içinde
    # os.system() ile ffmpeg çağırıyor; Windows'ta bu, pipe write-end handle'ının
    # torun process'lere (cmd.exe -> ffmpeg.exe) miras kalıp tam kapanmamasına ve
    # bizim okuma döngümüzün render %100'e ulaştıktan sonra sonsuza kadar EOF
    # beklemesine (deadlock) yol açıyor. Gerçek bir dosyaya yönlendirmek bu Windows
    # pipe-inheritance sorununu tamamen ortadan kaldırıyor.
    # max_render_minutes artık PARÇA başına sınır (parçalar kısa olduğu için bol pay).
    max_seconds = cfg.get("max_render_minutes", 30) * 60
    tail = []
    with open(raw_log, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, cwd=str(repo_dir), stdout=f, stderr=subprocess.STDOUT)

        last_pos = 0
        started = time.monotonic()
        while proc.poll() is None:
            if time.monotonic() - started > max_seconds:
                proc.kill()
                proc.wait()
                raise RuntimeError(
                    f"SadTalker {max_seconds // 60} dakikadan uzun sürdü, muhtemelen takıldı; sonlandırıldı."
                )
            time.sleep(2)
            with open(raw_log, "r", encoding="utf-8", errors="replace") as rf:
                rf.seek(last_pos)
                new_data = rf.read()
                last_pos = rf.tell()
            for line in new_data.splitlines():
                line = line.strip()
                if line:
                    log.info(f"[SadTalker] {line}")
                    tail.append(line)
            tail = tail[-40:]

        with open(raw_log, "r", encoding="utf-8", errors="replace") as rf:
            rf.seek(last_pos)
            new_data = rf.read()
        for line in new_data.splitlines():
            line = line.strip()
            if line:
                log.info(f"[SadTalker] {line}")
                tail.append(line)
        tail = tail[-40:]

    if proc.returncode != 0:
        raise RuntimeError("SadTalker başarısız oldu:\n" + "\n".join(tail))

    candidates = sorted(result_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError(f"SadTalker çıktı videosu bulunamadı: {result_dir}")
    return candidates[0]


def _split_audio(audio_file, n_chunks, chunk_len, duration, out_dir):
    """Ses'i n_chunks parçaya böler (örnek-doğru output-seek). Path listesi döner."""
    parts = []
    for i in range(n_chunks):
        start = i * chunk_len
        # Son parça kalanı tam alsın diye biraz uzun iste; ffmpeg dosya sonunda kendiliğinden durur.
        length = chunk_len if i < n_chunks - 1 else max(duration - start + 1.0, chunk_len)
        part = out_dir / f"audio_{i:03d}.wav"
        cmd = [
            "ffmpeg", "-y", "-i", str(audio_file),
            "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
            "-ar", "16000", "-ac", "1", str(part),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res.returncode != 0 or not part.exists():
            raise RuntimeError(f"Ses parçası çıkarılamadı ({i}):\n{res.stderr[-1000:]}")
        parts.append(part)
    return parts


def _concat_videos(clip_paths, out_file):
    """SadTalker parça kliplerini tek videoya birleştirir (video-only; sesi s07 orijinalden
    ekliyor). Parçalar aynı SadTalker parametreleriyle üretildiği için tutarlı; yine de
    yeniden kodlayarak (concat demuxer + libx264) her ortamda güvenli birleştirme sağlıyoruz."""
    list_file = out_file.parent / "avatar_concat_list.txt"
    lines = []
    for p in clip_paths:
        safe = str(p.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
        str(out_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0 or not out_file.exists():
        raise RuntimeError(f"Avatar parçaları birleştirilemedi:\n{res.stderr[-1500:]}")


def _run_sadtalker(job_id, photo, audio_file, cfg) -> dict:
    photo = _prepare_source_photo(photo)

    venv_python = (ROOT / cfg["venv_python"]).resolve()
    repo_dir = (ROOT / cfg["repo_dir"]).resolve()
    if not venv_python.exists():
        raise RuntimeError(f"SadTalker venv python bulunamadı: {venv_python}")

    avatar_file = job_path(job_id, "avatar.mp4")
    chunk_sec = int(cfg.get("sadtalker_max_chunk_seconds", 0) or 0)
    duration = _ffprobe_duration(audio_file)
    preprocess = cfg.get("preprocess", "full")

    # Parçalama kapalı veya ses zaten kısa -> tek koşu (eski davranış).
    if chunk_sec <= 0 or duration <= chunk_sec:
        result_dir = job_path(job_id, "avatar_raw").resolve()
        result_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"SadTalker çalıştırılıyor (tek koşu, {duration:.0f}s, preprocess={preprocess}) ...")
        raw_log = job_path(job_id, "avatar_raw_stdout.log")
        mp4 = _sadtalker_one(photo, audio_file, result_dir, venv_python, repo_dir, cfg, raw_log)
        shutil.copy2(mp4, avatar_file)
        log.info(f"Avatar videosu yazıldı: {avatar_file}")
        return {"avatar_file": str(avatar_file)}

    # PARÇALI RENDER: paste_pic donmasını önlemek için ses'i kısa parçalara böl,
    # her parçaya ayrı SadTalker koşusu, sonra klipleri birleştir.
    n_chunks = max(1, math.ceil(duration / chunk_sec))
    chunk_len = duration / n_chunks
    chunks_dir = job_path(job_id, "avatar_chunks").resolve()
    chunks_dir.mkdir(parents=True, exist_ok=True)
    log.info(
        f"SadTalker PARÇALI render: {duration:.0f}s ses -> {n_chunks} parça (~{chunk_len:.0f}s/parça), "
        f"preprocess={preprocess} (donma önleme)"
    )

    audio_parts = _split_audio(audio_file, n_chunks, chunk_len, duration, chunks_dir)
    clip_paths = []
    for i, part_audio in enumerate(audio_parts):
        part_dir = chunks_dir / f"raw_{i:03d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        raw_log = job_path(job_id, f"avatar_raw_stdout_c{i:03d}.log")
        log.info(f"  Parça {i + 1}/{n_chunks} render ediliyor ...")
        mp4 = _sadtalker_one(photo, part_audio, part_dir, venv_python, repo_dir, cfg, raw_log)
        clip_paths.append(mp4)

    _concat_videos(clip_paths, avatar_file)
    log.info(f"Avatar videosu yazıldı (parçalı, {n_chunks} parça birleştirildi): {avatar_file}")
    return {"avatar_file": str(avatar_file)}


if __name__ == "__main__":
    import sys
    job = sys.argv[1] if len(sys.argv) > 1 else "manual-test"
    run(job)
