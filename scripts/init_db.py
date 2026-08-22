#!/usr/bin/env python3
"""ATPL soru bankası veritabanını oluşturur ve JSON dosyalarını içe aktarır.

Kullanım:
    python3 scripts/init_db.py                       # data/ altındaki tüm JSON'ları yükler
    python3 scripts/init_db.py data/501_*.json       # sadece verilen dosyaları yükler

Betik idempotenttir: aynı dosya tekrar yüklenirse sorular güncellenir, çoğaltılmaz.
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "atpl.db"
DATA_DIR = ROOT / "data"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subjects (
    code TEXT PRIMARY KEY,              -- ör. '501'
    name TEXT NOT NULL                  -- ör. 'Havacılığa Giriş'
);

CREATE TABLE IF NOT EXISTS sections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_code TEXT NOT NULL REFERENCES subjects(code) ON DELETE CASCADE,
    code         TEXT NOT NULL,         -- ör. '01-01'
    name         TEXT NOT NULL,
    UNIQUE (subject_code, code)
);

CREATE TABLE IF NOT EXISTS questions (
    id           INTEGER PRIMARY KEY,   -- kaynaktaki soru ID'si (ATPL TV)
    subject_code TEXT NOT NULL REFERENCES subjects(code) ON DELETE CASCADE,
    section_id   INTEGER REFERENCES sections(id) ON DELETE SET NULL,
    text         TEXT NOT NULL,
    explanation  TEXT,                  -- sonradan not eklemek için
    source       TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS options (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    ord         INTEGER NOT NULL,       -- 1..5
    label       TEXT NOT NULL,          -- A, B, C, D, E
    text        TEXT NOT NULL,
    is_correct  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (question_id, ord)
);

CREATE INDEX IF NOT EXISTS idx_questions_subject ON questions(subject_code);
CREATE INDEX IF NOT EXISTS idx_questions_section ON questions(section_id);
CREATE INDEX IF NOT EXISTS idx_options_question  ON options(question_id);
CREATE INDEX IF NOT EXISTS idx_options_correct   ON options(question_id, is_correct);

-- Soru + doğru cevabı tek satırda veren görünüm.
-- Kaynak şıkları doğru cevap başta veriyor: doğru cevap her zaman A.
DROP VIEW IF EXISTS v_sorular;
CREATE VIEW v_sorular AS
SELECT q.id                        AS soru_id,
       q.subject_code              AS ders,
       s.code                      AS bolum,
       s.name                      AS bolum_adi,
       q.text                      AS soru,
       o.label                     AS dogru_sik,
       o.text                      AS dogru_cevap
FROM questions q
LEFT JOIN sections s ON s.id = q.section_id
LEFT JOIN options  o ON o.question_id = q.id AND o.is_correct = 1;

-- Şıkları kaynak sırasıyla, tek tek satır olarak veren görünüm
DROP VIEW IF EXISTS v_quiz;
CREATE VIEW v_quiz AS
SELECT q.id                        AS soru_id,
       q.subject_code              AS ders,
       s.code                      AS bolum,
       q.text                      AS soru,
       o.label                     AS sik,
       o.text                      AS sik_metni,
       o.is_correct                AS dogru_mu
FROM questions q
LEFT JOIN sections s ON s.id = q.section_id
JOIN options o ON o.question_id = q.id
ORDER BY q.id, o.ord;
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS questions_fts
USING fts5(text, content='questions', content_rowid='id', tokenize='unicode61');
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        conn.executescript(FTS_SCHEMA)
    except sqlite3.OperationalError:
        print("uyarı: FTS5 mevcut değil, tam metin arama tablosu atlandı")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Var olan veritabanına sonradan eklenen sütunlar."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(questions)")}
    if "origin" not in cols:
        # 'banka' = gerçek sınav sorusu, 'uretilmis' = ders notundan üretilmiş
        conn.execute("ALTER TABLE questions ADD COLUMN origin TEXT NOT NULL DEFAULT 'banka'")
    if "needs_figure" not in cols:
        # soru bir şekle/diyagrama atıf yapıyor; görsel olmadan cevaplanamaz
        conn.execute("ALTER TABLE questions ADD COLUMN needs_figure INTEGER NOT NULL DEFAULT 0")
    if "dup_of" not in cols:
        # aynı sorunun kopyasıysa kanonik sorunun id'si
        conn.execute("ALTER TABLE questions ADD COLUMN dup_of INTEGER")
    if "flagged" not in cols:
        # kaynakta "Attention!" işaretli sorular: cevabı tartışmalı olabilir
        conn.execute("ALTER TABLE questions ADD COLUMN flagged INTEGER NOT NULL DEFAULT 0")

    conn.commit()



def apply_duplicates(conn: sqlite3.Connection) -> int:
    """data/_tekrarlar.json'daki grupları uygular: gruptaki ilk id kanonik sayılır."""
    path = DATA_DIR / "_tekrarlar.json"
    conn.execute("UPDATE questions SET dup_of = NULL")
    if not path.exists():
        return 0
    groups = json.loads(path.read_text(encoding="utf-8"))["gruplar"]
    n = 0
    for g in groups:
        ids = g["ids"]
        canon = ids[0]
        for other in ids[1:]:
            cur = conn.execute(
                "UPDATE questions SET dup_of = ? WHERE id = ? AND dup_of IS NULL", (canon, other))
            n += cur.rowcount
    conn.commit()
    return n


def import_file(conn: sqlite3.Connection, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))

    subject_code = data["subject_code"]
    conn.execute(
        "INSERT INTO subjects(code, name) VALUES (?, ?) "
        "ON CONFLICT(code) DO UPDATE SET name = excluded.name",
        (subject_code, data["subject_name"]),
    )

    # Bölümler: ya tek bölüm (section_code/section_name) ya da {kod: ad} sözlüğü.
    sections = dict(data.get("sections", {}))
    if data.get("section_code"):
        sections[data["section_code"]] = data.get("section_name", "")

    section_ids: dict[str, int] = {}
    for code, name in sections.items():
        conn.execute(
            "INSERT INTO sections(subject_code, code, name) VALUES (?, ?, ?) "
            "ON CONFLICT(subject_code, code) DO UPDATE SET name = excluded.name",
            (subject_code, code, name),
        )
        section_ids[code] = conn.execute(
            "SELECT id FROM sections WHERE subject_code = ? AND code = ?",
            (subject_code, code),
        ).fetchone()[0]

    default_section = data.get("section_code")
    source = data.get("source")
    origin = data.get("origin", "banka")
    labels = "ABCDE"

    for q in data["questions"]:
        code = q.get("section", default_section)
        if code and code not in section_ids:
            sys.exit(f"hata: soru {q['id']} tanımsız bölüme işaret ediyor: {code}")

        conn.execute(
            "INSERT INTO questions(id, subject_code, section_id, text, source, flagged, origin, needs_figure) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET subject_code = excluded.subject_code, "
            "section_id = excluded.section_id, text = excluded.text, "
            "source = excluded.source, flagged = excluded.flagged, origin = excluded.origin, "
            "needs_figure = excluded.needs_figure",
            (q["id"], subject_code, section_ids.get(code), q["text"], source,
             1 if q.get("flagged") else 0, q.get("origin", origin),
             1 if q.get("needs_figure") else 0),
        )
        # Şıklar her içe aktarımda yeniden yazılır (sıra/metin düzeltmeleri için)
        conn.execute("DELETE FROM options WHERE question_id = ?", (q["id"],))
        correct_index = q.get("correct_index", 0)  # kaynak formatında doğru şık ilk sırada
        for i, opt in enumerate(q["options"]):
            conn.execute(
                "INSERT INTO options(question_id, ord, label, text, is_correct) VALUES (?, ?, ?, ?, ?)",
                (q["id"], i + 1, labels[i], opt, 1 if i == correct_index else 0),
            )

    conn.commit()
    return len(data["questions"])


def rebuild_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO questions_fts(questions_fts) VALUES ('rebuild')")
        conn.commit()
    except sqlite3.OperationalError:
        pass


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(
        f for f in DATA_DIR.glob("*.json") if not f.name.startswith("_"))
    if not paths:
        sys.exit(f"hata: {DATA_DIR} içinde JSON bulunamadı")

    conn = connect()
    total = 0
    for path in paths:
        n = import_file(conn, path)
        total += n
        print(f"{path.name}: {n} soru içe aktarıldı")

    dups = apply_duplicates(conn)
    rebuild_fts(conn)

    q = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    o = conn.execute("SELECT COUNT(*) FROM options").fetchone()[0]
    uret = conn.execute("SELECT COUNT(*) FROM questions WHERE origin = 'uretilmis'").fetchone()[0]
    missing = conn.execute(
        "SELECT COUNT(*) FROM questions q "
        "WHERE NOT EXISTS (SELECT 1 FROM options o WHERE o.question_id = q.id AND o.is_correct = 1)"
    ).fetchone()[0]
    conn.close()

    print(f"\n{DB_PATH}: toplam {q} soru, {o} şık")
    print(f"  {dups} tekrar işaretlendi → {q - dups} benzersiz soru")
    print(f"  {uret} soru ders notundan üretilmiş")
    if missing:
        print(f"UYARI: {missing} sorunun doğru cevabı işaretlenmemiş")


if __name__ == "__main__":
    main()
