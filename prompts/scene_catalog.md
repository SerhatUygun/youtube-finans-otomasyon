# Sahne şablonu kataloğu (Remotion `src/auto`)

Her sahne: `{"t": "<Şablon>", "cue": "<tetik>", "p": {...}}`. Sahne, `cue` anından bir sonraki sahnenin
`cue`'suna kadar ekranda kalır. **Sahneler segment sırasıyla ilerlemeli** (cue'lar artan).

## Tetik (cue) sözdizimi
- `"12"` → 12. segmentin başı (0 tabanlı, `segments` dizisindeki sıra)
- `"12:yüzde"` → 12. segmentte **ekran metninde** "yüzde" ile başlayan ilk kelime (büyük/küçük harf ve noktalama önemsiz)
- `"12:yüzde#2"` → ikinci eşleşme · `"12:3"` → 3. kelime · `"12:end"` → segment sonu · `"12:fed+10"` → +10 kare
- Rakamlı ekran metninde kelime `4.147` ise tetik `"27:4147"` olur (ekran metnine göre eşleşir, nokta/virgül yok sayılır).
  **Dikkat:** 1–2 haneli sayı (`"27:12"`) KELİME SIRASI olarak okunur; "12" rakamına kilitlemek için komşu kelimeyi kullan.
- Bir öğe tetiğini söylendiği kelimeye kilitle: rakam ekranda, seslendirmede söylendiği an belirmeli.

## Renk adları (hex YASAK)
`hero` (marka altını, kare başına EN FAZLA 1 öğe) · `gold` · `silver` · `btc` · `oil` · `accent` (mavi) · `up` (yeşil) · `down` (kırmızı) · `hawk` (şahin kırmızısı) · `text` · `dim`

## Ortak opsiyonel prop
`tag: {"n": "01", "title": "Fed tonu", "color": "hawk", "of": 4}` → sol üstte bölüm/sebep etiketi.

## Şablonlar

| t | Ne zaman | p alanları |
|---|---|---|
| `Intro` | Sadece ilk sahne (cue yok) | `subtitle`, `presenter` ("sunucu"), `presenterCue` ("0:ben") |
| `KineticTitle` | Güçlü tek cümle / geçiş | `text`, `highlight:[kelime]`, `hl` (renk), `kicker`, `sub`, `subCue`, `align` ("left"/"center"), `tint` |
| `Stamp` | Tek büyük rakam vuruşu (+25 bp, −%8 …) | `kicker`, `big`, `bigCue`, `unit`, `label`, `labelCue`, `sub`, `subCue`, `stamp` ("\n" ile 2 satır), `stampCue`, `watermark`, `color` |
| `DateQuestion` | Tarih + büyük soru | `month` ("EKİM"), `day`, `weekday`, `question` (soru işaretsiz), `highlight`, `qCue`, `note:{label,text}`, `noteCue` |
| `Gauge` | Olasılık (%) — 1 ya da 2 gösterge | `gauges:[{value,label,color,cue,dec}]`, `kicker`, `side:{title,rows:[{k,v,color,cue}],source}`, `footer`, `footerCue` |
| `Dots` | n içinden k (16/18 üye, 12-0 oy) | `n`, `lit`, `cols`, `litCue`, `kicker`, `caption`, `captionCue`, `color` |
| `ReasonCards` | 2–5 numaralı madde ("dört sebep") | `title`, `highlight`, `cardsCue`, `items:[{title,sub,color}]` |
| `Quote` | KAYNAKLI birebir alıntı | `who`, `initials`, `role`, `text`, `cue` (alıntı başlangıcı), `endCue`, `note`, `noteCue`, `tag`, `tagCue` |
| `StatCards` | 1–4 büyük sayı kartı | `title`, `items:[{label,title,value,from,dec,prefix,suffix,color,cue,note,badge,badgeCue,glow}]` |
| `Chart` | Canlı fiyat grafiği | `symbol` (series.json anahtarı, ör. XAUUSD, BRENT, GAUTRY), `since` ("2026-08-01") / `last` (gün), `title`, `prefix`, `suffix`, `dec`, `color`, `change:{text,color,cue}`, `hlines:[{value,label,color,cue,dashed}]`, `markers:[{at:"max"|"min"|"last"|"YYYY-MM-DD", label ("{v}" = değer), color, cue, above}]`, `bands:[{from,to,label,color,cue}]`, `badge:{text,sub,color,cue}`, `head` (false = uç etiketi yok), `showPrice` |
| `Normalized` | 2–3 varlığın % performans kıyası | `title`, `kicker`, `highlight`, `hl`, `since`, `lines:[{symbol,label,color}]`, `stat:{value,label,cue}`, `note` |
| `Compare` | Yatay çubuk kıyası (gerçekleşen vs beklenti) | `title`, `items:[{label,value,valueText,color,cue,dim}]`, `big:{text,sub,color,cue}`, `chips:[{value,label,color,cue}]`, `tag` |
| `Ladder` | Hedef fiyat merdiveni | `title`, `highlight`, `prefix`, `min`, `max`, `dec`, `items:[{label,value,color,cue,ref:true (referans=bugün)}]`, `note:{label,text}`, `noteCue` |
| `Scenario` | İki senaryo (düşüş / yükseliş) | `asset`, `left:{cond,sub,target,tsub,cue}`, `right:{...}`, `focus` ("left"/"right" soluklaşır), `focusCue` |
| `RangeBar` | Tahmin aralığı + bugün | `headline`, `title`, `min`, `max`, `prefix`, `dec`, `current`, `pins:[{value,label,cue}]` |
| `Vote` | Meclis/komite oylaması | `yes`, `no`, `kicker`, `title`, `stamp`, `stampCue`, `stampColor`, `sub` |
| `Bars` | Dikey çubuklar (fon girişleri vb.) | `kicker`, `title`, `big:{text,sub,cue}`, `items:[{label,value,valueText,color}]`, `color` |
| `Volatility` | Oynaklık / risk uyarısı | `chips:[{text,cue}]`, `headline`, `headlineCue`, `highlight`, `stamp`, `stampCue`, `peakCue` |
| `Timeline` | Takvim (2–4 olay) | `kicker`, `items:[{date,time,title,color,cue}]`, `footer`, `footerCue` |
| `CoinFlip` | Karşı görüşe geçiş | `front`, `back`, `headline`, `highlight`, `sub` |
| `Tug` | İki baskı arasında kalan özne | `left:{label,word}`, `right:{label,word}`, `center`, `headline`, `headlineCue` |
| `AssetCards` | 2–4 varlığın son fiyatı + değişim | `title`, `cardsCue`, `items:[{symbol,name,kind:"gold"|"silver"|"btc"|"oil"|"accent",glyph,dec,prefix,back (gün, BTC için 7)}]` |
| `Chapter` | Bölüm kartı — cue YOK, `before` ile | `before` (segment no; sahne o segmentten önceki boşluğa oturur), `kind`, `glyph`, `title`, `n`, `of` |
| `Disclaimer` | Yasal uyarı | `title`, `titleCue`, `sub`, `sub2`, `sub2Cue` |
| `Poll` | İzleyiciye soru | `question`, `options:[{text,cue}]`, `cta`, `ctaCue` |
| `Outro` | Son sahne | `likeCue`, `subCue`, `line`, `lineCue` |
| `Candles` | OHLC mum grafiği (endeks/hisse/emtia teknik görünüm) | `symbol`, `last` (gün, vars. 40) / `since`, `title`, `prefix`, `suffix`, `dec`, `change:{text,color,cue}`, `hlines:[{value,label,color,cue}]` (destek/direnç) |
| `Heatmap` | Sektör/varlık ısı haritası (alan=ağırlık, renk=% değişim) | `title`, `items:[{label,value (% değişim),weight,cue,dec}]` (4–12 öğe, doğrulanmış veri), `source` |
| `WorldMap` | Dünya haritası: ülke vurgusu + akış okları | `title`, `highlight:[{name (İngilizce ülke adı: "Turkey","Iran","United States of America"),color,cue}]`, `flows:[{from:[lon,lat],to:[lon,lat],label,color,cue}]`, `markers:[{at:[lon,lat],label,color,cue}]`, `focus:[ülke adları]` (yakınlaştır) |
| `YieldCurve` | Vade/verim eğrisi (bugün vs önce) | `title`, `items:[{m:"2Y",v,prev}]`, `nowLabel`, `prevLabel`, `color` |
| `Breaking` | SON DAKİKA bandı — günün kritik haberi | `kicker` ("SON DAKİKA"), `time` ("14:05"), `headline`, `highlight:[kelime]`, `hl`, `sub`, `subCue`, `source` |
| `Countdown` | Kritik veri/karara geri sayım | `kicker`, `title`, `days`, `hours`, `date` ("30 Eylül · 15:30 TSİ"), `color` |
| `Headline` | Gazete manşeti + fosforlu vurgu (KAYNAKLI haber) | `outlet`, `date`, `text` (manşet — brief'teki kaynaktan), `highlight` (vurgulanacak ifade), `hlCue`, `sub`, `note` |
| `Metal3D` | **3D** dönen altın/gümüş külçe ya da sikke + büyük fiyat (emtia açılış/vurgu) | `symbol` (XAUUSD/XAGUSD), `shape` ("bar"/"coin"), `metal` ("gold"/"silver"/"copper"), `kicker`, `value` (yoksa son fiyat), `changeText`, `sub`, `subCue` |
| `Globe3D` | **3D** dönen dünya küresi + şehir işaretleri + akış yayı (jeopolitik/küresel) | `kicker`, `title`, `focus:[lon,lat]` (öne dönecek nokta), `markers:[{at:[lon,lat],label,color,cue}]`, `flows:[{from,to,color,cue}]` |
| `Object3D` | **3D (18 Eki)** storyboard'un KAHRAMAN NESNESİ: kamera nesneye yolculuk eder, fiyatsız; yanında kısa başlık/büyük ifade | `object` (gold/silver/coin/barrel/bills/dollar/lira/btc), `kicker`, `big` (≤ 8 karakter: "%70", "KUR"), `title` |
| `Bars3D` | **3D (18 Eki)** 2–5 kalem 3D sütun kıyası (100 bin TL altında/dolarda/borsada; varlık getirileri) | `kicker`, `title`, `items:[{label,value,text,color,cue}]` (value sayı, text ekranda görünen) |
| `Stack3D` | **3D (18 Eki)** önce/sonra sikke kuleleri (Ocak 100 bin → bugün 78 bin; maaşın alım gücü) | `kicker`, `title`, `metal` (gold/silver/copper), `from:{label,value,text}`, `to:{label,value,text}`, `toCue` |
| `Scale3D` | **3D (18 Eki)** iki karşıt gücü tartan altın terazi (petrol ↑ vs faiz ↓ altını zıt çekiyor; risk vs getiri) | `kicker`, `title`, `left` {label, text?, color?}, `right` {label, text?, color?}, `tilt` (-1..1, eksi = sol ağır basar), `tiltCue?` (terazinin yattığı kelime), `verdict?` (kısa hüküm) |
| `HostStage` | **İMZA (19 Eki)** takım elbiseli 3D sunucu stüdyoda, yanında konunun nesnesi (açılışın 2. sahnesi, bölüm geçişi, kapanış) | `kicker`, `title`, `big?`, `object` (gold/silver/coin/barrel/bills/btc), `act` (hold = nesneyi elinde tutar · present · point · explain · wave = kapanışta el sallar), `actCue?` |

| `PumpBoard` | Akaryakıt totemi: bugün → yeni fiyat (tabela gibi döner, fark rozeti) | `title`, `place`, `items:[{name,from,to,dec}]`, `flipCue` (rakamların döndüğü an), `note`, `color` |
| `Waterfall` | Kalem kalem toplam (ÖTV + KDV = 12,47 TL; maliyet kalemleri) | `title`, `items:[{label,value,color,cue,dec}]`, `total` (yoksa toplam), `totalText`, `totalLabel`, `totalCue`, `totalColor`, `source` |

| `DominoChain` | Sebep → sonuç zinciri (kural → temerrüt → tasfiye → endeks düşüşü); taşlar sırayla devrilir | `title`, `items:[{title,sub,kicker,color,cue}]` (3–5 halka, son halka sonuç), `color` (sonuç rengi) |

Ek parametreler: `Scenario.tone: "consumer"` (fiyat artışı kötü → yukarı kart kırmızı), `Bars.big.color`, `Poll` 3–4 seçenekte otomatik dikey liste.

Sahne geçişi: her sahneye isteğe bağlı `"tr": "fade"|"push"|"rise"|"wipe"|"zoom"|"iris"` (yoksa otomatik dönüşümlü; Chapter=zoom).
**3D sahneler (three.js — 18 Eki kanal sahibi kararı: görsellerin omurgası):** Metal3D, Globe3D, Object3D, Bars3D, Stack3D, Scale3D, HostStage. **Sahne içi sunucu (19 Eki):** uzun videoda 3D sunucu Bars3D/Stack3D/Scale3D sahnelerinde nesnenin yanında durup işaret eder, Object3D'de nesneyi ELİNDE tutar, HostStage'de stüdyoda konuyu açar — bu sahnelerde köşe kutusu kendiliğinden gizlenir. Uzun videoda **8–12** 3D sahne (sahnelerin ~%25–30'u), her reel'de **en az 2**. Storyboard'daki kahraman nesne zinciri bunlarla kurulur. Aynı 3D şablon art arda gelmez; 2D veri sahneleri (Chart, Candles, Waterfall…) arada kalır.

## Kurallar
- Uzun video: 30–45 sahne; aynı şablon art arda iki kez olmasın (Chart hariç, farklı sembolle).
- Segmentler paragraf uzunluğunda (20–45 kelime) olduğu için sahne `cue`'ları çoğunlukla KELİME tetiği olur
  (`"12:petrol"`): her 6–12 saniyede bir yeni sahne, bir segmentte 1–3 sahne.
- Sayılar `series` / brief'teki doğrulanmış veriden gelmeli; grafikte olmayan sayı uydurma.
- Dikey Reels (1080×1920): 6–10 sahne, sadece `KineticTitle, Stamp, Gauge, StatCards, Chart, Compare, Scenario, Dots, AssetCards, Bars, Poll, Object3D, Bars3D, Stack3D, Metal3D, Outro`.
