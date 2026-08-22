"""İstatistik sorguları. Hepsi attempts + mastery tabloları üzerinden çalışır."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import db


def summary(conn: sqlite3.Connection, uid: int) -> dict:
    r = conn.execute(
        """SELECT COUNT(*) AS n,
                  COALESCE(SUM(correct), 0) AS ok,
                  COUNT(DISTINCT question_id) AS uniq
             FROM attempts WHERE user_id = ?""", (uid,)).fetchone()
    runs = conn.execute(
        "SELECT COUNT(*) FROM runs WHERE user_id = ? AND ended_at IS NOT NULL",
        (uid,)).fetchone()[0]
    days = [r[0] for r in conn.execute(
        "SELECT DISTINCT substr(created_at,1,10) d FROM attempts WHERE user_id = ? "
        "ORDER BY d DESC LIMIT 400", (uid,))]
    streak, cur = 0, date.today()
    dayset = set(days)
    if str(cur) not in dayset and str(cur - timedelta(days=1)) in dayset:
        cur -= timedelta(days=1)          # bugün henüz çalışılmadıysa dünden say
    while str(cur) in dayset:
        streak += 1
        cur -= timedelta(days=1)
    bank = conn.execute(
        "SELECT COUNT(*) FROM bank.questions WHERE dup_of IS NULL").fetchone()[0]
    return {
        "n": r["n"], "ok": r["ok"], "wrong": r["n"] - r["ok"],
        "pct": round(r["ok"] / r["n"] * 100) if r["n"] else None,
        "uniq": r["uniq"], "bank": bank,
        "coverage": round(r["uniq"] / bank * 100) if bank else 0,
        "runs": runs, "streak": streak,
    }


def per_subject(conn: sqlite3.Connection, uid: int) -> list[dict]:
    rows = conn.execute(
        """SELECT s.code, s.name,
                  (SELECT COUNT(*) FROM bank.questions q
                    WHERE q.subject_code = s.code AND q.dup_of IS NULL) AS bank_n,
                  COUNT(a.id) AS n,
                  COALESCE(SUM(a.correct), 0) AS ok,
                  COUNT(DISTINCT a.question_id) AS uniq
             FROM bank.subjects s
             LEFT JOIN bank.questions q ON q.subject_code = s.code
             LEFT JOIN attempts a ON a.question_id = q.id AND a.user_id = ?
            GROUP BY s.code ORDER BY s.code""", (uid,)).fetchall()
    out = []
    for r in rows:
        out.append({
            "code": r["code"], "name": r["name"], "bank_n": r["bank_n"],
            "n": r["n"], "ok": r["ok"], "uniq": r["uniq"],
            "pct": round(r["ok"] / r["n"] * 100) if r["n"] else None,
            "coverage": round(r["uniq"] / r["bank_n"] * 100) if r["bank_n"] else 0,
        })
    return out


def weakest_sections(conn: sqlite3.Connection, uid: int, limit: int = 12) -> list[dict]:
    rows = conn.execute(
        """SELECT q.subject_code, sec.code, sec.name,
                  COUNT(*) AS n, SUM(a.correct) AS ok
             FROM attempts a
             JOIN bank.questions q  ON q.id = a.question_id
             JOIN bank.sections sec ON sec.id = q.section_id
            WHERE a.user_id = ?
            GROUP BY sec.id HAVING n >= 4
            ORDER BY (CAST(ok AS REAL) / n) ASC, n DESC LIMIT ?""",
        (uid, limit)).fetchall()
    return [{"subject": r["subject_code"], "code": r["code"], "name": r["name"],
             "n": r["n"], "ok": r["ok"], "pct": round(r["ok"] / r["n"] * 100)}
            for r in rows]


def daily(conn: sqlite3.Connection, uid: int, days: int = 30) -> list[dict]:
    first = date.today() - timedelta(days=days - 1)
    rows = {r[0]: (r[1], r[2]) for r in conn.execute(
        """SELECT substr(created_at,1,10) d, COUNT(*), COALESCE(SUM(correct),0)
             FROM attempts WHERE user_id = ? AND substr(created_at,1,10) >= ?
            GROUP BY d""", (uid, str(first)))}
    out = []
    for i in range(days):
        d = str(first + timedelta(days=i))
        n, ok = rows.get(d, (0, 0))
        out.append({"d": d, "n": n, "ok": ok,
                    "pct": round(ok / n * 100) if n else None})
    return out


def wrong_by_subject(conn: sqlite3.Connection, uid: int) -> list[dict]:
    rows = conn.execute(
        """SELECT q.subject_code AS code, s.name, COUNT(*) AS n
             FROM mastery m
             JOIN bank.questions q ON q.id = m.question_id
             JOIN bank.subjects s  ON s.code = q.subject_code
            WHERE m.user_id = ? AND m.wrong_n > 0 AND m.right_streak < ?
            GROUP BY q.subject_code ORDER BY n DESC""",
        (uid, db.MASTER_STREAK)).fetchall()
    return [dict(r) for r in rows]


def recent_runs(conn: sqlite3.Connection, uid: int, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """SELECT r.id, r.mode, r.scope, r.started_at, r.ended_at,
                  (SELECT COUNT(*) FROM attempts a WHERE a.run_id = r.id) AS n,
                  (SELECT COALESCE(SUM(a.correct),0) FROM attempts a WHERE a.run_id = r.id) AS ok,
                  (LENGTH(r.qids) - LENGTH(REPLACE(r.qids, ',', '')) + 1) AS total
             FROM runs r WHERE r.user_id = ?
            ORDER BY r.started_at DESC LIMIT ?""", (uid, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["pct"] = round(r["ok"] / r["n"] * 100) if r["n"] else None
        out.append(d)
    return out


def run_detail(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT a.question_id, a.chosen_ord, a.correct,
                  q.text, q.subject_code, sec.code AS sec_code,
                  (SELECT text FROM bank.options o
                    WHERE o.question_id = q.id AND o.is_correct = 1) AS right_text,
                  (SELECT text FROM bank.options o
                    WHERE o.question_id = q.id AND o.ord = a.chosen_ord) AS chosen_text
             FROM attempts a
             JOIN bank.questions q  ON q.id = a.question_id
             LEFT JOIN bank.sections sec ON sec.id = q.section_id
            WHERE a.run_id = ? ORDER BY a.id""", (run_id,)).fetchall()
    return [dict(r) for r in rows]
