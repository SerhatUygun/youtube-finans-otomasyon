## ÖZEL FORMAT: {{MIN}} DAKİKALIK HAFTALIK DEV VİDEO (bu bölüm yukarıdaki "8–9 dk / 1300–1500 kelime / 30–45 segment" kurallarını EZER)

Bugün kanal sahibinin özel isteği: **{{MIN}} dakikalık** tek uzun video + 3 Shorts. Video "haftanın tüm detayları"dır: bu haftanın
altın/gümüş, dolar/TL, Fed ve faiz beklentileri, borsa, kripto, petrol, Türkiye gündemi (fon tasfiyeleri, TCMB, enflasyon) ve gelecek
haftanın takvimini TEK çatıda, derinlemesine ve doğrulanmış verilerle anlatır. Yayın: Cumartesi 17:00 (sistem ayarlar).

### Süre ve ölçü
- **tts toplamı en az {{MIN}} × 138 kelime** (≈ {{MIN}} dk). Her segment yine paragraf: 2–3 cümle, 20–45 kelime. Toplam ~140–170 segment.
- Dolgu YOK. {{MIN}} dakikayı doldurmanın yolu daha çok doğrulanmış veri, hesap, senaryo ve açıklamadır; tekrar değil.
- 40 dk'da dikkat düşer: **~4 dakikada bir yeni "mini bölüm"** (Chapter kartı), her bölümün başında 1 cümlelik "bu bölümde ne öğreneceksin",
  sonunda 1 cümlelik özet. Her ~3 dakikada bir "birazdan …" köprüsü (toplam 10–14; hepsi videoda yerine getirilir).
- Yapı (bölüm sırası serbest ama hepsi olsun; her biri ~3–5 dk): 0) kanca + haftanın tek cümlelik karnesi ve vaat · 1) haftanın karnesi:
  100 bin TL varlık varlık nereye gitti · 2) altın/gümüş ve Fed (sebepler + madalyonun öbür yüzü + gram altın hesabı) ·
  3) dolar/TL ve TCMB · 4) borsa İstanbul ve yabancı piyasalar · 5) kripto · 6) petrol/akaryakıt ve enflasyona etkisi ·
  7) Türkiye gündemi (fon tasfiyeleri vb.; birikimine dersi) · 8) "Sık sorulanlar": `yt_suggest.json`daki gerçek arama sorgularından
  4–6 tanesini kısaca yanıtla · 9) önümüzdeki haftanın takvimi (Türkiye saatiyle) + her varlık için koşul→seviye senaryoları ·
  10) kapanış: yasal uyarı, izleyiciye soru, abone çağrısı, bir sonraki videoya söz (yalnız tutulabilecek).
- **Yenilikçi, tekdüze olmayan anlatım:** her bölümde farklı sahne şablonları kullan (`prompts/scene_catalog.md` — Candles, Heatmap,
  WorldMap, YieldCurve, Metal3D, Globe3D, Countdown, Headline… hepsini tara). Videonun ortasında **"Haftanın mini sınavı"** (3 soru,
  cevaplar bölüm sonunda) ve sonunda **"tek sayfalık özet"** (tüm varlıklar, hafta rakamı, gelecek hafta seviyesi) olsun.
  Aynı şablonu art arda 3 kereden fazla kullanma. Sakin tempo kuralı (hits ≤ 8) geçerli.
- Kanca/açılış, kendini tanıtma yasağı, "yatırım tavsiyesi değildir" kuralları, TL/rakam/tts yazım kuralları AYNEN geçerli.
- Her sayı doğrulanmış olmalı: `brief.json` `facts` en az 25 madde, her biri kaynaklı. Doğrulanamayan şeyi söyleme, süre dolduruyor diye uydurma.
  Hesaplar (gram altın = ons × kur / 31,1035 vb.) `market_snapshot` verisiyle tutarlı olmalı.

### Dosya yazma düzeni (ÇOK ÖNEMLİ — tek JSON'a sığmaz)
1. `video.json`'a yalnız üst veriyi yaz: title, titles, description, tags, pinned_comment, community_post, hud_date, chapters_hud
   (6–8 bölüm; `seg` = bölümün başladığı GLOBAL segment indeksi), ticker, hits, hook_variants, mood, experiment ve **`"segments": []`, `"scenes": []`**.
2. Segment ve sahneleri `{{JOB_DIR}}/video_parts/part_01.json`, `part_02.json`, … dosyalarına yaz. Her dosya:
   `{"segments": [ {"tts":…,"text":…}, … 25 adet ], "scenes": [ … ]}`. Parça k (1'den) segment indeksleri **(k−1)×25 … k×25−1**.
   **Sahnelerdeki `cue` ve `before` indeksleri GLOBALdir** (ör. parça 3'te `"cue": "57:fed"`, `{"t":"Chapter","before": 50}`).
   Her parça kendi segmentlerinin sahnelerini içerir; `Intro` sahnesi yalnız part_01'in ilk sahnesi. Parçalar sırayla birleştirilir,
   sen birleştirme YAPMA. Dosyaları parça parça, art arda yaz (bir parçayı bitirmeden sonrakine geçme).
3. Bölüm kartları (`Chapter`) 6–8 adet; `chapters_hud` ile uyumlu olsun. Videonun hiçbir segmenti 50 kelimeyi aşmasın.

### Shorts (3 adet) — bu dev videodan AYRI değil, ona bağlı
- Üçü üç farklı açı (reels.json kuralları aynı). Her biri dev videonun BİR bölümünden bir "somut soru" açar; caption'ın ilk satırı o soruyu
  tekrar eder ve "tam analiz Cumartesi 17:00'daki {{MIN}} dakikalık haftalık videoda" diye yönlendirir. Son segment tam cümleyle biter.

### Kapak (`thumb.json`)
- Normal kuralla yaz; kapak "HAFTANIN TAMAMI" hissi versin (tek güçlü rakam + 2–4 kelime), videoda geçen rakamlar kullanılsın.
