#!/bin/bash
# Serverdagi saytni GitHub'dagi oxirgi versiyaga yangilash.
#
#   bash ~/talim/yangilash.sh
#
# Avval bazadan nusxa oladi (~/zaxira/). O'quvchilar bazasi va .env o'zgarmaydi.
# Yangi versiya ishga tushmasa, eski kod qaytariladi.
set -Eeuo pipefail

XIZMAT=talim
TEKSHIR=http://127.0.0.1:5000/healthz

ishlayaptimi() {
  # Javob berishi va bir necha soniyadan keyin ham o'chib qolmagan bo'lishi kerak
  local i
  for i in $(seq 1 30); do
    if curl -sf -m 3 "$TEKSHIR" > /dev/null; then
      sleep 3
      systemctl is-active --quiet "$XIZMAT" && curl -sf -m 3 "$TEKSHIR" > /dev/null && return 0
    fi
    sleep 1
  done
  return 1
}

main() {
  cd "$(dirname "$(readlink -f "$0")")"
  exec 9> /tmp/talim-yangilash.lock
  flock -n 9 || { echo "Yangilash allaqachon ishlayapti."; exit 1; }

  local eski yangi z
  eski=$(git rev-parse HEAD)
  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "Serverdagi kod qo'lda o'zgartirilgan, yangilash to'xtatildi:"
    git status --short --untracked-files=no
    exit 1
  fi

  git fetch -q origin main
  yangi=$(git rev-parse origin/main)
  if [ "$eski" = "$yangi" ]; then
    echo "Yangilanish yo'q: ${eski:0:7} oxirgi versiya."
    exit 0
  fi
  if ! git merge-base --is-ancestor "$eski" "$yangi"; then
    echo "GitHub'dagi tarix o'zgargan, avtomatik yangilab bo'lmaydi. Hech narsa o'zgarmadi."
    exit 1
  fi
  echo "O'zgarishlar (${eski:0:7} -> ${yangi:0:7}):"
  git log --oneline "$eski..$yangi"

  echo "1/3 Bazadan nusxa..."
  z=~/zaxira/app-$(date +%Y%m%d-%H%M%S).db
  mkdir -p -m 700 ~/zaxira
  venv/bin/python - "$z" <<'PY'
import sqlite3
import sys

import common as c

src, dst = sqlite3.connect(c.DB_PATH), sqlite3.connect(sys.argv[1])
src.backup(dst)
ok = dst.execute("pragma integrity_check").fetchone()[0]
n = dst.execute("select count(*) from users").fetchone()[0]
print(f"   {sys.argv[1]} ({n} ta hisob, {ok})")
sys.exit(ok != "ok")
PY
  chmod 600 "$z"

  echo "2/3 O'rnatish..."
  git reset -q --hard "$yangi"
  if venv/bin/pip install -q --disable-pip-version-check -r requirements.txt \
    && venv/bin/python -m compileall -q ./*.py \
    && sudo systemctl restart "$XIZMAT" && ishlayaptimi; then
    echo "3/3 TAYYOR: ${yangi:0:7} ishlayapti."
    exit 0
  fi

  echo "XATO: yangi versiya ishga tushmadi. Eski kod qaytarilmoqda..."
  sudo journalctl -u "$XIZMAT" -n 15 --no-pager 2> /dev/null | tail -15 || true
  git reset -q --hard "$eski"
  venv/bin/pip install -q --disable-pip-version-check -r requirements.txt || true
  sudo systemctl reset-failed "$XIZMAT" 2> /dev/null || true
  sudo systemctl restart "$XIZMAT" || true
  if ishlayaptimi; then
    echo "Eski versiya (${eski:0:7}) yana ishlayapti."
  else
    echo "DIQQAT: eski versiya ham javob bermayapti. Tekshiring: sudo journalctl -u $XIZMAT -n 50"
  fi
  exit 1
}

# Skript o'zini ham yangilaydi: funksiya to'liq o'qilgani uchun bu xavfsiz
main "$@"
exit
