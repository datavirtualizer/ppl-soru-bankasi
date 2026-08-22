"""ATPL Soru Bankası — çok kullanıcılı çalışma sunucusu.

Çalıştırmak için:
    .venv/bin/uvicorn app:app --app-dir server --reload

Güvenlik notu: doğru cevap hiçbir zaman istemciye gönderilmez. Şıklar sunucuda,
tur tohumu + soru id'sinden türeyen sabit bir sırayla karıştırılır; tarayıcı yalnızca
görünen sırayı bilir, cevabı sunucu doğrular.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import auth
import db
import stats as stats_mod

HERE = Path(__file__).resolve().parent
SECURE_COOKIE = os.environ.get("ATPL_SECURE_COOKIE", "0") == "1"

db.init()   # şema idempotent; içe aktarmada kurulur, her sunucuda çalışır

app = FastAPI(title="ATPL Soru Bankası", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
tpl = Jinja2Templates(directory=str(HERE / "templates"))

with db.db() as _c:
    db.sweep_guests(_c)          # boş kalmış eski misafir kayıtlarını temizle


@app.middleware("http")
async def ensure_user(request: Request, call_next):
    """Girişsiz gelen herkese sessizce bir misafir hesabı açar.

    Böylece siteye girer girmez soru çözülebilir; ilerleme çerezdeki oturuma
    bağlı olarak bu cihazda saklanır. Kullanıcı isterse sonradan e-posta ve
    parola ekleyip aynı hesabı kalıcı hale getirir — geçmiş kaybolmaz.
    """
    if request.url.path.startswith("/static"):
        return await call_next(request)

    fresh = None
    with db.db() as conn:
        if not auth.session_user(conn, request.cookies.get(auth.COOKIE)):
            fresh = auth.start_session(conn, auth.create_guest(conn))
    if fresh:
        request.state.token = fresh

    response = await call_next(request)
    if fresh:
        response.set_cookie(auth.COOKIE, fresh, max_age=auth.SESSION_DAYS * 86400,
                            httponly=True, samesite="lax", secure=SECURE_COOKIE, path="/")
    return response


# ── yardımcılar ───────────────────────────────────────────────────────

def current_user(conn, request: Request):
    token = getattr(request.state, "token", None) or request.cookies.get(auth.COOKIE)
    return auth.session_user(conn, token)


def page(request: Request, name: str, **ctx):
    return tpl.TemplateResponse(request, name, ctx)


# ── Girişte kaba kuvvet koruması ────────────────────────────────────
# Tek süreçlik basit sayaç. Birden fazla worker ile çalıştırırsan her worker
# kendi sayacını tutar; sıkı bir sınır istiyorsan Redis'e taşı ya da nginx'in
# limit_req modülünü kullan.
FAIL_MAX, FAIL_WINDOW = 8, 900          # 15 dakikada 8 hatalı deneme
_fails: dict[str, list[float]] = defaultdict(list)


def _fail_key(request: Request, email: str) -> str:
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))
    return f"{ip}|{email.strip().lower()}"


def login_blocked(key: str) -> int:
    """Kalan kilit süresi (saniye); 0 ise engel yok."""
    now = time.time()
    hits = [t for t in _fails[key] if now - t < FAIL_WINDOW]
    _fails[key] = hits
    if len(hits) >= FAIL_MAX:
        return int(FAIL_WINDOW - (now - hits[0]))
    return 0


def note_fail(key: str) -> None:
    _fails[key].append(time.time())


def display_order(seed: int, qid: int, n: int) -> list[int]:
    """Şıkların görünen sırası: gerçek `ord` değerlerinin karıştırılmış listesi.

    Aynı tur + aynı soru için her zaman aynı sonucu verir, böylece sayfa
    yenilendiğinde şıklar yerinden oynamaz.
    """
    t = (seed * 2654435761 + qid * 40503) & 0xFFFFFFFF

    def nxt():
        nonlocal t
        t = (t ^ (t << 13)) & 0xFFFFFFFF
        t ^= t >> 17
        t = (t ^ (t << 5)) & 0xFFFFFFFF
        return t / 0x100000000

    ords = list(range(1, n + 1))
    for i in range(len(ords) - 1, 0, -1):
        j = int(nxt() * (i + 1))
        ords[i], ords[j] = ords[j], ords[i]
    return ords


# ── kimlik ────────────────────────────────────────────────────────────

@app.get("/kayit", response_class=HTMLResponse)
def register_form(request: Request):
    with db.db() as conn:
        user = current_user(conn, request)
        if user and not user["is_guest"]:
            return RedirectResponse("/", status_code=303)
        n = conn.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?",
                         (user["id"],)).fetchone()[0] if user else 0
    return page(request, "register.html", err=None, values={}, carry=n)


@app.post("/kayit")
def register(request: Request, email: str = Form(""), name: str = Form(""),
             password: str = Form(""), password2: str = Form("")):
    values = {"email": email, "name": name}
    err = auth.email_problem(email) or auth.password_problem(password)
    if not err and password != password2:
        err = "Parolalar birbirini tutmuyor."
    with db.db() as conn:
        user = current_user(conn, request)
        if not err and auth.find_user(conn, email):
            err = "Bu e-posta zaten kayıtlı. Giriş yapmayı dene."
        if err:
            carry = conn.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?",
                                 (user["id"],)).fetchone()[0] if user else 0
            return page(request, "register.html", err=err, values=values, carry=carry)
        if user and user["is_guest"]:
            auth.upgrade_guest(conn, user["id"], email, name, password)
            uid = user["id"]          # geçmiş olduğu gibi kalır
        else:
            uid = auth.create_user(conn, email, name, password)
        token = auth.start_session(conn, uid)
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400,
                 httponly=True, samesite="lax", secure=SECURE_COOKIE, path="/")
    return r


@app.get("/giris", response_class=HTMLResponse)
def login_form(request: Request, next: str = "/"):
    with db.db() as conn:
        user = current_user(conn, request)
        if user and not user["is_guest"]:
            return RedirectResponse("/", status_code=303)
    return page(request, "login.html", err=None, next=next, values={})


@app.post("/giris")
def login(request: Request, email: str = Form(""), password: str = Form(""),
          next: str = Form("/")):
    key = _fail_key(request, email)
    left = login_blocked(key)
    if left:
        return page(request, "login.html", next=next, values={"email": email},
                    err=f"Çok fazla hatalı deneme. {left // 60 + 1} dakika sonra tekrar dene.")
    with db.db() as conn:
        user = auth.find_user(conn, email)
        if not user or not auth.verify_password(password, user["pw_hash"]):
            note_fail(key)
            # Hangisinin yanlış olduğunu söyleme — hesap taramasını zorlaştırır
            return page(request, "login.html", err="E-posta veya parola hatalı.",
                        next=next, values={"email": email})
        _fails.pop(key, None)
        auth.purge_expired(conn)
        token = auth.start_session(conn, user["id"])
    r = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    r.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400,
                 httponly=True, samesite="lax", secure=SECURE_COOKIE, path="/")
    return r


@app.post("/cikis")
def logout(request: Request):
    with db.db() as conn:
        auth.end_session(conn, request.cookies.get(auth.COOKIE) or "")
    r = RedirectResponse("/", status_code=303)
    r.delete_cookie(auth.COOKIE, path="/")
    return r


# ── panel ─────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with db.db() as conn:
        user = current_user(conn, request)
        return page(request, "home.html", user=user,
                    subjects=db.subjects(conn),
                    summary=stats_mod.summary(conn, user["id"]),
                    wrong_n=db.wrong_book_size(conn, user["id"]),
                    runs=stats_mod.recent_runs(conn, user["id"], 8))


@app.get("/api/bolumler/{subject}")
def api_sections(request: Request, subject: str):
    with db.db() as conn:
        if not current_user(conn, request):
            return JSONResponse({"error": "yetki yok"}, status_code=401)
        if subject == "all":
            return {"sections": []}
        return {"sections": [{"code": s["code"], "name": s["name"], "n": s["n"]}
                             for s in db.sections(conn, subject)]}


# ── tur ───────────────────────────────────────────────────────────────

@app.post("/tur")
def start_run(request: Request, subject: str = Form("all"), section: str = Form("all"),
              count: int = Form(20), mode: str = Form("calisma"),
              hide_dups: str = Form(""), show_gen: str = Form(""),
              only_wrong: str = Form("")):
    with db.db() as conn:
        user = current_user(conn, request)
        if not user:
            return RedirectResponse("/", status_code=303)
        qids = db.pick_questions(
            conn, user["id"], subject=subject, section=section,
            hide_dups=hide_dups == "on", show_gen=show_gen == "on",
            only_wrong=only_wrong == "on", limit=count)
        if not qids:
            return RedirectResponse("/?bos=1", status_code=303)

        scope = []
        scope.append("Tüm dersler" if subject == "all" else subject)
        if section != "all":
            scope.append(section)
        if only_wrong == "on":
            scope.append("yanlış defteri")
        cur = conn.execute(
            "INSERT INTO runs(user_id, mode, scope, qids, seed, started_at) VALUES (?,?,?,?,?,?)",
            (user["id"], "sinav" if mode == "sinav" else "calisma", " · ".join(scope),
             ",".join(map(str, qids)), secrets.randbelow(2**31), db.now()))
        run_id = cur.lastrowid
    return RedirectResponse(f"/tur/{run_id}", status_code=303)


def _load_run(conn, user_id: int, run_id: int):
    r = conn.execute("SELECT * FROM runs WHERE id = ? AND user_id = ?",
                     (run_id, user_id)).fetchone()
    return r


@app.get("/tur/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: int):
    with db.db() as conn:
        user = current_user(conn, request)
        if not user:
            return RedirectResponse("/", status_code=303)
        run = _load_run(conn, user["id"], run_id)
        if not run:
            return RedirectResponse("/", status_code=303)
        qids = [int(x) for x in run["qids"].split(",")]
        answered = conn.execute(
            "SELECT COUNT(*) FROM attempts WHERE run_id = ?", (run_id,)).fetchone()[0]
        return page(request, "quiz.html", user=user, run=run,
                    total=len(qids), answered=answered)


@app.get("/api/tur/{run_id}/soru/{idx}")
def api_question(request: Request, run_id: int, idx: int):
    with db.db() as conn:
        user = current_user(conn, request)
        if not user:
            return JSONResponse({"error": "yetki yok"}, status_code=401)
        run = _load_run(conn, user["id"], run_id)
        if not run:
            return JSONResponse({"error": "tur yok"}, status_code=404)
        qids = [int(x) for x in run["qids"].split(",")]
        if idx < 0 or idx >= len(qids):
            return JSONResponse({"done": True, "total": len(qids)})
        q = db.question(conn, qids[idx])
        if not q:
            return JSONResponse({"error": "soru yok"}, status_code=404)

        order = display_order(run["seed"], q["id"], len(q["options"]))
        by_ord = {o["ord"]: o for o in q["options"]}
        # Doğru cevap bilgisi bilerek dışarıda bırakıldı
        opts = [{"pos": i, "text": by_ord[o]["text"]} for i, o in enumerate(order)]

        prev = conn.execute(
            "SELECT chosen_ord, correct FROM attempts WHERE run_id = ? AND question_id = ?",
            (run_id, q["id"])).fetchone()
        answered = None
        if prev:
            answered = {
                "pos": order.index(prev["chosen_ord"]),
                "correct": bool(prev["correct"]),
                "correct_pos": next(i for i, o in enumerate(order) if by_ord[o]["correct"]),
            }
        return {
            "idx": idx, "total": len(qids), "id": q["id"], "text": q["text"],
            "subject_code": q["subject_code"], "subject": q["subject"],
            "sec_code": q["sec_code"], "sec_name": q["sec_name"],
            "flagged": q["flagged"], "needs_figure": q["needs_figure"],
            "generated": q["generated"], "options": opts,
            "mode": run["mode"], "answered": answered,
        }


@app.post("/api/tur/{run_id}/cevap")
async def api_answer(request: Request, run_id: int):
    body = await request.json()
    with db.db() as conn:
        user = current_user(conn, request)
        if not user:
            return JSONResponse({"error": "yetki yok"}, status_code=401)
        run = _load_run(conn, user["id"], run_id)
        if not run or run["ended_at"]:
            return JSONResponse({"error": "tur kapalı"}, status_code=400)
        qid = int(body.get("qid", 0))
        pos = int(body.get("pos", -1))
        ms = body.get("ms")
        qids = [int(x) for x in run["qids"].split(",")]
        if qid not in qids:
            return JSONResponse({"error": "soru bu turda değil"}, status_code=400)

        q = db.question(conn, qid)
        order = display_order(run["seed"], qid, len(q["options"]))
        if pos < 0 or pos >= len(order):
            return JSONResponse({"error": "geçersiz şık"}, status_code=400)
        by_ord = {o["ord"]: o for o in q["options"]}
        chosen_ord = order[pos]
        correct = by_ord[chosen_ord]["correct"]
        correct_pos = next(i for i, o in enumerate(order) if by_ord[o]["correct"])

        already = conn.execute(
            "SELECT correct FROM attempts WHERE run_id = ? AND question_id = ?",
            (run_id, qid)).fetchone()
        if not already:
            db.record(conn, user["id"], run_id, qid, chosen_ord, correct,
                      int(ms) if isinstance(ms, (int, float)) else None)
        return {
            "correct": correct,
            "correct_pos": correct_pos,
            "correct_text": by_ord[order[correct_pos]]["text"],
            "wrong_book": db.wrong_book_size(conn, user["id"]),
            "repeat": bool(already),
        }


@app.post("/api/tur/{run_id}/bitir")
def api_finish(request: Request, run_id: int):
    with db.db() as conn:
        user = current_user(conn, request)
        if not user:
            return JSONResponse({"error": "yetki yok"}, status_code=401)
        conn.execute("UPDATE runs SET ended_at = ? WHERE id = ? AND user_id = ? AND ended_at IS NULL",
                     (db.now(), run_id, user["id"]))
    return {"ok": True}


@app.get("/sonuc/{run_id}", response_class=HTMLResponse)
def result(request: Request, run_id: int):
    with db.db() as conn:
        user = current_user(conn, request)
        if not user:
            return RedirectResponse("/", status_code=303)
        run = _load_run(conn, user["id"], run_id)
        if not run:
            return RedirectResponse("/", status_code=303)
        conn.execute("UPDATE runs SET ended_at = COALESCE(ended_at, ?) WHERE id = ?",
                     (db.now(), run_id))
        rows = stats_mod.run_detail(conn, run_id)
        ok = sum(1 for r in rows if r["correct"])
        return page(request, "result.html", user=user, run=run, rows=rows, ok=ok,
                    total=len(rows), wrong_n=db.wrong_book_size(conn, user["id"]))


# ── istatistik ────────────────────────────────────────────────────────

@app.get("/istatistik", response_class=HTMLResponse)
def stats_page(request: Request):
    with db.db() as conn:
        user = current_user(conn, request)
        if not user:
            return RedirectResponse("/", status_code=303)
        return page(request, "stats.html", user=user,
                    summary=stats_mod.summary(conn, user["id"]),
                    per_subject=stats_mod.per_subject(conn, user["id"]),
                    weakest=stats_mod.weakest_sections(conn, user["id"], 12),
                    daily=stats_mod.daily(conn, user["id"], 30),
                    wrong_n=db.wrong_book_size(conn, user["id"]),
                    wrong_by_subject=stats_mod.wrong_by_subject(conn, user["id"]))
