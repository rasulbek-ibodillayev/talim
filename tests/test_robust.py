"""Noto'g'ri ma'lumotlar, xavfsizlik va o'quvchining to'liq yo'li."""
import io
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from werkzeug.security import generate_password_hash

import seed
from tests.base import ADMIN_PHONE, Base, app, c, password_mark

BIG = "9" * 30
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_VALUES = [None, "", [], {}, -1, 10 ** 30, 1.5, True, [1], {"a": 1}, "²", "\ud800", "\x00", "x" * 5000, "' OR 1=1 --"]
FORM_VALUES = ["", "²", "--5", "\x00", "nan", "inf", "1e999", BIG, "-" + BIG, "x" * 5000, "-1"]


def fresh_content():
    conn = c.get_db()
    try:
        seed.replace_all(conn)
        conn.execute("DELETE FROM rate")
        conn.execute("DELETE FROM meta WHERE key LIKE 'set:%'")
        conn.commit()
    finally:
        conn.close()


def field_names():
    src = ""
    for f in ("app.py", "learn.py", "admin.py"):
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            src += fh.read()
    return set(re.findall(r'\.get\("(\w+)"', src)) | {"o1", "o2", "o3", "o4"} | set(c.SETTINGS)


class Robust(Base):
    @classmethod
    def setUpClass(cls):
        fresh_content()

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.uid, self.st = self.new_user()
        self.sql("UPDATE users SET diag_declined=1 WHERE id=?", self.uid)
        self.admin_id, self.ad = self.new_user(ADMIN_PHONE)
        self.ad.get("/admin")
        with self.ad.session_transaction() as s:
            self.tok = s["csrf"]
        app.config["PROPAGATE_EXCEPTIONS"] = False
        self.addCleanup(app.config.__setitem__, "PROPAGATE_EXCEPTIONS", None)

    def urls(self, method):
        for rule in app.url_map.iter_rules():
            if rule.endpoint != "static" and method in rule.methods and "logout" not in rule.rule:
                for num in ("1", "0", BIG):
                    yield re.sub(r"<\w+>", "dtm", re.sub(r"<int:\w+>", num, rule.rule))
                    if "<int" not in rule.rule:
                        break

    def test_get_never_crashes(self):
        for url in self.urls("GET"):
            for cl in (self.st, self.ad, app.test_client()):
                for q in ("", f"?q=%00'%25&kind=²&f={BIG}&topic={BIG}"):
                    with self.subTest(url + q):
                        r = cl.get(url + q)
                        self.assertLess(r.status_code, 500)
                        r.close()

    def test_api_never_crashes(self):
        names = field_names()
        for url in self.urls("POST"):
            if not url.startswith("/api"):
                continue
            for cl in (self.st, self.ad, app.test_client()):
                for v in JSON_VALUES:
                    with self.subTest(f"{url} {v!a:.40}"):
                        for data in (v, {k: v for k in names}):
                            r = cl.post(url, data=json.dumps(data), content_type="application/json")
                            self.assertLess(r.status_code, 500)
                            self.assertTrue(r.is_json)        # sahifa kodi doim JSON kutadi
                self.assertLess(cl.post(url, data="{buzuq", content_type="application/json").status_code, 500)

    def test_admin_forms_never_crash(self):
        names = field_names()
        for url in self.urls("POST"):
            if url.startswith("/admin") and "delete" not in url:
                for v in FORM_VALUES:
                    with self.subTest(f"{url} {v!a:.30}"):
                        r = self.ad.post(url, data={**{k: v for k in names}, "_csrf": self.tok})
                        self.assertLess(r.status_code, 500)
        conn = c.get_db()
        try:
            for k, v in c.get_settings(conn).items():        # nan yoki cheksiz son saqlanib qolmagan
                self.assertTrue(0 <= v <= 1000, k)
        finally:
            conn.close()
        fresh_content()

    def test_admin_posts_require_csrf(self):
        for url in self.urls("POST"):
            if url.startswith("/admin") and BIG not in url:
                with self.subTest(url):
                    for data in ({}, {"_csrf": "xato"}):
                        self.assertIn(self.ad.post(url, data=data).status_code, (400, 404))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM topics")[0][0], 10)

    def test_api_requires_json_and_login(self):
        for url in self.urls("POST"):
            if not url.startswith("/api") or url == "/api/profile/avatar":
                continue
            with self.subTest(url):
                self.assertIn(self.st.post(url, data={"a": "b"}).status_code, (404, 415))
                if not re.match(r"/api/(login|register|recover)", url):
                    r = app.test_client().post(url, json={})
                    self.assertEqual((r.status_code, r.get_json()["redirect"]), (401, "/"))

    def test_wrong_method_is_json(self):
        r = self.st.get("/api/login")
        self.assertEqual((r.status_code, r.is_json), (405, True))

    def test_server_error_page(self):
        app.view_functions["healthz_original"] = app.view_functions["healthz"]
        app.view_functions["healthz"] = lambda: 1 / 0
        try:
            r = app.test_client().get("/healthz")
            self.assertEqual(r.status_code, 500)
            self.assertIn("Serverda xatolik", r.get_data(as_text=True))
        finally:
            app.view_functions["healthz"] = app.view_functions.pop("healthz_original")
        self.assertEqual(app.test_client().get("/healthz").data, b"ok")

    # ---- XSS ----
    def test_user_text_is_escaped(self):
        bad = "<script>alert(1)</script>"
        self.post(self.st, "/api/profile", first_name=bad, last_name=bad, region=c.REGIONS[0], education=bad, bio=bad)
        tid = self.sql("SELECT id FROM topics ORDER BY position LIMIT 1")[0]["id"]
        self.sql("INSERT INTO materials(topic_id, title, body, url) VALUES (?, ?, ?, ?)", tid, bad, bad,
                 "javascript:alert(1)\nX | https://ok.uz/")
        for cl, url in ((self.st, "/dashboard"), (self.st, "/profile"), (self.st, f"/topic/{tid}"),
                        (self.ad, "/admin/users"), (self.ad, f"/admin/user/{self.uid}"), (self.ad, f"/admin/topic/{tid}"),
                        (self.ad, "/admin/users?q=" + bad)):
            with self.subTest(url):
                html = cl.get(url).get_data(as_text=True)
                self.assertNotIn(bad, html)
                self.assertNotIn('href="javascript:', html)
        self.sql("DELETE FROM materials WHERE title=?", bad)

    def test_file_names_and_types(self):
        tid = self.sql("SELECT id FROM topics LIMIT 1")[0]["id"]
        for name, data, ok in (("../../evil.pdf", b"%PDF-1", True), ("a.exe", b"MZ", False), ("a.pdf", b"MZ", False),
                               ("a.docx", b"%PDF", False), ("a.html", b"<script>", False), ("pdf", b"%PDF", False)):
            with self.subTest(name):
                self.ad.post(f"/admin/topic/{tid}/file", content_type="multipart/form-data",
                             data={"_csrf": self.tok, "file": (io.BytesIO(data), name)})
                rows = self.sql("SELECT * FROM topic_files WHERE topic_id=?", tid)
                rows = rows if isinstance(rows, list) else []
                self.assertEqual(len(rows), 1 if ok else 0)
                for r in rows:
                    self.assertRegex(r["stored"], r"^\d+_[0-9a-f]{16}\.pdf$")
                    self.assertNotIn("..", r["name"])
                    self.ad.post(f"/admin/file/{r['id']}/delete", data={"_csrf": self.tok})
                    self.assertFalse(os.path.exists(os.path.join(c.FILES_DIR, r["stored"])))

    # ---- Sessiyalar ----
    def test_password_change_closes_other_sessions(self):
        self.sql("UPDATE users SET password_hash=? WHERE id=?", generate_password_hash("birinchi-parol"), self.uid)
        phone = self.sql("SELECT phone FROM users WHERE id=?", self.uid)[0]["phone"]
        one, two = app.test_client(), app.test_client()
        for cl in (one, two):
            self.assertEqual(self.post(cl, "/api/login", phone=phone, password="birinchi-parol")[0], 200)
        r = self.post(one, "/api/profile/password", old="birinchi-parol", new="ikkinchi-parol", new2="ikkinchi-parol")
        self.assertTrue(r[1]["ok"])
        self.assertEqual(one.get("/dashboard").status_code, 200)             # o'zi kirgan holda qoladi
        self.assertEqual(two.get("/dashboard").headers["Location"], "/")

    def test_deleted_user_is_logged_out(self):
        self.sql("DELETE FROM users WHERE id=?", self.uid)
        self.assertEqual(self.st.get("/dashboard").headers["Location"], "/")
        self.assertEqual(self.post(self.st, "/api/profile/secret")[0], 401)

    def test_login_is_limited(self):
        phone = self.sql("SELECT phone FROM users WHERE id=?", self.uid)[0]["phone"]
        self.sql("DELETE FROM rate")
        codes = [self.post(app.test_client(), "/api/login", phone=phone, password="xato")[0] for _ in range(10)]
        self.assertEqual(codes, [401] * 8 + [429] * 2)
        self.sql("DELETE FROM rate")

    def test_security_headers(self):
        r = self.st.get("/dashboard")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        cookie = app.test_client().get("/").headers.get("Set-Cookie", "") or "HttpOnly"
        self.assertIn("HttpOnly", cookie)

    # ---- O'chirilgan mavzu va testlar ----
    def test_deleting_removes_open_attempts_but_keeps_results(self):
        tid = self.sql("INSERT INTO topics(title, position) VALUES ('Vaqtincha', 50)")
        eid = self.sql("INSERT INTO exams(kind, title, time_limit, created_at) VALUES ('olympiad', 'V', 5, 0)")
        ids = {}
        for kind, t, e in (("topic", tid, None), ("exam", None, eid)):
            for done in (None, 1):
                ids[kind, done] = self.sql(
                    "INSERT INTO attempts(user_id, kind, topic_id, exam_id, payload, created_at, finished_at, score, total, "
                    "result) VALUES (?, ?, ?, ?, '[]', 0, ?, 1, 1, '{\"answers\": [], \"topics\": []}')",
                    self.uid, kind, t, e, done)
        self.ad.post(f"/admin/topic/{tid}/delete", data={"_csrf": self.tok})
        self.ad.post(f"/admin/exam/{eid}/delete", data={"_csrf": self.tok})
        left = {r["id"] for r in self.sql("SELECT id FROM attempts WHERE user_id=?", self.uid)}
        self.assertEqual(left, {ids["topic", 1], ids["exam", 1]})
        for aid in left:
            self.assertEqual(self.st.get(f"/result/{aid}").status_code, 200)
        for url in ("/dashboard", "/results", "/mistakes"):
            self.assertEqual(self.st.get(url).status_code, 200)
        self.assertEqual(self.ad.get(f"/admin/user/{self.uid}").status_code, 200)

    # ---- Bir vaqtda ko'p o'quvchi ----
    def test_many_students_at_once(self):
        eid = self.sql("SELECT id FROM exams WHERE kind='olympiad'")[0]["id"]
        users = [self.new_user()[0] for _ in range(20)]
        marks = {u: password_mark(self.sql("SELECT * FROM users WHERE id=?", u)[0]) for u in users}

        def go(uid):
            cl = app.test_client()
            with cl.session_transaction() as s:
                s["uid"], s["pm"] = uid, marks[uid]
            url = cl.post(f"/api/exam/{eid}/start", json={}).get_json()["redirect"]
            aid = int(url.rsplit("/", 1)[1])
            n = len(cl.get(f"/api/quiz/{aid}").get_json()["questions"])
            codes = [cl.post(f"/api/quiz/{aid}/save", json={"answers": [i % 4] * n}).status_code for i in range(5)]
            codes.append(cl.post(f"/api/quiz/{aid}/submit", json={"answers": [0] * n}).status_code)
            return n, codes
        with ThreadPoolExecutor(10) as ex:
            for n, codes in ex.map(go, users):
                self.assertEqual((n, codes), (30, [200] * 6))


class Journey(Base):
    """Namunaviy ma'lumotlar bilan: ro'yxatdan o'tishdan dars reja tugaguncha."""

    def setUp(self):
        fresh_content()
        self.cl = app.test_client()
        Base._n += 1
        self.phone = f"+99895{Base._n:07d}"
        code, _ = self.post(self.cl, "/api/register", phone=self.phone, first_name="Ali", last_name="Vali",
                            region=c.REGIONS[0], password="parol-12345", password2="parol-12345", secret="registon")
        self.assertEqual(code, 200)
        self.uid = self.sql("SELECT id FROM users WHERE phone=?", self.phone)[0]["id"]

    def start(self, url):
        code, r = self.post(self.cl, url)
        self.assertEqual(code, 200, r)
        return int(r["redirect"].rsplit("/", 1)[1])

    def finish(self, aid, right):
        payload = json.loads(self.attempt(aid)["payload"])
        data = self.cl.get(f"/api/quiz/{aid}").get_json()
        for q in data["questions"]:
            self.assertNotIn("correct", q)                    # to'g'ri javob brauzerga yuborilmaydi
            self.assertNotIn("explanation", q)
        answers = [q["correct"] if right(i, q) else (q["correct"] + 1) % 4 for i, q in enumerate(payload)]
        self.assertEqual(self.post(self.cl, f"/api/quiz/{aid}/submit", answers=answers)[0], 200)
        self.assertEqual(self.cl.get(f"/result/{aid}").status_code, 200)
        return [q["qid"] for q in payload]

    def lesson(self, tid, right):
        self.assertEqual(self.cl.get(f"/topic/{tid}").status_code, 200)
        for m in self.sql("SELECT id FROM materials WHERE topic_id=?", tid):
            self.assertEqual(self.post(self.cl, f"/api/material/{m['id']}/read")[0], 200)
        return self.finish(self.start(f"/api/topic/{tid}/test/start"), right)

    def test_full_path(self):
        self.assertEqual(self.cl.get("/dashboard").headers["Location"], "/welcome")
        topics = [r["id"] for r in self.sql("SELECT id FROM topics ORDER BY position")]
        aid = self.start("/api/diagnostic/start")
        used = self.finish(aid, lambda i, q: q["topic_id"] in topics[:2])
        self.assertEqual(len(used), 30)
        plan = topics[2:]                                     # bilgan 2 ta mavzu chiqarildi
        for n, tid in enumerate(plan):
            for later in plan[n + 1:]:
                self.assertEqual(self.cl.get(f"/topic/{later}").status_code, 403)
            if n % 3 == 0:                                    # har uchinchi mavzudan avval yiqiladi
                used += self.lesson(tid, lambda i, q: False)
            used += self.lesson(tid, lambda i, q: True)
        self.assertEqual(len(used), len(set(used)))           # birorta savol takrorlanmadi
        html = self.cl.get("/dashboard").get_data(as_text=True).replace("&#39;", "'")
        self.assertIn("Dars reja to'liq bajarildi!", html)
        self.assertIn("8/8", html)
        self.assertEqual(self.cl.get("/mistakes").get_data(as_text=True).count("/restudy"), 3)
        for e in self.sql("SELECT id, kind FROM exams"):
            aid = self.start(f"/api/exam/{e['id']}/start")
            n = {"dtm": 40, "olympiad": 30, "certificate": 35}[e["kind"]]
            self.assertEqual(len(self.finish(aid, lambda i, q: True)), n)
            a = self.attempt(aid)
            self.assertEqual((a["score"], a["points"]), (n, a["max_points"]))
            self.assertEqual(a["max_points"], {"dtm": 10 * 1.1 + 30 * 3.1, "olympiad": 30, "certificate": 35}[e["kind"]])
        self.assertEqual(self.cl.get("/results").status_code, 200)

    def test_three_attempts_fit_into_bank(self):
        self.post(self.cl, "/api/diagnostic/decline")
        tid = self.sql("SELECT id FROM topics ORDER BY position LIMIT 1")[0]["id"]
        used = []
        for size in (5, 5, 5):
            ids = self.lesson(tid, lambda i, q: False)
            self.assertEqual(len(ids), size)
            used += ids
        self.assertEqual(len(set(used)), 15)
