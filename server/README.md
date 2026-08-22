# ATPL Soru Bankası — web sunucusu

Misafir öncelikli çalışma uygulaması: giriş yapmadan çözmeye başlanır, hesap açmak
isteğe bağlıdır. Soru bankasını (`atpl.db`) salt okunur kullanır,
kullanıcı verisini ayrı bir veritabanında (`server/app.db`) tutar — bankayı yeniden
üretmek (`scripts/init_db.py`) kullanıcı geçmişini etkilemez.

| Dosya | İşi |
|---|---|
| `app.py` | FastAPI rotaları |
| `db.py` | Şema, bağlantı, soru seçimi, cevap kaydı |
| `auth.py` | Parola saklama (PBKDF2), oturum jetonları |
| `stats.py` | İstatistik sorguları |
| `templates/` | Jinja2 şablonları |
| `static/` | CSS ve soru ekranının JavaScript'i |
| `test_flow.py` | Uçtan uca test (kayıt → tur → defter → istatistik) |
| `seed_demo.py` | İstatistik ekranını denemek için sahte geçmiş üretir |

## Yerelde çalıştırma

```bash
./run.sh
```

`http://127.0.0.1:8778` açılır. İlk çalıştırmada venv kurulur ve şema oluşturulur.

Testler:

```bash
.venv/bin/python server/test_flow.py
```

## Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `ATPL_BANK_DB` | `atpl.db` | Soru bankası yolu |
| `ATPL_APP_DB` | `server/app.db` | Kullanıcı veritabanı yolu |
| `ATPL_SECURE_COOKIE` | `0` | **HTTPS'te `1` yap** — çerez yalnızca şifreli bağlantıda gider |

## Sunucuya kurulum (Ubuntu/Debian)

```bash
sudo apt install python3-venv nginx
sudo useradd -r -m -d /srv/atpl atpl
sudo -u atpl git clone <depo> /srv/atpl/app
cd /srv/atpl/app
sudo -u atpl python3 -m venv .venv
sudo -u atpl .venv/bin/pip install -r requirements.txt
sudo -u atpl .venv/bin/python scripts/init_db.py     # soru bankasını üret
```

`/etc/systemd/system/atpl.service`:

```ini
[Unit]
Description=ATPL Soru Bankasi
After=network.target

[Service]
User=atpl
WorkingDirectory=/srv/atpl/app
Environment=ATPL_SECURE_COOKIE=1
ExecStart=/srv/atpl/app/.venv/bin/uvicorn app:app --app-dir server \
          --host 127.0.0.1 --port 8778 --workers 2 --proxy-headers \
          --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now atpl
```

nginx (`/etc/nginx/sites-available/atpl`):

```nginx
server {
    listen 80;
    server_name ornek.com;

    location /static/ {
        alias /srv/atpl/app/server/static/;
        expires 7d;
    }
    location / {
        proxy_pass http://127.0.0.1:8778;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/atpl /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d ornek.com          # HTTPS
```

**HTTPS kurduktan sonra `ATPL_SECURE_COOKIE=1` olduğundan emin ol.**

## Yedekleme

Değeri olan tek dosya `server/app.db` — kullanıcılar ve tüm cevap geçmişi orada.
`atpl.db` her zaman `scripts/init_db.py` ile yeniden üretilebilir.

```bash
sqlite3 /srv/atpl/app/server/app.db ".backup '/yedek/app-$(date +%F).db'"
```

Günlük yedek için crontab:

```
0 4 * * * sqlite3 /srv/atpl/app/server/app.db ".backup '/yedek/app-$(date +\%F).db'"
```

## Güvenlik notları

- **Doğru cevap istemciye hiç gönderilmez.** Şıklar sunucuda, tur tohumu + soru
  id'sinden türeyen sabit bir sırayla karıştırılır; tarayıcı yalnızca görünen sırayı
  bilir. Sayfa kaynağına bakarak cevabı görmek mümkün değil.
- Parolalar PBKDF2-HMAC-SHA256 ile 600.000 turda saklanır (standart kütüphane).
- Oturumlar sunucu tarafında; çıkış yapınca jeton gerçekten silinir.
- Girişte 15 dakikada 8 hatalı deneme sınırı var. Bu sayaç **süreç içinde** tutulur;
  `--workers 2` ile her worker kendi sayacını tutar. Sıkı bir sınır gerekiyorsa
  nginx `limit_req` ekle.
- Kullanıcılar birbirinin turunu göremez (her sorgu `user_id` ile kısıtlı).
- Giriş yapmayan her ziyaretçiye otomatik misafir hesabı açılır. Bot trafiği boş kayıt
  biriktirmesin diye, hiç soru çözmemiş 14 günden eski misafirler açılışta silinir
  (`db.sweep_guests`).

## Ölçek

SQLite tek sunucuda rahatlıkla yüzlerce eşzamanlı kullanıcıyı taşır (WAL modu açık).
Yazma yükü çok artarsa `db.py` içindeki bağlantı katmanını PostgreSQL'e taşımak
yeterli — sorguların tamamı standart SQL.
