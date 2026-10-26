# LatentSync 1.5 (ByteDance) setup - video-based lip sync for the "digital twin".
# 1.5 = 256px, ~8GB VRAM (1.6 = 512px needs ~18GB, does not fit 16GB). Output face is restored with GFPGAN later if needed.
# Separate venv: vendor/LatentSync/.venv (Python 3.10). Blackwell GPU (RTX 50xx) -> torch cu128 (requirements pin 2.5.1/cu121 is skipped).
# ASCII only (non-ASCII .ps1 breaks on Windows PowerShell 5.1).
$ErrorActionPreference = "Continue"
$root = "$PSScriptRoot\.."
$dir = "$root\vendor\LatentSync"
$log = "$root\output\_logs\setup_latentsync.log"
New-Item -ItemType Directory -Force "$root\output\_logs" | Out-Null
function L($m) { $t = (Get-Date -Format HH:mm:ss); "$t $m" | Tee-Object -FilePath $log -Append }

L "== LatentSync setup start"
if (-not (Test-Path "$dir\.git")) {
    git clone --depth 1 https://github.com/bytedance/LatentSync.git $dir 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { L "!! git clone failed"; exit 1 }
}
L "repo ok"
if (-not (Test-Path "$dir\.venv\Scripts\python.exe")) {
    & py -3.10 -m venv "$dir\.venv"
}
$py = "$dir\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip wheel setuptools 2>&1 | Out-Null
L "installing torch cu128"
& $py -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 2>&1 | Out-File -Append $log
if ($LASTEXITCODE -ne 0) { L "!! torch install failed"; exit 1 }

# requirements without torch lines / cu121 index / insightface (Windows needs prebuilt wheel)
$req = Get-Content "$dir\requirements.txt" | Where-Object { $_ -notmatch '^(torch|torchvision)==' -and $_ -notmatch 'extra-index-url' -and $_ -notmatch '^insightface' -and $_ -notmatch '^gradio' }
$req | Set-Content -Encoding ascii "$dir\requirements_win.txt"
L "installing requirements"
& $py -m pip install -r "$dir\requirements_win.txt" 2>&1 | Out-File -Append $log
if ($LASTEXITCODE -ne 0) { L "!! requirements install failed (see log)"; exit 1 }

L "installing insightface (prebuilt win wheel)"
& $py -m pip install "https://github.com/Gourieff/Assets/raw/main/Insightface/insightface-0.7.3-cp310-cp310-win_amd64.whl" 2>&1 | Out-File -Append $log
if ($LASTEXITCODE -ne 0) { L "!! insightface wheel failed"; exit 1 }

# insightface/albumentations pull numpy 2, opencv 5, protobuf 6, onnx 1.23 -> binary mismatch with mediapipe/skimage.
# Verified working set (29 Sep): numpy 1.26.4, opencv-python-headless 4.9.0.80, protobuf 3.20.3, onnx 1.16.1
L "pinning numpy/opencv/protobuf/onnx"
& $py -m pip install "numpy==1.26.4" "opencv-python-headless==4.9.0.80" "protobuf==3.20.3" "onnx==1.16.1" 2>&1 | Out-File -Append $log

# 16GB RAM: 5GB unet checkpoint fully loaded into RAM dropped free RAM to 1.7GB -> load with mmap
$u = "$dir\latentsync\models\unet.py"
(Get-Content $u -Raw).Replace("weights_only=True)", "weights_only=True, mmap=True)  # YOUTUBEBOT: 16GB RAM").Replace("        unet = cls.from_config(model_config).to(device)", "        with torch.device(device):  # YOUTUBEBOT: build params directly on GPU`n            unet = cls.from_config(model_config)") | Set-Content -Encoding utf8 $u
# build the 1.27B-param unet on GPU (CPU fp32 copy = 5GB + load copy -> free RAM hit 0.5GB, verified 29 Sep)
$i = "$dir\scripts\inference.py"
(Get-Content $i -Raw).Replace('        device="cpu",', '        device="cuda",  # YOUTUBEBOT: 16GB RAM') | Set-Content -Encoding utf8 $i
& $py -m pip install hf_xet 2>&1 | Out-Null

# restore_video kept every restored 1080p frame in RAM (350 frames -> ~8GB) -> stream frames to the writer instead
$lp = "$dir\latentsync\pipelines\lipsync_pipeline.py"
& "$root\.venv\Scripts\python.exe" "$root\scripts\patch_latentsync_stream.py" $lp 2>&1 | Tee-Object -FilePath $log -Append

L "downloading checkpoints (LatentSync-1.5: unet ~5GB + whisper tiny + auxiliary)"
& $py -m pip install "huggingface_hub[cli]" 2>&1 | Out-Null
& $py -c "from huggingface_hub import hf_hub_download, snapshot_download; d=r'$dir\checkpoints'; hf_hub_download('ByteDance/LatentSync-1.5','latentsync_unet.pt',local_dir=d); hf_hub_download('ByteDance/LatentSync-1.5','whisper/tiny.pt',local_dir=d); snapshot_download('ByteDance/LatentSync-1.5',allow_patterns=['auxiliary/*'],local_dir=d)" 2>&1 | Out-File -Append $log
if ($LASTEXITCODE -ne 0) { L "!! checkpoint download failed"; exit 1 }

L "import test"
& $py -c "import torch, insightface, mediapipe, diffusers, decord; print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))" 2>&1 | Tee-Object -FilePath $log -Append
if ($LASTEXITCODE -ne 0) { L "!! import test failed"; exit 1 }
L "== LatentSync setup DONE"
"done" | Set-Content "$root\output\_logs\setup_latentsync.done"
