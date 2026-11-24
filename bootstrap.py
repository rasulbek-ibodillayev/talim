"""Ishga tushishdagi tayyorgarlik: baza sxemasi, namunaviy ma'lumot, admin hisobi.

gunicorn bir nechta jarayonda ishlaydi va ular bir vaqtda ishga tushadi. Qulf bo'lmasa, sxema ikki marta
o'zgartirilishi yoki namunaviy ma'lumot ikki marta yozilishi mumkin edi.
"""
import os
import sqlite3
import time
from contextlib import contextmanager

from werkzeug.security import generate_password_hash

import common as c
import seed


@contextmanager
def lock():
    folder = os.path.dirname(c.DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(c.DB_PATH + ".lock", timeout=120, isolation_level=None)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        yield
        conn.execute("COMMIT")
    finally:
        conn.close()


def ensure_admins(conn):
    """ADMIN_PASSWORD berilgan bo'lsa, hali hisobi yo'q adminlar uchun hisob ochiladi.
    Mavjud hisobning paroliga tegilmaydi: admin uni profilda almashtirgan bo'lishi mumkin."""
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password or c.password_error(password, password):
        return
    for phone in sorted(c.ADMIN_PHONES):
        if not conn.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            conn.execute(
                "INSERT INTO users(phone, first_name, last_name, region, password_hash, created_at) "
                "VALUES (?, 'Admin', 'Admin', ?, ?, ?)",
                (phone, c.REGIONS[0], generate_password_hash(password), int(time.time())),
            )
    conn.commit()


def run():
    with lock():
        c.init_db()
        conn = c.get_db()
        try:
            seed.seed_if_empty(conn)
            seed.seed_exams_if_empty(conn)
            ensure_admins(conn)
        finally:
            conn.close()
