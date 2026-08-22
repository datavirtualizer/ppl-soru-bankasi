"""Uçtan uca akış testi:  kayıt → tur → cevap → yanlış defteri → istatistik.

    .venv/bin/python server/test_flow.py
"""
import os, sys, tempfile, pathlib
TMP = tempfile.mkdtemp()
os.environ["ATPL_APP_DB"] = str(pathlib.Path(TMP) / "test.db")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
import app as appmod, db

c = TestClient(appmod.app)
ok = lambda m: print("  ✓", m)

# ── kayıt ve oturum ──
r = c.get("/"); assert r.status_code == 200 and "Hesap oluştur" in r.text
ok("giriş yapmamış kullanıcı tanıtım sayfasını görüyor")

r = c.post("/kayit", data={"email": "pilot@example.com", "name": "Mustafa",
                           "password": "ucak12345", "password2": "ucak12345"},
           follow_redirects=False)
assert r.status_code == 303, r.text[:300]
assert "atpl_session" in r.cookies or c.cookies.get("atpl_session")
ok("kayıt oldu, oturum çerezi verildi")

r = c.post("/kayit", data={"email": "pilot@example.com", "name": "X",
                           "password": "ucak12345", "password2": "ucak12345"})
assert "zaten kayıtlı" in r.text
ok("aynı e-postayla ikinci kayıt reddediliyor")

r = c.get("/"); assert "Merhaba Mustafa" in r.text
ok("panel açılıyor")

# ── tur başlat ──
r = c.post("/tur", data={"subject": "080", "section": "all", "count": "6",
                         "mode": "calisma", "hide_dups": "on", "show_gen": "on"},
           follow_redirects=False)
assert r.status_code == 303, r.text[:300]
run_id = int(r.headers["location"].rsplit("/", 1)[1])
ok(f"tur açıldı (#{run_id})")

# ── SIZINTI KONTROLÜ: cevap istemciye gitmemeli ──
q = c.get(f"/api/tur/{run_id}/soru/0").json()
assert "correct" not in str(q.get("options")), "şıklarda doğruluk bilgisi sızmış!"
for key in ("is_correct", "correct_pos", "answer"):
    assert key not in q, f"yanıtta {key} sızmış!"
assert q["answered"] is None
ok("soru yükleniyor · doğru cevap sızmıyor")

# bankadaki gerçek doğru cevabı ayrıca okuyup karşılaştıralım
with db.db() as conn:
    real = db.question(conn, q["id"])
right_text = next(o["text"] for o in real["options"] if o["correct"])
right_pos = next(i for i, o in enumerate(q["options"]) if o["text"] == right_text)
wrong_pos = next(i for i in range(len(q["options"])) if i != right_pos)

# ── yanlış cevap ──
v = c.post(f"/api/tur/{run_id}/cevap", json={"qid": q["id"], "pos": wrong_pos, "ms": 3000}).json()
assert v["correct"] is False and v["correct_pos"] == right_pos
assert v["correct_text"] == right_text and v["wrong_book"] == 1
ok("yanlış cevap · doğru şık bildiriliyor · defter 1")

# aynı soruyu tekrar cevaplamak istatistiği bozmamalı
v2 = c.post(f"/api/tur/{run_id}/cevap", json={"qid": q["id"], "pos": right_pos}).json()
assert v2["repeat"] is True and v2["wrong_book"] == 1
ok("aynı soru iki kez sayılmıyor")

# ── kalan soruları doğru cevapla ──
for i in range(1, 6):
    qq = c.get(f"/api/tur/{run_id}/soru/{i}").json()
    with db.db() as conn:
        rr = db.question(conn, qq["id"])
    rt = next(o["text"] for o in rr["options"] if o["correct"])
    p = next(k for k, o in enumerate(qq["options"]) if o["text"] == rt)
    assert c.post(f"/api/tur/{run_id}/cevap", json={"qid": qq["id"], "pos": p}).json()["correct"]
ok("kalan 5 soru doğru cevaplandı")

c.post(f"/api/tur/{run_id}/bitir")
r = c.get(f"/sonuc/{run_id}")
assert "%83" in r.text, r.text[r.text.find("score"):][:200]
ok("sonuç sayfası %83 gösteriyor (6 soruda 5 doğru)")

# ── yanlış defteri turu ──
r = c.post("/tur", data={"only_wrong": "on", "count": "10", "mode": "calisma",
                         "hide_dups": "on", "show_gen": "on"}, follow_redirects=False)
wrun = int(r.headers["location"].rsplit("/", 1)[1])
wq = c.get(f"/api/tur/{wrun}/soru/0").json()
assert wq["total"] == 1 and wq["id"] == q["id"]
ok("yanlış defteri turu yalnızca o soruyu getiriyor")

# iki kez doğru cevaplayınca defterden düşmeli
with db.db() as conn:
    rr = db.question(conn, wq["id"])
rt = next(o["text"] for o in rr["options"] if o["correct"])
p = next(k for k, o in enumerate(wq["options"]) if o["text"] == rt)
v = c.post(f"/api/tur/{wrun}/cevap", json={"qid": wq["id"], "pos": p}).json()
assert v["wrong_book"] == 1, "bir doğru yetmemeli"
r = c.post("/tur", data={"only_wrong": "on", "count": "10", "mode": "calisma"},
           follow_redirects=False)
w2 = int(r.headers["location"].rsplit("/", 1)[1])
wq2 = c.get(f"/api/tur/{w2}/soru/0").json()
p2 = next(k for k, o in enumerate(wq2["options"]) if o["text"] == rt)
v = c.post(f"/api/tur/{w2}/cevap", json={"qid": wq2["id"], "pos": p2}).json()
assert v["wrong_book"] == 0, "ikinci doğrudan sonra defter boşalmalı"
ok("üst üste iki doğru → soru defterden düşüyor")

# ── istatistik ──
r = c.get("/istatistik")
assert "Genel başarı" in r.text and "En zayıf bölümlerin" in r.text
ok("istatistik sayfası açılıyor")

# ── yetki ──
c2 = TestClient(appmod.app)
assert c2.get(f"/api/tur/{run_id}/soru/0").status_code == 401
ok("oturumsuz istek 401")
r = c2.post("/giris", data={"email": "pilot@example.com", "password": "yanlis"},
            follow_redirects=False)
assert r.status_code == 200 and "hatalı" in r.text
ok("yanlış parola reddediliyor")
r = c2.post("/giris", data={"email": "pilot@example.com", "password": "ucak12345"},
            follow_redirects=False)
assert r.status_code == 303
ok("doğru parolayla giriş")

# başka kullanıcının turuna erişememeli
c3 = TestClient(appmod.app)
c3.post("/kayit", data={"email": "baska@example.com", "name": "B",
                        "password": "sifre12345", "password2": "sifre12345"})
assert c3.get(f"/api/tur/{run_id}/soru/0").status_code == 404
ok("başka kullanıcının turu görünmüyor")

# ── kaba kuvvet koruması ──
c4 = TestClient(appmod.app)
for i in range(8):
    c4.post("/giris", data={"email": "pilot@example.com", "password": "yanlis%d" % i})
r = c4.post("/giris", data={"email": "pilot@example.com", "password": "ucak12345"},
            follow_redirects=False)
assert r.status_code == 200 and "Çok fazla hatalı deneme" in r.text, "kilit devreye girmedi"
ok("8 hatalı denemeden sonra giriş kilitleniyor")
appmod._fails.clear()

r = c.post("/cikis", follow_redirects=False)
assert r.status_code == 303
assert c.get("/").text.count("Hesap oluştur") > 0
ok("çıkış oturumu sonlandırıyor")

print("\nTÜM TESTLER GEÇTİ")
