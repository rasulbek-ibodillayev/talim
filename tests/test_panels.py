"""Admin va o'quvchi panellari bir-biridan ajratilgani."""
import re
import time

from werkzeug.security import generate_password_hash

from tests.base import ADMIN_PHONE, Base, app, c

SHARED = {"learn.profile_save", "learn.password_change", "learn.avatar_upload", "learn.avatar_delete",
          "learn.avatar_file"}


def routes(prefix):
    """(metod, manzil, endpoint): blueprintdagi hamma marshrutlar."""
    for rule in app.url_map.iter_rules():
        if rule.endpoint.startswith(prefix + "."):
            url = re.sub(r"<int:\w+>", "1", rule.rule)
            url = re.sub(r"<\w+>", "dtm", url)
            for m in rule.methods & {"GET", "POST"}:
                yield m, url, rule.endpoint


def hrefs(html):
    return set(re.findall(r'(?:href|action)="(/[^"#?]*)', html))


class Panels(Base):
    def setUp(self):
        self.uid, self.student = self.new_user()
        self.admin_id, self.admin = self.new_user(ADMIN_PHONE)

    # ---- Ruxsatlar: har bir marshrut ----
    def test_student_cannot_open_any_admin_route(self):
        n = 0
        for m, url, ep in routes("admin"):
            with self.subTest(f"{m} {url}"):
                self.assertTrue(url.startswith("/admin"))
                self.assertEqual(self.student.open(url, method=m).status_code, 403)
            n += 1
        self.assertGreater(n, 20)

    def test_anonymous_cannot_open_any_admin_route(self):
        for m, url, ep in routes("admin"):
            with self.subTest(f"{m} {url}"):
                self.assertEqual(app.test_client().open(url, method=m).status_code, 302)

    def test_admin_cannot_use_student_routes(self):
        n = 0
        for m, url, ep in routes("learn"):
            if ep in SHARED:
                continue
            with self.subTest(f"{m} {url}"):
                self.assertFalse(url.startswith("/admin"))
                r = self.admin.open(url, method=m, json={} if m == "POST" else None)
                if url.startswith("/api"):
                    self.assertEqual((r.status_code, r.get_json()["redirect"]), (403, "/admin"))
                else:
                    want = "/admin/profile" if ep == "learn.profile" else "/admin"
                    self.assertEqual((r.status_code, r.headers["Location"]), (302, want))
            n += 1
        self.assertGreater(n, 20)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM attempts WHERE user_id=?", self.admin_id)[0]["n"], 0)

    # ---- Kirish ----
    def test_home(self):
        self.assertEqual(self.student.get("/").headers["Location"], "/dashboard")
        self.assertEqual(self.admin.get("/").headers["Location"], "/admin")
        self.assertEqual(app.test_client().get("/").status_code, 200)

    def test_login_leads_to_own_panel(self):
        for phone, home in (("+998990000001", "/dashboard"), (ADMIN_PHONE, "/admin")):
            uid, _ = self.new_user(phone)
            self.sql("UPDATE users SET password_hash=? WHERE id=?", generate_password_hash("parol-123"), uid)
            cl = app.test_client()
            code, r = self.post(cl, "/api/login", phone=phone, password="parol-123")
            self.assertEqual(code, 200)
            self.assertEqual(cl.get(r["redirect"]).headers["Location"], home)

    # ---- Menyu va havolalar ----
    def test_student_pages_have_no_admin_links(self):
        self.sql("UPDATE users SET diag_declined=1 WHERE id=?", self.uid)
        tid = self.sql("SELECT id FROM topics ORDER BY position, id LIMIT 1")[0]["id"]
        for url in ("/dashboard", f"/topic/{tid}", "/exams/olympiad", "/exams/certificate", "/exams/dtm", "/exam/1",
                    "/results", "/mistakes", "/profile"):
            with self.subTest(url):
                r = self.student.get(url)
                self.assertEqual(r.status_code, 200)
                html = r.get_data(as_text=True)
                self.assertFalse([h for h in hrefs(html) if h.startswith("/admin")])
                self.assertIn("O'quvchi</span>", html.replace("&#39;", "'"))

    def test_menus_match_the_task_file(self):
        def menu(client, url):
            return re.findall(r'class="nav-link [^"]*" href="([^"]+)"', client.get(url).get_data(as_text=True))
        self.sql("UPDATE users SET diag_declined=1 WHERE id=?", self.uid)
        self.assertEqual(menu(self.student, "/dashboard"), [
            "/dashboard", "/exams/olympiad", "/exams/certificate", "/exams/dtm", "/results", "/mistakes", "/profile"])
        self.assertEqual(menu(self.admin, "/admin"), [
            "/admin", "/admin/exams", "/admin/settings", "/admin/users", "/admin/profile"])

    def test_removed_sections(self):
        for url in ("/plan", "/path", "/diagnostic", "/my-tests"):
            self.assertEqual(self.student.get(url).status_code, 404)

    def test_admin_pages_have_only_admin_links(self):
        self.sql("INSERT INTO attempts(user_id, kind, payload, created_at, finished_at, score, total, result) "
                 "VALUES (?, 'diagnostic', '[]', 0, 1, 1, 2, '{\"answers\": [], \"topics\": []}')", self.uid)
        tid = self.sql("SELECT id FROM topics LIMIT 1")[0]["id"]
        self.sql("INSERT INTO topic_files(topic_id, name, stored, size, created_at) VALUES (?, 'a.pdf', 'a', 1, 0)", tid)
        mid = self.sql("SELECT id FROM materials LIMIT 1")[0]["id"]
        qid = self.sql("SELECT id FROM questions LIMIT 1")[0]["id"]
        eq = self.sql("SELECT id FROM exam_questions LIMIT 1")[0]["id"]
        for url in ("/admin", f"/admin/topic/{tid}", f"/admin/material/{mid}", f"/admin/question/{qid}",
                    "/admin/exams", "/admin/exams?kind=olympiad", "/admin/exam/1", f"/admin/exam-question/{eq}",
                    "/admin/users", f"/admin/user/{self.uid}", "/admin/settings", "/admin/profile"):
            with self.subTest(url):
                r = self.admin.get(url)
                self.assertEqual(r.status_code, 200)
                html = r.get_data(as_text=True)
                bad = [h for h in hrefs(html) if not h.startswith(("/admin", "/static/"))]
                self.assertEqual(bad, [])
                self.assertIn("admin-area", html)

    # ---- Profil ikkala panelda ham ishlaydi ----
    def test_admin_profile_save_keeps_education(self):
        self.sql("UPDATE users SET education='5-maktab' WHERE id=?", self.admin_id)
        html = self.admin.get("/admin/profile").get_data(as_text=True)
        self.assertIn('type="hidden" name="education" value="5-maktab"', html)
        code, r = self.post(self.admin, "/api/profile", first_name="Yangi", last_name="Admin",
                            region=c.REGIONS[0], education="5-maktab")
        self.assertEqual((code, r["ok"]), (200, True))
        self.assertIn("Yangi Admin", self.admin.get("/admin").get_data(as_text=True))

    # ---- Statistika: adminlar o'quvchi sifatida sanalmaydi ----
    def test_admins_not_counted_as_students(self):
        html = self.admin.get("/admin/users").get_data(as_text=True)
        self.assertNotIn(f"/admin/user/{self.admin_id}\"", html)
        self.assertIn(f"/admin/user/{self.uid}\"", html)
        n = self.sql("SELECT COUNT(*) AS n FROM users")[0]["n"] - 1
        self.assertIn(f"Ro'yxat ({n})", html.replace("&#39;", "'"))
        self.assertIn(f'<div class="stat-value">{n}</div><div class="stat-label">Jami', html)
        self.assertEqual(self.admin.get(f"/admin/user/{self.admin_id}").status_code, 404)
        found = self.admin.get("/admin/users?q=" + ADMIN_PHONE[1:]).get_data(as_text=True)
        self.assertIn("Foydalanuvchi topilmadi", found)

    def test_admin_old_attempts_not_in_stats(self):
        def total():
            html = self.admin.get("/admin/users").get_data(as_text=True)
            return re.search(r"natija · (\d+) test", html).group(1)
        before = total()
        self.sql("INSERT INTO attempts(user_id, kind, payload, created_at, finished_at, score, total) "
                 "VALUES (?, 'diagnostic', '[]', ?, 1, 1, 2)", self.admin_id, int(time.time()))
        self.assertEqual(total(), before)
        self.sql("DELETE FROM attempts WHERE user_id=?", self.admin_id)
