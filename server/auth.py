"""Kullanıcı kaydı, parola saklama ve oturum çerezleri.

Parolalar PBKDF2-HMAC-SHA256 ile saklanır (standart kütüphane, ek bağımlılık yok).
Oturumlar sunucu tarafında tutulur; çerez yalnızca rastgele bir jeton taşır, böylece
çıkış yapıldığında oturum gerçekten geçersizleşir.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

import db

ITERATIONS = 600_000          # OWASP 2023 önerisi
COOKIE = "atpl_session"
SESSION_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# ── Parola ────────────────────────────────────────────────────────────

def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS)
    return "pbkdf2${}${}${}".format(
        ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(),
                                 base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "Parola en az 8 karakter olmalı."
    if pw.isdigit():
        return "Parola sadece rakamlardan oluşamaz."
    return None


def email_problem(email: str) -> str | None:
    if not EMAIL_RE.match(email or ""):
        return "Geçerli bir e-posta adresi gir."
    return None


# ── Kullanıcı ─────────────────────────────────────────────────────────

def create_user(conn: sqlite3.Connection, email: str, name: str, pw: str) -> int:
    cur = conn.execute(
        "INSERT INTO users(email, name, pw_hash, created_at) VALUES (?,?,?,?)",
        (email.strip(), name.strip() or email.split("@")[0], hash_password(pw), db.now()))
    return cur.lastrowid


def find_user(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE email = ?", (email.strip(),)).fetchone()


# ── Oturum ────────────────────────────────────────────────────────────

def start_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn.execute(
        "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, db.now(), exp.isoformat(timespec="seconds")))
    conn.execute("UPDATE users SET last_seen = ? WHERE id = ?", (db.now(), user_id))
    return token


def end_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def session_user(conn: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    r = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND s.expires_at > ?", (token, db.now())).fetchone()
    if r:
        conn.execute("UPDATE users SET last_seen = ? WHERE id = ?", (db.now(), r["id"]))
    return r


def purge_expired(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (db.now(),))
