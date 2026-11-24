"""Dastlabki ma'lumotlarning to'liqligi va bir marta yozilishi."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import seed
import seed_exams
import seed_topics
from tests.base import Base, c

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SeedContent(unittest.TestCase):
    def rows(self):
        for t in seed_topics.TOPICS:
            for r in seed.parse_rows(t["questions"], 5):
                yield t["title"], r
        for e in seed_exams.EXAMS:
            for s in ("a", "b"):
                for num, *r in seed.parse_rows(e.get(s, ""), 6):
                    self.assertIn(int(num), range(0, len(seed_topics.TOPICS) + 1))
                    yield e["title"], r

    def test_counts_match_settings(self):
        self.assertEqual(len(seed_topics.TOPICS), 10)
        st = {k: v[0] for k, v in c.SETTINGS.items()}
        for t in seed_topics.TOPICS:
            n = len(seed.parse_rows(t["questions"], 5))
            # Diagnostika va mavzu testining kamida 3 ta urinishiga yetishi kerak
            left = n - st["diag_per_topic"]
            self.assertGreaterEqual(left, 2 * st["topic_count"] + 3, t["title"])
            self.assertGreaterEqual(len(t["materials"]), 2)
            self.assertTrue(all(len(body) > 200 for _title, body in t["materials"]))
        size = {e["kind"]: [len(seed.parse_rows(e.get(s, ""), 6)) for s in ("a", "b")] for e in seed_exams.EXAMS}
        self.assertEqual(size["dtm"], [st["dtm_mandatory_count"], st["dtm_special_count"]])
        self.assertEqual(size["olympiad"], [st["olympiad_count"], 0])
        self.assertEqual(size["certificate"], [st["certificate_count"], 0])

    def test_every_question_is_valid_and_unique(self):
        seen = {}
        for where, (text, *opts) in self.rows():
            with self.subTest(text):
                self.assertTrue(text.endswith("?"))
                self.assertEqual(len({o.lower() for o in opts}), 4)
                self.assertTrue(all(len(o) <= 300 for o in opts))
                self.assertNotIn(text.lower(), seen, f"takror: {where} va {seen.get(text.lower())}")
                seen[text.lower()] = where
        self.assertEqual(len(seen), 160 + 30 + 35 + 40)

    def test_bad_row_is_reported(self):
        for bad in ("savol|a|b|c", "savol|a|b||d", "savol|a|b|c|d|e"):
            with self.assertRaises(ValueError):
                seed.parse_rows(bad, 5)


class SeedDatabase(Base):
    def test_correct_answer_survives_shuffle(self):
        right = {r[0]: r[1] for t in seed_topics.TOPICS for r in seed.parse_rows(t["questions"], 5)}
        conn = c.get_db()
        try:
            seed.replace_all(conn)
            for q in conn.execute("SELECT * FROM questions").fetchall():
                self.assertEqual(q[f"o{q['correct']}"], right[q["text"]])
            exams = conn.execute("SELECT COUNT(*), SUM(topic_id IS NULL) FROM exam_questions").fetchone()
            self.assertEqual(tuple(exams), (105, 11))
            self.assertFalse(seed.seed_if_empty(conn))
            self.assertFalse(seed.seed_exams_if_empty(conn))
            conn.execute("DELETE FROM topics")              # admin hammasini o'chirsa ham qaytib kelmaydi
            conn.execute("DELETE FROM exams")
            conn.commit()
            self.assertFalse(seed.seed_if_empty(conn))
            self.assertFalse(seed.seed_exams_if_empty(conn))
            seed.replace_all(conn)
        finally:
            conn.close()

    def test_replace_keeps_users(self):
        uid, _ = self.new_user()
        self.sql("UPDATE users SET diag_declined=1 WHERE id=?", uid)
        self.sql("INSERT INTO attempts(user_id, kind, payload, created_at) VALUES (?, 'topic', '[]', 0)", uid)
        conn = c.get_db()
        try:
            seed.replace_all(conn)
        finally:
            conn.close()
        self.assertEqual(self.sql("SELECT diag_declined FROM users WHERE id=?", uid)[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM attempts")[0][0], 0)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM topics")[0][0], 10)


class Startup(unittest.TestCase):
    """gunicorn kabi: bir nechta jarayon bir vaqtda bo'sh bazada ishga tushadi."""

    def start(self, folder, n, **env):
        code = "import app; print('ok')"
        env = {**os.environ, "DB_PATH": os.path.join(folder, "new.db"), "FLASK_SECRET": "x" * 32,
               "ADMIN_PHONES": "+998900000009", "ADMIN_PASSWORD": "", **env}
        ps = [subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True) for _ in range(n)]
        for p in ps:
            out, err = p.communicate(timeout=120)
            self.assertEqual(out.strip(), "ok", err)

    def count(self, folder, sql):
        conn = sqlite3.connect(os.path.join(folder, "new.db"))
        try:
            return conn.execute(sql).fetchone()[0]
        finally:
            conn.close()

    def test_parallel_start_and_admin(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            self.start(d, 5)
            self.assertEqual(self.count(d, "SELECT COUNT(*) FROM topics"), 10)
            self.assertEqual(self.count(d, "SELECT COUNT(*) FROM questions"), 160)
            self.assertEqual(self.count(d, "SELECT COUNT(*) FROM exams"), 3)
            self.assertEqual(self.count(d, "SELECT COUNT(*) FROM users"), 0)          # parol berilmagan
            self.start(d, 2, ADMIN_PASSWORD="qisqa")
            self.assertEqual(self.count(d, "SELECT COUNT(*) FROM users"), 0)          # yaroqsiz parol
            self.start(d, 3, ADMIN_PASSWORD="birinchi-parol")
            self.assertEqual(self.count(d, "SELECT COUNT(*) FROM users"), 1)
            before = self.count(d, "SELECT password_hash FROM users")
            self.start(d, 1, ADMIN_PASSWORD="ikkinchi-parol")                         # mavjud parolga tegilmaydi
            self.assertEqual(self.count(d, "SELECT password_hash FROM users"), before)

    def test_secret_is_required(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            p = subprocess.run([sys.executable, "-c", "import app"], cwd=ROOT, capture_output=True, text=True,
                               env={**os.environ, "DB_PATH": os.path.join(d, "new.db"), "FLASK_SECRET": ""})
            self.assertNotEqual(p.returncode, 0)
