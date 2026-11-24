"""Testlar uchun umumiy asos: vaqtinchalik baza, foydalanuvchilar va kirish.

Ishga tushirish (talim papkasidan):  python -m unittest
"""
import atexit
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="talim-test-")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

ADMIN_PHONE = "+998900000001"
os.environ.update(
    DB_PATH=os.path.join(TMP, "test.db"),   # haqiqiy bazaga tegilmaydi
    FLASK_SECRET="test-only-" + "x" * 32,
    ADMIN_PHONES=ADMIN_PHONE,
    ADMIN_PASSWORD="",      # .env dagi admin test bazasiga tushmasin
)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common as c  # noqa: E402
from app import app  # noqa: E402
from web_utils import password_mark  # noqa: E402

assert os.path.abspath(c.DB_PATH).startswith(os.path.abspath(TMP)), "Test haqiqiy bazaga ulanmasligi kerak"


class Base(unittest.TestCase):
    _n = 0

    def sql(self, q, *args):
        conn = c.get_db()
        try:
            cur = conn.execute(q, args)
            rows = cur.fetchall()
            conn.commit()
            return rows if rows else cur.lastrowid
        finally:
            conn.close()

    def new_user(self, phone=None):
        """Yangi foydalanuvchi va uning nomidan kirgan mijoz."""
        Base._n += 1
        phone = phone or f"+99891{Base._n:07d}"
        rows = self.sql("SELECT id FROM users WHERE phone=?", phone)
        uid = rows[0]["id"] if rows else self.sql(
            "INSERT INTO users(phone, first_name, last_name, region, password_hash, created_at) "
            "VALUES (?, 'Ism', 'Familiya', ?, 'x', ?)", phone, c.REGIONS[0], int(time.time()),
        )
        client = app.test_client()
        with client.session_transaction() as s:
            s["uid"] = uid
            s["pm"] = password_mark(self.sql("SELECT * FROM users WHERE id=?", uid)[0])
        return uid, client

    def post(self, client, url, **data):
        r = client.post(url, json=data)
        return r.status_code, r.get_json()

    def attempt(self, aid):
        return self.sql("SELECT * FROM attempts WHERE id=?", aid)[0]

    def draft(self, aid):
        d = self.attempt(aid)["draft"]
        return json.loads(d) if d else None

    def result(self, aid):
        return json.loads(self.attempt(aid)["result"])["answers"]
