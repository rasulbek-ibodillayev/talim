"""Saytni lokal ko'rib chiqish uchun demo rejim (.env shart emas).

Ishga tushirish:  python demo.py   ->  http://127.0.0.1:8000

Demo hisoblar (faqat shu lokal demo baza uchun, haqiqiy serverda ishlatmang):
  Admin:    telefon 90 123 45 67   parol: demo-pass-1
  O'quvchi: telefon 91 111 11 11   parol: demo-pass-1   mahfiy so'z: samarqand

Demo baza: data/demo.db (asosiy data/app.db ga tegmaydi). Toza boshlash uchun shu faylni o'chiring.
"""
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.update(
    DB_PATH=os.path.join(HERE, "data", "demo.db"),
    FLASK_SECRET="demo-only-" + "x" * 32,
    ADMIN_PHONES="+998901234567",
    ADMIN_PASSWORD="",
)
os.chdir(HERE)

from werkzeug.security import generate_password_hash  # noqa: E402

import common as c  # noqa: E402
import app as appmod  # noqa: E402

DEMO_USERS = (
    ("+998901234567", "Admin", "Adminov"),
    ("+998911111111", "Aziza", "Karimova"),
)

conn = c.get_db()
for phone, first, last in DEMO_USERS:
    if not conn.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
        conn.execute(
            "INSERT INTO users(phone, first_name, last_name, region, password_hash, created_at) VALUES (?,?,?,?,?,?)",
            (phone, first, last, c.REGIONS[0], generate_password_hash("demo-pass-1"), int(time.time())),
        )
# Parolni tiklashni sinash uchun demo o'quvchining mahfiy so'zi
conn.execute("UPDATE users SET secret_hash=? WHERE phone='+998911111111' AND secret_hash IS NULL",
             (generate_password_hash(c.normalize_secret("samarqand")),))
conn.commit()
conn.close()

if __name__ == "__main__":
    print("Demo sayt: http://127.0.0.1:8000  (hisoblar demo.py faylining boshida)")
    appmod.app.run(host="127.0.0.1", port=8000, debug=False)
