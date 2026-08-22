#!/usr/bin/env python3
"""Ders notunda geçen ama soru bankasında karşılığı olmayan konuları bulur.

    python3 scripts/topic_gap.py notes/501-ders-notlari.md 501
    python3 scripts/topic_gap.py notes/050-ders-notlari.md 050 --limit 40

Nasıl çalışır: nottaki başlıklar, kalın yazılmış terimler ve tablo satır
etiketleri "konu adayı" sayılır. Her aday, ilgili dersin sorularında (metin +
şıklar) aranır. Hiç geçmeyen ya da çok az geçen adaylar boşluk olarak listelenir.

Bu betik soru ÜRETMEZ — yalnızca nereye soru gerektiğini gösterir. Üretilen
sorular data/<ders>_uretilmis_sorular.json dosyasına `"origin": "uretilmis"`
ile eklenir ve uygulamada "üretilmiş" etiketiyle görünür.
"""

from __future__ import annotations

import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "atpl.db"

# Konu adayı sayılmayacak, her metinde geçen genel kelimeler
STOP = {
    "not", "önemli", "tanım", "örnek", "bölüm", "konu", "özet", "tablo", "liste",
    "sınav", "soru", "cevap", "kalın", "ilave", "pratik", "adet", "diğer", "genel",
    "temel", "kural", "kurallar", "madde", "ayrım", "ayrica", "ayrıca", "birim",
    "deger", "değer", "nicelik", "bilesen", "bileşen", "notlar", "ozet",
    "the", "and", "for", "with", "that", "this", "from", "into",
}


def worth_checking(c: str) -> bool:
    """Tek kelimelik genel sözcükleri ele; kısaltma ya da çok kelimeli olsun."""
    words = c.split()
    if len(words) > 1:
        return True
    w = words[0] if words else ""
    if len(w) >= 3 and w.isupper():      # DHMİ, AWOS, GNSS gibi kısaltmalar
        return True
    return len(w) >= 8                   # tek kelimeyse en az uzun olsun


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.casefold())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def candidates(md: str) -> list[str]:
    """Nottan konu adaylarını çıkarır: başlıklar, kalınlar, tablo ilk sütunu."""
    out: list[str] = []
    for line in md.splitlines():
        s = line.strip()
        if m := re.match(r"^#{2,4}\s+(.+)$", s):
            out.append(m.group(1))
        out += re.findall(r"\*\*([^*]{3,60})\*\*", s)
        if s.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", s):
            first = s.strip("|").split("|")[0].strip()
            if first:
                out.append(first)
    seen, uniq = set(), []
    for c in out:
        c = re.sub(r"[*`]", "", c).strip(" —–-·:")
        c = re.sub(r"^(Bölüm|Adım)\s*\d+\s*[—–-]?\s*", "", c)
        k = norm(c)
        if len(k) < 4 or k in STOP or k in seen or k.isdigit():
            continue
        if not worth_checking(c):
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    note = Path(sys.argv[1])
    subject = sys.argv[2]
    limit = 30
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if not note.exists():
        sys.exit(f"not bulunamadı: {note}")

    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT q.id, q.text, "
        "  (SELECT group_concat(o.text, ' ') FROM options o WHERE o.question_id = q.id) "
        "FROM questions q WHERE q.subject_code = ?", (subject,)).fetchall()
    conn.close()
    if not rows:
        sys.exit(f"{subject} dersinde soru yok")

    haystack = [norm(f"{r[1]} {r[2] or ''}") for r in rows]
    cands = candidates(note.read_text(encoding="utf-8"))

    scored = []
    for c in cands:
        key = norm(c)
        words = [w for w in key.split() if len(w) > 3]
        if not words:
            continue
        hits = sum(1 for h in haystack if all(w in h for w in words))
        scored.append((hits, c))
    scored.sort(key=lambda x: (x[0], len(x[1])))

    gaps = [(n, c) for n, c in scored if n == 0]
    thin = [(n, c) for n, c in scored if 1 <= n <= 2]

    print(f"{note.name} · {subject} dersi · {len(rows)} soru · {len(cands)} konu adayı\n")
    print(f"═══ Soru bankasında hiç geçmeyen: {len(gaps)} ═══")
    for _, c in gaps[:limit]:
        print(f"  ○ {c}")
    if len(gaps) > limit:
        print(f"  … {len(gaps) - limit} tane daha (--limit ile artır)")
    print(f"\n═══ Yalnızca 1-2 soruda geçen: {len(thin)} ═══")
    for n, c in thin[:limit]:
        print(f"  ◔ {c}  ({n} soru)")
    print("\nBunlar aday listesidir; hangisinin gerçekten soru gerektirdiğine insan karar verir.")


if __name__ == "__main__":
    main()
