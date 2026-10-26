"""Alt-surec render izleyici -- RAM/VRAM tukenmeden ONCE surecti guvenle durdurur.

18 Agu olayi (EchoMimic render'inin PC'yi tamamen kilitleyip donanim seviyesinde
yeniden baslatmaya zorlamasi) sonrasi s03_avatar.py'de eklenen desenin ortak hali.
Agir model yukleyen her izole-venv subprocess (EchoMimic, MuseTalk, FramePack, ...)
bunu kullanabilir. s03_avatar.py kendi ozel kopyasini tutmaya devam eder (calisan
kodu bozmamak icin dokunulmadi); bu modul yeni entegrasyonlar icindir.
"""
import subprocess
import time


def free_ram_gb() -> float:
    """Windows GlobalMemoryStatusEx ile kullanilabilir fiziksel RAM (GB)."""
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


def free_vram_gb():
    """nvidia-smi ile bos VRAM (GB); okunamazsa None (o turda VRAM izlemesi atlanir)."""
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


def kill_process_tree(pid: int):
    """taskkill /T ile TUM alt surec agacini oldurur (proc.kill() sadece ust sureci
    oldurur; CUDA/DataLoader alt surecleri VRAM/RAM'i tutmaya devam edebilir)."""
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def wait_render_process(proc, raw_log, engine_label, max_seconds,
                         min_free_ram_gb=2.5, min_free_vram_gb=1.0):
    """Sureci bekler; RAM/VRAM esigin altina 3 ardisik olcumde (~6sn) duserse ya da
    max_seconds asilirsa sureci (ve alt agacini) hemen oldurup RuntimeError firlatir."""
    low_streak = 0
    started = time.monotonic()
    while proc.poll() is None:
        elapsed = time.monotonic() - started
        if elapsed > max_seconds:
            kill_process_tree(proc.pid)
            proc.wait()
            raise RuntimeError(
                f"{engine_label} {max_seconds // 60} dakikadan uzun surdu, muhtemelen takildi; "
                f"sonlandirildi (bkz. {raw_log})."
            )

        free_ram = free_ram_gb()
        free_vram = free_vram_gb()
        low = free_ram < min_free_ram_gb or (free_vram is not None and free_vram < min_free_vram_gb)
        low_streak = low_streak + 1 if low else 0
        if low_streak >= 3:
            kill_process_tree(proc.pid)
            proc.wait()
            vram_txt = f"{free_vram:.1f}GB" if free_vram is not None else "?"
            raise RuntimeError(
                f"{engine_label} kaynak guvenligi tetiklendi: bos RAM {free_ram:.1f}GB / bos VRAM "
                f"{vram_txt} esigin altina dustu ({elapsed / 60:.0f}dk'da) -> sistem kilitlenmeden "
                f"ONCE durduruldu (bkz. {raw_log})."
            )
        time.sleep(2)

    if proc.returncode is None:
        proc.wait()
