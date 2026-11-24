"""Dars fayllarini yuklab olish dars qulfiga bo'ysunishi."""
import os
import time

from tests.base import ADMIN_PHONE, Base, app, c


class FileLock(Base):
    def setUp(self):
        self.uid, self.cl = self.new_user()
        self.sql("UPDATE users SET diag_declined=1 WHERE id=?", self.uid)
        self.topics = [r["id"] for r in self.sql("SELECT id FROM topics WHERE published=1 ORDER BY position, id")]
        self.assertGreaterEqual(len(self.topics), 2)
        os.makedirs(c.FILES_DIR, exist_ok=True)

    def add_file(self, tid):
        stored = f"t{tid}-{time.time_ns()}.pdf"
        with open(os.path.join(c.FILES_DIR, stored), "wb") as f:
            f.write(b"%PDF-dars")
        return self.sql(
            "INSERT INTO topic_files(topic_id, name, stored, size, created_at) VALUES (?, 'dars.pdf', ?, 9, 0)",
            tid, stored,
        )

    def get(self, fid, client=None, prefix=""):
        r = (client or self.cl).get(f"{prefix}/file/{fid}")
        data, code = r.data, r.status_code
        r.close()
        return code, data

    def set_progress(self, tid, **kw):
        cols = {"diag_percent": None, "best_percent": None, "passed": 0, **kw}
        self.sql("INSERT INTO progress(user_id, topic_id, diag_percent, best_percent, passed) VALUES (?, ?, ?, ?, ?)",
                 self.uid, tid, cols["diag_percent"], cols["best_percent"], cols["passed"])

    def test_current_lesson_open(self):
        self.assertEqual(self.get(self.add_file(self.topics[0])), (200, b"%PDF-dars"))

    def test_locked_lesson_closed(self):
        code, data = self.get(self.add_file(self.topics[1]))
        self.assertEqual(code, 403)
        self.assertNotIn(b"%PDF", data)

    def test_undecided_student_goes_to_diagnostics(self):
        self.sql("UPDATE users SET diag_declined=0 WHERE id=?", self.uid)
        r = self.cl.get(f"/file/{self.add_file(self.topics[0])}")
        self.assertEqual((r.status_code, r.headers["Location"]), (302, "/welcome"))

    def test_opens_after_previous_passed(self):
        fid = self.add_file(self.topics[1])
        self.set_progress(self.topics[0], best_percent=90, passed=1)
        self.assertEqual(self.get(fid)[0], 200)
        self.assertEqual(self.get(self.add_file(self.topics[0]))[0], 200)   # o'tilgan dars ham ochiq

    def test_skipped_by_diagnostic_is_open(self):
        """Diagnostikada yuqori natija olingan (rejaga kirmagan) mavzu fayli ochiq qoladi."""
        self.sql("INSERT INTO attempts(user_id, kind, payload, created_at, finished_at) "
                 "VALUES (?, 'diagnostic', '[]', 0, 1)", self.uid)
        self.set_progress(self.topics[1], diag_percent=95)
        self.assertEqual(self.get(self.add_file(self.topics[1]))[0], 200)

    def test_admin_gets_everything(self):
        _, admin = self.new_user(ADMIN_PHONE)
        self.assertEqual(self.get(self.add_file(self.topics[-1]), admin, "/admin")[0], 200)
        tid = self.sql("INSERT INTO topics(title, position, published) VALUES ('Qoralama', 99, 0)")
        fid = self.add_file(tid)
        self.assertEqual(self.get(fid, admin, "/admin")[0], 200)
        self.assertEqual(self.get(fid)[0], 404)
        self.assertEqual(self.get(fid, prefix="/admin")[0], 403)

    def test_missing_and_anonymous(self):
        self.assertEqual(self.get(10 ** 6)[0], 404)
        fid = self.add_file(self.topics[0])
        self.assertEqual(self.get(fid, app.test_client())[0], 302)
