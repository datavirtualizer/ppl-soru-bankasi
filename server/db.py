"""Veri katmanı.

İki veritabanı kullanılır:
  atpl.db        — soru bankası (salt okunur, scripts/init_db.py üretir)
  server/app.db  — kullanıcılar, oturumlar, cevap geçmişi (bu dosya yönetir)

Soru bankası ATTACH ile bağlanır, böylece tek sorguda birleştirilebilir.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK_DB = Path(os.environ.get("ATPL_BANK_DB", ROOT / "atpl.db"))
APP_DB = Path(os.environ.get("ATPL_APP_DB", ROOT / "server" / "app.db"))

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Misafir hesabında email ve pw_hash boştur; kullanıcı sonradan hesap
-- oluşturursa aynı satır güncellenir ve tüm geçmiş korunur.
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT UNIQUE COLLATE NOCASE,
    name       TEXT NOT NULL,
    pw_hash    TEXT,                   -- pbkdf2$<iter>$<salt_b64>$<hash_b64>
    is_guest   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen  TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- Bir çalışma turu
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode       TEXT NOT NULL,          -- 'calisma' | 'sinav'
    scope      TEXT NOT NULL,          -- insan okunur kapsam özeti
    qids       TEXT NOT NULL,          -- virgülle ayrılmış soru id sırası
    seed       INTEGER NOT NULL,       -- şık karıştırma tohumu
    started_at TEXT NOT NULL,
    ended_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id, started_at DESC);

-- Her cevap bir satır; geçmiş asla silinmez
CREATE TABLE IF NOT EXISTS attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    run_id      INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    question_id INTEGER NOT NULL,
    chosen_ord  INTEGER NOT NULL,      -- 1..5 (bankadaki gerçek sıra)
    correct     INTEGER NOT NULL,
    ms          INTEGER,               -- soruda geçen süre
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_att_user      ON attempts(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_att_user_q    ON attempts(user_id, question_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_att_run_q ON attempts(run_id, question_id);

-- Soru başına özet: "yanlış defteri" ve istatistik bunun üzerinden çalışır
CREATE TABLE IF NOT EXISTS mastery (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id  INTEGER NOT NULL,
    seen_n       INTEGER NOT NULL DEFAULT 0,
    wrong_n      INTEGER NOT NULL DEFAULT 0,
    right_streak INTEGER NOT NULL DEFAULT 0,
    last_at      TEXT,
    PRIMARY KEY (user_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_mastery_open ON mastery(user_id, wrong_n, right_streak);
"""

# Yanlış defterinden çıkmak için gereken üst üste doğru sayısı
MASTER_STREAK = 2


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(APP_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("ATTACH DATABASE ? AS bank", (str(BANK_DB),))
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    """Eski şemadan misafir destekli şemaya geçiş.

    SQLite NOT NULL kısıtını doğrudan kaldıramaz; tablo yeniden kurulur.
    Veri kaybı olmaz.
    """
    cols = {r[1]: r for r in conn.execute("PRAGMA table_info(users)")}
    if not cols:
        return
    email_notnull = bool(cols.get("email", (0, "", "", 0))[3])
    if "is_guest" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_guest INTEGER NOT NULL DEFAULT 0")
    if email_notnull:
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE users_new (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT UNIQUE COLLATE NOCASE,
                name       TEXT NOT NULL,
                pw_hash    TEXT,
                is_guest   INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_seen  TEXT
            );
            INSERT INTO users_new(id, email, name, pw_hash, is_guest, created_at, last_seen)
                SELECT id, email, name, pw_hash, 0, created_at, last_seen FROM users;
            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;
            PRAGMA foreign_keys = ON;
        """)
    conn.commit()


def sweep_guests(conn: sqlite3.Connection, days: int = 14) -> int:
    """Hiç soru çözmemiş eski misafir hesaplarını siler (bot/kazara ziyaretler)."""
    cur = conn.execute(
        "DELETE FROM users WHERE is_guest = 1 AND created_at < datetime('now', ?) "
        "AND id NOT IN (SELECT DISTINCT user_id FROM attempts)", (f"-{days} days",))
    return cur.rowcount


def init() -> None:
    APP_DB.parent.mkdir(parents=True, exist_ok=True)
    if not BANK_DB.exists():
        raise SystemExit(
            f"Soru bankası bulunamadı: {BANK_DB}\n"
            "Önce `python3 scripts/init_db.py` çalıştır."
        )
    conn = sqlite3.connect(APP_DB)
    conn.executescript(SCHEMA)
    conn.commit()
    migrate(conn)
    conn.close()


# ── Soru bankası okuma ────────────────────────────────────────────────

def subjects(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.code, s.name,
                  (SELECT COUNT(*) FROM bank.questions q
                    WHERE q.subject_code = s.code AND q.dup_of IS NULL) AS n
             FROM bank.subjects s ORDER BY s.code"""
    ).fetchall()


def sections(conn: sqlite3.Connection, subject: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT sec.code, sec.name,
                  (SELECT COUNT(*) FROM bank.questions q
                    WHERE q.section_id = sec.id AND q.dup_of IS NULL) AS n
             FROM bank.sections sec WHERE sec.subject_code = ? ORDER BY sec.code""",
        (subject,),
    ).fetchall()


def pick_questions(conn, user_id: int, *, subject: str, section: str,
                   hide_dups: bool, show_gen: bool, only_wrong: bool,
                   limit: int) -> list[int]:
    """Kapsama uyan soru id'lerini rastgele sırada döndürür."""
    sql = ["SELECT q.id FROM bank.questions q"]
    args: list = []
    if only_wrong:
        sql.append(
            "JOIN mastery m ON m.question_id = q.id AND m.user_id = ? "
            "AND m.wrong_n > 0 AND m.right_streak < ?"
        )
        args += [user_id, MASTER_STREAK]
    sql.append("WHERE 1=1")
    if hide_dups:
        sql.append("AND q.dup_of IS NULL")
    if not show_gen:
        sql.append("AND q.origin <> 'uretilmis'")
    if subject != "all":
        sql.append("AND q.subject_code = ?")
        args.append(subject)
    if section != "all":
        sql.append(
            "AND q.section_id = (SELECT id FROM bank.sections "
            "WHERE subject_code = q.subject_code AND code = ?)")
        args.append(section)
    sql.append("ORDER BY RANDOM() LIMIT ?")
    args.append(max(1, min(limit, 500)))
    return [r[0] for r in conn.execute(" ".join(sql), args)]


def question(conn: sqlite3.Connection, qid: int) -> dict | None:
    r = conn.execute(
        """SELECT q.id, q.text, q.subject_code, q.flagged, q.needs_figure,
                  q.origin, sub.name AS subject, sec.code AS sec_code, sec.name AS sec_name
             FROM bank.questions q
             JOIN bank.subjects sub ON sub.code = q.subject_code
             LEFT JOIN bank.sections sec ON sec.id = q.section_id
            WHERE q.id = ?""", (qid,)).fetchone()
    if not r:
        return None
    opts = conn.execute(
        "SELECT ord, text, is_correct FROM bank.options WHERE question_id = ? ORDER BY ord",
        (qid,)).fetchall()
    return {
        "id": r["id"], "text": r["text"], "subject_code": r["subject_code"],
        "subject": r["subject"], "sec_code": r["sec_code"] or "", "sec_name": r["sec_name"] or "",
        "flagged": bool(r["flagged"]), "needs_figure": bool(r["needs_figure"]),
        "generated": r["origin"] == "uretilmis",
        "options": [{"ord": o["ord"], "text": o["text"], "correct": bool(o["is_correct"])} for o in opts],
    }


# ── Cevap kaydı ───────────────────────────────────────────────────────

def record(conn, user_id: int, run_id: int | None, qid: int,
           chosen_ord: int, correct: bool, ms: int | None) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO attempts(user_id, run_id, question_id, chosen_ord, correct, ms, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (user_id, run_id, qid, chosen_ord, 1 if correct else 0, ms, now()))
    conn.execute(
        "INSERT INTO mastery(user_id, question_id, seen_n, wrong_n, right_streak, last_at) "
        "VALUES (?,?,1,?,?,?) "
        "ON CONFLICT(user_id, question_id) DO UPDATE SET "
        "  seen_n = seen_n + 1, "
        "  wrong_n = wrong_n + ?, "
        "  right_streak = CASE WHEN ? THEN right_streak + 1 ELSE 0 END, "
        "  last_at = ?",
        (user_id, qid, 0 if correct else 1, 1 if correct else 0, now(),
         0 if correct else 1, 1 if correct else 0, now()))


def wrong_book_size(conn, user_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM mastery WHERE user_id = ? AND wrong_n > 0 AND right_streak < ?",
        (user_id, MASTER_STREAK)).fetchone()[0]
