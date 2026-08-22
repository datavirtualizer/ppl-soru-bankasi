# ATPL Soru Bankası

SQLite tabanlı ATPL soru bankası. **2.514 soru, 10 ders** (226 tekrar işaretli → 2.288 benzersiz; 71'i ders notundan üretilmiş).

| Ders | Soru | Benzersiz | Bölüm |
|---|---|---|---|
| 050 \| Meteorology | 385 | 346 | 9 |
| 020 \| Aircraft General Knowledge | 347 | 325 | 24 |
| 501 \| Havacılığa Giriş | 252 | 251 | 3 |
| 040 \| Human Performance and Limitations | 251 | **210** | 9 |
| 060 \| Navigation | 245 | 231 | 14 |
| 080 \| Principles of Flight | 244 | **197** | 9 |
| 030 \| Flight Performance and Planning | 237 | 220 | 10 |
| 070 \| Operational Procedures | 193 | 183 | 7 |
| 090 \| Communications | 183 | **150** | 6 |
| 010 \| Air Law | 177 | 175 | 7 |

```
atpl.db                                 # veritabanı (script ile üretilir)
data/501_havaciliga_giris.json          # kaynak veri
data/070_operational_procedures.json
data/010_air_law.json
data/090_communications.json
data/020_aircraft_general_knowledge.json
data/030_flight_performance_and_planning.json
data/040_human_performance.json
data/050_meteorology.json
data/060_navigation.json
data/080_principles_of_flight.json
data/501_ders_notu_sorulari.json         # ders notu quiz soruları
data/070_ders_notu_sorulari.json         # 073 ders notu quiz soruları
data/501_uretilmis_sorular.json          # ders notundan üretilmiş (gerçek sınav sorusu değil)
data/070_uretilmis_sorular.json
data/_tekrarlar.json                     # elle doğrulanmış tekrar grupları
scripts/init_db.py                      # şema + içe aktarma
```

**Doğru cevap her soruda A şıkkıdır** — kaynak şıkları doğru cevap başta olacak
şekilde veriyor, bu sıra korunuyor.

## Kurulum / güncelleme

```bash
python3 scripts/init_db.py
```

Betik idempotenttir: JSON'u düzeltip tekrar çalıştırınca sorular güncellenir, çoğaltılmaz.

## Şema

| Tablo | Açıklama |
|---|---|
| `subjects` | Ders (`501` → Havacılığa Giriş) |
| `sections` | Ders bölümü (`01-01`) |
| `questions` | Soru; `id` = ATPL TV'deki soru ID'si, `explanation` kendi notların için boş, `flagged` kaynakta "Attention!" işaretli, `origin` = `banka`/`uretilmis`, `dup_of` = tekrarsa kanonik sorunun id'si, `needs_figure` = soru bir şekle atıf yapıyor |
| `options` | Şıklar; `ord` 1..5, `label` A..E, `is_correct` doğru cevap |
| `v_sorular` | Soru + doğru cevabı tek satırda veren görünüm |
| `questions_fts` | FTS5 tam metin arama |

`flagged = 1` olan 3 soru (14554, 15967, 16159) kaynakta "Attention!" ile işaretli —
kullanıcılar cevabı tartışmalı bulmuş. Bunlara körü körüne güvenme:

```bash
sqlite3 -box atpl.db "SELECT soru_id, soru, dogru_cevap FROM v_sorular WHERE soru_id IN (SELECT id FROM questions WHERE flagged=1);"
```

**Doğru cevap kuralı:** Kaynak rapor şıkları doğru cevap en başta olacak şekilde listeliyor. Bu yüzden her sorunun ilk şıkkı (`ord = 1`, `label = 'A'`) doğru kabul edildi. Bir soruda hata görürsen JSON'daki `options` sırasını düzelt ya da o soruya `"correct_index": 2` gibi bir alan ekleyip betiği tekrar çalıştır.

## Örnek sorgular

Bir sorunun tüm şıklarını görmek:

```bash
sqlite3 -box atpl.db "SELECT label, text, is_correct FROM options WHERE question_id=27142 ORDER BY ord;"
```

Rastgele 10 soruluk deneme (cevaplar gizli):

```bash
sqlite3 -box atpl.db "SELECT q.id, q.text, o.label, o.text FROM questions q JOIN options o ON o.question_id=q.id WHERE q.id IN (SELECT id FROM questions ORDER BY random() LIMIT 10) ORDER BY q.id, o.ord;"
```

Konu araması (tam metin):

```bash
sqlite3 -box atpl.db "SELECT q.id, q.text FROM questions_fts f JOIN questions q ON q.id=f.rowid WHERE questions_fts MATCH 'Annex';"
```

Doğru cevap listesi (cevap anahtarı):

```bash
sqlite3 -box atpl.db "SELECT soru_id, dogru_sik, dogru_cevap FROM v_sorular ORDER BY soru_id;"
```

## Çalışma notları

| Dosya | İçerik |
|---|---|
| [notes/501-ders-notlari.md](notes/501-ders-notlari.md) | 501 Havacılığa Giriş ders notları — 7 bölümün sınav odaklı özeti |
| [notes/501-ezber-listesi.md](notes/501-ezber-listesi.md) | 501 kısa ezber listesi — soru kelimesi → cevap |
| [notes/073-ders-notlari.md](notes/073-ders-notlari.md) | 073 Uçak Operasyonel Prosedürler ders notları — 070 bankasının ders karşılığı |
| [notes/070-cheat-sheet.md](notes/070-cheat-sheet.md) | 070 Operational Procedures özeti — sayılar, tanımlar, tuzaklar |
| [notes/annex-sifre.md](notes/annex-sifre.md) | ICAO Annex 1–19 rakam bağlama yöntemi |
| [notes/annex-kart-promptlari.md](notes/annex-kart-promptlari.md) | Annex kartlarının görüntü promptları |

## Annex ezber kartları

`cards/annex-01.png … annex-19.png` — her ICAO Annex için rakamın şeklini konuya
gömen görsel kart. `cards/00-kontak-sayfasi.png` hepsini tek sayfada gösterir.

Promptlar [notes/annex-kart-promptlari.md](notes/annex-kart-promptlari.md) içinde.
Yeniden üretmek için (yerel `grok` CLI'yi ve senin Grok kotanı kullanır):

```bash
python3 scripts/generate_cards.py            # eksik kartlar
python3 scripts/generate_cards.py --force 17 # tek kartı yeniden üret
```

Bir kart ~20 saniye. Rakam görünmüyorsa prompt'a "A giant numeral N ... clearly
readable" kalıbını ekleyip `--force` ile tekrar üret — ilk turda 1, 2, 6 ve 17'de
rakam çıkmamıştı, bu kalıpla düzeldi.

## Video kartlar

`videos/annex-01.mp4 … annex-19.mp4` — her kartın 6 saniyelik animasyonlu hali
(544×544, 24 fps, ~1–2 MB).

```bash
python3 scripts/generate_videos.py            # eksik videolar
python3 scripts/generate_videos.py --force 15 # tek videoyu yeniden üret
```

**Grok CLI'nin `image_to_video` aracını kullanma** — ZDR hesaplarında şu hatayı verir:

```
HTTP 400 invalid-argument:
"Zero Data Retention teams must provide output.upload_url for video generation."
```

Bunun yerine `~/.grok/bin/grok-image-to-video` script'i doğrudan
`https://api.x.ai/v1/videos/generations` API'sine gidiyor ve aynı hesapla sorunsuz
çalışıyor (yanıt `zdr=false` dönüyor). `scripts/generate_videos.py` bu script'i çağırır.
Video başına ~30 saniye.

### Tek dikey video (reel)

`videos/annex-reel.mp4` — 19 klibin tamamı sırayla, 1080×1920, 103 saniye, 31 MB.
Üstte "ANNEX N", altta Annex adı ve hatırlama çengeli, geçişlerde 0,6 sn crossfade.

```bash
python3 scripts/build_reel.py
```

Yazılar bilerek **birleştirmeden sonra** basılıyor. Önce her klibe yazıp sonra
crossfade yaparsan geçiş anında iki klibin yazısı üst üste binip hayalet gibi
görünüyor. Sonda basınca her yazı yalnızca kendi aralığında görünür
(`enable='between(t,…)'`), geçiş sırasında ikisi de gizlidir.

Türkçe karakterler için metin drawtext'e `textfile=` ile veriliyor; font
`Arial Bold.ttf` (macOS'ta ı, ğ, ş, ö, ü hepsini taşıyor).

### Hareket promptu yazarken

Kamera hareketi rakamı kırpıyor ya da bozuyor. İlk turda 1, 9, 14, 17'de rakam kadraj
dışında kaldı; 3, 5, 6, 11'de formu bozuldu; **15'te tabela "20" yazdı** — yani video
yanlış bilgi öğretir hale geldi. Çözüm, script'teki `HOLD` öneki:

> camera holds completely still, no zoom and no pan, *[rakam sabit kalacak cümlesi]*,
> only *[tek küçük hareket]*

Yeni video ürettiğinde **son kareyi mutlaka kontrol et** — rakam hâlâ doğru mu:

```bash
ffmpeg -ss 5.5 -i videos/annex-15.mp4 -frames:v 1 -y /tmp/son-kare.png
```

## Web sunucusu (kullanıcı girişli)

`server/` — çalışma sitesi. **Giriş zorunlu değil:** siteye girer girmez soru çözmeye
başlanır, ilerleme tarayıcıdaki oturuma bağlı olarak saklanır. Hesap oluşturmak isteğe
bağlıdır ve misafir geçmişini olduğu gibi taşır (başka cihazdan devam etmek için).
Kalıcı yanlış defteri, ders ve bölüm bazında istatistik, mobil uyumlu arayüz.

```bash
./run.sh          # http://127.0.0.1:8778
```

Kurulum, systemd/nginx örnekleri ve yedekleme: [server/README.md](server/README.md).
Uçtan uca test: `.venv/bin/python server/test_flow.py`.

Soru bankası (`atpl.db`) salt okunur kullanılır; kullanıcı verisi `server/app.db`
içinde durur, `scripts/init_db.py` çalıştırmak geçmişi etkilemez.

**Yanlış defteri kuralı:** yanlış cevaplanan soru deftere girer, **üst üste iki kez**
doğru cevaplanınca düşer. "Sadece yanlış defterim" seçeneğiyle yalnızca o sorulardan
tur açılabilir.

**Doğru cevap istemciye gönderilmez** — şıklar sunucuda karıştırılır, tarayıcı yalnızca
görünen sırayı bilir.

## Tek dosyalık web uygulaması (artifact)


`web/atpl-soru-bankasi.html` — 2.514 sorunun tamamını içeren tek dosyalık çalışma
uygulaması (veri HTML'e gömülü, dış bağımlılık yok). Artifact olarak yayımlandı:
https://claude.ai/code/artifact/5b35bb1b-5314-4199-a8a9-8f07589837ed

Ders/bölüm filtresi (bölüm adlarıyla), arama, çalışma ve sınav modu, açık/koyu tema,
klavye kısayolları (1–5 şık, Enter devam).

**Çalışma modu akışı:** doğru cevapta soru ~0,6 sn sonra kendiliğinden geçer; yanlışta
doğru cevap ekranda kalır, "Anladım, devam" ile ilerlenir.

**Yanlış defteri:** yanlış cevaplanan her soru `localStorage`'daki `atpl.wrong` kaydına
`{soru_id: kaç kez yanlış}` olarak yazılır ve tarayıcı kapansa da durur. "Defteri çöz"
sadece o soruları, ders/bölüm filtrelerini yok sayarak sorar. Doğru cevaplanınca sayaç
düşer, sıfırlanınca soru defterden silinir. "Defteri temizle" iki adımlıdır (yanlışlıkla
silinmesin diye ilk basış onay ister).

**Kapsam anahtarları:** "Tekrarları gizle" (varsayılan açık) ve "Üretilmiş sorular"
(varsayılan açık).

**Sorular da şıklar da her turda karıştırılır** — veritabanında doğru cevap hep A
şıkkıdır, uygulamada her soruda farklı harfe düşer.

Veri değişince yeniden üret:

```bash
python3 scripts/build_web.py
```

Sonra aynı dosya yolunu Artifact'e tekrar yayımla — link değişmez.


## Tekrar eden sorular

`data/_tekrarlar.json` elle doğrulanmış tekrar gruplarını tutar; her grupta ilk ID
kanonik, diğerleri `dup_of` ile ona bağlanır. Metin benzerliği ≥%60 olan tüm çiftler
tek tek incelendi. **Cevabı farklı olan benzer sorular bilerek tekrar sayılmadı** —
onlar sınavın en değerli tuzakları (ör. 15969/15970 gündüz-gece yakıtı,
15993/15998 yaralanma var/yok, 14343/14344 destination-location tabela renkleri).

Benzer çiftleri yeniden taramak için:

```bash
python3 scripts/find_duplicates.py
```

## Yeni ders eklemek

`data/` altına aynı formatta yeni bir JSON koy (`subject_code`, `subject_name`, `section_code`, `questions[]`) ve `python3 scripts/init_db.py` çalıştır.
