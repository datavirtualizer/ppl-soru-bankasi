# ATPL Soru Bankası — çalışma kuralları

Mustafa'nın PPL/ATPL teori sınavlarına hazırlandığı soru bankası ve çalışma sitesi.
Sorular ATPL TV platformundaki sınav raporlarından elle çevrildi.

## Bozulmaması gereken kural

**Veritabanında her sorunun doğru cevabı A şıkkıdır.** Kaynak rapor şıkları doğru cevap
en başta olacak şekilde veriyor; bu sıra `data/*.json` içinde ve `atpl.db`'de korunur.
Şıkları veritabanında karıştırma. Karıştırma yalnızca sunum katmanında yapılır:

- `server/` — sunucuda, tur tohumu + soru id'sinden türeyen sabit sırayla
- `web/` artifact — tarayıcıda

## Yerleşim

```
data/*.json          soru kaynağı (elle çevrilmiş, tek doğruluk kaynağı)
data/_tekrarlar.json elle doğrulanmış tekrar grupları
scripts/init_db.py   data/ → atpl.db  (idempotent, ON CONFLICT ile günceller)
scripts/find_duplicates.py  benzer soru tarayıcı
atpl.db              üretilmiş soru bankası — elle düzenleme, JSON'u düzelt
server/              FastAPI çalışma sitesi (misafir öncelikli, giriş isteğe bağlı)
server/app.db        kullanıcı verisi — .gitignore'da, YEDEKLENMESİ GEREKEN TEK DOSYA
web/template.html    çalışma uygulamasının kaynağı (build_web.py veriyi gömer)
web/atpl-soru-bankasi.html  üretilmiş tek dosya — elle düzenleme, template'i düzelt
notes/               ders notları ve cheat sheet'ler
```

Soru değişikliği her zaman `data/*.json` üzerinden yapılır, sonra:

```bash
python3 scripts/init_db.py     # bankayı yeniden üret
python3 scripts/build_web.py   # artifact sürümünü tazele
```

`init_db.py` tabloları düşürmez; kullanıcı verisi ayrı dosyada olduğu için güvenlidir.

## Tekrar grupları

`data/_tekrarlar.json` içinde her grubun ilk id'si kanonik, diğerleri `dup_of` ile
ona bağlanır. **Cevabı farklı olan benzer sorular tekrar sayılmaz** — onlar sınavın
en değerli tuzakları (ör. 15613 METAR'da true north / 15666 ATIS'te magnetic north).
Yeni ders eklerken hem metin benzerliğini hem de "cevabı aynı ama metni farklı"
çiftleri tara; karar insana ait.

## Çalışma uygulaması (`web/`)

Asıl kullanılan sürüm bu: tek dosya, sunucusuz, `localStorage` tabanlı. Aralıklı tekrar
kutuları `BOX_MS`, takılma eşiği `LEECH`, yanlış defterinden çıkış `MASTER` sabitleriyle
ayarlanır. Kaynak `web/template.html`; `__DATA__` yer tutucusuna `build_web.py` veriyi
gömer. Değişiklikten sonra `python3 scripts/build_web.py` çalıştır.

Yedekleme metin kopyala/yapıştır üzerinden yapılır — artifact kum havuzunda dosya
indirme engelli. Dosya düğmeleri yalnızca `window.self === window.top` iken gösterilir.

## Sunucu (isteğe bağlı)

Çok cihazlı senkron isteyene FastAPI sürümü duruyor; günlük kullanım için gerekli değil.

```bash
./run.sh                                   # http://127.0.0.1:8778
.venv/bin/python server/test_flow.py       # uçtan uca test (20 kontrol)
```

Değişiklikten sonra testleri çalıştır. Kritik davranışlar:

- **Doğru cevap istemciye gönderilmez.** `/api/tur/{id}/soru/{idx}` yanıtında doğruluk
  bilgisi olmamalı; test bunu kontrol ediyor. Bu kuralı bozacak bir alan ekleme.
- **Giriş zorunlu değil.** Siteye giren herkes otomatik misafir hesabı alır
  (`ensure_user` middleware). Hesap oluşturmak misafiri *yükseltir*, yeni satır açmaz —
  geçmiş korunur.
- **Yanlış defteri:** yanlış → deftere girer, **üst üste iki doğru** → düşer
  (`db.MASTER_STREAK`).
- Kullanıcılar birbirinin turunu göremez; her sorgu `user_id` ile kısıtlıdır.

## Dil

Arayüz, kod yorumları ve commit mesajları Türkçe. Soru metinleri kaynaktaki dilinde
(çoğu İngilizce) bırakılır — sınavda öyle çıkıyor.
