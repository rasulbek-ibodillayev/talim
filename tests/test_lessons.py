"""Diagnostika, dars reja, mavzu testi, Xatolarim va Test sozlamalari qoidalari."""
import io
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import excel_io
from tests.base import ADMIN_PHONE, Base, app, c, password_mark

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class Lessons(Base):
    def setUp(self):
        # Har bir test o'z mavzulari bilan ishlaydi
        for t in ("attempts", "progress", "reads", "questions", "materials", "topic_files", "topics"):
            self.sql(f"DELETE FROM {t}")
        self.sql("DELETE FROM meta WHERE key LIKE 'set:%'")
        self.sql("DELETE FROM rate")
        self.uid, self.cl = self.new_user()
        _, self.admin = self.new_user(ADMIN_PHONE)
        self.settings(topic_count=4, diag_per_topic=2, pass_percent=60, high_percent=80)
        self.topics = [self.topic(f"Mavzu {i}", i, n=10) for i in (1, 2, 3)]

    # ---- Yordamchilar ----
    def settings(self, **kw):
        for k, v in kw.items():
            self.sql("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", f"set:{k}", str(v))

    def topic(self, title, pos, n):
        tid = self.sql("INSERT INTO topics(title, position) VALUES (?, ?)", title, pos)
        self.sql("INSERT INTO materials(topic_id, title, body, position) VALUES (?, 'M', 'matn', 1)", tid)
        self.add_questions(tid, n)
        return tid

    def add_questions(self, tid, n):
        for i in range(n):
            self.sql("INSERT INTO questions(topic_id, text, o1, o2, o3, o4, correct) VALUES (?, ?, 'a', 'b', 'c', 'd', 1)",
                     tid, f"Savol {tid}-{i}")

    def decline(self):
        return self.post(self.cl, "/api/diagnostic/decline")

    def payload(self, aid):
        return json.loads(self.attempt(aid)["payload"])

    def qids(self, aid):
        return [q["qid"] for q in self.payload(aid)]

    def start(self, url):
        code, r = self.post(self.cl, url)
        self.assertEqual(code, 200, r)
        return int(r["redirect"].rsplit("/", 1)[1])

    def submit(self, aid, right=True):
        """right: True - hammasi to'g'ri, False - hammasi xato, set - shu mavzular to'g'ri."""
        ok = (lambda q: q["topic_id"] in right) if isinstance(right, set) else (lambda q: right)
        answers = [q["correct"] if ok(q) else (q["correct"] + 1) % 4 for q in self.payload(aid)]
        code, _ = self.post(self.cl, f"/api/quiz/{aid}/submit", answers=answers)
        self.assertEqual(code, 200)

    def read(self, tid):
        for m in self.sql("SELECT id FROM materials WHERE topic_id=?", tid):
            self.assertEqual(self.post(self.cl, f"/api/material/{m['id']}/read")[0], 200)

    def take(self, tid, right=True):
        self.read(tid)
        aid = self.start(f"/api/topic/{tid}/test/start")
        self.submit(aid, right)
        return aid

    def status(self, tid):
        return self.cl.get(f"/topic/{tid}").status_code

    def progress(self, tid):
        return self.sql("SELECT * FROM progress WHERE user_id=? AND topic_id=?", self.uid, tid)[0]

    def csrf(self):
        self.admin.get("/admin")
        with self.admin.session_transaction() as s:
            return s["csrf"]

    def admin_post(self, url, **data):
        r = self.admin.post(url, data={"_csrf": self.csrf(), **data}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        return self.admin.get(r.headers["Location"].split("#")[0]).get_data(as_text=True).replace("&#39;", "'")

    # ---- Birinchi kirish ----
    def test_first_visit_offers_diagnostics(self):
        self.assertEqual(self.cl.get("/dashboard").headers["Location"], "/welcome")
        html = self.cl.get("/welcome").get_data(as_text=True)
        self.assertIn("3 ta mavzudan 6 ta savol", html)
        for tid in self.topics:
            self.assertEqual(self.cl.get(f"/topic/{tid}").headers["Location"], "/welcome")
            self.assertEqual(self.post(self.cl, f"/api/topic/{tid}/test/start")[0], 403)

    def test_decline_gives_all_topics_in_order(self):
        self.assertEqual(self.decline()[1]["redirect"], "/dashboard")
        html = self.cl.get("/dashboard").get_data(as_text=True)
        self.assertEqual([int(x) for x in re.findall(r"(\d)-dars\. Mavzu", html)], [1, 2, 3])
        self.assertEqual([self.status(t) for t in self.topics], [200, 403, 403])
        self.assertEqual(self.cl.get("/welcome").headers["Location"], "/dashboard")
        self.assertFalse(self.post(self.cl, "/api/diagnostic/start")[1]["ok"])

    def test_diagnostics_removes_known_topics(self):
        aid = self.start("/api/diagnostic/start")
        self.assertEqual([q["topic_id"] for q in self.payload(aid)], [t for t in self.topics for _ in range(2)])
        self.assertFalse(self.decline()[1]["ok"])       # boshlangan diagnostikani rad etib bo'lmaydi
        self.assertIn(f"/quiz/{aid}", self.cl.get("/welcome").get_data(as_text=True))
        self.submit(aid, right={self.topics[0]})
        html = self.cl.get("/dashboard").get_data(as_text=True)
        self.assertEqual(re.findall(r"(\d)-dars\. (Mavzu \d)", html), [("1", "Mavzu 2"), ("2", "Mavzu 3")])
        self.assertEqual([self.status(t) for t in self.topics], [200, 200, 403])
        self.read(self.topics[0])
        self.assertEqual(self.post(self.cl, f"/api/topic/{self.topics[0]}/test/start")[0], 403)
        self.assertFalse(self.post(self.cl, "/api/diagnostic/start")[1]["ok"])     # faqat bir marta

    def test_diagnostics_leaves_questions_for_topic_test(self):
        tid = self.topic("Kichik", 4, n=4)
        self.settings(diag_per_topic=4)
        aid = self.start("/api/diagnostic/start")
        self.assertEqual(sum(q["topic_id"] == tid for q in self.payload(aid)), 1)

    # ---- Mavzu testi ----
    def test_pass_opens_next(self):
        self.decline()
        self.take(self.topics[0])
        self.assertEqual([self.status(t) for t in self.topics], [200, 200, 403])
        self.read(self.topics[0])
        self.assertEqual(self.post(self.cl, f"/api/topic/{self.topics[0]}/test/start")[0], 403)

    def test_count_comes_from_settings(self):
        self.decline()
        self.read(self.topics[0])
        self.assertEqual(len(self.qids(self.start(f"/api/topic/{self.topics[0]}/test/start"))), 4)

    def test_fail_requires_relearning(self):
        self.decline()
        t = self.topics[0]
        self.take(t, right=False)
        self.assertEqual([self.status(x) for x in self.topics], [200, 403, 403])
        code, r = self.post(self.cl, f"/api/topic/{t}/test/start")      # materiallar qaytadan o'qilishi kerak
        self.assertEqual(code, 400)
        self.assertIn("materiallar", r["error"])
        self.take(t)
        self.assertEqual(self.status(self.topics[1]), 200)

    def test_question_never_repeats(self):
        aid = self.start("/api/diagnostic/start")
        used = self.qids(aid)
        self.submit(aid, right=False)
        t = self.topics[0]
        for size in (4, 4):                                   # 10 - 2 (diagnostika) = 8
            aid = self.take(t, right=False)
            self.assertEqual(len(self.qids(aid)), size)
            used += self.qids(aid)
        self.assertEqual(len(used), len(set(used)))
        self.read(t)
        code, r = self.post(self.cl, f"/api/topic/{t}/test/start")
        self.assertEqual(code, 400)
        self.assertIn("yangi savollar qolmadi", r["error"])
        self.assertIn("yangi savollar qolmadi", self.cl.get(f"/topic/{t}").get_data(as_text=True))
        self.assertIn("1 o'quvchi yangi savol kutmoqda", self.admin.get("/admin").get_data(as_text=True))
        self.add_questions(t, 3)                              # admin savol qo'shdi
        aid = self.start(f"/api/topic/{t}/test/start")
        self.assertEqual(len(self.qids(aid)), 3)
        self.assertFalse(set(self.qids(aid)) & set(used))

    def test_parallel_starts_give_one_attempt(self):
        self.decline()
        t = self.topics[0]
        self.read(t)

        pm = password_mark(self.sql("SELECT * FROM users WHERE id=?", self.uid)[0])

        def go(_):
            cl = app.test_client()
            with cl.session_transaction() as s:
                s["uid"], s["pm"] = self.uid, pm
            return cl.post(f"/api/topic/{t}/test/start", json={}).get_json()["redirect"]
        with ThreadPoolExecutor(6) as ex:
            self.assertEqual(len(set(ex.map(go, range(6)))), 1)

    def test_wrong_answers_shown(self):
        self.decline()
        aid = self.take(self.topics[0], right=False)
        html = self.cl.get(f"/result/{aid}").get_data(as_text=True).replace("&#39;", "'")
        self.assertEqual(html.count("<em>Sizning javobingiz</em>"), 4)
        self.assertEqual(html.count("<em>To'g'ri javob</em>"), 4)

    def test_results_are_clickable_and_unfinished_on_home(self):
        self.decline()
        aid = self.take(self.topics[0])
        self.assertIn(f'data-href="/result/{aid}"', self.cl.get("/results").get_data(as_text=True))
        eid = self.sql("SELECT id FROM exams LIMIT 1")[0]["id"]
        ex = self.start(f"/api/exam/{eid}/start")
        self.assertIn(f'href="/quiz/{ex}"', self.cl.get("/dashboard").get_data(as_text=True))

    # ---- Bo'sh mavzu ----
    def test_empty_topic_is_not_mastered_and_does_not_block(self):
        self.sql("UPDATE topics SET position=position+10")
        new = self.sql("INSERT INTO topics(title, position) VALUES ('Yangi mavzu', 1)")
        self.decline()
        html = self.cl.get("/dashboard").get_data(as_text=True)
        self.assertIn("Tayyorlanmoqda", html)
        self.assertIn("0/3", html)                            # bo'sh mavzu hisobga kirmaydi
        self.assertNotIn(f'href="/topic/{new}"', html)
        self.assertEqual([self.status(t) for t in (new, *self.topics[:2])], [403, 200, 403])
        self.assertIn("tayyorlanmoqda", self.cl.get(f"/topic/{new}").get_data(as_text=True))
        self.assertIn("Bo'sh</span>", self.admin.get("/admin").get_data(as_text=True).replace("&#39;", "'"))
        # Material qo'shilsa ochiladi, o'qilmaguncha o'tilgan emas
        mid = self.sql("INSERT INTO materials(topic_id, title, body) VALUES (?, 'M', 'x')", new)
        self.assertEqual([self.status(t) for t in (new, self.topics[0])], [200, 403])
        self.assertEqual(self.post(self.cl, f"/api/material/{mid}/read")[0], 200)
        self.assertEqual(self.status(self.topics[0]), 200)
        # Keyin test qo'shilsa, mavzu testdan o'tilishi kerak
        self.add_questions(new, 4)
        self.assertEqual(self.status(self.topics[0]), 403)
        self.take(new)
        self.assertEqual(self.status(self.topics[0]), 200)

    def test_only_empty_topics(self):
        self.sql("DELETE FROM topics")
        self.sql("INSERT INTO topics(title, position) VALUES ('Yangi', 1)")
        self.decline()
        html = self.cl.get("/dashboard").get_data(as_text=True)
        self.assertIn("Darslar tayyorlanmoqda", html)
        self.assertNotIn("bajarildi!", html)

    # ---- Xatolarim ----
    def test_mistakes_lists_topics_failed_first_time(self):
        self.decline()
        t1, t2, _ = self.topics
        self.assertIn("Xatolar yo", self.cl.get("/mistakes").get_data(as_text=True))
        self.take(t1, right=False)
        self.assertIn("Hali o&#39;tilmagan".replace("&#39;", "'"),
                      self.cl.get("/mistakes").get_data(as_text=True).replace("&#39;", "'"))
        self.take(t1)
        self.take(t2)                                         # birinchi urinishda o'tdi
        html = self.cl.get("/mistakes").get_data(as_text=True).replace("&#39;", "'")
        self.assertIn(f"/api/topic/{t1}/restudy", html)
        self.assertIn("Keyin o'zlashtirildi", html)
        self.assertNotIn(f"/api/topic/{t2}/restudy", html)
        self.assertEqual((self.progress(t1)["first_failed"], self.progress(t2)["first_failed"]), (1, 0))

    def test_restudy_passed_topic(self):
        self.decline()
        t1, t2, t3 = self.topics
        first = self.take(t1, right=False)
        second = self.take(t1)
        code, r = self.post(self.cl, f"/api/topic/{t1}/restudy")
        self.assertEqual((code, r["redirect"]), (200, f"/topic/{t1}"))
        self.assertEqual(self.post(self.cl, f"/api/topic/{t1}/test/start")[0], 400)   # avval o'qiladi
        self.add_questions(t1, 4)
        third = self.take(t1, right=False)                    # yomon natija oldingi yutuqni bekor qilmaydi
        ids = self.qids(first) + self.qids(second) + self.qids(third)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(self.progress(t1)["passed"], 1)
        self.assertEqual(self.status(t2), 200)

    def test_restudy_rules(self):
        self.decline()
        t1, t2, t3 = self.topics
        self.take(t1)
        self.assertEqual(self.post(self.cl, f"/api/topic/{t1}/restudy")[0], 403)      # xatosi yo'q
        self.assertEqual(self.post(self.cl, f"/api/topic/{t3}/restudy")[0], 403)      # yopiq
        self.assertEqual(self.post(self.cl, "/api/topic/999999/restudy")[0], 404)
        self.take(t2, right=False)
        self.read(t2)
        self.assertEqual(self.post(self.cl, f"/api/topic/{t2}/restudy")[0], 200)      # o'qilganlar yo'qolmaydi
        self.start(f"/api/topic/{t2}/test/start")

    def test_migration_of_first_failed(self):
        self.sql("INSERT INTO progress(user_id, topic_id, passed, attempts) VALUES (?, ?, 1, 2)", self.uid, self.topics[0])
        self.sql("INSERT INTO progress(user_id, topic_id, passed, attempts) VALUES (?, ?, 1, 1)", self.uid, self.topics[1])
        for t, score in ((0, 1), (0, 4), (1, 4)):
            self.sql("INSERT INTO attempts(user_id, kind, topic_id, payload, created_at, finished_at, score, total) "
                     "VALUES (?, 'topic', ?, '[]', 0, 1, ?, 4)", self.uid, self.topics[t], score)
        self.sql("ALTER TABLE progress DROP COLUMN first_failed")
        c.init_db()
        self.assertEqual([self.progress(t)["first_failed"] for t in self.topics[:2]], [1, 0])

    # ---- Imtihonlar: avval yangi savollar ----
    def test_exam_prefers_unseen(self):
        self.settings(olympiad_count=4)
        eid = self.sql("INSERT INTO exams(kind, title, time_limit, created_at) VALUES ('olympiad', 'O', 30, 0)")
        for i in range(8):
            self.sql("INSERT INTO exam_questions(exam_id, text, o1, o2, o3, o4, correct) "
                     "VALUES (?, ?, 'a', 'b', 'c', 'd', 1)", eid, f"s{i}")
        seen = []
        for _ in range(2):
            aid = self.start(f"/api/exam/{eid}/start")
            seen += self.qids(aid)
            self.submit(aid)
        self.assertEqual(len(set(seen)), 8)
        self.assertEqual(len(self.qids(self.start(f"/api/exam/{eid}/start"))), 4)
        self.sql("DELETE FROM exams WHERE id=?", eid)

    # ---- Admin: Test sozlamalari ----
    def form(self, **kw):
        conn = c.get_db()
        try:
            base = {k: str(v) for k, v in c.get_settings(conn).items()}
        finally:
            conn.close()
        return {**base, **kw}

    def test_settings_choose_diagnostic_topics(self):
        t1, t2, t3 = self.topics
        html = self.admin_post("/admin/settings", **self.form(**{
            f"diag_on_{t1}": "on", f"diag_n_{t1}": "3", f"diag_n_{t2}": "5", f"diag_on_{t3}": "on", f"diag_n_{t3}": "1"}))
        self.assertIn("Test sozlamalari saqlandi", html)
        counts = [r["diag_count"] for r in self.sql("SELECT diag_count FROM topics ORDER BY position")]
        self.assertEqual(counts, [3, 0, 1])
        aid = self.start("/api/diagnostic/start")
        self.assertEqual([q["topic_id"] for q in self.payload(aid)], [t1, t1, t1, t3])

    def test_settings_validation(self):
        for bad in ({"pass_percent": "0"}, {"high_percent": "101"}, {"topic_count": "0"}):
            r = self.admin.post("/admin/settings", data={"_csrf": self.csrf(), **self.form(**bad)})
            self.assertEqual(r.status_code, 200)
            self.assertNotIn("saqlandi", r.get_data(as_text=True))

    # ---- Admin: mavzu ----
    def test_topic_create_edit_delete(self):
        html = self.admin_post("/admin/topic/new", title="Yangi mavzu", position="9", published="on")
        self.assertIn("Mavzu yaratildi", html)
        tid = self.sql("SELECT id FROM topics WHERE title='Yangi mavzu'")[0]["id"]
        self.assertIn("Tahrirlangan", self.admin_post(f"/admin/topic/{tid}/save", title="Tahrirlangan", position="9"))
        self.assertIn("balli va vaqti saqlandi", self.admin_post(f"/admin/topic/{tid}/test", test_time="25", test_points="1,5"))
        t = self.sql("SELECT * FROM topics WHERE id=?", tid)[0]
        self.assertEqual((t["test_time"], t["test_points"]), (25, 1.5))
        self.assertIn("vaqtni", self.admin_post(f"/admin/topic/{tid}/test", test_time="0", test_points="1"))
        self.assertIn("ballni", self.admin_post(f"/admin/topic/{tid}/test", test_time="5", test_points=""))
        self.assertIn("chirildi", self.admin_post(f"/admin/topic/{tid}/delete"))
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM topics WHERE id=?", tid)[0]["n"], 0)

    def test_material_image(self):
        t1, t2, _ = self.topics
        self.admin_post(f"/admin/topic/{t1}/material", title="Rasmli", position="2", image=(io.BytesIO(PNG), "a.png"))
        m = self.sql("SELECT * FROM materials WHERE title='Rasmli'")[0]
        path = os.path.join(c.FILES_DIR, m["image"])
        self.assertTrue(os.path.exists(path))
        r = self.admin.get(f"/admin/material/{m['id']}/image")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        r.close()
        self.assertEqual(self.cl.get(f"/material-image/{m['id']}").status_code, 403)     # hali qaror qilmagan
        self.decline()
        r = self.cl.get(f"/material-image/{m['id']}")
        self.assertEqual(r.status_code, 200)
        r.close()
        self.assertIn(f"/material-image/{m['id']}", self.cl.get(f"/topic/{t1}").get_data(as_text=True))
        self.sql("UPDATE materials SET topic_id=? WHERE id=?", t2, m["id"])
        self.assertEqual(self.cl.get(f"/material-image/{m['id']}").status_code, 403)     # yopiq dars
        # Rasm almashtirilsa eski fayl o'chadi; rasmsiz va matnsiz saqlab bo'lmaydi
        self.admin_post(f"/admin/material/{m['id']}", title="Rasmli", body="matn", image=(io.BytesIO(PNG), "b.png"))
        self.assertFalse(os.path.exists(path))
        new = os.path.join(c.FILES_DIR, self.sql("SELECT image FROM materials WHERE id=?", m["id"])[0]["image"])
        r = self.admin.post(f"/admin/material/{m['id']}", data={"_csrf": self.csrf(), "title": "Rasmli", "image_delete": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(os.path.exists(new))
        self.admin_post(f"/admin/topic/{t2}/delete")
        self.assertFalse(os.path.exists(new))

    def test_material_bad_image(self):
        n = len(os.listdir(c.FILES_DIR)) if os.path.isdir(c.FILES_DIR) else 0
        html = self.admin_post(f"/admin/topic/{self.topics[0]}/material", title="Yomon", body="x",
                               image=(io.BytesIO(b"<svg onload=alert(1)>"), "a.png"))
        self.assertIn("Faqat JPG, PNG", html)
        self.assertEqual(len(os.listdir(c.FILES_DIR)) if os.path.isdir(c.FILES_DIR) else 0, n)

    def test_excel_template_and_import(self):
        r = self.admin.get("/admin/template/topic.xlsx")
        items, errors = excel_io.parse_xlsx(r.data, "topic")
        self.assertEqual((len(items), errors), (2, []))
        tid = self.topic("Excel", 5, n=0)
        html = self.admin_post(f"/admin/topic/{tid}/import-xlsx", file=(io.BytesIO(r.data), "n.xlsx"))
        self.assertIn("2 ta savol qo'shildi", html)
        html = self.admin_post(f"/admin/topic/{tid}/question", text="Yangi savol?", o1="1", o2="2", o3="3", o4="4", correct="2")
        self.assertIn("Savol qo'shildi", html)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM questions WHERE topic_id=?", tid)[0]["n"], 3)
        r = self.admin.get("/admin/template/exam.xlsx")
        self.assertEqual(len(excel_io.parse_xlsx(r.data, "exam")[0]), 2)
