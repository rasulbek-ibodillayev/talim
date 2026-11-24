"""Ro'yxatdan o'tish, kirish va parolni mahfiy so'z orqali tiklash."""
import time

import create_admin
from tests.base import ADMIN_PHONE, Base, app, c


class Auth(Base):
    PW = "eski-parol-1"

    def setUp(self):
        self.sql("DELETE FROM rate")
        Base._n += 1
        self.phone = f"+99893{Base._n:07d}"
        self.cl = app.test_client()

    def form(self, **kw):
        return {"phone": self.phone, "first_name": "Ali", "last_name": "Valiyev", "region": c.REGIONS[0],
                "password": self.PW, "password2": self.PW, "secret": "Samarqand Shahri", **kw}

    def register(self, **kw):
        return self.post(self.cl, "/api/register", **self.form(**kw))

    def user(self, phone=None):
        rows = self.sql("SELECT * FROM users WHERE phone=?", phone or self.phone)
        return rows[0] if rows else None

    def login(self, password, client=None):
        return self.post(client or app.test_client(), "/api/login", phone=self.phone, password=password)[0]

    def check(self, secret, client=None, phone=None):
        return self.post(client or self.cl, "/api/recover/check", phone=phone or self.phone, secret=secret)

    def reset(self, pw, pw2=None, client=None):
        return self.post(client or self.cl, "/api/recover/reset", password=pw, password2=pw if pw2 is None else pw2)

    # ---- Ro'yxatdan o'tish ----
    def test_register_logs_in_and_offers_diagnostics(self):
        code, r = self.register()
        self.assertEqual((code, r["redirect"]), (200, "/"))
        self.assertEqual(self.cl.get("/").headers["Location"], "/dashboard")
        u = self.user()
        for field in ("password_hash", "secret_hash"):
            self.assertNotIn("amarqand", u[field].lower())
            self.assertNotIn(self.PW, u[field])
        self.assertEqual(self.login(self.PW), 200)
        self.assertEqual(self.login("boshqa-parol"), 401)

    def test_register_validation(self):
        for bad in ({"phone": "12345"}, {"phone": None}, {"first_name": "A"}, {"last_name": ""}, {"region": "Mars"},
                    {"password": "qisqa", "password2": "qisqa"}, {"password2": "boshqa-parol"}, {"secret": ""},
                    {"secret": "  ab "}, {"secret": "x" * 65}, {"secret": None}, {"secret": self.PW.upper()}):
            with self.subTest(bad):
                code, r = self.register(**bad)
                self.assertEqual(code, 400)
                self.assertFalse(r["ok"])
        self.assertIsNone(self.user())

    def test_phone_is_unique(self):
        self.register()
        before = self.user()["password_hash"]
        code, r = self.post(app.test_client(), "/api/register", **self.form(
            phone=self.phone[4:], password="begona-parol", password2="begona-parol"))
        self.assertEqual(code, 409)
        self.assertEqual(self.user()["password_hash"], before)

    def test_admin_phone_cannot_be_taken(self):
        self.sql("DELETE FROM users WHERE phone=?", ADMIN_PHONE)
        code, _ = self.register(phone=ADMIN_PHONE)
        self.assertEqual(code, 409)
        self.assertIsNone(self.user(ADMIN_PHONE))

    def test_class_can_register_from_one_ip(self):
        for i in range(35):
            self.phone = f"+99894{Base._n:03d}{i:04d}"
            self.assertEqual(self.post(app.test_client(), "/api/register", **self.form())[0], 200)

    def test_telegram_routes_are_gone(self):
        for url in ("start", "verify", "complete"):
            self.assertEqual(self.post(self.cl, f"/api/register/{url}")[0], 404)
        html = self.cl.get("/").get_data(as_text=True).lower()
        self.assertNotIn("telegram", html)
        self.assertNotIn("bot", html.replace("bottom", ""))

    # ---- Parolni tiklash ----
    def test_recover(self):
        self.register()
        cl = app.test_client()
        self.assertEqual(self.check("  samarqand   SHAHRI ", cl)[0], 200)
        self.assertEqual(self.reset("yangi-parol-2", client=cl)[0], 200)
        self.assertEqual((self.login(self.PW), self.login("yangi-parol-2")), (401, 200))
        self.assertEqual(self.reset("uchinchi-parol", client=cl)[0], 401)       # ruxsat bir martalik
        self.assertEqual(self.login("uchinchi-parol"), 401)

    def test_apostrophes_do_not_matter(self):
        self.register(secret="O‘zbekiston yo’li")
        self.assertEqual(self.check("o'zbekiston yo`li", app.test_client())[0], 200)

    def test_wrong_secret_or_phone_look_the_same(self):
        self.register()
        a = self.check("xato so'z", app.test_client())
        b = self.check("xato so'z", app.test_client(), "+998970000000")
        self.assertEqual(a, b)
        self.assertEqual(a[0], 401)
        cl = app.test_client()
        self.check("xato so'z", cl)
        self.assertEqual(self.reset("yangi-parol-2", client=cl)[0], 401)
        self.assertEqual(self.login(self.PW), 200)

    def test_reset_without_check(self):
        self.register()
        self.assertEqual(self.reset("yangi-parol-2", client=app.test_client())[0], 401)

    def test_reset_password_rules_keep_permission(self):
        self.register()
        cl = app.test_client()
        self.check("samarqand shahri", cl)
        self.assertEqual(self.reset("qisqa", client=cl)[0], 400)
        self.assertEqual(self.reset("yangi-parol-2", "boshqa-parol", client=cl)[0], 400)
        self.assertEqual(self.reset("Samarqand Shahri", client=cl)[0], 400)     # mahfiy so'z parol bo'lmaydi
        self.assertEqual(self.reset("yangi-parol-2", client=cl)[0], 200)

    def test_permission_expires(self):
        self.register()
        cl = app.test_client()
        self.check("samarqand shahri", cl)
        with cl.session_transaction() as s:
            s["reset"] = {**s["reset"], "until": int(time.time()) - 1}
        self.assertEqual(self.reset("yangi-parol-2", client=cl)[0], 401)
        self.assertEqual(self.login(self.PW), 200)

    def test_permission_dies_when_password_changed_elsewhere(self):
        self.register()
        one, two = app.test_client(), app.test_client()
        self.check("samarqand shahri", one)
        self.check("samarqand shahri", two)
        self.assertEqual(self.reset("yangi-parol-2", client=one)[0], 200)
        self.assertEqual(self.reset("begona-parol-3", client=two)[0], 401)
        self.assertEqual(self.login("yangi-parol-2"), 200)

    def test_check_does_not_log_in(self):
        self.register()
        cl = app.test_client()
        self.check("samarqand shahri", cl)
        self.assertEqual(cl.get("/dashboard").status_code, 302)
        self.assertEqual(cl.get("/dashboard").headers["Location"], "/")

    def test_guessing_is_limited(self):
        self.register()
        for _ in range(5):
            self.assertEqual(self.check("xato so'z", app.test_client())[0], 401)
        self.assertEqual(self.check("samarqand shahri", app.test_client())[0], 429)

    def test_user_without_secret_cannot_recover(self):
        self.register()
        self.sql("UPDATE users SET secret_hash=NULL WHERE phone=?", self.phone)
        for s in ("samarqand shahri", "dummy-password-for-timing"):
            self.assertEqual(self.check(s, app.test_client())[0], 401)

    def test_admin_cannot_recover_by_secret(self):
        self.new_user(ADMIN_PHONE)
        self.register()
        self.sql("UPDATE users SET secret_hash=? WHERE phone=?", self.user()["secret_hash"], ADMIN_PHONE)
        self.assertEqual(self.check("samarqand shahri", app.test_client(), ADMIN_PHONE)[0], 401)
        self.sql("UPDATE users SET secret_hash=NULL WHERE phone=?", ADMIN_PHONE)

    # ---- Profilda mahfiy so'z ----
    def test_secret_in_profile(self):
        self.register()
        self.sql("UPDATE users SET secret_hash=NULL WHERE phone=?", self.phone)
        self.assertIn("Mahfiy so'z qo'yilmagan", self.cl.get("/profile").get_data(as_text=True))
        self.assertIn("secret-form", self.cl.get("/profile").get_data(as_text=True))
        self.assertFalse(self.post(self.cl, "/api/profile/secret", password="xato", secret="yangi so'z")[1]["ok"])
        self.assertFalse(self.post(self.cl, "/api/profile/secret", password=self.PW, secret="ab")[1]["ok"])
        self.assertTrue(self.post(self.cl, "/api/profile/secret", password=self.PW, secret="yangi so'z")[1]["ok"])
        self.assertEqual(self.check("yangi so'z", app.test_client())[0], 200)
        self.assertEqual(self.check("samarqand shahri", app.test_client())[0], 401)

    def test_notice_for_users_without_secret(self):
        self.register()
        self.sql("UPDATE users SET diag_declined=1 WHERE phone=?", self.phone)
        self.assertNotIn("/profile#secret", self.cl.get("/dashboard").get_data(as_text=True))
        self.sql("UPDATE users SET secret_hash=NULL WHERE phone=?", self.phone)
        self.assertIn("/profile#secret", self.cl.get("/dashboard").get_data(as_text=True))

    def test_admin_has_no_secret_form(self):
        _, admin = self.new_user(ADMIN_PHONE)
        self.assertNotIn("secret-form", admin.get("/admin/profile").get_data(as_text=True))
        self.assertEqual(self.post(admin, "/api/profile/secret", password="x", secret="yangi")[0], 403)

    # ---- create_admin.py ----
    def test_create_admin(self):
        self.sql("DELETE FROM users WHERE phone=?", ADMIN_PHONE)
        self.assertTrue(create_admin.save_admin(ADMIN_PHONE, "admin-parol-1"))
        self.assertFalse(create_admin.save_admin(ADMIN_PHONE, "admin-parol-2"))
        cl = app.test_client()
        self.assertEqual(self.post(cl, "/api/login", phone=ADMIN_PHONE, password="admin-parol-1")[0], 401)
        self.assertEqual(self.post(cl, "/api/login", phone=ADMIN_PHONE, password="admin-parol-2")[0], 200)
        self.assertEqual(cl.get("/").headers["Location"], "/admin")
        for phone, pw in ((self.phone, "admin-parol-1"), (ADMIN_PHONE, "qisqa")):
            with self.assertRaises(ValueError):
                create_admin.save_admin(phone, pw)
