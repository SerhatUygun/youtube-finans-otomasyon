# MuseTalk v1.5 kurulumu — ses-tahrikli AĞIZ INPAINT (izole venv).
# SadTalker'ın bulanık ağzı / robotik mimiği yerine, statik foto-gerçekçi karakterin
# yalnızca AĞIZ bölgesini VAE ile foto-gerçekçi yeniden çizer -> çok daha net + doğal,
# O(n) (paste_pic donması yok), 16GB'a sığar. s03_avatar.py engine=musetalk ile çağırır.
#
# !! ÖNEMLİ (RTX 50xx / Blackwell) !!
#   MuseTalk resmi olarak torch 2.0.1 der; ANCAK Blackwell (sm_120) yalnızca cu128 + torch>=2.7
#   ile çalışır. Bu script Blackwell için cu128 torch kurar. mmcv/mmpose bu torch ile Windows'ta
#   kurulumu ZOR paketlerdir — openmim (mim install) yolu denenir; başarısız olursa aşağıdaki
#   "SORUN GİDERME" notlarına bak. Bu, "klonla-çalıştır" değil, iterasyon gerektirebilen bir kurulumdur.
#
# 13/14 Ağu GECE: UÇTAN UCA DOĞRULANDI (import-only; render testi HENÜZ yapılmadı — bkz.
# output/_logs/musetalk_setup_report.md). Bu makinede (cu128 + torch 2.11) OpenMMLab hiçbir
# prebuilt mmcv wheel YAYINLAMAMIŞ (download.openmmlab.com/mmcv/dist/cu128/torch*/index.html
# tüm sürümler için 404) -> `mim install mmcv` kaynaktan derlemeye düşüyor, bu da nvcc (CUDA
# Toolkit) + MSVC (VS Build Tools) ister; İKİSİ DE bu makinede kurulu DEĞİL. Çözüm: derlenmiş
# mmcv yerine SAF PYTHON "mmcv-lite" kullan (aşağıda adım 5'te uygulanıyor). Bunun 2 yan etkisi
# oldu, ikisi de aşağıda otomatik ele alınıyor:
#   (a) numpy ABI uyumsuzluğu: torch cu128 numpy 2.x çekiyor ama opencv-python==4.9.0.80 (ve
#       mmcv-lite'ın cv2 bağımlılığı) numpy 1.x'e derli -> "numpy.core.multiarray failed to
#       import" / "_ARRAY_API not found". Fix: numpy'ı 1.26.4'e SABİTLE (torch cu128 ile uyumlu,
#       ama cv2/mmcv ABI'siyle de uyumlu).
#   (b) mmpose 1.3.2 (en yeni), EDPoseHead'i (DETR-tipi poz modeli) paket import zincirine
#       eager olarak sokuyor -> `mmcv.ops.MultiScaleDeformableAttention` gerektiriyor, bu da
#       DERLENMİŞ mmcv._ext ister (mmcv-lite'ta yok) -> import ANINDA ModuleNotFoundError:
#       'mmcv._ext'. MuseTalk aslında yalnızca RTMPose/DWPose (topdown poz) kullanıyor, EDPose
#       DEĞİL. Fix: mmpose==1.1.0'a SABİTLE (EDPoseHead henüz yokken) — inference_topdown/
#       init_model/merge_data_samples aynı şekilde çalışıyor, import temiz.
#   (c) mmdet, mmcv sürümüne katı assert koyuyor ("MMCV==X.X.X incompatible") -> mmcv-lite'ı
#       spesifik olarak 2.1.0'a sabitledik (2.2.0 mmdet 3.3.0 ile çakışıyordu).
# ÖZET: mmcv-lite==2.1.0 + mmdet 3.3.0 + mmpose==1.1.0 + numpy==1.26.4 üçlüsü bu makinede
# TEMİZ import ediyor. Gerçek render/inference (GPU'ya init_model ile model yükleme) henüz
# test edilmedi çünkü kurulum sırasında ana GPU (16GB) tools/auto_improve_loop.py'nin
# EchoMimic render'ıyla doluydu — eşzamanlı render OOM riskiydi.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\MuseTalk"

Write-Host "1) MuseTalk repo klonlanıyor -> $vendor"
if (-not (Test-Path $vendor)) {
    git clone https://github.com/TMElyralab/MuseTalk $vendor
}

Write-Host "2) İzole venv (Python 3.10) oluşturuluyor"
$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) {
    py -3.10 -m venv $venv
}
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip setuptools wheel
# EchoMimic kurulumunda görülen sorun: yeni setuptools pkg_resources'ı kaldırıyor, bazı eski
# paketlerin (chumpy, mmcv derleme zinciri) build script'i pkg_resources/pip'i import ediyor.
# Eski bir sürüme sabitle (75.6.0'da pkg_resources hâlâ mevcut).
& $vpy -m pip install "setuptools==75.6.0"

Write-Host "3) PyTorch (Blackwell -> cu128) kuruluyor"
# RTX 50xx için cu128. Eski GPU'da (30xx/40xx) cu121 de olur; o durumda index-url'i değiştir.
& $vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Write-Host "4) MuseTalk bağımlılıkları kuruluyor"
# requirements.txt torch'u yeniden sabitleyebilir; --no-deps mantığıyla önce çekirdek paketler.
& $vpy -m pip install diffusers==0.30.2 accelerate==0.28.0 transformers==4.39.2 huggingface_hub==0.30.2
& $vpy -m pip install opencv-python==4.9.0.80 imageio imageio-ffmpeg omegaconf einops==0.8.1 librosa==0.11.0 soundfile==0.12.1 scipy tqdm gdown ffmpeg-python moviepy
# torch cu128 numpy 2.x çeker ama opencv-python==4.9.0.80/mmcv-lite numpy 1.x ABI'sine derli
# ("numpy.core.multiarray failed to import" hatası verir) -> 1.26.4'e SABİTLE (torch cu128 ile
# de, cv2/mmcv ile de uyumlu). torch/torchvision kurulumundan SONRA çalıştırılmalı.
& $vpy -m pip install "numpy==1.26.4"

Write-Host "5) mmcv / mmpose / mmdet — EN KIRILGAN ADIM"
# 13 Ağu doğrulandı: bu makinede (cu128 + torch 2.11) OpenMMLab hiçbir prebuilt mmcv wheel
# YAYINLAMAMIŞ (download.openmmlab.com/mmcv/dist/cu128/torch*/index.html tüm sürümler 404) ->
# `mim install mmcv` kaynaktan derlemeye düşer, bu da nvcc (CUDA Toolkit) + MSVC (VS Build
# Tools) ister. Bu makinede ikisi de YOK ve kurulumu ~10GB+ ek indirme gerektirir. Bunun yerine
# SAF PYTHON "mmcv-lite" (derlenmiş CUDA op'ları yok, MuseTalk'ın kullandığı RTMPose/DWPose
# topdown poz modeli için yeterli) + eski bir mmpose (EDPoseHead'in mmcv derlenmiş op'u
# gerektirdiği 1.3.x öncesi) kullanılıyor.
& $vpy -m pip install -U openmim
& $vpy -m mim install "mmengine"
# chumpy (mmpose'un dolaylı bağımlılığı) eski setup.py'de "import pip" yapıyor -> pip'in
# izole build ortamında görünmemesi hatasını önlemek için --no-build-isolation şart.
& $vpy -m pip install chumpy --no-build-isolation
# mmcv (full, CUDA-derlenmiş) YERİNE mmcv-lite -> derleme/nvcc/MSVC gerektirmez.
# 2.2.0 DEĞİL 2.1.0: mmdet 3.3.0 "MMCV==2.2.0 incompatible, mmcv<2.2.0 gerekli" diye assert atar.
& $vpy -m pip install "mmcv-lite==2.1.0"
& $vpy -m mim install "mmdet>=3.1.0"
# mmpose 1.3.x DEĞİL 1.1.0: 1.3.x, EDPoseHead'i eager import ediyor -> mmcv.ops.
# MultiScaleDeformableAttention (derlenmiş op, mmcv-lite'ta yok) -> import anında
# "ModuleNotFoundError: No module named 'mmcv._ext'". 1.1.0'da bu head yok, RTMPose/DWPose
# (MuseTalk'ın gerçekten kullandığı) sorunsuz çalışıyor.
& $vpy -m pip install "mmpose==1.1.0" --no-deps

Write-Host "5b) Doğrulama (import-only, GPU'ya yük bindirmez)"
& $vpy -c "import mmcv, mmdet, mmpose; from mmpose.apis import inference_topdown, init_model; from mmpose.structures import merge_data_samples; print('mmcv', mmcv.__version__, 'mmdet', mmdet.__version__, 'mmpose', mmpose.__version__, '-> OK')"

Write-Host "6) Model ağırlıkları indiriliyor -> $vendor\models"
# MuseTalk'ın kendi download_weights.sh'i Linux bash içindir. Git-Bash varsa onu kullanmayı
# deneyebilirsin; burada Windows için huggingface_hub tabanlı bir indirici çalıştırıyoruz.
# NOT: repo id / dosya adları değişirse bu bloğu güncelle (bkz. MuseTalk README "Download weights").
$dl = @"
import os
from huggingface_hub import snapshot_download, hf_hub_download
root = r'$vendor'
models = os.path.join(root, 'models')
os.makedirs(models, exist_ok=True)

def safe(fn, what):
    try:
        fn(); print('OK ->', what)
    except Exception as e:
        print('UYARI indirilemedi:', what, '->', e)

# 1) MuseTalk v1.5 ağırlıkları (unet.pth + musetalk.json) ve v1
safe(lambda: snapshot_download(repo_id='TMElyralab/MuseTalk', local_dir=models,
     allow_patterns=['musetalkV15/*','musetalk/*']), 'MuseTalk unet (v15+v1)')

# 2) sd-vae-ft-mse (VAE) -> 'sd-vae' klasör adı (configs/training/*.yaml vae_type: "sd-vae"
#    ile eşleşir; MuseTalk'ın kendi download_weights.bat'ı da bu adı kullanıyor)
safe(lambda: snapshot_download(repo_id='stabilityai/sd-vae-ft-mse',
     local_dir=os.path.join(models, 'sd-vae'),
     allow_patterns=['config.json','diffusion_pytorch_model.bin','diffusion_pytorch_model.safetensors']), 'sd-vae-ft-mse')

# 3) whisper (ses özelliği) — tiny yeterli
safe(lambda: hf_hub_download(repo_id='openai/whisper-tiny', filename='config.json',
     local_dir=os.path.join(models, 'whisper')), 'whisper-tiny config')
safe(lambda: snapshot_download(repo_id='openai/whisper-tiny',
     local_dir=os.path.join(models, 'whisper')), 'whisper-tiny full')

# 4) DWPose
safe(lambda: hf_hub_download(repo_id='yzd-v/DWPose', filename='dw-ll_ucoco_384.pth',
     local_dir=os.path.join(models, 'dwpose')), 'dwpose')

# 5) face-parse-bisent (yüz maskesi) + resnet18
safe(lambda: hf_hub_download(repo_id='ManyOtherFunctions/face-parse-bisent',
     filename='79999_iter.pth', local_dir=os.path.join(models, 'face-parse-bisent')), 'face-parse 79999_iter')
safe(lambda: hf_hub_download(repo_id='ManyOtherFunctions/face-parse-bisent',
     filename='resnet18-5c106cde.pth', local_dir=os.path.join(models, 'face-parse-bisent')), 'face-parse resnet18')

print('Model indirme tamam (UYARI satırlarını kontrol et; eksik varsa README mirror ile tamamla).')
"@
& $vpy -c $dl

Write-Host ""
Write-Host "BITTI. Sonraki adımlar:" -ForegroundColor Green
Write-Host "  a) Doğrula: vendor\MuseTalk\models\musetalkV15\unet.pth mevcut mu?"
Write-Host "  b) İlk render testi (avatarı config'de enabled:false bırakıp izole çağır):"
Write-Host '       python -c "from pipeline.stages import s03_avatar; s03_avatar.run(''<job_id>'')"'
Write-Host "  c) Çıktı avatar.mp4 KALİTELİ ise config.yaml -> avatar.enabled: true yap."
Write-Host ""
Write-Host "SORUN GİDERME (mmcv/mmpose Blackwell'de kurulmazsa):" -ForegroundColor Yellow
Write-Host "  - 'Visual Studio Build Tools 2022' (C++ masaüstü geliştirme) kur; sonra mim install'i tekrar dene."
Write-Host "  - Alternatif: cu121 torch (torch==2.4.1) + mmcv 2.1 prebuilt wheel dene (Blackwell'de GPU çalışmaz;"
Write-Host "    sadece CPU test için). Blackwell'de GPU için cu128 şart."
Write-Host "  - Son çare: MuseTalk yerine geçici olarak engine=wav2lip (scripts/setup_wav2lip.ps1) — daha basit deps."
