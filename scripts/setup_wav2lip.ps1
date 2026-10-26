# Wav2Lip kurulumu — ses-tahrikli dudak senkronu (izole venv).
# SadTalker'ın paste_pic yavaşlığı olmadan, foto-gerçekçi AI karaktere (yeşil ekran)
# dudak senkronu uygular. s03_avatar.py engine=wav2lip ile bunu çağırır.
#
# NOT: Wav2Lip'in bağımlılıkları eski; Windows'ta kurulum iterasyon gerektirebilir.
# Bu script en makul yolu dener; checkpoint kaynakları değişebilir (aşağıdaki HF mirror'ı
# güncellemek gerekebilir). Kurulum bittikten sonra config.yaml avatar.enabled: true yap.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor\Wav2Lip"
$ckptDir = Join-Path $vendor "checkpoints"

Write-Host "1) Wav2Lip repo klonlanıyor -> $vendor"
if (-not (Test-Path $vendor)) {
    git clone https://github.com/Rudrabha/Wav2Lip $vendor
}

Write-Host "2) İzole venv oluşturuluyor (Python 3.10 tercih; yoksa py launcher)"
$venv = Join-Path $vendor ".venv"
if (-not (Test-Path $venv)) {
    # SadTalker'ın 3.10 venv python'ı varsa onun tabanını kullanmak yerine sistem py:
    py -3.10 -m venv $venv
}
$vpy = Join-Path $venv "Scripts\python.exe"

Write-Host "3) Bağımlılıklar kuruluyor (torch cu + wav2lip gereksinimleri)"
& $vpy -m pip install --upgrade pip
# torch: CUDA sürümünü makineye göre ayarla (SadTalker setup'ında cu128 kullanıldı)
& $vpy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
& $vpy -m pip install numpy opencv-python "librosa==0.9.1" scipy tqdm numba huggingface_hub

Write-Host "4) Checkpoint'ler indiriliyor -> $ckptDir"
New-Item -ItemType Directory -Force -Path $ckptDir | Out-Null
# wav2lip_gan.pth (yüksek kalite) + s3fd yüz dedektörü. HF mirror kullanılıyor
# (resmi linkler Google Drive; script'lenemez). Mirror değişirse burayı güncelle.
$dl = @"
from huggingface_hub import hf_hub_download
import shutil, os
root = r'$root'
ckpt = os.path.join(root, 'vendor', 'Wav2Lip', 'checkpoints')
sfd  = os.path.join(root, 'vendor', 'Wav2Lip', 'face_detection', 'detection', 'sfd')
os.makedirs(ckpt, exist_ok=True); os.makedirs(sfd, exist_ok=True)
# NOT: repo id'leri doğrula/güncelle — aşağıdakiler yaygın mirror'lar:
for repo, fname, dst in [
    ('numz/wav2lip_studio', 'Wav2Lip/wav2lip_gan.pth', os.path.join(ckpt, 'wav2lip_gan.pth')),
    ('numz/wav2lip_studio', 'Wav2Lip/s3fd.pth', os.path.join(sfd, 's3fd.pth')),
]:
    try:
        p = hf_hub_download(repo_id=repo, filename=fname)
        shutil.copy2(p, dst); print('indirildi ->', dst)
    except Exception as e:
        print('UYARI: indirilemedi', fname, '->', e, '(mirror güncelle)')
"@
& $vpy -c $dl

Write-Host "BITTI. Doğrula: config.yaml avatar.wav2lip_checkpoint mevcut mu, sonra avatar.enabled: true yap."
Write-Host "Test: .venv çıktısı olmadan  ->  python -c `"from pipeline.stages import s03_avatar; s03_avatar.run('<job_id>')`""
