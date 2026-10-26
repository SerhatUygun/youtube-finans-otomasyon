"""Editor / Denetleyici (Reviewer) / Tester üçlü ajan çerçevesi.

17 Eyl eklendi -- kullanıcı isteği: motion-skills/video-skills-toolkit gibi referans
"skill" kütüphanelerindeki kalite disiplinini, kendi Remotion tabanlı üretimimize
otomatik bir denetim katmanı olarak taşımak. Üç rol:

  - Editor    : mevcut aşama kodunun kendisi (örn. motion_graphics_director,
                s07_edit montaj mantığı) -- burada yeniden yazılmaz.
  - Reviewer  (denetleyici, bkz. reviewer.py) : render ÖNCESİ yerel LLM (Ollama) ile
                aday kararı kalite rubriğine göre kritik eder.
  - Tester    (bkz. tester.py) : render SONRASI ffprobe/ffmpeg ile teknik doğrulama
                yapar (süre, çözünürlük, siyah kare) ve raporu diske + Drive'a yazar.

review_loop.run_loop bu üçünü genel bir retry-with-feedback döngüsünde birleştirir.
Her fonksiyon savunmacıdır: Ollama/ffmpeg yoksa veya hata verirse üretimi ASLA
durdurmaz, sadece o denetim adımını atlar (mevcut güvenli davranış korunur)."""
