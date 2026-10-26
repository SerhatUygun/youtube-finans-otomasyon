# 🎬 YouTube Finans Otomasyon Hattı

**Her gün kendi kendine araştıran, yazan, seslendiren, hareketli grafiklerle kurgulayan ve YouTube'a yükleyen yerel bir video fabrikası.**

Türkçe finans içeriği (altın, gümüş, Fed, TL, borsa) için tasarlandı; promptları değiştirerek her nişe uyarlanabilir.

```
 araştırma ─▶ senaryo ─▶ kanca puanı ─▶ seslendirme ─▶ motion graphics ─▶ render ─▶ kapak ─▶ YouTube
 (Claude +    (bible +     (5 kanca,     (VoxCPM2,      (Remotion +        (16:9 +   (A/B/C)   (zamanlanmış
  canlı veri)  storyboard)  zayıf halka)  ses klonu)     three.js)          9:16)               yayın)
```

---

## ✨ Neler yapıyor?

| | |
|---|---|
| 🧠 **Araştırma + senaryo** | Claude Code (`claude -p`) güncel haberleri ve piyasa verisini toplar, rakamları doğrular, sahne sahne senaryo + storyboard yazar |
| 🪝 **Kanca puanlama** | Açılış için 5 kanca yazılır; somutluk / hitap / risk / merak / kısalık üzerinden puanlanır (`tools/hookscore_tr.py`) |
| 🗣️ **Seslendirme** | VoxCPM2 ile ses klonu (paragraf bazlı, sabit tohum → tutarlı ses); Türkçe sayı okuma kuralları |
| 🎞️ **Hareketli grafik** | 40+ Remotion şablonu: grafikler, haritalar, mum çubukları, 3D nesneler, sunucu karakteri, kinetik tipografi |
| ✅ **Denetim** | Render öncesi görsel QA, metin doğrulayıcı, başlık/kapak paketleme denetimi, politika/sorumluluk reddi katmanı |
| 📱 **Shorts** | Aynı gün 2 dikey Shorts, uzun videoya köprü yorumuyla |
| 📤 **Yayın** | YouTube Data API ile private yükleme + `publishAt` zamanlama, oynatma listesi, AI içerik beyanı, kapak |
| 🤖 **Ajanlar** | Haber avcısı, trend izci, performans/retention raporu, yorum asistanı, sistem bekçisi (yerel Ollama) |
| 📊 **Panel** | `tools/dashboard/` — koşu durumu, loglar, ajan çıktıları (localhost:8765) |

## 🗓️ Günlük akış (varsayılan)

| Saat | Ne olur |
|---|---|
| 12:00 | Görev Zamanlayıcı `tools/daily_run.py --auto` başlatır (PC uykudaysa uyandırır, koşu bitene kadar uyutmaz) |
| ~12:20 | Senaryo hazır → doğrulama → ses → render |
| 15:00 | 1. Shorts yayında |
| 18:00 | Uzun video yayında (Pzt/Çar/Cum; diğer günler yalnız Shorts) |
| 21:00 | 2. Shorts yayında |

Saatler `config.yaml → youtube.auto_publish` altında. Belirli bir güne konu sabitlemek için `output/_daily/topic_YYYY-MM-DD.txt` dosyasına konuyu yazman yeterli.

---

## 🖥️ Gereksinimler

- **Windows 10/11**, NVIDIA GPU (16 GB VRAM ile test edildi; RTX 50 serisi için CUDA 12.8)
- **Python 3.12**, **Node.js 20+**, **ffmpeg** (PATH'te)
- **[Claude Code](https://claude.com/claude-code)** CLI (senaryo üretimi için, `claude` komutu PATH'te)
- **[Ollama](https://ollama.com)** (yerel ajanlar için, ör. `qwen3:14b`) — opsiyonel
- Google Cloud projesi: **YouTube Data API v3**, **YouTube Analytics API**, (opsiyonel) **Drive API**

## 🚀 Kurulum

```powershell
git clone <bu-repo>
cd <bu-repo>

# 1) Python ortamı + PyTorch (cu128) + bağımlılıklar
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# 2) Seslendirme motoru (VoxCPM2)
powershell -ExecutionPolicy Bypass -File scripts\setup_voxcpm.ps1

# 3) Remotion
cd remotion; npm install; cd ..

# 4) Ses efektlerini üret (telifsiz, sentetik)
.venv\Scripts\python.exe scripts\gen_sfx.py
```

### Yapılandırma

1. `.env.example` → `.env` olarak kopyala, gerekli anahtarları doldur.
2. **Ses referansı:** `assets/voice_reference/prompt_clean.wav` — kendi sesinden 10–30 sn temiz kayıt.
   Yalnızca **sana ait ya da kullanım izni olan** bir sesi klonla.
3. **Kanal kişiliği:** `channel_persona.json` — niş, ton, hedef kitle, kanca tarzı.
4. **Marka:** `remotion/public/brand/emblem_white.png` (yer tutucu var, kendi logonla değiştir) ve
   `remotion/src/core/brand.tsx` içindeki kanal adı.
5. **Opsiyonel:** `seslendir.txt` (kendi yazdığın üslup örneği, senaryo tonunu belirler) ve
   `config.yaml → ref_watch.channel` (ilham alınacak referans kanal; yalnız konu/yapı, kopya değil).
6. **YouTube:** Google Cloud Console → OAuth Client ID (Desktop app) → JSON'u
   `secrets/youtube_client_secret.json` olarak kaydet, sonra:
   ```powershell
   .venv\Scripts\python.exe tools\reauth_google.py
   ```
   > ⚠️ OAuth uygulaması **Testing** modundaysa Google yetkileri **7 günde bir** düşer.
   > Kalıcı çalışma için uygulamayı **In production**'a al.

### Çalıştırma

```powershell
# Bugünün videosu (yüklemeden, sadece üret)
.venv\Scripts\python.exe -X utf8 tools\daily_run.py --no-upload

# Konuyu sabitle
.venv\Scripts\python.exe -X utf8 tools\daily_run.py --topic "Fed faiz kararı öncesi altın"

# Yalnız Shorts / zorla uzun video
.venv\Scripts\python.exe -X utf8 tools\daily_run.py --shorts-only
.venv\Scripts\python.exe -X utf8 tools\daily_run.py --long

# Her gün otomatik çalışsın (Görev Zamanlayıcı, uyandırma açık)
powershell -ExecutionPolicy Bypass -File scripts\setup_daily_auto.ps1
```

Çıktılar `output/daily-YYYYMMDD/` altına, günlük rapor `output/_daily/YYYY-MM-DD.md` dosyasına yazılır.

---

> ℹ️ **Bu repoda olmayanlar:** kanala özel müzik üreteci (`scripts/fed_motion/`) ve stil dokümanları (`docs/`) çıkarıldı.
> Müzik üreteci yoksa hat sessiz bir müzik yatağıyla render eder; `make_music.py <saniye> <çıktı.wav> <tohum> <ruh_hali>`
> imzasıyla kendi betiğini `scripts/fed_motion/` altına koyabilirsin.

## 📁 Proje yapısı

```
pipeline/
  daily/          günlük hat: build (ses→render→yükleme), validate, timeline, packaging_audit
  stages/         eski aşamalı hat (s01 script … s10 drive) — yükleme/Drive yardımcıları buradan
  policy.py       hassas konu tonu + sorumluluk reddi + AI beyanı
  tv_data.py      fiyat verisi (TradingView spot, Yahoo yedek)
prompts/          Claude'a giden talimatlar (daily_video.md = ana senaryo talimatı)
remotion/src/
  auto/           günlük video kompozisyonları ve şablon kütüphanesi (templates*.tsx, Presenter3D)
  core/           tema, marka, ortak bileşenler
tools/
  daily_run.py    günlük koşunun giriş noktası
  hookscore_tr.py Türkçe kanca puanlayıcı
  agents/         yerel ajanlar (haber, trend, performans, QA, gece editörü)
  dashboard/      kontrol paneli
scripts/          kurulum ve model indirme betikleri
config.yaml       tüm ayarlar (yorumlu)
```

## 🪝 Kanca puanlayıcı

```powershell
.venv\Scripts\python.exe -X utf8 tools\hookscore_tr.py --hook "Faiz inince gram altın uçar, değil mi?"
.venv\Scripts\python.exe -X utf8 tools\hookscore_tr.py --daily output\daily-20261021
```

Karar = %60 ortalama + %40 en zayıf özellik — tek bir zayıf yan kancayı sızdırır.
[chatgpt-youtube-agent-skill](https://github.com/Jakeschincariol/chatgpt-youtube-agent-skill)'deki `hookscore.py`'den Türkçeye uyarlandı.

---

## ⚖️ Sorumlu kullanım

- Videolar **yatırım tavsiyesi değildir**; hat her açıklamaya sorumluluk reddi ekler.
- YouTube politikası gereği sentetik içerik **AI beyanı** ile yüklenir (`contains_synthetic_media`).
- Ses klonlamayı yalnızca kendi sesin ya da izinli bir ses için kullan.
- Başka kanalların içeriğini kopyalamak/çevirmek için tasarlanmadı; referans izleyici yalnız ilham notu çıkarır.

## 📄 Lisans

MIT — bkz. [LICENSE](LICENSE). Kullanılan modellerin (VoxCPM2, SDXL, Whisper vb.) kendi lisansları geçerlidir.
