"""Test vaqti va to'xtatish qoidalari serverda tekshirilishi."""
import json
import time

from tests.base import Base


class QuizTime(Base):
    N = 4
    EARLY = [0, 1, None, None]     # o'z vaqtida saqlangan javoblar
    LATE = [0, 0, 0, 0]            # kechikib yuborilgan javoblar (hammasi to'g'ri)

    def setUp(self):
        self.uid, self.cl = self.new_user()

    def make(self, left=600, paused=0, time_left=None, draft=True):
        """left: muddatgacha qolgan soniya (manfiy = vaqt tugagan, None = vaqtsiz)."""
        payload = [
            {"id": i, "topic_id": None, "topic": "", "text": "?", "options": list("abcd"), "correct": 0,
             "points": 1, "section": "", "explanation": ""} for i in range(self.N)
        ]
        now = int(time.time())
        return self.sql(
            "INSERT INTO attempts(user_id, kind, deadline, paused, time_left, draft, payload, created_at) "
            "VALUES (?, 'diagnostic', ?, ?, ?, ?, ?, ?)",
            self.uid, None if left is None else now + left, paused, time_left,
            json.dumps(self.EARLY) if draft else None, json.dumps(payload), now - 3600,
        )

    def call(self, aid, action, answers=None):
        return self.post(self.cl, f"/api/quiz/{aid}/{action}", answers=answers or self.LATE)

    # ---- O'z vaqtida: oddiy ish ----
    def test_save_in_time(self):
        aid = self.make()
        code, r = self.call(aid, "save")
        self.assertEqual((code, r["ok"]), (200, True))
        self.assertEqual(self.draft(aid), self.LATE)

    def test_submit_in_time(self):
        aid = self.make()
        code, r = self.call(aid, "submit")
        self.assertEqual((code, r["redirect"]), (200, f"/result/{aid}"))
        self.assertEqual(self.result(aid), self.LATE)
        self.assertEqual(self.attempt(aid)["score"], self.N)

    def test_untimed_is_never_late(self):
        aid = self.make(left=None)
        self.assertEqual(self.call(aid, "save")[0], 200)
        self.assertEqual(self.call(aid, "submit")[0], 200)
        self.assertEqual(self.result(aid), self.LATE)

    def test_autosubmit_within_grace(self):
        """Brauzer vaqt tugagan zahoti yuboradi: tarmoq kechikishi kechiriladi."""
        aid = self.make(left=-5)
        self.assertEqual(self.call(aid, "submit")[0], 200)
        self.assertEqual(self.result(aid), self.LATE)

    # ---- Kechikkan so'rovlar: saqlangan javoblar bilan yakunlanadi ----
    def check_late(self, action):
        aid = self.make(left=-120)
        code, r = self.call(aid, action)
        self.assertEqual(code, 410)
        self.assertFalse(r["ok"])
        self.assertEqual(r["redirect"], f"/result/{aid}")
        self.assertIsNotNone(self.attempt(aid)["finished_at"])
        self.assertEqual(self.result(aid), self.EARLY)
        self.assertEqual(self.attempt(aid)["score"], 1)

    def test_late_save(self):
        self.check_late("save")

    def test_late_submit(self):
        self.check_late("submit")

    def test_late_submit_without_draft(self):
        aid = self.make(left=-120, draft=False)
        self.assertEqual(self.call(aid, "submit")[0], 410)
        self.assertEqual(self.attempt(aid)["score"], 0)

    def test_late_bad_body_still_finishes(self):
        aid = self.make(left=-120)
        self.assertEqual(self.post(self.cl, f"/api/quiz/{aid}/submit", answers="x")[0], 410)
        self.assertEqual(self.result(aid), self.EARLY)

    # ---- To'xtatish olib tashlangan; eski bazada to'xtatilgan testlar davom ettiriladi ----
    def test_no_pause_or_discard(self):
        aid = self.make()
        for action in ("pause", "discard"):
            self.assertEqual(self.call(aid, action)[0], 404)
        self.assertEqual(self.attempt(aid)["paused"], 0)

    def test_old_paused_attempt_resumes_with_its_time(self):
        aid = self.make(left=None, paused=1, time_left=300)
        r = self.cl.get(f"/api/quiz/{aid}").get_json()
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["remaining"], 300, delta=3)
        self.assertEqual(r["answers"], self.EARLY)
        self.assertEqual(self.attempt(aid)["paused"], 0)

    def test_resume_with_no_time_left(self):
        """Eski bazada qolgan vaqti 0 bo'lib to'xtatilgan test davom ettirilmaydi."""
        aid = self.make(left=None, paused=1, time_left=0)
        r = self.cl.get(f"/api/quiz/{aid}")
        self.assertEqual(r.status_code, 410)
        self.assertEqual(self.result(aid), self.EARLY)

    def test_save_and_submit_while_paused(self):
        for action in ("save", "submit"):
            with self.subTest(action):
                aid = self.make(left=None, paused=1, time_left=300)
                code, r = self.call(aid, action)
                self.assertEqual(code, 409)
                self.assertEqual(r["redirect"], f"/quiz/{aid}")
                self.assertIsNone(self.attempt(aid)["finished_at"])
                self.assertEqual(self.draft(aid), self.EARLY)

    # ---- Boshqalar ----
    def test_finished_stays_unchanged(self):
        aid = self.make()
        self.call(aid, "submit", self.EARLY)
        for action in ("save", "submit"):
            code, r = self.call(aid, action)
            self.assertEqual((code, r["redirect"]), (200, f"/result/{aid}"))
        self.assertEqual(self.result(aid), self.EARLY)

    def test_other_users_attempt(self):
        aid = self.make(left=-120)
        _, other = self.new_user()
        for action in ("save", "submit"):
            self.assertEqual(self.post(other, f"/api/quiz/{aid}/{action}", answers=self.LATE)[0], 404)
        self.assertIsNone(self.attempt(aid)["finished_at"])
