import os
from pathlib import Path

# C: sürücüsü doluyordu — model indirmeleri (HuggingFace cache) varsayılan olarak
# kullanıcı profiline (C:) gidiyor. Burayı E: sürücüsüne (bol boş alan) yönlendiriyoruz.
_ROOT_DIR = Path(__file__).resolve().parent.parent
_hf_cache_dir = _ROOT_DIR / ".cache" / "huggingface"
os.environ.setdefault("HF_HOME", str(_hf_cache_dir))
os.environ.setdefault("TORCH_HOME", str(_ROOT_DIR / ".cache" / "torch"))

# torchcodec (torchaudio >= 2.9'un ses IO backend'i), sistemdeki ffmpeg statik
# derleme olduğu için (avutil-*.dll vb. paylaşımlı kütüphaneler yok) DLL'lerini
# bulamıyor. vendor/ffmpeg-shared/bin altındaki paylaşımlı derlemeyi PATH'e ekliyoruz.
_vendor_ffmpeg_bin = Path(__file__).resolve().parent.parent / "vendor" / "ffmpeg-shared" / "bin"
if _vendor_ffmpeg_bin.is_dir():
    os.environ["PATH"] = str(_vendor_ffmpeg_bin) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(_vendor_ffmpeg_bin))

# Windows'ta symlink oluşturmak için Developer Mode ya da admin yetkisi gerekir.
# huggingface_hub'ın kendi kontrolü tutarsız davranabiliyor (bazı dosyalarda
# WinError 1314 ile patlıyor); model indirmelerinde symlink'i baştan kapatıyoruz.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
try:
    import huggingface_hub.file_download as _hf_file_download
    _hf_file_download.are_symlinks_supported = lambda *a, **k: False
except ImportError:
    pass
