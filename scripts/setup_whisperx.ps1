# WhisperX kurulumu — faster-whisper + wav2vec2 FORCED ALIGNMENT (<100ms kelime senkronu).
# s06_subtitles.py engine=whisperx ile IN-PROCESS import eder -> ANA venv'e kurulur.
# UYARI: whisperx ana venv'deki torch/torchaudio/numpy'yi değiştirebilir. Riskliyse önce
# `pip freeze > .venv_backup.txt` al. (Altyazı zaten çoğunlukla script-timing'den üretiliyor;
# whisperx yalnızca elle-ses yedek yolunda çalışır -> düşük öncelikli iyileştirme.)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vpy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $vpy)) { throw "Ana venv bulunamadı: $vpy" }

Write-Host "1) Mevcut ortam yedekleniyor -> .venv_pipfreeze_backup.txt"
& $vpy -m pip freeze > (Join-Path $root ".venv_pipfreeze_backup.txt")

Write-Host "2) whisperx kuruluyor (ana venv)"
& $vpy -m pip install whisperx

Write-Host ""
Write-Host "BITTI. config.yaml -> subtitles.engine: whisperx" -ForegroundColor Green
Write-Host "Sorun olursa geri dön: pip install -r .venv_pipfreeze_backup.txt"
