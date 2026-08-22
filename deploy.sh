#!/usr/bin/env bash
# Soru bankasını yeniden üretip siteyi yayına gönderir.
set -e
cd "$(dirname "$0")"
python3 scripts/init_db.py
python3 scripts/build_web.py
if git diff --quiet && git diff --cached --quiet; then
  echo "Değişiklik yok, gönderilecek bir şey bulunamadı."
  exit 0
fi
git add -A
git commit -m "${1:-Soru bankası ve site güncellendi}"
git push
echo
echo "Yayında: https://datavirtualizer.github.io/ppl-soru-bankasi/"
echo "(GitHub Pages yeniden derlemesi ~1 dakika sürer)"
