"""O'quvchi paneli: bosh sahifa (diagnostika va dars reja), mavzular, testlar, natijalar, xatolar, profil."""
import json
import os
import random
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, abort, g, redirect, render_template, request, send_from_directory, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import common as c
from web_utils import (
    api_login_required, body, check_csrf, current_user, fail, is_admin, json_only, login_required, ok,
    password_mark, to_int,
)

bp = Blueprint("learn", __name__)

MAX_AVATAR = 2 * 1024 * 1024
TZ = timezone(timedelta(hours=5))   # O'zbekiston vaqti
IDK = -1                            # "Bilmayman" javobi
MIN_TEST = 3                        # mavzu testi uchun kerak bo'lgan eng kam yangi savollar
GRACE = 30                          # vaqt tugagach tarmoq kechikishi uchun beriladigan soniya

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


@bp.app_template_filter("num")
def fmt_num(v):
    """1.1 -> '1.1', 3.0 -> '3'"""
    if v is None:
        return "-"
    return f"{round(float(v), 2):g}"


@bp.app_template_filter("links")
def links_filter(text):
    return parse_links(text)[0]


@bp.app_template_filter("filesize")
def filesize(n):
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{max(1, round(n / 1024))} KB"


@bp.app_context_processor
def inject_settings():
    return {"kinds": c.EXAM_KINDS, "dtm_sections": c.DTM_SECTIONS}


# Ikkala panel ham ishlatadigan manzillar: profil shakli va rasm
SHARED = {"learn.profile_save", "learn.password_change", "learn.avatar_upload", "learn.avatar_delete",
          "learn.avatar_file"}


@bp.before_request
def students_only():
    """O'quvchi panelida admin ishlamaydi: u o'z paneliga qaytariladi."""
    if request.endpoint in SHARED or not is_admin():
        return None
    if request.path.startswith("/api"):
        return fail("Bu amal faqat o'quvchilar uchun.", 403, redirect=url_for("admin.admin_index"))
    return redirect(url_for("admin.admin_profile" if request.endpoint == "learn.profile" else "admin.admin_index"))


@bp.before_app_request
def touch_last_seen():
    user = current_user()
    now = int(time.time())
    if user and (user["last_seen"] is None or now - user["last_seen"] > 300):
        conn = c.get_db()
        try:
            conn.execute("UPDATE users SET last_seen=? WHERE id=?", (now, user["id"]))
            conn.commit()
        finally:
            conn.close()


# ---------------- Yordamchi funksiyalar ----------------
def one_line(v, mx):
    return " ".join(str(v or "").split())[:mx]


def block(v, mx):
    return str(v or "").replace("\r\n", "\n").strip()[:mx]


def valid_url(u):
    return bool(re.match(r"^https?://[^\s<>\"']+$", u or ""))


def parse_links(text):
    """Har bir qatorda bitta havola: 'https://...' yoki 'Nomi | https://...'.
    Qaytaradi: ([(nomi, url), ...], xatolar)"""
    out, errors = [], []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        title, _, url = line.rpartition("|") if "|" in line else ("", "", line)
        title, url = title.strip(), url.strip()
        if not valid_url(url):
            errors.append(f"Havola noto'g'ri: {url[:60]}")
            continue
        out.append((title or re.sub(r"^https?://(www\.)?", "", url).split("/")[0], url))
    return out, errors


def settings(conn):
    if "_settings" not in g:
        g._settings = c.get_settings(conn)
    return g._settings


def level_of(p, st):
    if p is None:
        return None
    if p < st["pass_percent"]:
        return "low"
    if p < st["high_percent"]:
        return "mid"
    return "high"


LEVELS = {"low": ("Past", "err"), "mid": ("O'rta", "warn"), "high": ("Yuqori", "ok")}
STATES = {
    "done": ("O'zlashtirildi", "ok"),
    "current": ("Joriy dars", "brand"),
    "locked": ("Yopiq", "new"),
    "soon": ("Tayyorlanmoqda", "new"),
    "skipped": ("Yuqori daraja", "info"),
}


CLOSED = ("locked", "soon")     # o'quvchi ocholmaydigan holatlar


def has_finished_diag(conn, uid):
    return conn.execute(
        "SELECT 1 FROM attempts WHERE user_id=? AND kind='diagnostic' AND finished_at IS NOT NULL LIMIT 1", (uid,)
    ).fetchone() is not None


def plan_data(conn, user):
    """Dars reja: admin tuzgan mavzular tartibida. Diagnostikadan o'tgan bo'lsa, bilish foizi yetarli mavzular
    chiqarib tashlanadi. Darslar ketma-ket ochiladi: oldingi mavzu testidan o'tilmaguncha keyingisi yopiq.
    Diagnostika ishlanmagan yoki rad etilmagan bo'lsa, hamma darslar yopiq turadi.
    Materiali ham, testi ham yo'q mavzu tayyorlanmoqda: o'tilgan hisoblanmaydi va keyingilarini to'smaydi."""
    st = settings(conn)
    uid = user["id"]
    rows = conn.execute(
        """
        SELECT t.id, t.title, t.summary, t.position,
          (SELECT COUNT(*) FROM materials m WHERE m.topic_id = t.id) AS mat_total,
          (SELECT COUNT(*) FROM reads r JOIN materials m ON m.id = r.material_id
             WHERE m.topic_id = t.id AND r.user_id = ?) AS mat_read,
          (SELECT COUNT(*) FROM questions q WHERE q.topic_id = t.id) AS n_test,
          p.diag_percent, p.best_percent, COALESCE(p.first_failed, 0) AS first_failed,
          COALESCE(p.passed, 0) AS passed, COALESCE(p.attempts, 0) AS attempts
        FROM topics t LEFT JOIN progress p ON p.topic_id = t.id AND p.user_id = ?
        WHERE t.published = 1 ORDER BY t.position, t.id
        """,
        (uid, uid),
    ).fetchall()
    has_diag = has_finished_diag(conn, uid)
    declined = bool(user["diag_declined"])
    items = []
    for r in rows:
        d = dict(r)
        d["level"] = level_of(d["diag_percent"], st)
        d["mat_pct"] = round(100 * d["mat_read"] / d["mat_total"]) if d["mat_total"] else 0
        # Test savollari bo'lmagan mavzu materiallar o'qilgach o'tilgan hisoblanadi
        d["empty"] = not d["n_test"] and not d["mat_total"]
        d["done"] = bool(d["passed"]) or (d["n_test"] == 0 and 0 < d["mat_total"] <= d["mat_read"])
        d["in_plan"] = not (has_diag and d["level"] == "high")
        items.append(d)
    plan = [d for d in items if d["in_plan"]]
    unlocked = has_diag or declined
    for n, d in enumerate(plan, 1):
        d["n"] = n
        if d["done"] and (has_diag or declined):
            d["state"] = "done"
        elif d["empty"]:
            d["state"] = "soon"
        elif unlocked:
            d["state"] = "current"
            unlocked = False
        else:
            d["state"] = "locked"
    skipped = [d for d in items if not d["in_plan"]]
    for d in skipped:
        d["state"] = "skipped"
    done = sum(1 for d in plan if d["state"] == "done")
    total = sum(1 for d in plan if d["state"] != "soon")
    return {
        "plan": plan, "skipped": skipped, "all": items, "has_diag": has_diag, "declined": declined,
        "decided": has_diag or declined, "done": done, "total": total,
        "current": next((d for d in plan if d["state"] == "current"), None),
        "pct": round(100 * done / total) if total else 0,
    }


def topic_info(conn, user, tid):
    return next((d for d in plan_data(conn, user)["all"] if d["id"] == tid), None)


def exam_kind_or_404(kind):
    if kind not in c.EXAM_KINDS:
        abort(404)
    return kind


def get_attempt(conn, aid, uid):
    a = conn.execute("SELECT * FROM attempts WHERE id = ? AND user_id = ?", (aid, uid)).fetchone()
    if a is None:
        abort(404)
    return a


def recent_attempts(conn, uid, limit, kind=None, exam_kind=None):
    sql = """SELECT a.*, t.title AS topic_title, e.title AS exam_title, e.kind AS exam_kind
             FROM attempts a
             LEFT JOIN topics t ON t.id = a.topic_id
             LEFT JOIN exams e ON e.id = a.exam_id
             WHERE a.user_id = ? AND a.finished_at IS NOT NULL"""
    args = [uid]
    if kind:
        sql += " AND a.kind = ?"
        args.append(kind)
    if exam_kind:
        sql += " AND e.kind = ?"
        args.append(exam_kind)
    sql += " ORDER BY a.id DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def stats_for(conn, uid):
    r = conn.execute(
        "SELECT COUNT(*) AS n, AVG(100.0 * score / total) AS avg, MAX(100.0 * score / total) AS best "
        "FROM attempts WHERE user_id=? AND finished_at IS NOT NULL AND total > 0", (uid,),
    ).fetchone()
    paused = conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE user_id=? AND finished_at IS NULL", (uid,)
    ).fetchone()[0]
    return {"n": r["n"], "avg": round(r["avg"] or 0), "best": round(r["best"] or 0), "unfinished": paused}


# ---------------- Bosh sahifa ----------------
@bp.get("/dashboard")
@login_required
def dashboard():
    user = current_user()
    conn = c.get_db()
    try:
        expire_overdue(conn, user["id"])
        pd = plan_data(conn, user)
        if pd["all"] and not pd["decided"]:
            return redirect(url_for("learn.welcome"))
        stats = stats_for(conn, user["id"])
        unfinished = unfinished_tests(conn, user["id"])
        st = settings(conn)
    finally:
        conn.close()
    return render_template("dashboard.html", pd=pd, stats=stats, unfinished=unfinished, st=st, states=STATES,
                           levels=LEVELS)


def unfinished_tests(conn, uid):
    """Boshlangan, lekin yakunlanmagan testlar (Bosh sahifadan davom ettiriladi)."""
    now = int(time.time())
    items = []
    for a in conn.execute(
        """SELECT a.*, t.title AS topic_title, e.title AS exam_title, e.kind AS exam_kind
           FROM attempts a LEFT JOIN topics t ON t.id=a.topic_id LEFT JOIN exams e ON e.id=a.exam_id
           WHERE a.user_id=? AND a.finished_at IS NULL ORDER BY a.id DESC""", (uid,),
    ).fetchall():
        left = a["time_left"] if a["paused"] else (max(0, a["deadline"] - now) if a["deadline"] else None)
        items.append({**dict(a), "left": left})
    return items


@bp.get("/welcome")
@login_required
def welcome():
    """Birinchi kirish: diagnostikadan o'tish yoki uni rad etish."""
    user = current_user()
    conn = c.get_db()
    try:
        expire_overdue(conn, user["id"])
        if has_finished_diag(conn, user["id"]) or user["diag_declined"]:
            return redirect(url_for("learn.dashboard"))
        st = settings(conn)
        plan = diag_plan(conn, st, seen_questions(conn, user["id"]))
        pending = conn.execute(
            "SELECT id FROM attempts WHERE user_id=? AND kind='diagnostic' AND finished_at IS NULL "
            "ORDER BY id DESC LIMIT 1", (user["id"],),
        ).fetchone()
    finally:
        conn.close()
    return render_template("welcome.html", n_topics=len(plan), n_questions=sum(k for _t, k, _q in plan), st=st,
                           pending=pending)


@bp.post("/api/diagnostic/decline")
@api_login_required
@json_only
def diagnostic_decline():
    uid = current_user()["id"]
    conn = c.get_db()
    try:
        if conn.execute("SELECT 1 FROM attempts WHERE user_id=? AND kind='diagnostic' LIMIT 1", (uid,)).fetchone():
            return fail("Diagnostika boshlangan, uni yakunlang.", redirect=url_for("learn.welcome"))
        conn.execute("UPDATE users SET diag_declined=1 WHERE id=?", (uid,))
        conn.commit()
    finally:
        conn.close()
    return ok(redirect=url_for("learn.dashboard"))


# ---------------- Profil ----------------
@bp.get("/profile")
@login_required
def profile():
    return render_template("profile.html", regions=c.REGIONS)


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
        birth_year = to_int(by_raw, 0)
        if not 1930 <= birth_year <= datetime.now(TZ).year - 5:
            return fail("Tug'ilgan yilni to'g'ri kiriting.")
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
        err = c.password_error(new, new2)
        if err:
            return fail(err)
        if user["secret_hash"] and check_password_hash(user["secret_hash"], c.normalize_secret(new)):
            return fail("Parol mahfiy so'z bilan bir xil bo'lmasligi kerak.")
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), user["id"]))
        conn.commit()
        session["pm"] = password_mark(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
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


@bp.post("/api/profile/secret")
@api_login_required
@json_only
def secret_change():
    """Mahfiy so'zni qo'yish yoki almashtirish (joriy parol bilan)."""
    user = current_user()
    d = body()
    password, secret = str(d.get("password", "")), d.get("secret", "")
    conn = c.get_db()
    try:
        key = f"pw:{user['id']}"
        if c.too_many(conn, key, 5, 900):
            return fail("Juda ko'p urinish. Birozdan keyin qayta urinib ko'ring.", 429)
        if not check_password_hash(user["password_hash"], password):
            c.hit(conn, key)
            return fail("Joriy parol noto'g'ri.")
        err = c.secret_error(secret, password)
        if err:
            return fail(err)
        conn.execute("UPDATE users SET secret_hash=? WHERE id=?",
                     (generate_password_hash(c.normalize_secret(secret)), user["id"]))
        conn.commit()
    finally:
        conn.close()
    return ok(message="Mahfiy so'z saqlandi.")


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


# ---------------- Test sessiyasi: tuzish, saqlash, baholash ----------------
def _shuffle_options(q):
    opts = [q["o1"], q["o2"], q["o3"], q["o4"]]
    order = list(range(4))
    random.shuffle(order)
    return [opts[i] for i in order], order.index(q["correct"] - 1)


def _item(q, topic_id, topic_title, points, section=""):
    options, correct = _shuffle_options(q)
    return {
        "qid": q["id"], "topic_id": topic_id, "topic": topic_title or "", "text": q["text"],
        "options": options, "correct": correct, "explanation": q["explanation"],
        "points": points, "section": section,
    }


def _pick(rows, n, keep_order=True, seen=frozenset()):
    """n ta savol: avval o'quvchiga tushmaganlari, yetmasa avval tushganlari bilan to'ldiriladi."""
    rows = list(rows)
    if n and len(rows) > n:
        new = [r for r in rows if r["id"] not in seen]
        old = [r for r in rows if r["id"] in seen]
        rows = random.sample(new, min(n, len(new)))
        rows += random.sample(old, n - len(rows))
        if keep_order:
            rows.sort(key=lambda r: (r["position"], r["id"]))
    return rows


def seen_questions(conn, uid, exam_id=None):
    """O'quvchiga tushgan savollar: mavzu savollari (diagnostika va mavzu testi) yoki bitta imtihon savollari."""
    if exam_id is None:
        rows = conn.execute("SELECT payload FROM attempts WHERE user_id=? AND kind IN ('diagnostic', 'topic')", (uid,))
    else:
        rows = conn.execute("SELECT payload FROM attempts WHERE user_id=? AND exam_id=?", (uid, exam_id))
    return {q.get("qid") for r in rows.fetchall() for q in json.loads(r["payload"])}


def fresh_questions(conn, tid, seen):
    return [q for q in conn.execute("SELECT * FROM questions WHERE topic_id=?", (tid,)) if q["id"] not in seen]


def test_size(st, n_total, n_fresh):
    """Mavzu testida beriladigan savollar soni. Bitta savol o'quvchiga faqat bir marta tushadi, shuning uchun
    yangi savollar juda kam qolgan bo'lsa 0 qaytadi (admin savol qo'shishi kerak)."""
    want = min(st["topic_count"] or n_total, n_total)
    n = min(want, n_fresh)
    return n if n >= min(MIN_TEST, want) else 0


def diag_count_of(t, st):
    return t["diag_count"] if t["diag_count"] is not None else st["diag_per_topic"]


def diag_quota(want, n_fresh, st):
    """Diagnostikaga beriladigan savollar soni: mavzu testiga ham savol qolishi kerak."""
    reserve = min(MIN_TEST, st["topic_count"] or MIN_TEST)
    return max(0, min(want, n_fresh - reserve))


def diag_plan(conn, st, seen=frozenset()):
    """Diagnostika tarkibi: [(mavzu, savollar soni, yangi savollar)], admin tuzgan mavzular tartibida."""
    out = []
    for t in conn.execute("SELECT * FROM topics WHERE published=1 ORDER BY position, id").fetchall():
        qs = fresh_questions(conn, t["id"], seen)
        k = diag_quota(diag_count_of(t, st), len(qs), st)
        if k:
            out.append((t, k, qs))
    return out


def build_payload(conn, kind, uid, topic=None, exam=None):
    st = settings(conn)
    items = []
    if kind == "diagnostic":
        for t, k, qs in diag_plan(conn, st, seen_questions(conn, uid)):
            items += [_item(q, t["id"], t["title"], 1.0) for q in random.sample(qs, k)]
    elif kind == "topic":
        fresh = fresh_questions(conn, topic["id"], seen_questions(conn, uid))
        total = conn.execute("SELECT COUNT(*) FROM questions WHERE topic_id=?", (topic["id"],)).fetchone()[0]
        pts = topic["test_points"] if topic["test_points"] is not None else st["topic_points"]
        items = [_item(q, topic["id"], topic["title"], pts)
                 for q in random.sample(fresh, test_size(st, total, len(fresh)))]
    else:
        rows = conn.execute(
            """SELECT q.*, t.title AS topic_title FROM exam_questions q
               LEFT JOIN topics t ON t.id = q.topic_id WHERE q.exam_id=? ORDER BY q.position, q.id""",
            (exam["id"],),
        ).fetchall()
        seen = seen_questions(conn, uid, exam["id"])
        if exam["kind"] == "dtm":
            parts = [
                ("a", st["dtm_mandatory_count"], exam["points_a"], c.DTM_SECTIONS["a"]),
                ("b", st["dtm_special_count"], exam["points_b"], c.DTM_SECTIONS["b"]),
            ]
            for sec, n, pts, label in parts:
                chosen = _pick([r for r in rows if r["section"] == sec], n, not exam["shuffle"], seen)
                if exam["shuffle"]:
                    random.shuffle(chosen)
                items += [_item(q, q["topic_id"], q["topic_title"], pts, label) for q in chosen]
        else:
            chosen = _pick(rows, st[f"{exam['kind']}_count"], not exam["shuffle"], seen)
            if exam["shuffle"]:
                random.shuffle(chosen)
            items = [_item(q, q["topic_id"], q["topic_title"], exam["points_a"]) for q in chosen]
    return items


def time_limit_for(conn, kind, topic=None, exam=None):
    st = settings(conn)
    if kind == "diagnostic":
        return st["diag_time"]
    if kind == "topic":
        return topic["test_time"] if topic["test_time"] is not None else st["topic_time"]
    return exam["time_limit"]


def clean_answers(raw, n):
    if not isinstance(raw, list) or len(raw) != n:
        return None
    out = []
    for x in raw:
        if x is None:
            out.append(None)
        elif isinstance(x, int) and not isinstance(x, bool) and IDK <= x <= 3:
            out.append(x)
        else:
            return None
    return out


def finalize(conn, a, answers):
    """Testni baholaydi va yakunlaydi. Qayta chaqirilsa hech narsa o'zgarmaydi."""
    payload = json.loads(a["payload"])
    if answers is None or len(answers) != len(payload):
        answers = [None] * len(payload)
    st = settings(conn)
    score, points, max_points = 0, 0.0, 0.0
    per_topic = {}
    for q, ans in zip(payload, answers):
        right = ans == q["correct"]
        pts = float(q.get("points", 1) or 0)
        max_points += pts
        if right:
            score += 1
            points += pts
        if q.get("topic_id") is None:
            continue
        t = per_topic.setdefault(q["topic_id"], {"id": q["topic_id"], "title": q["topic"], "correct": 0, "total": 0})
        t["total"] += 1
        t["correct"] += right
    topics_res = []
    for t in per_topic.values():
        t["percent"] = round(100 * t["correct"] / t["total"])
        topics_res.append(t)
    total = len(payload)
    percent = round(100 * score / total) if total else 0
    cur = conn.execute(
        "UPDATE attempts SET finished_at=?, score=?, total=?, points=?, max_points=?, result=?, draft=NULL, "
        "paused=0 WHERE id=? AND finished_at IS NULL",
        (int(time.time()), score, total, round(points, 2), round(max_points, 2),
         json.dumps({"answers": answers, "topics": topics_res}), a["id"]),
    )
    if cur.rowcount == 1:
        uid = a["user_id"]
        if a["kind"] == "diagnostic":
            for t in topics_res:
                conn.execute(
                    "INSERT INTO progress(user_id, topic_id, diag_percent, best_percent, passed, attempts) "
                    "VALUES (?, ?, ?, NULL, 0, 0) "
                    "ON CONFLICT(user_id, topic_id) DO UPDATE SET diag_percent=excluded.diag_percent",
                    (uid, t["id"], t["percent"]),
                )
        elif a["kind"] == "topic":
            passed = 1 if percent >= st["pass_percent"] else 0
            conn.execute(
                "INSERT INTO progress(user_id, topic_id, diag_percent, best_percent, passed, attempts, first_failed) "
                "VALUES (?, ?, NULL, ?, ?, 1, ?) "
                "ON CONFLICT(user_id, topic_id) DO UPDATE SET "
                "best_percent=MAX(COALESCE(best_percent, 0), excluded.best_percent), "
                "passed=MAX(passed, excluded.passed), "
                "first_failed=CASE WHEN attempts=0 THEN excluded.first_failed ELSE first_failed END, "
                "attempts=attempts+1",
                (uid, a["topic_id"], percent, passed, 1 - passed),
            )
            if not passed:
                reset_reads(conn, uid, a["topic_id"])     # mavzu qaytadan o'zlashtiriladi
    conn.commit()


def reset_reads(conn, uid, tid):
    conn.execute(
        "DELETE FROM reads WHERE user_id=? AND material_id IN (SELECT id FROM materials WHERE topic_id=?)", (uid, tid),
    )


def saved_answers(a):
    return json.loads(a["draft"]) if a["draft"] else None


def is_overdue(a):
    return bool(a["deadline"]) and a["deadline"] < int(time.time()) - GRACE


def expire_overdue(conn, uid):
    """Vaqti tugagan (to'xtatilmagan) testlarni saqlangan javoblar bilan yakunlaydi."""
    for a in conn.execute(
        "SELECT * FROM attempts WHERE user_id=? AND finished_at IS NULL AND paused=0 "
        "AND deadline IS NOT NULL AND deadline < ?", (uid, int(time.time()) - GRACE),
    ).fetchall():
        finalize(conn, a, saved_answers(a))


NO_FRESH = ("Bu mavzu bo'yicha siz uchun yangi savollar qolmadi (har bir savol faqat bir marta tushadi). "
            "Ustoz yangi savol qo'shgach, testni topshira olasiz.")


def start_attempt(conn, user, kind, topic=None, exam=None):
    """Tugallanmagan sessiyani davom ettiradi yoki yangisini boshlaydi."""
    expire_overdue(conn, user["id"])
    # Yozish qulfi: bir vaqtda kelgan ikki so'rov bir xil savollarni ikki marta bermasin
    conn.execute("BEGIN IMMEDIATE")
    topic_id = topic["id"] if topic else None
    exam_id = exam["id"] if exam else None
    ex = conn.execute(
        "SELECT id FROM attempts WHERE user_id=? AND kind=? AND COALESCE(topic_id,0)=? AND COALESCE(exam_id,0)=? "
        "AND finished_at IS NULL ORDER BY id DESC LIMIT 1",
        (user["id"], kind, topic_id or 0, exam_id or 0),
    ).fetchone()
    if ex:
        return ex["id"], None
    key = f"quiz:{user['id']}"
    if c.too_many(conn, key, 40, 3600):
        return None, fail("Juda ko'p urinish. Birozdan keyin qayta urinib ko'ring.", 429)
    payload = build_payload(conn, kind, user["id"], topic, exam)
    if not payload:
        if topic and conn.execute("SELECT 1 FROM questions WHERE topic_id=? LIMIT 1", (topic_id,)).fetchone():
            return None, fail(NO_FRESH)
        return None, fail("Bu test uchun savollar hali kiritilmagan.")
    now = int(time.time())
    minutes = time_limit_for(conn, kind, topic, exam)
    deadline = now + minutes * 60 if minutes else None
    cur = conn.execute(
        "INSERT INTO attempts(user_id, kind, topic_id, exam_id, deadline, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user["id"], kind, topic_id, exam_id, deadline, json.dumps(payload, ensure_ascii=False), now),
    )
    c.hit(conn, key)      # commit ham shu yerda
    return cur.lastrowid, None


def attempt_title(conn, a):
    """(sarlavha, orqaga qaytish manzili, turi nomi, menyudagi imtihon turi)"""
    if a["kind"] == "diagnostic":
        return "Diagnostik test", url_for("learn.dashboard"), "Diagnostika", None
    if a["kind"] == "exam":
        e = conn.execute("SELECT id, title, kind FROM exams WHERE id=?", (a["exam_id"],)).fetchone()
        if not e:
            return "O'chirilgan test", url_for("learn.exams_home"), "Test", None
        return e["title"], url_for("learn.exam_page", eid=e["id"]), c.EXAM_KINDS[e["kind"]][0], e["kind"]
    t = conn.execute("SELECT title FROM topics WHERE id=?", (a["topic_id"],)).fetchone()
    return ((t["title"] if t else "O'chirilgan mavzu"), url_for("learn.topic_page", tid=a["topic_id"]),
            "Mavzu testi", None)


# ---------------- Diagnostika ----------------
@bp.post("/api/diagnostic/start")
@api_login_required
@json_only
def diagnostic_start():
    user = current_user()
    conn = c.get_db()
    try:
        if has_finished_diag(conn, user["id"]) or user["diag_declined"]:
            return fail("Diagnostika faqat bir marta, birinchi kirishda ishlanadi.",
                        redirect=url_for("learn.dashboard"))
        aid, err = start_attempt(conn, user, "diagnostic")
    finally:
        conn.close()
    if err:
        return err
    return ok(redirect=url_for("learn.quiz_page", aid=aid))


# ---------------- Mavzular ----------------
def locked_page(topic, info, pd):
    if not pd["decided"]:
        return redirect(url_for("learn.welcome"))
    return render_template("topic_locked.html", topic=topic, info=info, current=pd["current"]), 403


@bp.get("/topic/<int:tid>")
@login_required
def topic_page(tid):
    user = current_user()
    conn = c.get_db()
    try:
        topic = conn.execute("SELECT * FROM topics WHERE id=? AND published=1", (tid,)).fetchone()
        if not topic:
            abort(404)
        pd = plan_data(conn, user)
        info = next((t for t in pd["all"] if t["id"] == tid), None)
        if info and info["state"] in CLOSED:
            return locked_page(topic, info, pd)
        materials = conn.execute(
            """SELECT m.*, EXISTS(SELECT 1 FROM reads r WHERE r.material_id=m.id AND r.user_id=?) AS read
               FROM materials m WHERE m.topic_id=? ORDER BY m.position, m.id""",
            (user["id"], tid),
        ).fetchall()
        files = conn.execute("SELECT * FROM topic_files WHERE topic_id=? ORDER BY id", (tid,)).fetchall()
        attempts = conn.execute(
            "SELECT * FROM attempts WHERE user_id=? AND kind='topic' AND topic_id=? AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 5", (user["id"], tid),
        ).fetchall()
        pending = conn.execute(
            "SELECT id FROM attempts WHERE user_id=? AND kind='topic' AND topic_id=? AND finished_at IS NULL "
            "ORDER BY id DESC LIMIT 1", (user["id"], tid),
        ).fetchone()
        st = settings(conn)
        n_test = info["n_test"] if info else 0
        size = test_size(st, n_test, len(fresh_questions(conn, tid, seen_questions(conn, user["id"]))))
    finally:
        conn.close()
    read_count = sum(1 for m in materials if m["read"])
    nxt = None
    if info and info["state"] in ("done", "current"):
        idx = next((i for i, t in enumerate(pd["plan"]) if t["id"] == tid), None)
        if idx is not None and idx + 1 < len(pd["plan"]):
            nxt = pd["plan"][idx + 1]
    return render_template(
        "topic.html", topic=topic, materials=materials, files=files, info=info, attempts=attempts,
        read_count=read_count, st=st, states=STATES, levels=LEVELS, next_topic=nxt, n_test=n_test, test_count=size,
        pending=pending, no_fresh=NO_FRESH,
        can_test=bool(info) and (not info["passed"] or bool(info["first_failed"])) and info["state"] != "skipped",
        test_time=topic["test_time"] if topic["test_time"] is not None else st["topic_time"],
        test_points=topic["test_points"] if topic["test_points"] is not None else st["topic_points"],
    )


def send_topic_file(f):
    resp = send_from_directory(c.FILES_DIR, f["stored"], as_attachment=True, download_name=f["name"])
    resp.headers["Cache-Control"] = "private, no-store"
    return resp


@bp.get("/file/<int:fid>")
@login_required
def topic_file(fid):
    user = current_user()
    conn = c.get_db()
    try:
        f = conn.execute(
            "SELECT f.* FROM topic_files f JOIN topics t ON t.id=f.topic_id WHERE f.id=? AND t.published=1", (fid,),
        ).fetchone()
        if not f:
            abort(404)
        pd = plan_data(conn, user)
        info = next((t for t in pd["all"] if t["id"] == f["topic_id"]), None)
        if info and info["state"] in CLOSED:
            return locked_page(info, info, pd)
    finally:
        conn.close()
    return send_topic_file(f)


def send_material_image(m):
    resp = send_from_directory(c.FILES_DIR, m["image"])
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


@bp.get("/material-image/<int:mid>")
@login_required
def material_image(mid):
    conn = c.get_db()
    try:
        m = conn.execute(
            "SELECT m.topic_id, m.image FROM materials m JOIN topics t ON t.id=m.topic_id "
            "WHERE m.id=? AND t.published=1 AND m.image IS NOT NULL", (mid,),
        ).fetchone()
        if not m:
            abort(404)
        info = topic_info(conn, current_user(), m["topic_id"])
        if info and info["state"] in CLOSED:
            abort(403)
    finally:
        conn.close()
    return send_material_image(m)


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
        info = topic_info(conn, user, m["topic_id"])
        if info and info["state"] in CLOSED:
            return fail("Bu dars hali yopiq. Avval oldingi mavzu testidan o'ting.", 403)
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


@bp.post("/api/topic/<int:tid>/restudy")
@api_login_required
@json_only
def topic_restudy(tid):
    """Xatolarim bo'limidan: birinchi urinishda o'tilmagan mavzuni qaytadan o'zlashtirish."""
    user = current_user()
    conn = c.get_db()
    try:
        info = topic_info(conn, user, tid)
        if not info:
            return fail("Mavzu topilmadi.", 404)
        if info["state"] in CLOSED:
            return fail("Bu dars hali yopiq. Avval oldingi mavzu testidan o'ting.", 403)
        if not info["first_failed"]:
            return fail("Bu mavzu xatolar ro'yxatida yo'q.", 403)
        if info["passed"]:      # o'tilmagan mavzuning belgilari test yakunida tozalangan
            reset_reads(conn, user["id"], tid)
            conn.commit()
    finally:
        conn.close()
    return ok(redirect=url_for("learn.topic_page", tid=tid))


@bp.post("/api/topic/<int:tid>/test/start")
@api_login_required
@json_only
def topic_test_start(tid):
    user = current_user()
    conn = c.get_db()
    try:
        topic = conn.execute("SELECT * FROM topics WHERE id=? AND published=1", (tid,)).fetchone()
        if not topic:
            return fail("Mavzu topilmadi.", 404)
        info = topic_info(conn, user, tid)
        if info and info["state"] in CLOSED:
            return fail("Bu dars hali yopiq. Avval oldingi mavzu testidan o'ting.", 403)
        if info and info["state"] == "skipped":
            return fail("Bu mavzu dars rejangizga kirmaydi.", 403)
        if info and info["passed"] and not info["first_failed"]:
            return fail("Siz bu mavzu testidan o'tgansiz.", 403)
        left = conn.execute(
            "SELECT COUNT(*) FROM materials m WHERE m.topic_id=? AND NOT EXISTS "
            "(SELECT 1 FROM reads r WHERE r.material_id=m.id AND r.user_id=?)", (tid, user["id"]),
        ).fetchone()[0]
        if left:
            return fail("Avval mavzudagi barcha materiallar bilan tanishib chiqing.")
        aid, err = start_attempt(conn, user, "topic", topic=topic)
    finally:
        conn.close()
    if err:
        return err
    return ok(redirect=url_for("learn.quiz_page", aid=aid))


# ---------------- Testlar bo'limi: DTM, olimpiada, milliy sertifikat ----------------
@bp.get("/exams")
@bp.get("/tests")
@login_required
def exams_home():
    return redirect(url_for("learn.exams_list", kind=next(iter(c.EXAM_KINDS))))


@bp.get("/exams/<kind>")
@login_required
def exams_list(kind):
    exam_kind_or_404(kind)
    user = current_user()
    conn = c.get_db()
    try:
        exams = conn.execute(
            """SELECT e.*,
                 (SELECT COUNT(*) FROM exam_questions q WHERE q.exam_id=e.id AND q.section='a') AS n_a,
                 (SELECT COUNT(*) FROM exam_questions q WHERE q.exam_id=e.id AND q.section='b') AS n_b,
                 (SELECT MAX(100 * score / total) FROM attempts a WHERE a.exam_id=e.id AND a.user_id=?
                    AND a.finished_at IS NOT NULL AND a.total > 0) AS best,
                 (SELECT COUNT(*) FROM attempts a WHERE a.exam_id=e.id AND a.user_id=?
                    AND a.finished_at IS NOT NULL) AS tries,
                 (SELECT id FROM attempts a WHERE a.exam_id=e.id AND a.user_id=?
                    AND a.finished_at IS NULL LIMIT 1) AS pending
               FROM exams e WHERE e.kind=? AND e.published=1 ORDER BY e.position, e.id""",
            (user["id"], user["id"], user["id"], kind),
        ).fetchall()
        counts = {
            r["kind"]: r["n"] for r in conn.execute(
                "SELECT kind, COUNT(*) AS n FROM exams WHERE published=1 GROUP BY kind"
            )
        }
        st = settings(conn)
    finally:
        conn.close()
    shaped = [exam_shape(e, st) for e in exams]
    return render_template("exams.html", exams=shaped, kind=kind, counts=counts, exam_nav_kind=kind)


def exam_shape(e, st):
    """Imtihon tuzilishi: savollar soni va maksimal ball (sozlamalardagi soniga ko'ra)."""
    d = dict(e)
    n_a = d.get("n_a", 0)
    n_b = d.get("n_b", 0)
    if d["kind"] == "dtm":
        qa = min(n_a, st["dtm_mandatory_count"])
        qb = min(n_b, st["dtm_special_count"])
        d["parts"] = [
            {"name": c.DTM_SECTIONS["a"], "n": qa, "points": d["points_a"]},
            {"name": c.DTM_SECTIONS["b"], "n": qb, "points": d["points_b"]},
        ]
    else:
        qa = min(n_a + n_b, st[f"{d['kind']}_count"])
        qb = 0
        d["parts"] = [{"name": "Savollar", "n": qa, "points": d["points_a"]}]
    d["n_q"] = qa + qb
    d["max_points"] = round(sum(p["n"] * p["points"] for p in d["parts"]), 2)
    return d


@bp.get("/exam/<int:eid>")
@login_required
def exam_page(eid):
    user = current_user()
    conn = c.get_db()
    try:
        exam = conn.execute(
            """SELECT e.*,
                 (SELECT COUNT(*) FROM exam_questions q WHERE q.exam_id=e.id AND q.section='a') AS n_a,
                 (SELECT COUNT(*) FROM exam_questions q WHERE q.exam_id=e.id AND q.section='b') AS n_b
               FROM exams e WHERE e.id=? AND e.published=1""", (eid,),
        ).fetchone()
        if not exam:
            abort(404)
        st = settings(conn)
        topics = conn.execute(
            """SELECT t.title, COUNT(*) AS n FROM exam_questions q JOIN topics t ON t.id=q.topic_id
               WHERE q.exam_id=? GROUP BY t.id ORDER BY n DESC""", (eid,),
        ).fetchall()
        history = conn.execute(
            "SELECT * FROM attempts WHERE user_id=? AND exam_id=? AND finished_at IS NOT NULL "
            "ORDER BY id DESC LIMIT 10", (user["id"], eid),
        ).fetchall()
        expire_overdue(conn, user["id"])
        pending = conn.execute(
            "SELECT id, paused FROM attempts WHERE user_id=? AND exam_id=? AND finished_at IS NULL "
            "ORDER BY id DESC LIMIT 1", (user["id"], eid),
        ).fetchone()
    finally:
        conn.close()
    return render_template(
        "exam.html", exam=exam_shape(exam, st), topics=topics, history=history, pending=pending,
        kind_name=c.EXAM_KINDS[exam["kind"]][0], exam_nav_kind=exam["kind"],
    )


@bp.post("/api/exam/<int:eid>/start")
@api_login_required
@json_only
def exam_start(eid):
    conn = c.get_db()
    try:
        exam = conn.execute("SELECT * FROM exams WHERE id=? AND published=1", (eid,)).fetchone()
        if not exam:
            return fail("Test topilmadi.", 404)
        aid, err = start_attempt(conn, current_user(), "exam", exam=exam)
    finally:
        conn.close()
    if err:
        return err
    return ok(redirect=url_for("learn.quiz_page", aid=aid))


# ---------------- Test ishlash ----------------
@bp.get("/quiz/<int:aid>")
@login_required
def quiz_page(aid):
    conn = c.get_db()
    try:
        a = get_attempt(conn, aid, current_user()["id"])
        if a["finished_at"]:
            return redirect(url_for("learn.result_page", aid=aid))
        title, back, kind_label, nav_kind = attempt_title(conn, a)
    finally:
        conn.close()
    return render_template("quiz.html", aid=aid, title=title, back=back, kind_label=kind_label,
                           exam_nav_kind=nav_kind)


@bp.get("/api/quiz/<int:aid>")
@api_login_required
def quiz_data(aid):
    conn = c.get_db()
    try:
        a = get_attempt(conn, aid, current_user()["id"])
        result_url = url_for("learn.result_page", aid=aid)
        if a["finished_at"]:
            return fail("Bu test yakunlangan.", 410, redirect=result_url)
        now = int(time.time())
        draft = saved_answers(a)
        no_time = a["paused"] and a["time_left"] is not None and a["time_left"] <= 0
        if no_time or is_overdue(a):
            finalize(conn, a, draft)
            return fail("Vaqt tugagan, test yakunlandi.", 410, redirect=result_url)
        if a["paused"]:
            # Eski bazada to'xtatilgan testni davom ettirish: qolgan vaqt qayta hisoblanadi
            deadline = now + a["time_left"] if a["time_left"] is not None else None
            conn.execute(
                "UPDATE attempts SET paused=0, deadline=?, time_left=NULL WHERE id=? AND paused=1", (deadline, aid),
            )
            conn.commit()
            a = get_attempt(conn, aid, current_user()["id"])
        payload = json.loads(a["payload"])
    finally:
        conn.close()
    remaining = max(0, a["deadline"] - int(time.time())) if a["deadline"] else None
    return ok(
        questions=[
            {"text": q["text"], "options": q["options"], "topic": q["topic"], "section": q.get("section", ""),
             "points": q.get("points", 1)}
            for q in payload
        ],
        answers=draft if draft and len(draft) == len(payload) else None,
        remaining=remaining,
    )


def _load_open_attempt(conn, aid):
    """Javob qabul qilsa bo'ladigan test. Vaqti tugagan bo'lsa, kechikkan javoblar hisobga olinmaydi:
    test o'z vaqtida saqlangan javoblar bilan yakunlanadi."""
    a = get_attempt(conn, aid, current_user()["id"])
    result_url = url_for("learn.result_page", aid=aid)
    if a["finished_at"]:
        return a, ok(redirect=result_url)
    if is_overdue(a):
        finalize(conn, a, saved_answers(a))
        return a, fail("Vaqt tugagan, test yakunlandi.", 410, redirect=result_url)
    return a, None


def _paused_fail(aid):
    """Eski bazada to'xtatib qo'yilgan test: avval sahifasi ochilib, davom ettirilishi kerak."""
    return fail("Test to'xtatilgan. Uni qaytadan oching.", 409, redirect=url_for("learn.quiz_page", aid=aid))


@bp.post("/api/quiz/<int:aid>/save")
@api_login_required
@json_only
def quiz_save(aid):
    conn = c.get_db()
    try:
        a, done = _load_open_attempt(conn, aid)
        if done:
            return done
        answers = clean_answers(body().get("answers"), len(json.loads(a["payload"])))
        if answers is None:
            return fail("Javoblar noto'g'ri formatda.")
        cur = conn.execute(
            "UPDATE attempts SET draft=? WHERE id=? AND finished_at IS NULL AND paused=0", (json.dumps(answers), aid),
        )
        conn.commit()
        if cur.rowcount == 0:
            return _paused_fail(aid)
    finally:
        conn.close()
    return ok()


@bp.post("/api/quiz/<int:aid>/submit")
@api_login_required
@json_only
def quiz_submit(aid):
    conn = c.get_db()
    try:
        a, done = _load_open_attempt(conn, aid)
        if done:
            return done
        answers = clean_answers(body().get("answers"), len(json.loads(a["payload"])))
        if answers is None:
            return fail("Javoblar noto'g'ri formatda.")
        if a["paused"]:
            return _paused_fail(aid)
        finalize(conn, a, answers)
    finally:
        conn.close()
    return ok(redirect=url_for("learn.result_page", aid=aid))


def review_items(payload, answers):
    out = []
    for n, (q, ans) in enumerate(zip(payload, answers), 1):
        if ans is None:
            status = "skip"
        elif ans == IDK:
            status = "idk"
        elif ans == q["correct"]:
            status = "right"
        else:
            status = "wrong"
        out.append({**q, "n": n, "chosen": ans, "right": status == "right", "status": status})
    return out


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
        pd = plan_data(conn, user)
        title, back, kind_label, nav_kind = attempt_title(conn, a)
        exam = None
        if a["kind"] == "exam":
            exam = conn.execute("SELECT * FROM exams WHERE id=?", (a["exam_id"],)).fetchone()
        st = settings(conn)
    finally:
        conn.close()
    review = review_items(payload, res["answers"])
    counts = {s: sum(1 for r in review if r["status"] == s) for s in ("right", "wrong", "skip", "idk")}
    percent = round(100 * a["score"] / a["total"]) if a["total"] else 0
    limit = st["high_percent"] if a["kind"] == "diagnostic" else st["pass_percent"]
    weak = sorted([t for t in res["topics"] if t["percent"] < limit], key=lambda t: t["percent"])
    published_ids = {t["id"]: t for t in pd["all"]}
    for t in res["topics"]:
        t["available"] = t["id"] in published_ids and published_ids[t["id"]]["state"] not in CLOSED
    # Bo'limlar bo'yicha (DTM) natija
    sections = {}
    for q, r in zip(payload, review):
        if q.get("section"):
            s = sections.setdefault(q["section"], {"name": q["section"], "right": 0, "total": 0, "points": 0.0,
                                                   "max": 0.0})
            s["total"] += 1
            s["max"] += float(q.get("points", 1))
            if r["right"]:
                s["right"] += 1
                s["points"] += float(q.get("points", 1))
    duration = a["finished_at"] - a["created_at"]
    return render_template(
        "result.html", a=a, percent=percent, topics_res=res["topics"], review=review, counts=counts,
        weak=weak, passed=percent >= st["pass_percent"], title=title, back=back, kind_label=kind_label,
        exam=exam, next_topic=pd["current"], pass_percent=st["pass_percent"], duration=duration,
        exam_nav_kind=nav_kind, sections=list(sections.values()),
        points=a["points"] if a["points"] is not None else a["score"],
        max_points=a["max_points"] if a["max_points"] is not None else a["total"],
    )


# ---------------- Natijalarim, Xatolarim ----------------
@bp.get("/results")
@login_required
def results_page():
    user = current_user()
    f = request.args.get("f", "all")
    conn = c.get_db()
    try:
        if f in ("diagnostic", "topic"):
            rows = recent_attempts(conn, user["id"], 300, kind=f)
        elif f in c.EXAM_KINDS:
            rows = recent_attempts(conn, user["id"], 300, kind="exam", exam_kind=f)
        else:
            f = "all"
            rows = recent_attempts(conn, user["id"], 300)
        stats = stats_for(conn, user["id"])
    finally:
        conn.close()
    return render_template("results.html", rows=rows, f=f, stats=stats)


def collect_mistakes(conn, uid, limit=300):
    """Foydalanuvchining xatolari: har bir savol bo'yicha eng oxirgi javob hisobga olinadi
    (keyin to'g'ri javob bergan bo'lsa, xato ro'yxatdan chiqadi)."""
    rows = conn.execute(
        """SELECT a.id, a.kind, a.payload, a.result, a.finished_at, t.title AS topic_title,
                  e.title AS exam_title, e.kind AS exam_kind
           FROM attempts a LEFT JOIN topics t ON t.id=a.topic_id LEFT JOIN exams e ON e.id=a.exam_id
           WHERE a.user_id=? AND a.finished_at IS NOT NULL ORDER BY a.id DESC LIMIT ?""", (uid, limit),
    ).fetchall()
    seen, items = set(), []
    for a in rows:
        payload = json.loads(a["payload"])
        answers = json.loads(a["result"])["answers"]
        if a["kind"] == "diagnostic":
            source = "Diagnostika"
        elif a["kind"] == "exam":
            source = a["exam_title"] or "Test"
        else:
            source = f"Mavzu testi: {a['topic_title'] or ''}"
        for q, r in zip(payload, review_items(payload, answers)):
            key = ("exam" if a["kind"] == "exam" else "q", q["qid"])
            if key in seen:
                continue
            seen.add(key)
            if r["right"]:
                continue
            items.append({**r, "source": source, "aid": a["id"], "date": a["finished_at"]})
    return items


@bp.get("/mistakes")
@login_required
def mistakes_page():
    """Mavzu testidan birinchi urinishda o'tilmagan mavzular: qayta o'zlashtirish shu yerdan boshlanadi."""
    user = current_user()
    conn = c.get_db()
    try:
        items = [t for t in plan_data(conn, user)["all"] if t["first_failed"]]
        for t in items:
            rows = conn.execute(
                "SELECT id, score, total, finished_at FROM attempts WHERE user_id=? AND kind='topic' AND topic_id=? "
                "AND finished_at IS NOT NULL AND total > 0 ORDER BY id", (user["id"], t["id"]),
            ).fetchall()
            t["first"] = rows[0] if rows else None
            t["last"] = rows[-1] if rows else None
        st = settings(conn)
    finally:
        conn.close()
    items.sort(key=lambda t: t["passed"])      # o'tilmaganlari tepada, ichida dars reja tartibi saqlanadi
    return render_template("mistakes.html", items=items, st=st, states=STATES)
