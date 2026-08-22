"""Uçtan uca akış testi.

    .venv/bin/python server/test_flow.py

Ana senaryo girişsiz kullanım: siteye gir, çöz, yanlışların kaydolsun.
Hesap oluşturmak isteğe bağlı ve geçmişi taşımalı.
"""
import os, sys, tempfile, pathlib
TMP = tempfile.mkdtemp()
os.environ["ATPL_APP_DB"] = str(pathlib.Path(TMP) / "test.db")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
import app as appmod, auth, db

ok = lambda m: print("  ✓", m)


def solve(c, run_id, idx, correctly=True):
    """Turdaki bir soruyu bilerek doğru ya da yanlış cevaplar."""
    q = c.get(f"/api/tur/{run_id}/soru/{idx}").json()
    with db.db() as conn:
        real = db.question(conn, q["id"])
    right = next(o["text"] for o in real["options"] if o["correct"])
    pos = next(i for i, o in enumerate(q["options"]) if o["text"] == right)
    if not correctly:
        pos = next(i for i in range(len(q["options"])) if i != pos)
    return q, c.post(f"/api/tur/{run_id}/cevap",
                     json={"qid": q["id"], "pos": pos, "ms": 4000}).json()


# ── 1. Girişsiz kullanım ─────────────────────────────────────────────
c = TestClient(appmod.app)
r = c.get("/")
assert r.status_code == 200, r.status_code
assert "Hemen başla" in r.text, "hızlı başlangıç yok"
assert "giriş yapmana gerek yok" in r.text, "misafir şeridi yok"
assert c.cookies.get("atpl_session"), "misafire oturum çerezi verilmedi"
ok("siteye girer girmez panel açılıyor · giriş duvarı yok")

with db.db() as conn:
    u = conn.execute("SELECT * FROM users").fetchone()
assert u["is_guest"] == 1 and u["email"] is None
ok("arka planda misafir hesabı açıldı")

r = c.post("/tur", data={"subject": "080", "count": "5", "mode": "calisma",
                         "hide_dups": "on", "show_gen": "on"}, follow_redirects=False)
assert r.status_code == 303, r.text[:200]
run_id = int(r.headers["location"].rsplit("/", 1)[1])
ok("misafir tur açabiliyor")

# ── 2. Cevap sızmıyor ────────────────────────────────────────────────
q = c.get(f"/api/tur/{run_id}/soru/0").json()
for key in ("is_correct", "correct_pos", "answer", "correct"):
    assert key not in q, f"yanıtta {key} sızmış"
assert "correct" not in str(q["options"])
ok("doğru cevap istemciye gönderilmiyor")

# ── 3. Yanlış → deftere, iki doğru → defterden ───────────────────────
first_q, v = solve(c, run_id, 0, correctly=False)
assert v["correct"] is False and v["wrong_book"] == 1
assert v["correct_text"], "doğru cevap bildirilmedi"
ok("yanlış cevap · doğru cevap gösteriliyor · deftere yazıldı")

_, v = solve(c, run_id, 0, correctly=True)
assert v["repeat"] is True and v["wrong_book"] == 1
ok("aynı soru iki kez sayılmıyor")

for i in range(1, 5):
    solve(c, run_id, i, correctly=True)
c.post(f"/api/tur/{run_id}/bitir")
assert "%80" in c.get(f"/sonuc/{run_id}").text
ok("sonuç sayfası %80 (5 soruda 4 doğru)")

r = c.post("/tur", data={"only_wrong": "on", "count": "10", "mode": "calisma"},
           follow_redirects=False)
w1 = int(r.headers["location"].rsplit("/", 1)[1])
wq = c.get(f"/api/tur/{w1}/soru/0").json()
assert wq["total"] == 1 and wq["id"] == first_q["id"]
ok("yanlış defteri turu yalnızca o soruyu getiriyor")

_, v = solve(c, w1, 0, correctly=True)
assert v["wrong_book"] == 1, "tek doğru defterden düşürmemeli"
r = c.post("/tur", data={"only_wrong": "on", "count": "10"}, follow_redirects=False)
w2 = int(r.headers["location"].rsplit("/", 1)[1])
_, v = solve(c, w2, 0, correctly=True)
assert v["wrong_book"] == 0
ok("üst üste iki doğru → soru defterden düşüyor")

# ── 4. İlerleme cihazda kalıyor ──────────────────────────────────────
r = c.get("/")
assert "6 soru cevapladın" in r.text or "cevapladın" in r.text
r = c.get("/istatistik")
assert "Genel başarı" in r.text and "En zayıf" in r.text
ok("misafir istatistiklerini görüyor")

fresh = TestClient(appmod.app)          # başka tarayıcı = başka misafir
assert "Hemen başla" in fresh.get("/").text
with db.db() as conn:
    assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
ok("her tarayıcı kendi misafir hesabını alıyor")

# ── 5. Hesap oluşturmak isteğe bağlı, geçmişi taşıyor ────────────────
with db.db() as conn:
    before = conn.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?",
                          (u["id"],)).fetchone()[0]
r = c.get("/kayit")
assert f"{before}</span> cevabın" in r.text, "taşınacak cevap sayısı yazmıyor"
ok(f"kayıt sayfası {before} cevabın taşınacağını söylüyor")

r = c.post("/kayit", data={"email": "pilot@example.com", "name": "Deneme",
                           "password": "ucak12345", "password2": "ucak12345"},
           follow_redirects=False)
assert r.status_code == 303
with db.db() as conn:
    row = conn.execute("SELECT * FROM users WHERE email = 'pilot@example.com'").fetchone()
    after = conn.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?",
                         (row["id"],)).fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
assert row["id"] == u["id"], "yeni hesap açılmış, misafir yükseltilmemiş"
assert row["is_guest"] == 0 and after == before
assert total_users == 2, "fazladan hesap oluştu"
ok(f"misafir hesabı yükseltildi · {after} cevap korundu")

assert "Merhaba Deneme" in c.get("/").text
ok("artık adıyla karşılanıyor")

# ── 6. Çıkış siteyi kilitlemiyor ─────────────────────────────────────
r = c.post("/cikis", follow_redirects=False)
assert r.status_code == 303 and r.headers["location"] == "/"
r = c.get("/")
assert "Hemen başla" in r.text and "giriş yapmana gerek yok" in r.text
ok("çıkış sonrası site misafir olarak çalışmaya devam ediyor")

# ── 7. Kimlik ve yetki ───────────────────────────────────────────────
c2 = TestClient(appmod.app)
c2.get("/")                                     # misafir oturumu al
assert c2.get(f"/api/tur/{run_id}/soru/0").status_code == 404
ok("başka kullanıcının turu görünmüyor")

r = c2.post("/giris", data={"email": "pilot@example.com", "password": "yanlis"},
            follow_redirects=False)
assert r.status_code == 200 and "hatalı" in r.text
r = c2.post("/giris", data={"email": "pilot@example.com", "password": "ucak12345"},
            follow_redirects=False)
assert r.status_code == 303
assert "Merhaba Deneme" in c2.get("/").text
ok("e-posta ve parolayla giriş çalışıyor")

c3 = TestClient(appmod.app); c3.get("/")
for i in range(8):
    c3.post("/giris", data={"email": "pilot@example.com", "password": "yanlis%d" % i})
r = c3.post("/giris", data={"email": "pilot@example.com", "password": "ucak12345"},
            follow_redirects=False)
assert r.status_code == 200 and "Çok fazla hatalı deneme" in r.text
appmod._fails.clear()
ok("8 hatalı denemeden sonra giriş kilitleniyor")

r = c3.post("/kayit", data={"email": "pilot@example.com", "name": "X",
                            "password": "ucak12345", "password2": "ucak12345"})
assert "zaten kayıtlı" in r.text
ok("aynı e-postayla ikinci kayıt reddediliyor")

# ── 8. Boş misafirlerin temizliği ────────────────────────────────────
with db.db() as conn:
    conn.execute("INSERT INTO users(email,name,pw_hash,is_guest,created_at) "
                 "VALUES (NULL,'Misafir',NULL,1,datetime('now','-30 days'))")
    n = db.sweep_guests(conn)
assert n >= 1
ok("hiç çözmemiş eski misafir kayıtları temizleniyor")

print("\nTÜM TESTLER GEÇTİ")
