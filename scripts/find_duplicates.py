#!/usr/bin/env python3
"""Benzer soru çiftlerini tarar; data/_tekrarlar.json'u güncellemek için kullanılır.

    python3 scripts/find_duplicates.py [eşik]        # varsayılan eşik 0.60

Soru metni benzerliği eşiği geçen her çifti, doğru cevaplarının da benzerliğiyle
birlikte listeler. Karar insana aittir: cevabı FARKLI olan benzer sorular tekrar
değildir, sınav tuzağıdır — _tekrarlar.json'a eklenmemelidir.
"""

import re
import sqlite3
import sys
import unicodedata
from itertools import combinations
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "atpl.db"


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def main() -> None:
    thr = float(sys.argv[1]) if len(sys.argv) > 1 else 0.60
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        "SELECT q.id, q.subject_code sc, q.text, q.dup_of, "
        "(SELECT text FROM options o WHERE o.question_id = q.id AND o.is_correct = 1) ans "
        "FROM questions q"))
    conn.close()

    by_subj: dict[str, list] = {}
    for r in rows:
        by_subj.setdefault(r["sc"], []).append(
            (r["id"], r["text"], r["ans"], set(norm(r["text"]).split()),
             set(norm(r["ans"] or "").split()), r["dup_of"]))

    for sc, items in sorted(by_subj.items()):
        pairs = []
        for a, b in combinations(items, 2):
            s = jac(a[3], b[3])
            if s >= thr:
                pairs.append((s, jac(a[4], b[4]), a, b))
        pairs.sort(reverse=True, key=lambda p: p[0])
        print(f"═══ {sc} — {len(pairs)} çift (eşik %{int(thr*100)}) ═══")
        for s, asim, a, b in pairs:
            state = "işaretli" if (a[5] or b[5]) else ("TEKRAR?" if asim >= 0.75 else "farklı")
            print(f"[{state:8}] {a[0]}↔{b[0]}  soru %{int(s*100)} · cevap %{int(asim*100)}")
            print(f"   {a[1][:76]}")
            if norm(a[1]) != norm(b[1]):
                print(f"   {b[1][:76]}")
            print(f"   → {a[2][:56]}" + ("" if asim >= 0.75 else f"   ||   {b[2][:56]}"))
        print()


if __name__ == "__main__":
    main()
