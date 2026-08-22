"""İstatistik ekranını dolu görmek için sahte geçmiş üretir.

    .venv/bin/python server/seed_demo.py demo@ornek.test

Var olan bir hesaba ~240 rastgele cevap yazar. Sadece deneme amaçlıdır —
gerçek hesabında çalıştırma, istatistiklerini bozar.
"""
import random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auth, db

email = sys.argv[1] if len(sys.argv) > 1 else "demo@ornek.test"
random.seed()
with db.db() as c:
    u = auth.find_user(c, email)
    if not u:
        sys.exit(f"{email} bulunamadı. Önce siteden kayıt ol.")
    uid = u["id"]
    qs = [r[0] for r in c.execute(
        "SELECT id FROM bank.questions WHERE dup_of IS NULL ORDER BY RANDOM() LIMIT 240")]
    now = datetime.now(timezone.utc)
    for qid in qs:
        ts = (now - timedelta(days=random.randint(0, 28),
                              hours=random.randint(0, 20))).isoformat(timespec="seconds")
        correct = random.random() < 0.71
        c.execute("INSERT INTO attempts(user_id,run_id,question_id,chosen_ord,correct,ms,created_at)"
                  " VALUES (?,NULL,?,?,?,?,?)",
                  (uid, qid, 1 if correct else 2, int(correct), random.randint(3000, 40000), ts))
        c.execute("INSERT INTO mastery(user_id,question_id,seen_n,wrong_n,right_streak,last_at)"
                  " VALUES (?,?,1,?,?,?) ON CONFLICT(user_id,question_id) DO UPDATE SET"
                  " seen_n=seen_n+1, wrong_n=wrong_n+?,"
                  " right_streak=CASE WHEN ? THEN right_streak+1 ELSE 0 END, last_at=?",
                  (uid, qid, 0 if correct else 1, 1 if correct else 0, ts,
                   0 if correct else 1, 1 if correct else 0, ts))
print(f"{email} hesabına {len(qs)} sahte cevap yazıldı.")
