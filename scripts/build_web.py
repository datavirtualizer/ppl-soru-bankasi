#!/usr/bin/env python3
"""atpl.db'yi web/template.html içine gömerek web/atpl-soru-bankasi.html üretir.

    python3 scripts/build_web.py

Sonra aynı dosya yolunu Artifact olarak yeniden yayımla — link değişmez.
Şıklar veritabanındaki sırayla (doğru cevap ilk) gömülür; karıştırma tarayıcıda,
çalışma anında yapılır.
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "atpl.db"
TPL = ROOT / "web" / "template.html"
OUT = ROOT / "web" / "atpl-soru-bankasi.html"


def export() -> dict:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    subjects, subj_idx, sec_idx = [], {}, {}
    for r in conn.execute("SELECT code, name FROM subjects ORDER BY code"):
        subj_idx[r["code"]] = len(subjects)
        subjects.append({"c": r["code"], "n": r["name"], "sec": []})

    for r in conn.execute("SELECT subject_code, code, name FROM sections ORDER BY subject_code, code"):
        s = subjects[subj_idx[r["subject_code"]]]
        sec_idx[(r["subject_code"], r["code"])] = len(s["sec"])
        s["sec"].append([r["code"], r["name"]])

    qs = []
    for r in conn.execute(
        "SELECT q.id, q.subject_code, s.code AS sec, q.text, q.flagged, "
        "       (q.dup_of IS NOT NULL) AS dup, (q.origin = 'uretilmis') AS gen, "
        "       q.needs_figure AS fig "
        "FROM questions q LEFT JOIN sections s ON s.id = q.section_id "
        "ORDER BY q.subject_code, s.code, q.id"
    ):
        opts = [o[0] for o in conn.execute(
            "SELECT text FROM options WHERE question_id = ? ORDER BY ord", (r["id"],))]
        qs.append([r["id"], subj_idx[r["subject_code"]],
                   sec_idx.get((r["subject_code"], r["sec"]), 0),
                   r["text"], opts, r["flagged"] or 0, r["dup"], r["gen"], r["fig"] or 0])
    conn.close()
    return {"s": subjects, "q": qs}


def main() -> None:
    if not TPL.exists():
        sys.exit(f"hata: {TPL} yok")

    data = export()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # </script> dizisi JSON içinde geçerse script bloğunu erken kapatır
    blob = blob.replace("</", "<\\/")

    tpl = TPL.read_text(encoding="utf-8")
    if "__DATA__" not in tpl:
        sys.exit("hata: şablonda __DATA__ yer tutucusu yok")

    OUT.write_text(tpl.replace("__DATA__", blob), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"{OUT}  ({len(data['q'])} soru, {len(data['s'])} ders, {kb:.1f} KB)")


if __name__ == "__main__":
    main()
