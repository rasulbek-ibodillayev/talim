"""O'quv qismi: profil, diagnostik test, mavzular, materiallar, mavzu testlari, admin panel."""
import json
import os
import random
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, abort, flash, redirect, render_template, request, send_from_directory, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import common as c
import seed
from web_utils import (
    admin_required, api_login_required, body, check_csrf, current_user, fail,
    json_only, login_required, ok,
)

bp = Blueprint("learn", __name__)

DIAG_PER_TOPIC = 3      # diagnostik testda har bir mavzudan nechta savol
TEST_SIZE = 8           # mavzu testidagi maksimal savollar soni
MAX_AVATAR = 2 * 1024 * 1024
TZ = timezone(timedelta(hours=5))   # O'zbekiston vaqti

c.init_db()
_conn = c.get_db()
try:
    seed.seed_if_empty(_conn)
finally:
    _conn.close()


# ---------------- Jinja filtrlari ----------------
@bp.app_template_filter("paragraphs")
def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]


@bp.app_template_filter("dt")
def fmt_dt(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m.%Y %H:%M")


@bp.app_template_filter("pct")
def pct(score, total):
    return round(100 * score / total) if total else 0


# ---------------- Yordamchi funksiyalar ----------------
def one_line(v, mx):
    return " ".join(str(v or "").split())[:mx]


def block(v, mx):
    return str(v or "").replace("\r\n", "\n").strip()[:mx]


def valid_url(u):
    return bool(re.match(r"^https?://[^\s<>\"']+$", u or ""))


def path_data(conn, uid):
    """Foydalanuvchining o'quv yo'li: mavzular holati bilan, tavsiya tartibida."""
    rows = conn.execute(
        """
        SELECT t.id, t.title, t.summary, t.position,
          (SELECT COUNT(*) FROM materials m WHERE m.topic_id = t.id) AS mat_total,
          (SELECT COUNT(*) FROM reads r JOIN materials m ON m.id = r.material_id
             WHERE m.topic_id = t.id AND r.user_id = ?) AS mat_read,
          p.diag_percent, p.best_percent,
          COALESCE(p.passed, 0) AS passed, COALESCE(p.attempts, 0) AS attempts
        FROM topics t LEFT JOIN progress p ON p.topic_id = t.id AND p.user_id = ?
        WHERE t.published = 1 ORDER BY t.position, t.id
        """,
        (uid, uid),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        dp = d["diag_percent"]
        if d["passed"]:
            d["status"], d["label"], d["rank"] = "done", "O'zlashtirilgan", 3
        elif dp is not None and dp < c.PASS_PERCENT:
            d["status"], d["label"], d["rank"] = "weak", "O'rganish tavsiya etiladi", 0
        elif dp is not None:
            d["status"], d["label"], d["rank"] = "strong", "Yaxshi bilasiz", 2
        else:
            d["status"], d["label"], d["rank"] = "new", "Boshlanmagan", 1
        out.append(d)
    out.sort(key=lambda d: (d["rank"], (d["diag_percent"] or 0) if d["rank"] == 0 else 0, d["position"], d["id"]))
    return out


def get_attempt(conn, aid, uid):
    a = conn.execute("SELECT * FROM attempts WHERE id = ? AND user_id = ?", (aid, uid)).fetchone()
    if a is None:
        abort(404)
    return a


# ---------------- Bosh sahifa ----------------
@bp.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    conn = c.get_db()
    try:
        topics = path_data(conn, user["id"])
        diag = conn.execute(
            "SELECT * FROM attempts WHERE user_id = ? AND kind = 'diagnostic' AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 1", (user["id"],),
        ).fetchone()
        recent = conn.execute(
            """SELECT a.*, t.title AS topic_title FROM attempts a
               LEFT JOIN topics t ON t.id = a.topic_id
               WHERE a.user_id = ? AND a.finished_at IS NOT NULL ORDER BY a.id DESC LIMIT 5""",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    done = sum(1 for t in topics if t["passed"])
    next_topic = next((t for t in topics if not t["passed"]), None)
    return render_template(
        "dashboard.html", topics=topics, diag=diag, recent=recent, done=done,
        total=len(topics), next_topic=next_topic,
    )


# ---------------- Profil ----------------
@bp.get("/profile")
@login_required
def profile():
    return render_template("profile.html", regions=c.REGIONS, this_year=datetime.now(TZ).year)


@bp.post("/api/profile")
@api_login_required
@json_only
def profile_save():
    d = body()
    first = one_line(d.get("first_name"), 50)
    last = one_line(d.get("last_name"), 50)
    region = str(d.get("region", ""))
    education = one_line(d.get("education"), 100)
    bio = block(d.get("bio"), 300)
    by_raw = str(d.get("birth_year") or "").strip()
    if len(first) < 2 or len(last) < 2:
        return fail("Ism va familiya kamida 2 ta belgidan iborat bo'lishi kerak.")
    if region not in c.REGIONS:
        return fail("Hududni ro'yxatdan tanlang.")
    birth_year = None
    if by_raw:
        if not by_raw.isdigit() or not (1930 <= int(by_raw) <= datetime.now(TZ).year - 5):
            return fail("Tug'ilgan yilni to'g'ri kiriting.")
        birth_year = int(by_raw)
    conn = c.get_db()
    try:
        conn.execute(
            "UPDATE users SET first_name=?, last_name=?, region=?, education=?, bio=?, birth_year=? WHERE id=?",
            (first, last, region, education, bio, birth_year, current_user()["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return ok(message="Ma'lumotlar saqlandi.")


@bp.post("/api/profile/password")
@api_login_required
@json_only
def password_change():
    user = current_user()
    d = body()
    old, new, new2 = str(d.get("old", "")), str(d.get("new", "")), str(d.get("new2", ""))
    conn = c.get_db()
    try:
        key = f"pw:{user['id']}"
        if c.too_many(conn, key, 5, 900):
            return fail("Juda ko'p urinish. Birozdan keyin qayta urinib ko'ring.", 429)
        if not check_password_hash(user["password_hash"], old):
            c.hit(conn, key)
            return fail("Joriy parol noto'g'ri.")
        if len(new) < 8 or len(new) > 128:
            return fail("Yangi parol kamida 8 ta belgidan iborat bo'lishi kerak.")
        if new != new2:
            return fail("Yangi parollar bir xil emas.")
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), user["id"]))
        conn.commit()
    finally:
        conn.close()
    return ok(message="Parol o'zgartirildi.")


def sniff_image(data):
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def remove_avatar_file(name):
    if name and re.match(r"^\d+_[0-9a-f]{12}\.(jpg|png|webp)$", name):
        try:
            os.remove(os.path.join(c.AVATAR_DIR, name))
        except OSError:
            pass


@bp.post("/api/profile/avatar")
@api_login_required
def avatar_upload():
    check_csrf()
    user = current_user()
    f = request.files.get("avatar")
    if not f:
        return fail("Rasm tanlanmagan.")
    data = f.read(MAX_AVATAR + 1)
    if len(data) > MAX_AVATAR:
        return fail("Rasm hajmi 2 MB dan oshmasligi kerak.", 413)
    ext = sniff_image(data)
    if not ext:
        return fail("Faqat JPG, PNG yoki WEBP rasm yuklash mumkin.")
    os.makedirs(c.AVATAR_DIR, exist_ok=True)
    name = f"{user['id']}_{secrets.token_hex(6)}.{ext}"
    with open(os.path.join(c.AVATAR_DIR, name), "wb") as out:
        out.write(data)
    conn = c.get_db()
    try:
        conn.execute("UPDATE users SET avatar=? WHERE id=?", (name, user["id"]))
        conn.commit()
    finally:
        conn.close()
    remove_avatar_file(user["avatar"])
    return ok(url=f"/avatar/{name}")


@bp.post("/api/profile/avatar/delete")
@api_login_required
@json_only
def avatar_delete():
    user = current_user()
    conn = c.get_db()
    try:
        conn.execute("UPDATE users SET avatar=NULL WHERE id=?", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    remove_avatar_file(user["avatar"])
    return ok()


@bp.get("/avatar/<name>")
def avatar_file(name):
    if not re.match(r"^\d+_[0-9a-f]{12}\.(jpg|png|webp)$", name):
        abort(404)
    resp = send_from_directory(c.AVATAR_DIR, name, max_age=86400)
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


# ---------------- Diagnostik test ----------------
@bp.get("/diagnostic")
@login_required
def diagnostic():
    user = current_user()
    conn = c.get_db()
    try:
        history = conn.execute(
            "SELECT * FROM attempts WHERE user_id=? AND kind='diagnostic' AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 10", (user["id"],),
        ).fetchall()
        n_topics = conn.execute(
            "SELECT COUNT(DISTINCT q.topic_id) FROM questions q JOIN topics t ON t.id=q.topic_id "
            "WHERE q.kind='diagnostic' AND t.published=1"
        ).fetchone()[0]
    finally:
        conn.close()
    return render_template("diagnostic.html", history=history, n_topics=n_topics, per_topic=DIAG_PER_TOPIC)


def build_payload(conn, kind, topic_id=None):
    if kind == "diagnostic":
        picked = []
        for t in conn.execute("SELECT id, title FROM topics WHERE published=1 ORDER BY position, id"):
            qs = conn.execute(
                "SELECT * FROM questions WHERE topic_id=? AND kind='diagnostic'", (t["id"],)
            ).fetchall()
            random.shuffle(qs)
            picked += [(t, q) for q in qs[:DIAG_PER_TOPIC]]
        random.shuffle(picked)
    else:
        t = conn.execute("SELECT id, title FROM topics WHERE id=? AND published=1", (topic_id,)).fetchone()
        qs = conn.execute("SELECT * FROM questions WHERE topic_id=? AND kind='topic'", (topic_id,)).fetchall()
        random.shuffle(qs)
        picked = [(t, q) for q in qs[:TEST_SIZE]]
    payload = []
    for t, q in picked:
        opts = [q["o1"], q["o2"], q["o3"], q["o4"]]
        order = list(range(4))
        random.shuffle(order)
        payload.append({
            "qid": q["id"], "topic_id": t["id"], "topic": t["title"], "text": q["text"],
            "options": [opts[i] for i in order],
            "correct": order.index(q["correct"] - 1),
            "explanation": q["explanation"],
        })
    return payload


def start_attempt(conn, user, kind, topic_id=None):
    """Test sessiyasini boshlaydi yoki tugallanmagan (2 soatdan yangi) sessiyani qaytaradi."""
    key = f"quiz:{user['id']}"
    if c.too_many(conn, key, 40, 3600):
        return None, fail("Juda ko'p urinish. Birozdan keyin qayta urinib ko'ring.", 429)
    now = int(time.time())
    ex = conn.execute(
        "SELECT id FROM attempts WHERE user_id=? AND kind=? AND COALESCE(topic_id,0)=? "
        "AND finished_at IS NULL AND created_at > ? ORDER BY id DESC LIMIT 1",
        (user["id"], kind, topic_id or 0, now - 7200),
    ).fetchone()
    if ex:
        return ex["id"], None
    payload = build_payload(conn, kind, topic_id)
    if not payload:
        return None, fail("Bu test uchun savollar hali kiritilmagan.")
    c.hit(conn, key)
    cur = conn.execute(
        "INSERT INTO attempts(user_id, kind, topic_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
        (user["id"], kind, topic_id, json.dumps(payload, ensure_ascii=False), now),
    )
    conn.commit()
    return cur.lastrowid, None


@bp.post("/api/diagnostic/start")
@api_login_required
@json_only
def diagnostic_start():
    conn = c.get_db()
    try:
        aid, err = start_attempt(conn, current_user(), "diagnostic")
    finally:
        conn.close()
    if err:
        return err
    return ok(redirect=url_for("learn.quiz_page", aid=aid))


@bp.post("/api/topic/<int:tid>/test/start")
@api_login_required
@json_only
def topic_test_start(tid):
    user = current_user()
    conn = c.get_db()
    try:
        if not conn.execute("SELECT 1 FROM topics WHERE id=? AND published=1", (tid,)).fetchone():
            return fail("Mavzu topilmadi.", 404)
        left = conn.execute(
            "SELECT COUNT(*) FROM materials m WHERE m.topic_id=? AND NOT EXISTS "
            "(SELECT 1 FROM reads r WHERE r.material_id=m.id AND r.user_id=?)", (tid, user["id"]),
        ).fetchone()[0]
        if left:
            return fail("Avval mavzudagi barcha materiallar bilan tanishib chiqing.")
        aid, err = start_attempt(conn, user, "topic", tid)
    finally:
        conn.close()
    if err:
        return err
    return ok(redirect=url_for("learn.quiz_page", aid=aid))


@bp.get("/quiz/<int:aid>")
@login_required
def quiz_page(aid):
    conn = c.get_db()
    try:
        a = get_attempt(conn, aid, current_user()["id"])
        if a["finished_at"]:
            return redirect(url_for("learn.result_page", aid=aid))
        title = "Diagnostik test"
        back = url_for("learn.diagnostic")
        if a["kind"] == "topic":
            t = conn.execute("SELECT title FROM topics WHERE id=?", (a["topic_id"],)).fetchone()
            title = f"Mavzu testi: {t['title']}" if t else "Mavzu testi"
            back = url_for("learn.topic_page", tid=a["topic_id"])
    finally:
        conn.close()
    return render_template("quiz.html", aid=aid, title=title, back=back)


@bp.get("/api/quiz/<int:aid>")
@api_login_required
def quiz_data(aid):
    conn = c.get_db()
    try:
        a = get_attempt(conn, aid, current_user()["id"])
        if a["finished_at"]:
            return fail("Bu test yakunlangan.", 410, redirect=url_for("learn.result_page", aid=aid))
        payload = json.loads(a["payload"])
    finally:
        conn.close()
    return ok(questions=[{"text": q["text"], "options": q["options"], "topic": q["topic"]} for q in payload])


@bp.post("/api/quiz/<int:aid>/submit")
@api_login_required
@json_only
def quiz_submit(aid):
    user = current_user()
    conn = c.get_db()
    try:
        a = get_attempt(conn, aid, user["id"])
        if a["finished_at"]:
            return ok(redirect=url_for("learn.result_page", aid=aid))
        payload = json.loads(a["payload"])
        answers = body().get("answers")
        if not isinstance(answers, list) or len(answers) != len(payload):
            return fail("Javoblar noto'g'ri formatda.")
        clean = []
        for x in answers:
            if x is None:
                clean.append(None)
            elif isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 3:
                clean.append(x)
            else:
                return fail("Javoblar noto'g'ri formatda.")

        score = 0
        per_topic = {}
        for q, ans in zip(payload, clean):
            right = ans == q["correct"]
            score += right
            t = per_topic.setdefault(q["topic_id"], {"id": q["topic_id"], "title": q["topic"], "correct": 0, "total": 0})
            t["total"] += 1
            t["correct"] += right
        topics_res = []
        for t in per_topic.values():
            t["percent"] = round(100 * t["correct"] / t["total"])
            topics_res.append(t)
        total = len(payload)
        percent = round(100 * score / total)

        cur = conn.execute(
            "UPDATE attempts SET finished_at=?, score=?, total=?, result=? WHERE id=? AND finished_at IS NULL",
            (int(time.time()), score, total, json.dumps({"answers": clean, "topics": topics_res}), aid),
        )
        if cur.rowcount == 1:
            if a["kind"] == "diagnostic":
                for t in topics_res:
                    conn.execute(
                        "INSERT INTO progress(user_id, topic_id, diag_percent, best_percent, passed, attempts) "
                        "VALUES (?, ?, ?, NULL, 0, 0) "
                        "ON CONFLICT(user_id, topic_id) DO UPDATE SET diag_percent=excluded.diag_percent",
                        (user["id"], t["id"], t["percent"]),
                    )
            else:
                passed = 1 if percent >= c.PASS_PERCENT else 0
                conn.execute(
                    "INSERT INTO progress(user_id, topic_id, diag_percent, best_percent, passed, attempts) "
                    "VALUES (?, ?, NULL, ?, ?, 1) "
                    "ON CONFLICT(user_id, topic_id) DO UPDATE SET "
                    "best_percent=MAX(COALESCE(best_percent, 0), excluded.best_percent), "
                    "passed=MAX(passed, excluded.passed), attempts=attempts+1",
                    (user["id"], a["topic_id"], percent, passed),
                )
        conn.commit()
    finally:
        conn.close()
    return ok(redirect=url_for("learn.result_page", aid=aid))


@bp.get("/result/<int:aid>")
@login_required
def result_page(aid):
    user = current_user()
    conn = c.get_db()
    try:
        a = get_attempt(conn, aid, user["id"])
        if not a["finished_at"]:
            return redirect(url_for("learn.quiz_page", aid=aid))
        payload = json.loads(a["payload"])
        res = json.loads(a["result"])
        topics = path_data(conn, user["id"])
        topic = None
        if a["kind"] == "topic":
            topic = conn.execute("SELECT id, title FROM topics WHERE id=?", (a["topic_id"],)).fetchone()
    finally:
        conn.close()
    review = []
    for q, ans in zip(payload, res["answers"]):
        review.append({**q, "chosen": ans, "right": ans == q["correct"]})
    percent = round(100 * a["score"] / a["total"]) if a["total"] else 0
    weak = sorted([t for t in res["topics"] if t["percent"] < c.PASS_PERCENT], key=lambda t: t["percent"])
    strong = [t for t in res["topics"] if t["percent"] >= c.PASS_PERCENT]
    next_topic = next((t for t in topics if not t["passed"] and t["id"] != a["topic_id"]), None)
    return render_template(
        "result.html", a=a, percent=percent, topics_res=res["topics"], review=review,
        weak=weak, strong=strong, topic=topic, passed=percent >= c.PASS_PERCENT,
        next_topic=next_topic, pass_percent=c.PASS_PERCENT,
    )


# ---------------- Mavzular va materiallar ----------------
@bp.get("/path")
@login_required
def path_page():
    user = current_user()
    conn = c.get_db()
    try:
        topics = path_data(conn, user["id"])
        has_diag = conn.execute(
            "SELECT 1 FROM attempts WHERE user_id=? AND kind='diagnostic' AND finished_at IS NOT NULL LIMIT 1",
            (user["id"],),
        ).fetchone() is not None
    finally:
        conn.close()
    return render_template("path.html", topics=topics, has_diag=has_diag)


@bp.get("/topic/<int:tid>")
@login_required
def topic_page(tid):
    user = current_user()
    conn = c.get_db()
    try:
        topic = conn.execute("SELECT * FROM topics WHERE id=? AND published=1", (tid,)).fetchone()
        if not topic:
            abort(404)
        materials = conn.execute(
            """SELECT m.*, EXISTS(SELECT 1 FROM reads r WHERE r.material_id=m.id AND r.user_id=?) AS read
               FROM materials m WHERE m.topic_id=? ORDER BY m.position, m.id""",
            (user["id"], tid),
        ).fetchall()
        info = next((t for t in path_data(conn, user["id"]) if t["id"] == tid), None)
        attempts = conn.execute(
            "SELECT * FROM attempts WHERE user_id=? AND kind='topic' AND topic_id=? AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 5", (user["id"], tid),
        ).fetchall()
        n_questions = conn.execute(
            "SELECT COUNT(*) FROM questions WHERE topic_id=? AND kind='topic'", (tid,)
        ).fetchone()[0]
    finally:
        conn.close()
    read_count = sum(1 for m in materials if m["read"])
    return render_template(
        "topic.html", topic=topic, materials=materials, info=info, attempts=attempts,
        read_count=read_count, n_questions=n_questions, pass_percent=c.PASS_PERCENT,
    )


@bp.post("/api/material/<int:mid>/read")
@api_login_required
@json_only
def material_read(mid):
    user = current_user()
    conn = c.get_db()
    try:
        m = conn.execute(
            "SELECT m.topic_id FROM materials m JOIN topics t ON t.id=m.topic_id WHERE m.id=? AND t.published=1",
            (mid,),
        ).fetchone()
        if not m:
            return fail("Material topilmadi.", 404)
        conn.execute("INSERT OR IGNORE INTO reads(user_id, material_id) VALUES (?, ?)", (user["id"], mid))
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM materials WHERE topic_id=?", (m["topic_id"],)).fetchone()[0]
        read = conn.execute(
            "SELECT COUNT(*) FROM reads r JOIN materials x ON x.id=r.material_id WHERE x.topic_id=? AND r.user_id=?",
            (m["topic_id"], user["id"]),
        ).fetchone()[0]
    finally:
        conn.close()
    return ok(read=read, total=total)


# =====================================================================
#                              ADMIN PANEL
# =====================================================================
def parse_questions(text, kind):
    """Ommaviy import. Savollar bo'sh qator bilan ajratilishi shart emas.

        1. Savol matni
        A) variant
        B) variant
        C) variant
        D) variant
        Javob: B          (yoki variant matni: "Javob: Buxoro")
        Izoh: (ixtiyoriy)
    """
    re_ans = re.compile(r"^(?:to'g'ri\s+)?(?:javob|answer)\s*[:\-=]\s*(.+)$", re.I)
    re_exp = re.compile(r"^(?:izoh|explanation)\s*[:\-=]\s*(.+)$", re.I)
    re_opt = re.compile(r"^\(?([A-Da-d])[\)\.\:]\s*(.+)$")

    def fresh():
        return {"q": [], "opts": {}, "last": None, "ans": None, "expl": ""}

    items, cur = [], fresh()

    def started(c):
        return bool(c["q"] or c["opts"])

    for raw in block(text, 200000).split("\n"):
        line = raw.strip()
        if not line:
            continue
        m_ans, m_exp, m_opt = re_ans.match(line), re_exp.match(line), re_opt.match(line)
        if m_ans:
            cur["ans"] = m_ans.group(1).strip()
        elif m_exp:
            cur["expl"] = m_exp.group(1).strip()
        elif m_opt and (cur["q"] or cur["opts"]) and cur["ans"] is None:
            letter = m_opt.group(1).upper()
            if letter in cur["opts"]:      # takroriy harf: yangi savol boshlangan
                items.append(cur)
                cur = fresh()
                cur["q"].append(line)
            else:
                cur["opts"][letter] = m_opt.group(2).strip()
                cur["last"] = letter
        else:
            if cur["ans"] is not None or len(cur["opts"]) == 4:
                items.append(cur)          # oldingi savol tugadi, yangisi boshlandi
                cur = fresh()
            if cur["opts"]:                 # variantning davomi (keyingi qator)
                cur["opts"][cur["last"]] += " " + line
            else:
                cur["q"].append(line)
    if started(cur):
        items.append(cur)

    parsed, errors = [], []
    for n, it in enumerate(items, 1):
        q_text = " ".join(it["q"])
        q_text = re.sub(r"^\s*\d+\s*[\.\)\-]\s*", "", q_text).strip()
        opts = it["opts"]
        label = f"{n}-savol" + (f" («{q_text[:30]}...»)" if q_text else "")
        if not q_text:
            errors.append(f"{label}: savol matni topilmadi.")
            continue
        if set(opts) != {"A", "B", "C", "D"}:
            errors.append(f"{label}: A, B, C, D variantlari to'liq emas (topildi: {''.join(sorted(opts)) or 'yo`q'}).")
            continue
        ans = it["ans"]
        letter = None
        if ans:
            m = re.match(r"^([A-Da-d])\b\s*[\)\.]?", ans)
            if m:
                letter = m.group(1).upper()
            else:  # javob variant matni bilan yozilgan
                for k, v in opts.items():
                    if v.strip().lower() == ans.strip().lower():
                        letter = k
        if letter is None:
            errors.append(f"{label}: 'Javob: A' (A-D harfi) topilmadi yoki tushunarsiz.")
            continue
        parsed.append((q_text[:500], opts["A"][:300], opts["B"][:300], opts["C"][:300], opts["D"][:300],
                       "ABCD".index(letter) + 1, it["expl"][:500]))
    return parsed, errors


@bp.get("/admin")
@admin_required
def admin_index():
    conn = c.get_db()
    try:
        topics = conn.execute(
            """SELECT t.*,
                 (SELECT COUNT(*) FROM materials m WHERE m.topic_id=t.id) AS n_mat,
                 (SELECT COUNT(*) FROM questions q WHERE q.topic_id=t.id AND q.kind='diagnostic') AS n_diag,
                 (SELECT COUNT(*) FROM questions q WHERE q.topic_id=t.id AND q.kind='topic') AS n_test
               FROM topics t ORDER BY t.position, t.id"""
        ).fetchall()
        stats = {
            "users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "attempts": conn.execute("SELECT COUNT(*) FROM attempts WHERE finished_at IS NOT NULL").fetchone()[0],
        }
    finally:
        conn.close()
    return render_template("admin/index.html", topics=topics, stats=stats)


@bp.get("/admin/users")
@admin_required
def admin_users():
    conn = c.get_db()
    try:
        users = conn.execute(
            """SELECT u.id, u.first_name, u.last_name, u.phone, u.region, u.created_at,
                 (SELECT COUNT(*) FROM progress p WHERE p.user_id=u.id AND p.passed=1) AS passed_cnt,
                 (SELECT score*100/total FROM attempts a WHERE a.user_id=u.id AND a.kind='diagnostic'
                    AND a.finished_at IS NOT NULL ORDER BY a.id DESC LIMIT 1) AS diag
               FROM users u ORDER BY u.id DESC LIMIT 500"""
        ).fetchall()
        n_topics = conn.execute("SELECT COUNT(*) FROM topics WHERE published=1").fetchone()[0]
    finally:
        conn.close()
    return render_template("admin/users.html", users=users, n_topics=n_topics)


def read_topic_form():
    title = one_line(request.form.get("title"), 120)
    summary = one_line(request.form.get("summary"), 300)
    pos = request.form.get("position", "0").strip()
    pos = int(pos) if pos.lstrip("-").isdigit() else 0
    published = 1 if request.form.get("published") else 0
    return title, summary, pos, published


@bp.post("/admin/topic/new")
@admin_required
def admin_topic_new():
    check_csrf()
    title, summary, pos, published = read_topic_form()
    if len(title) < 2:
        flash("Mavzu nomi kamida 2 ta belgi bo'lishi kerak.", "err")
        return redirect(url_for("learn.admin_index"))
    conn = c.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO topics(title, summary, position, published) VALUES (?, ?, ?, ?)",
            (title, summary, pos, published),
        )
        conn.commit()
        tid = cur.lastrowid
    finally:
        conn.close()
    flash("Mavzu qo'shildi. Endi material va savollar kiriting.", "ok")
    return redirect(url_for("learn.admin_topic", tid=tid))


@bp.get("/admin/topic/<int:tid>")
@admin_required
def admin_topic(tid):
    conn = c.get_db()
    try:
        topic = conn.execute("SELECT * FROM topics WHERE id=?", (tid,)).fetchone()
        if not topic:
            abort(404)
        materials = conn.execute(
            "SELECT * FROM materials WHERE topic_id=? ORDER BY position, id", (tid,)
        ).fetchall()
        questions = conn.execute(
            "SELECT * FROM questions WHERE topic_id=? ORDER BY kind, id", (tid,)
        ).fetchall()
    finally:
        conn.close()
    return render_template("admin/topic.html", topic=topic, materials=materials, questions=questions)


@bp.post("/admin/topic/<int:tid>/save")
@admin_required
def admin_topic_save(tid):
    check_csrf()
    title, summary, pos, published = read_topic_form()
    if len(title) < 2:
        flash("Mavzu nomi kamida 2 ta belgi bo'lishi kerak.", "err")
    else:
        conn = c.get_db()
        try:
            conn.execute(
                "UPDATE topics SET title=?, summary=?, position=?, published=? WHERE id=?",
                (title, summary, pos, published, tid),
            )
            conn.commit()
        finally:
            conn.close()
        flash("Saqlandi.", "ok")
    return redirect(url_for("learn.admin_topic", tid=tid))


@bp.post("/admin/topic/<int:tid>/delete")
@admin_required
def admin_topic_delete(tid):
    check_csrf()
    conn = c.get_db()
    try:
        conn.execute("DELETE FROM reads WHERE material_id IN (SELECT id FROM materials WHERE topic_id=?)", (tid,))
        conn.execute("DELETE FROM progress WHERE topic_id=?", (tid,))
        conn.execute("DELETE FROM topics WHERE id=?", (tid,))
        conn.commit()
    finally:
        conn.close()
    flash("Mavzu o'chirildi.", "ok")
    return redirect(url_for("learn.admin_index"))


def read_material_form():
    title = one_line(request.form.get("title"), 150)
    text = block(request.form.get("body"), 20000)
    url = request.form.get("url", "").strip()
    pos = request.form.get("position", "0").strip()
    pos = int(pos) if pos.lstrip("-").isdigit() else 0
    if len(title) < 2:
        return None, "Material nomini kiriting."
    if not text and not url:
        return None, "Material matni yoki havolasini kiriting."
    if url and not valid_url(url):
        return None, "Havola http:// yoki https:// bilan boshlanishi kerak."
    return (title, text, url[:500], pos), None


@bp.post("/admin/topic/<int:tid>/material")
@admin_required
def admin_material_add(tid):
    check_csrf()
    data, err = read_material_form()
    if err:
        flash(err, "err")
    else:
        conn = c.get_db()
        try:
            conn.execute(
                "INSERT INTO materials(topic_id, title, body, url, position) VALUES (?, ?, ?, ?, ?)", (tid, *data)
            )
            conn.commit()
        finally:
            conn.close()
        flash("Material qo'shildi.", "ok")
    return redirect(url_for("learn.admin_topic", tid=tid))


@bp.route("/admin/material/<int:mid>", methods=["GET", "POST"])
@admin_required
def admin_material_edit(mid):
    conn = c.get_db()
    try:
        m = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
        if not m:
            abort(404)
        if request.method == "POST":
            check_csrf()
            data, err = read_material_form()
            if err:
                flash(err, "err")
            else:
                conn.execute("UPDATE materials SET title=?, body=?, url=?, position=? WHERE id=?", (*data, mid))
                conn.commit()
                flash("Saqlandi.", "ok")
                return redirect(url_for("learn.admin_topic", tid=m["topic_id"]))
    finally:
        conn.close()
    return render_template("admin/edit_material.html", m=m)


@bp.post("/admin/material/<int:mid>/delete")
@admin_required
def admin_material_delete(mid):
    check_csrf()
    conn = c.get_db()
    try:
        m = conn.execute("SELECT topic_id FROM materials WHERE id=?", (mid,)).fetchone()
        if not m:
            abort(404)
        conn.execute("DELETE FROM reads WHERE material_id=?", (mid,))
        conn.execute("DELETE FROM materials WHERE id=?", (mid,))
        conn.commit()
    finally:
        conn.close()
    flash("Material o'chirildi.", "ok")
    return redirect(url_for("learn.admin_topic", tid=m["topic_id"]))


def read_question_form():
    kind = "diagnostic" if request.form.get("kind") == "diagnostic" else "topic"
    text = one_line(request.form.get("text"), 500)
    opts = [one_line(request.form.get(f"o{i}"), 300) for i in range(1, 5)]
    correct = request.form.get("correct", "")
    expl = one_line(request.form.get("explanation"), 500)
    if len(text) < 3:
        return None, "Savol matnini kiriting."
    if not all(opts):
        return None, "Barcha 4 ta variantni to'ldiring."
    if len({o.lower() for o in opts}) < 4:
        return None, "Variantlar bir-biridan farq qilishi kerak."
    if correct not in ("1", "2", "3", "4"):
        return None, "To'g'ri javobni tanlang."
    return (kind, text, *opts, int(correct), expl), None


@bp.post("/admin/topic/<int:tid>/question")
@admin_required
def admin_question_add(tid):
    check_csrf()
    data, err = read_question_form()
    if err:
        flash(err, "err")
    else:
        conn = c.get_db()
        try:
            conn.execute(
                "INSERT INTO questions(topic_id, kind, text, o1, o2, o3, o4, correct, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (tid, *data),
            )
            conn.commit()
        finally:
            conn.close()
        flash("Savol qo'shildi.", "ok")
    return redirect(url_for("learn.admin_topic", tid=tid) + "#questions")


@bp.route("/admin/question/<int:qid>", methods=["GET", "POST"])
@admin_required
def admin_question_edit(qid):
    conn = c.get_db()
    try:
        q = conn.execute("SELECT * FROM questions WHERE id=?", (qid,)).fetchone()
        if not q:
            abort(404)
        if request.method == "POST":
            check_csrf()
            data, err = read_question_form()
            if err:
                flash(err, "err")
            else:
                conn.execute(
                    "UPDATE questions SET kind=?, text=?, o1=?, o2=?, o3=?, o4=?, correct=?, explanation=? WHERE id=?",
                    (*data, qid),
                )
                conn.commit()
                flash("Saqlandi.", "ok")
                return redirect(url_for("learn.admin_topic", tid=q["topic_id"]) + "#questions")
    finally:
        conn.close()
    return render_template("admin/edit_question.html", q=q)


@bp.post("/admin/question/<int:qid>/delete")
@admin_required
def admin_question_delete(qid):
    check_csrf()
    conn = c.get_db()
    try:
        q = conn.execute("SELECT topic_id FROM questions WHERE id=?", (qid,)).fetchone()
        if not q:
            abort(404)
        conn.execute("DELETE FROM questions WHERE id=?", (qid,))
        conn.commit()
    finally:
        conn.close()
    flash("Savol o'chirildi.", "ok")
    return redirect(url_for("learn.admin_topic", tid=q["topic_id"]) + "#questions")


@bp.post("/admin/topic/<int:tid>/import")
@admin_required
def admin_import(tid):
    check_csrf()
    kind = "diagnostic" if request.form.get("kind") == "diagnostic" else "topic"
    parsed, errors = parse_questions(request.form.get("text", ""), kind)
    if parsed:
        conn = c.get_db()
        try:
            conn.executemany(
                "INSERT INTO questions(topic_id, kind, text, o1, o2, o3, o4, correct, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(tid, kind, *p) for p in parsed],
            )
            conn.commit()
        finally:
            conn.close()
        flash(f"{len(parsed)} ta savol qo'shildi.", "ok")
    for e in errors[:10]:
        flash(e, "err")
    if not parsed and not errors:
        flash("Matn bo'sh. Savollarni kiriting.", "err")
    return redirect(url_for("learn.admin_topic", tid=tid))