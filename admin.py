"""Admin panel: mavzular (matn, rasm, fayl, havola, test), testlar, test sozlamalari, foydalanuvchilar, profil."""
import math
import os
import re
import secrets
import time
from functools import partial

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

import common as c
import excel_io
from learn import (
    LEVELS, STATES, block, collect_mistakes, diag_count_of, diag_quota, exam_shape, fresh_questions, one_line,
    parse_links, plan_data, recent_attempts, seen_questions, send_material_image, send_topic_file, settings,
    sniff_image, stats_for, test_size,
)
from web_utils import admin_required, check_csrf, is_admin, to_int

bp = Blueprint("admin", __name__)

MAX_FILE = 20 * 1024 * 1024     # mavzu fayli (word, pdf)
MAX_XLSX = 5 * 1024 * 1024
MAX_IMAGE = 5 * 1024 * 1024     # material rasmi
FILE_TYPES = {
    "pdf": b"%PDF",
    "docx": b"PK\x03\x04",
    "doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
}


_int = partial(to_int, default=0)


def _float(v, default=None, lo=0.0, hi=100.0):
    v = str(v or "").strip().replace(",", ".")
    try:
        n = float(v)
    except ValueError:
        return default
    if not math.isfinite(n):
        return default
    return min(hi, max(lo, n))


def _opt_int(v, lo=0, hi=600):
    return to_int(v, None, lo, hi)


def back_to(endpoint, anchor="", **kw):
    return redirect(url_for(endpoint, **kw) + (f"#{anchor}" if anchor else ""))


def read_upload(field, max_size):
    f = request.files.get(field)
    if not f or not f.filename:
        return None, None, "Fayl tanlanmagan."
    data = f.read(max_size + 1)
    if len(data) > max_size:
        return None, None, f"Fayl hajmi {max_size // 1024 // 1024} MB dan oshmasligi kerak."
    return f.filename, data, None


def students_sql():
    """Faqat o'quvchilar: adminlar statistika va ro'yxatga kirmaydi. Raqamlar normalize_phone dan o'tgan
    (faqat + va raqam), shuning uchun SQL ichiga yozish xavfsiz."""
    phones = ", ".join(f"'{p}'" for p in sorted(c.ADMIN_PHONES))
    return f"(SELECT id FROM users WHERE phone NOT IN ({phones}))"


def topic_titles(conn):
    return {r["id"]: r["title"] for r in conn.execute("SELECT id, title FROM topics ORDER BY position, id")}




# =====================================================================
#                              MAVZULAR
# =====================================================================
@bp.get("/admin")
@admin_required
def admin_index():
    conn = c.get_db()
    students = students_sql()
    try:
        st = settings(conn)
        topics = conn.execute(
            f"""SELECT t.*,
                 (SELECT COUNT(*) FROM materials m WHERE m.topic_id=t.id) AS n_mat,
                 (SELECT COUNT(*) FROM topic_files f WHERE f.topic_id=t.id) AS n_files,
                 (SELECT COUNT(*) FROM questions q WHERE q.topic_id=t.id) AS n_q,
                 (SELECT COUNT(*) FROM progress p WHERE p.topic_id=t.id AND p.passed=1
                    AND p.user_id IN {students}) AS n_passed
               FROM topics t ORDER BY t.position, t.id"""
        ).fetchall()
        stats = {
            "users": conn.execute(f"SELECT COUNT(*) FROM users WHERE id IN {students}").fetchone()[0],
            "topics": len(topics),
            "questions": conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            + conn.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0],
        }
        waiting = waiting_students(conn, st, students)
    finally:
        conn.close()
    rows = []
    for t in topics:
        n_diag = diag_quota(diag_count_of(t, st), t["n_q"], st)
        size = min(st["topic_count"] or t["n_q"], t["n_q"])
        rows.append({**dict(t), "n_diag": n_diag, "size": size, "waiting": waiting.get(t["id"], 0),
                     "tries": tries_enough(t["n_q"], n_diag, st)})
    diag_total = sum(t["n_diag"] for t in rows if t["published"])
    return render_template("admin/index.html", topics=rows, stats=stats, st=st, diag_total=diag_total)


def tries_enough(n_q, n_diag, st):
    """Diagnostikadan keyin qolgan savollar mavzu testiga necha urinishga yetadi (savol takrorlanmaydi)."""
    left, tries = n_q - n_diag, 0
    while (k := test_size(st, n_q, left)) > 0:
        left -= k
        tries += 1
    return tries


def waiting_students(conn, st, students):
    """{mavzu: yangi savol kutayotgan o'quvchilar soni}: testdan o'tmagan va yangi savol qolmaganlar."""
    out, seen = {}, {}
    for r in conn.execute(
        f"""SELECT p.user_id, p.topic_id, (SELECT COUNT(*) FROM questions q WHERE q.topic_id=p.topic_id) AS n_q
            FROM progress p WHERE p.passed=0 AND p.user_id IN {students}
              AND (p.attempts > 0 OR COALESCE(p.diag_percent, 0) < {int(st["high_percent"])}) AND NOT EXISTS (
              SELECT 1 FROM attempts a WHERE a.user_id=p.user_id AND a.topic_id=p.topic_id AND a.kind='topic'
                AND a.finished_at IS NULL)"""
    ).fetchall():
        uid, tid = r["user_id"], r["topic_id"]
        if uid not in seen:
            seen[uid] = seen_questions(conn, uid)
        if r["n_q"] and not test_size(st, r["n_q"], len(fresh_questions(conn, tid, seen[uid]))):
            out[tid] = out.get(tid, 0) + 1
    return out


def read_topic_form():
    title = one_line(request.form.get("title"), 120)
    summary = one_line(request.form.get("summary"), 300)
    pos = _int(request.form.get("position"))
    published = 1 if request.form.get("published") else 0
    return title, summary, pos, published


@bp.post("/admin/topic/new")
@admin_required
def admin_topic_new():
    check_csrf()
    data = read_topic_form()
    if len(data[0]) < 2:
        flash("Mavzu nomi kamida 2 ta belgi bo'lishi kerak.", "err")
        return redirect(url_for("admin.admin_index"))
    conn = c.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO topics(title, summary, position, published) VALUES (?, ?, ?, ?)", data,
        )
        conn.commit()
        tid = cur.lastrowid
    finally:
        conn.close()
    flash("Mavzu yaratildi. Endi matn, rasm, fayl, havola va test savollarini kiriting.", "ok")
    return redirect(url_for("admin.admin_topic", tid=tid))


@bp.get("/admin/topic/<int:tid>")
@admin_required
def admin_topic(tid):
    conn = c.get_db()
    try:
        topic = conn.execute("SELECT * FROM topics WHERE id=?", (tid,)).fetchone()
        if not topic:
            abort(404)
        materials = conn.execute("SELECT * FROM materials WHERE topic_id=? ORDER BY position, id", (tid,)).fetchall()
        files = conn.execute("SELECT * FROM topic_files WHERE topic_id=? ORDER BY id", (tid,)).fetchall()
        questions = conn.execute("SELECT * FROM questions WHERE topic_id=? ORDER BY id", (tid,)).fetchall()
        st = settings(conn)
    finally:
        conn.close()
    return render_template("admin/topic.html", topic=topic, materials=materials, files=files,
                           questions=questions, st=st)


@bp.post("/admin/topic/<int:tid>/save")
@admin_required
def admin_topic_save(tid):
    check_csrf()
    data = read_topic_form()
    if len(data[0]) < 2:
        flash("Mavzu nomi kamida 2 ta belgi bo'lishi kerak.", "err")
    else:
        conn = c.get_db()
        try:
            conn.execute("UPDATE topics SET title=?, summary=?, position=?, published=? WHERE id=?", (*data, tid))
            conn.commit()
        finally:
            conn.close()
        flash("Saqlandi.", "ok")
    return redirect(url_for("admin.admin_topic", tid=tid))


@bp.post("/admin/topic/<int:tid>/test")
@admin_required
def admin_topic_test(tid):
    """Mavzu testi: 1 savol balli va ajratiladigan vaqt."""
    check_csrf()
    minutes = _opt_int(request.form.get("test_time"), 0, 600)
    points = _float(request.form.get("test_points"), None, 0, 100)
    if not minutes:
        flash("Test uchun ajratiladigan vaqtni (daqiqa) kiriting.", "err")
    elif not points:
        flash("1 ta savol uchun ballni kiriting (masalan: 1.5).", "err")
    else:
        conn = c.get_db()
        try:
            conn.execute("UPDATE topics SET test_time=?, test_points=? WHERE id=?", (minutes, points, tid))
            conn.commit()
        finally:
            conn.close()
        flash("Test balli va vaqti saqlandi.", "ok")
    return back_to("admin.admin_topic", "questions", tid=tid)


@bp.post("/admin/topic/<int:tid>/move")
@admin_required
def admin_topic_move(tid):
    """Mavzular tartibini o'zgartirish (yuqoriga / pastga)."""
    check_csrf()
    up = request.form.get("dir") == "up"
    conn = c.get_db()
    try:
        ids = [r["id"] for r in conn.execute("SELECT id FROM topics ORDER BY position, id")]
        if tid in ids:
            i = ids.index(tid)
            j = i - 1 if up else i + 1
            if 0 <= j < len(ids):
                ids[i], ids[j] = ids[j], ids[i]
            conn.executemany("UPDATE topics SET position=? WHERE id=?", [(n, x) for n, x in enumerate(ids, 1)])
            conn.commit()
    finally:
        conn.close()
    return redirect(url_for("admin.admin_index"))


@bp.post("/admin/topic/<int:tid>/delete")
@admin_required
def admin_topic_delete(tid):
    check_csrf()
    conn = c.get_db()
    try:
        files = [r["stored"] for r in conn.execute(
            "SELECT stored FROM topic_files WHERE topic_id=? "
            "UNION ALL SELECT image FROM materials WHERE topic_id=? AND image IS NOT NULL", (tid, tid))]
        conn.execute("DELETE FROM reads WHERE material_id IN (SELECT id FROM materials WHERE topic_id=?)", (tid,))
        conn.execute("DELETE FROM progress WHERE topic_id=?", (tid,))
        conn.execute("DELETE FROM attempts WHERE kind='topic' AND topic_id=? AND finished_at IS NULL", (tid,))
        conn.execute("DELETE FROM topics WHERE id=?", (tid,))
        conn.commit()
    finally:
        conn.close()
    for f in files:
        remove_stored_file(f)
    flash("Mavzu o'chirildi.", "ok")
    return redirect(url_for("admin.admin_index"))


# ---------------- Materiallar (matn, rasm, havolalar) ----------------
def read_material_image():
    """(rasm baytlari, kengaytma, xato). Rasm tanlanmagan bo'lsa, (None, None, None)."""
    f = request.files.get("image")
    if not f or not f.filename:
        return None, None, None
    data = f.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        return None, None, f"Rasm hajmi {MAX_IMAGE // 1024 // 1024} MB dan oshmasligi kerak."
    ext = sniff_image(data)
    if not ext:
        return None, None, "Faqat JPG, PNG yoki WEBP rasm yuklash mumkin."
    return data, ext, None


def store_file(tid, data, ext):
    os.makedirs(c.FILES_DIR, exist_ok=True)
    stored = f"{tid}_{secrets.token_hex(8)}.{ext}"
    with open(os.path.join(c.FILES_DIR, stored), "wb") as out:
        out.write(data)
    return stored


def read_material_form(has_image):
    title = one_line(request.form.get("title"), 150)
    text = block(request.form.get("body"), 20000)
    links_raw = block(request.form.get("url"), 3000)
    pos = _int(request.form.get("position"))
    if len(title) < 2:
        return None, "Material nomini kiriting."
    links, errors = parse_links(links_raw)
    if errors:
        return None, errors[0] + " (har bir qatorda: https://... yoki «Nomi | https://...»)"
    if not text and not links and not has_image:
        return None, "Material matni, rasmi yoki havolasini kiriting."
    return (title, text, links_raw, pos), None


@bp.post("/admin/topic/<int:tid>/material")
@admin_required
def admin_material_add(tid):
    check_csrf()
    img, ext, err = read_material_image()
    data = None
    if not err:
        data, err = read_material_form(bool(img))
    if err:
        flash(err, "err")
    else:
        conn = c.get_db()
        try:
            if not conn.execute("SELECT 1 FROM topics WHERE id=?", (tid,)).fetchone():
                abort(404)
            stored = store_file(tid, img, ext) if img else None
            conn.execute(
                "INSERT INTO materials(topic_id, title, body, url, position, image) VALUES (?, ?, ?, ?, ?, ?)",
                (tid, *data, stored),
            )
            conn.commit()
        finally:
            conn.close()
        flash("Material qo'shildi.", "ok")
    return back_to("admin.admin_topic", "materials", tid=tid)


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
            img, ext, err = read_material_image()
            keep = m["image"] if not img and not request.form.get("image_delete") else None
            data = None
            if not err:
                data, err = read_material_form(bool(img or keep))
            if err:
                flash(err, "err")
            else:
                image = store_file(m["topic_id"], img, ext) if img else keep
                conn.execute("UPDATE materials SET title=?, body=?, url=?, position=?, image=? WHERE id=?",
                             (*data, image, mid))
                conn.commit()
                if m["image"] != image:
                    remove_stored_file(m["image"])
                flash("Saqlandi.", "ok")
                return back_to("admin.admin_topic", "materials", tid=m["topic_id"])
    finally:
        conn.close()
    return render_template("admin/edit_material.html", m=m)


@bp.get("/admin/material/<int:mid>/image")
@admin_required
def admin_material_image(mid):
    conn = c.get_db()
    try:
        m = conn.execute("SELECT image FROM materials WHERE id=? AND image IS NOT NULL", (mid,)).fetchone()
    finally:
        conn.close()
    if not m:
        abort(404)
    return send_material_image(m)


@bp.post("/admin/material/<int:mid>/delete")
@admin_required
def admin_material_delete(mid):
    check_csrf()
    conn = c.get_db()
    try:
        m = conn.execute("SELECT topic_id, image FROM materials WHERE id=?", (mid,)).fetchone()
        if not m:
            abort(404)
        conn.execute("DELETE FROM reads WHERE material_id=?", (mid,))
        conn.execute("DELETE FROM materials WHERE id=?", (mid,))
        conn.commit()
    finally:
        conn.close()
    remove_stored_file(m["image"])
    flash("Material o'chirildi.", "ok")
    return back_to("admin.admin_topic", "materials", tid=m["topic_id"])


# ---------------- Mavzu fayllari (Word, PDF) ----------------
def remove_stored_file(name):
    if name and re.match(r"^\d+_[0-9a-f]{16}\.(pdf|docx|doc|jpg|png|webp)$", name):
        try:
            os.remove(os.path.join(c.FILES_DIR, name))
        except OSError:
            pass


@bp.post("/admin/topic/<int:tid>/file")
@admin_required
def admin_file_upload(tid):
    check_csrf()
    name, data, err = read_upload("file", MAX_FILE)
    if not err:
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in FILE_TYPES:
            err = "Faqat Word (.doc, .docx) yoki PDF fayl yuklash mumkin."
        elif not data.startswith(FILE_TYPES[ext]):
            err = "Fayl mazmuni kengaytmasiga mos emas (buzilgan yoki boshqa turdagi fayl)."
    if err:
        flash(err, "err")
        return back_to("admin.admin_topic", "files", tid=tid)
    title = one_line(request.form.get("title"), 150)
    base = os.path.basename(name.replace("\\", "/"))[:150]
    display = f"{title}.{ext}" if title else base
    conn = c.get_db()
    try:
        if not conn.execute("SELECT 1 FROM topics WHERE id=?", (tid,)).fetchone():
            abort(404)
        stored = store_file(tid, data, ext)
        conn.execute("INSERT INTO topic_files(topic_id, name, stored, size, created_at) VALUES (?, ?, ?, ?, ?)",
                     (tid, display, stored, len(data), int(time.time())))
        conn.commit()
    finally:
        conn.close()
    flash("Fayl yuklandi.", "ok")
    return back_to("admin.admin_topic", "files", tid=tid)


@bp.get("/admin/file/<int:fid>")
@admin_required
def admin_file(fid):
    conn = c.get_db()
    try:
        f = conn.execute("SELECT * FROM topic_files WHERE id=?", (fid,)).fetchone()
    finally:
        conn.close()
    if not f:
        abort(404)
    return send_topic_file(f)


@bp.post("/admin/file/<int:fid>/delete")
@admin_required
def admin_file_delete(fid):
    check_csrf()
    conn = c.get_db()
    try:
        f = conn.execute("SELECT * FROM topic_files WHERE id=?", (fid,)).fetchone()
        if not f:
            abort(404)
        conn.execute("DELETE FROM topic_files WHERE id=?", (fid,))
        conn.commit()
    finally:
        conn.close()
    remove_stored_file(f["stored"])
    flash("Fayl o'chirildi.", "ok")
    return back_to("admin.admin_topic", "files", tid=f["topic_id"])


# ---------------- Mavzu savollari (mavzu testi va diagnostika uchun umumiy) ----------------
def read_question_form():
    text = one_line(request.form.get("text"), 1000)
    opts = [one_line(request.form.get(f"o{i}"), 300) for i in range(1, 5)]
    correct = request.form.get("correct", "")
    expl = one_line(request.form.get("explanation"), 1000)
    if len(text) < 3:
        return None, "Savol matnini kiriting."
    if not all(opts):
        return None, "Barcha 4 ta variantni to'ldiring."
    if len({o.lower() for o in opts}) < 4:
        return None, "Variantlar bir-biridan farq qilishi kerak."
    if correct not in ("1", "2", "3", "4"):
        return None, "To'g'ri javobni tanlang."
    return (text, *opts, int(correct), expl), None


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
            if not conn.execute("SELECT 1 FROM topics WHERE id=?", (tid,)).fetchone():
                abort(404)
            conn.execute(
                "INSERT INTO questions(topic_id, text, o1, o2, o3, o4, correct, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (tid, *data),
            )
            conn.commit()
        finally:
            conn.close()
        flash("Savol qo'shildi.", "ok")
    return back_to("admin.admin_topic", "questions", tid=tid)


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
                    "UPDATE questions SET text=?, o1=?, o2=?, o3=?, o4=?, correct=?, explanation=? WHERE id=?",
                    (*data, qid),
                )
                conn.commit()
                flash("Saqlandi.", "ok")
                return back_to("admin.admin_topic", "questions", tid=q["topic_id"])
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
    return back_to("admin.admin_topic", "questions", tid=q["topic_id"])


def flash_import(n, errors):
    if n:
        flash(f"{n} ta savol qo'shildi.", "ok")
    for e in errors[:10]:
        flash(e, "err")
    if len(errors) > 10:
        flash(f"... yana {len(errors) - 10} ta xato.", "err")
    if not n and not errors:
        flash("Savol topilmadi.", "err")


@bp.post("/admin/topic/<int:tid>/import")
@admin_required
def admin_import(tid):
    check_csrf()
    parsed, errors = parse_questions(request.form.get("text", ""), "topic")
    if parsed:
        conn = c.get_db()
        try:
            conn.executemany(
                "INSERT INTO questions(topic_id, text, o1, o2, o3, o4, correct, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(tid, *p) for p in parsed],
            )
            conn.commit()
        finally:
            conn.close()
    flash_import(len(parsed), errors)
    return back_to("admin.admin_topic", "questions", tid=tid)


@bp.post("/admin/topic/<int:tid>/import-xlsx")
@admin_required
def admin_import_xlsx(tid):
    check_csrf()
    name, data, err = read_upload("file", MAX_XLSX)
    if not err and not excel_io.is_xlsx(data):
        err = "Faqat .xlsx formatidagi Excel fayl yuklang (namunani yuklab olib to'ldiring)."
    if err:
        flash(err, "err")
        return back_to("admin.admin_topic", "questions", tid=tid)
    items, errors = excel_io.parse_xlsx(data, "topic")
    if items:
        conn = c.get_db()
        try:
            if not conn.execute("SELECT 1 FROM topics WHERE id=?", (tid,)).fetchone():
                abort(404)
            conn.executemany(
                "INSERT INTO questions(topic_id, text, o1, o2, o3, o4, correct, explanation) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(tid, it["text"], *it["opts"], it["correct"], it["explanation"]) for it in items],
            )
            conn.commit()
        finally:
            conn.close()
    flash_import(len(items), errors)
    return back_to("admin.admin_topic", "questions", tid=tid)


@bp.get("/admin/template/<kind>.xlsx")
@admin_required
def admin_template(kind):
    if kind not in ("topic", "exam"):
        abort(404)
    conn = c.get_db()
    try:
        titles = list(topic_titles(conn).values())
    finally:
        conn.close()
    data = excel_io.build_template(kind, titles)
    fname = "mavzu_savollari_namuna.xlsx" if kind == "topic" else "test_savollari_namuna.xlsx"
    return Response(data, mimetype=excel_io.XLSX_MIME,
                    headers={"Content-Disposition": f"attachment; filename={fname}", "Cache-Control": "no-store"})


# =====================================================================
#                    TESTLAR (DTM, olimpiada, sertifikat)
# =====================================================================
def kind_defaults(st):
    return {
        "dtm": {"time": st["dtm_time"], "pa": st["dtm_points_mandatory"], "pb": st["dtm_points_special"]},
        "olympiad": {"time": st["olympiad_time"], "pa": st["olympiad_points"], "pb": 0},
        "certificate": {"time": st["certificate_time"], "pa": st["certificate_points"], "pb": 0},
    }


def read_exam_form():
    kind = request.form.get("kind", "")
    title = one_line(request.form.get("title"), 150)
    desc = block(request.form.get("description"), 1000)
    time_limit = _int(request.form.get("time_limit"), lo=0, hi=600)
    pa = _float(request.form.get("points_a"), None, 0, 100)
    pb = _float(request.form.get("points_b"), 0.0, 0, 100) if kind == "dtm" else 0.0
    pos = _int(request.form.get("position"))
    shuffle = 1 if request.form.get("shuffle") else 0
    published = 1 if request.form.get("published") else 0
    if kind not in c.EXAM_KINDS:
        return None, "Test turini tanlang."
    if len(title) < 2:
        return None, "Test nomi kamida 2 ta belgi bo'lishi kerak."
    if pa is None or pa <= 0:
        return None, "1 ta savol uchun ballni kiriting (masalan: 1.1)."
    if kind == "dtm" and (pb is None or pb <= 0):
        return None, "Mutaxassislik bloki uchun ballni kiriting (masalan: 3.1)."
    if time_limit <= 0:
        return None, "Test uchun ajratiladigan vaqtni (daqiqa) kiriting."
    return (kind, title, desc, time_limit, pa, pb or 0.0, shuffle, pos, published), None


def exam_rows(conn, where="", args=()):
    return conn.execute(
        f"""SELECT e.*,
              (SELECT COUNT(*) FROM exam_questions q WHERE q.exam_id=e.id AND q.section='a') AS n_a,
              (SELECT COUNT(*) FROM exam_questions q WHERE q.exam_id=e.id AND q.section='b') AS n_b,
              (SELECT COUNT(*) FROM attempts a WHERE a.exam_id=e.id AND a.finished_at IS NOT NULL) AS n_att
            FROM exams e {where} ORDER BY e.kind, e.position, e.id""", args,
    ).fetchall()


@bp.get("/admin/exams")
@admin_required
def admin_exams():
    conn = c.get_db()
    try:
        st = settings(conn)
        exams = [exam_shape(e, st) | {"n_att": e["n_att"]} for e in exam_rows(conn)]
    finally:
        conn.close()
    sel = request.args.get("kind")
    return render_template("admin/exams.html", exams=exams,
                           sel_kind=sel if sel in c.EXAM_KINDS else next(iter(c.EXAM_KINDS)),
                           st=st, defaults=kind_defaults(st))


@bp.post("/admin/exam/new")
@admin_required
def admin_exam_new():
    check_csrf()
    data, err = read_exam_form()
    if err:
        flash(err, "err")
        return redirect(url_for("admin.admin_exams", kind=request.form.get("kind", "dtm")))
    conn = c.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO exams(kind, title, description, time_limit, points_a, points_b, shuffle, position, "
            "published, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (*data, int(time.time())),
        )
        conn.commit()
        eid = cur.lastrowid
    finally:
        conn.close()
    flash("Test yaratildi. Endi savollar qo'shing (bittalab yoki Excel orqali).", "ok")
    return redirect(url_for("admin.admin_exam", eid=eid))


@bp.get("/admin/exam/<int:eid>")
@admin_required
def admin_exam(eid):
    conn = c.get_db()
    try:
        rows = exam_rows(conn, "WHERE e.id=?", (eid,))
        if not rows:
            abort(404)
        st = settings(conn)
        exam = exam_shape(rows[0], st)
        questions = conn.execute(
            """SELECT q.*, t.title AS topic_title FROM exam_questions q
               LEFT JOIN topics t ON t.id=q.topic_id WHERE q.exam_id=? ORDER BY q.section, q.position, q.id""",
            (eid,),
        ).fetchall()
        topics = conn.execute("SELECT id, title FROM topics ORDER BY position, id").fetchall()
    finally:
        conn.close()
    return render_template("admin/exam.html", exam=exam, questions=questions, topics=topics, st=st,
                           defaults=kind_defaults(st))


@bp.post("/admin/exam/<int:eid>/save")
@admin_required
def admin_exam_save(eid):
    check_csrf()
    data, err = read_exam_form()
    if err:
        flash(err, "err")
    else:
        conn = c.get_db()
        try:
            conn.execute(
                "UPDATE exams SET kind=?, title=?, description=?, time_limit=?, points_a=?, points_b=?, shuffle=?, "
                "position=?, published=? WHERE id=?", (*data, eid),
            )
            conn.commit()
        finally:
            conn.close()
        flash("Saqlandi.", "ok")
    return redirect(url_for("admin.admin_exam", eid=eid))


@bp.post("/admin/exam/<int:eid>/delete")
@admin_required
def admin_exam_delete(eid):
    check_csrf()
    conn = c.get_db()
    try:
        e = conn.execute("SELECT kind FROM exams WHERE id=?", (eid,)).fetchone()
        conn.execute("DELETE FROM attempts WHERE exam_id=? AND finished_at IS NULL", (eid,))
        conn.execute("DELETE FROM exams WHERE id=?", (eid,))
        conn.commit()
    finally:
        conn.close()
    flash("Test o'chirildi.", "ok")
    return redirect(url_for("admin.admin_exams", kind=e["kind"] if e else "dtm"))


def read_topic_ref(conn):
    tid = to_int(request.form.get("topic_id"))
    if tid is not None and conn.execute("SELECT 1 FROM topics WHERE id=?", (tid,)).fetchone():
        return tid
    return None


def read_exam_question_form(conn):
    text = one_line(request.form.get("text"), 1000)
    opts = [one_line(request.form.get(f"o{i}"), 300) for i in range(1, 5)]
    correct = request.form.get("correct", "")
    expl = one_line(request.form.get("explanation"), 1000)
    section = "b" if request.form.get("section") == "b" else "a"
    if len(text) < 3:
        return None, "Savol matnini kiriting."
    if not all(opts):
        return None, "Barcha 4 ta variantni to'ldiring."
    if len({o.lower() for o in opts}) < 4:
        return None, "Variantlar bir-biridan farq qilishi kerak."
    if correct not in ("1", "2", "3", "4"):
        return None, "To'g'ri javobni tanlang."
    return (read_topic_ref(conn), section, text, *opts, int(correct), expl), None


def next_exam_pos(conn, eid):
    return conn.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM exam_questions WHERE exam_id=?", (eid,)
    ).fetchone()[0]


@bp.post("/admin/exam/<int:eid>/question")
@admin_required
def admin_exam_question_add(eid):
    check_csrf()
    conn = c.get_db()
    try:
        if not conn.execute("SELECT 1 FROM exams WHERE id=?", (eid,)).fetchone():
            abort(404)
        data, err = read_exam_question_form(conn)
        if err:
            flash(err, "err")
        else:
            conn.execute(
                "INSERT INTO exam_questions(exam_id, topic_id, section, text, o1, o2, o3, o4, correct, explanation, "
                "position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (eid, *data, next_exam_pos(conn, eid)),
            )
            conn.commit()
            flash("Savol qo'shildi.", "ok")
    finally:
        conn.close()
    return back_to("admin.admin_exam", "questions", eid=eid)


@bp.route("/admin/exam-question/<int:qid>", methods=["GET", "POST"])
@admin_required
def admin_exam_question_edit(qid):
    conn = c.get_db()
    try:
        q = conn.execute(
            "SELECT q.*, e.kind AS exam_kind FROM exam_questions q JOIN exams e ON e.id=q.exam_id WHERE q.id=?",
            (qid,),
        ).fetchone()
        if not q:
            abort(404)
        if request.method == "POST":
            check_csrf()
            data, err = read_exam_question_form(conn)
            if err:
                flash(err, "err")
            else:
                conn.execute(
                    "UPDATE exam_questions SET topic_id=?, section=?, text=?, o1=?, o2=?, o3=?, o4=?, correct=?, "
                    "explanation=? WHERE id=?", (*data, qid),
                )
                conn.commit()
                flash("Saqlandi.", "ok")
                return back_to("admin.admin_exam", "questions", eid=q["exam_id"])
        topics = conn.execute("SELECT id, title FROM topics ORDER BY position, id").fetchall()
    finally:
        conn.close()
    return render_template("admin/edit_exam_question.html", q=q, topics=topics)


@bp.post("/admin/exam-question/<int:qid>/delete")
@admin_required
def admin_exam_question_delete(qid):
    check_csrf()
    conn = c.get_db()
    try:
        q = conn.execute("SELECT exam_id FROM exam_questions WHERE id=?", (qid,)).fetchone()
        if not q:
            abort(404)
        conn.execute("DELETE FROM exam_questions WHERE id=?", (qid,))
        conn.commit()
    finally:
        conn.close()
    flash("Savol o'chirildi.", "ok")
    return back_to("admin.admin_exam", "questions", eid=q["exam_id"])


@bp.post("/admin/exam/<int:eid>/import")
@admin_required
def admin_exam_import(eid):
    check_csrf()
    parsed, errors = parse_questions(request.form.get("text", ""), "exam")
    section = "b" if request.form.get("section") == "b" else "a"
    if parsed:
        conn = c.get_db()
        try:
            if not conn.execute("SELECT 1 FROM exams WHERE id=?", (eid,)).fetchone():
                abort(404)
            tid = read_topic_ref(conn)
            pos = next_exam_pos(conn, eid)
            conn.executemany(
                "INSERT INTO exam_questions(exam_id, topic_id, section, text, o1, o2, o3, o4, correct, explanation, "
                "position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(eid, tid, section, *p, pos + i) for i, p in enumerate(parsed)],
            )
            conn.commit()
        finally:
            conn.close()
    flash_import(len(parsed), errors)
    return back_to("admin.admin_exam", "questions", eid=eid)


@bp.post("/admin/exam/<int:eid>/import-xlsx")
@admin_required
def admin_exam_import_xlsx(eid):
    check_csrf()
    name, data, err = read_upload("file", MAX_XLSX)
    if not err and not excel_io.is_xlsx(data):
        err = "Faqat .xlsx formatidagi Excel fayl yuklang (namunani yuklab olib to'ldiring)."
    if err:
        flash(err, "err")
        return back_to("admin.admin_exam", "questions", eid=eid)
    conn = c.get_db()
    try:
        exam = conn.execute("SELECT * FROM exams WHERE id=?", (eid,)).fetchone()
        if not exam:
            abort(404)
        items, errors = excel_io.parse_xlsx(data, "exam", topic_titles(conn))
        pos = next_exam_pos(conn, eid)
        conn.executemany(
            "INSERT INTO exam_questions(exam_id, topic_id, section, text, o1, o2, o3, o4, correct, explanation, "
            "position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(eid, it["topic_id"], it["section"] if exam["kind"] == "dtm" else "a", it["text"], *it["opts"],
              it["correct"], it["explanation"], pos + i) for i, it in enumerate(items)],
        )
        conn.commit()
    finally:
        conn.close()
    flash_import(len(items), errors)
    return back_to("admin.admin_exam", "questions", eid=eid)


# =====================================================================
#                          FOYDALANUVCHILAR
# =====================================================================
@bp.get("/admin/users")
@admin_required
def admin_users():
    q = one_line(request.args.get("q"), 60)
    now = int(time.time())
    week = now - 7 * 86400
    students = students_sql()
    conn = c.get_db()
    try:
        st = settings(conn)
        n_topics = conn.execute("SELECT COUNT(*) FROM topics WHERE published=1").fetchone()[0]
        sql = f"""SELECT u.*,
                   (SELECT COUNT(*) FROM progress p JOIN topics t ON t.id=p.topic_id
                      WHERE p.user_id=u.id AND p.passed=1 AND t.published=1) AS passed_cnt,
                   (SELECT score*100/total FROM attempts a WHERE a.user_id=u.id AND a.kind='diagnostic'
                      AND a.finished_at IS NOT NULL AND a.total>0 ORDER BY a.id DESC LIMIT 1) AS diag,
                   (SELECT COUNT(*) FROM attempts a WHERE a.user_id=u.id AND a.finished_at IS NOT NULL) AS n_att,
                   (SELECT ROUND(AVG(100.0*score/total)) FROM attempts a WHERE a.user_id=u.id
                      AND a.finished_at IS NOT NULL AND a.total>0) AS avg_pct
                 FROM users u WHERE u.id IN {students}"""
        args = []
        if q:
            sql += " AND (u.first_name LIKE ? OR u.last_name LIKE ? OR u.phone LIKE ? OR u.region LIKE ?)"
            like = f"%{q}%"
            args = [like, like, like, like]
        users = conn.execute(sql + " ORDER BY u.id DESC LIMIT 500", args).fetchall()
        one = lambda s, a=(): conn.execute(s, a).fetchone()[0]  # noqa: E731
        stats = {
            "total": one(f"SELECT COUNT(*) FROM users WHERE id IN {students}"),
            "new_week": one(f"SELECT COUNT(*) FROM users WHERE id IN {students} AND created_at > ?", (week,)),
            "active_week": one(f"SELECT COUNT(*) FROM users WHERE id IN {students} AND last_seen > ?", (week,)),
            "diag_done": one("SELECT COUNT(DISTINCT user_id) FROM attempts WHERE kind='diagnostic' "
                             f"AND finished_at IS NOT NULL AND user_id IN {students}"),
            "declined": one(f"SELECT COUNT(*) FROM users WHERE id IN {students} AND diag_declined=1"),
            "attempts": one(f"SELECT COUNT(*) FROM attempts WHERE finished_at IS NOT NULL AND user_id IN {students}"),
            "avg": round(one("SELECT AVG(100.0*score/total) FROM attempts WHERE finished_at IS NOT NULL "
                             f"AND total>0 AND user_id IN {students}") or 0),
        }
        regions = conn.execute(
            f"SELECT region, COUNT(*) AS n FROM users WHERE id IN {students} GROUP BY region ORDER BY n DESC"
        ).fetchall()
        topic_stats = conn.execute(
            f"""SELECT t.id, t.title, ROUND(AVG(p.diag_percent)) AS avg_diag, COUNT(p.diag_percent) AS n_diag,
                 SUM(CASE WHEN p.passed=1 THEN 1 ELSE 0 END) AS n_passed
               FROM topics t LEFT JOIN progress p ON p.topic_id=t.id AND p.user_id IN {students}
               WHERE t.published=1 GROUP BY t.id ORDER BY t.position, t.id"""
        ).fetchall()
        kinds_stats = conn.execute(
            f"""SELECT COALESCE(e.kind, a.kind) AS k, COUNT(*) AS n, ROUND(AVG(100.0*a.score/a.total)) AS avg
               FROM attempts a LEFT JOIN exams e ON e.id=a.exam_id
               WHERE a.finished_at IS NOT NULL AND a.total>0 AND a.user_id IN {students} GROUP BY k"""
        ).fetchall()
    finally:
        conn.close()
    return render_template("admin/users.html", users=users, n_topics=n_topics, stats=stats, regions=regions,
                           topic_stats=topic_stats, kinds_stats=kinds_stats, q=q, st=st)


@bp.get("/admin/user/<int:uid>")
@admin_required
def admin_user(uid):
    conn = c.get_db()
    try:
        u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u or is_admin(u):
            abort(404)
        pd = plan_data(conn, u)
        attempts = recent_attempts(conn, uid, 100)
        stats = stats_for(conn, uid)
        mistakes = collect_mistakes(conn, uid)
    finally:
        conn.close()
    by_topic = {}
    for m in mistakes:
        key = m["topic"] or "Mavzusiz savollar"
        by_topic[key] = by_topic.get(key, 0) + 1
    return render_template("admin/user.html", u=u, pd=pd, attempts=attempts, stats=stats,
                           mistakes_by_topic=sorted(by_topic.items(), key=lambda x: -x[1]),
                           n_mistakes=len(mistakes), states=STATES, levels=LEVELS)


# =====================================================================
#                              PROFIL
# =====================================================================
@bp.get("/admin/profile")
@admin_required
def admin_profile():
    return render_template("admin/profile.html", regions=c.REGIONS)


# =====================================================================
#                           TEST SOZLAMALARI
# =====================================================================
@bp.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    conn = c.get_db()
    try:
        if request.method == "POST":
            check_csrf()
            values, errors = {}, []
            for key, (default, typ, label, _grp) in c.SETTINGS.items():
                raw = str(request.form.get(key, "")).strip().replace(",", ".")
                try:
                    v = typ(float(raw)) if typ is int else typ(raw)
                    if not math.isfinite(v):
                        raise ValueError
                except (ValueError, OverflowError):
                    errors.append(f"«{label}» qiymati noto'g'ri.")
                    continue
                if v < 0 or v > (1000 if typ is int else 100):
                    errors.append(f"«{label}» qiymati chegaradan tashqarida.")
                    continue
                values[key] = round(v, 2) if typ is float else v
            for k in ("pass_percent", "high_percent"):
                if k in values and not 1 <= values[k] <= 100:
                    errors.append("Foiz 1 dan 100 gacha bo'lishi kerak.")
            if values.get("topic_count") == 0:
                errors.append("Mavzu testida kamida 1 ta savol bo'lishi kerak.")
            # Diagnostikaga qaysi mavzulardan nechta savol tushishi (belgilanmagan mavzu = 0)
            diag = [(_opt_int(request.form.get(f"diag_n_{r['id']}"), 0, 50) or 0
                     if request.form.get(f"diag_on_{r['id']}") else 0, r["id"])
                    for r in conn.execute("SELECT id FROM topics").fetchall()
                    if f"diag_n_{r['id']}" in request.form]
            if errors:
                for e in errors:
                    flash(e, "err")
            else:
                conn.executemany("UPDATE topics SET diag_count=? WHERE id=?", diag)
                c.save_settings(conn, values)
                flash("Test sozlamalari saqlandi.", "ok")
                return redirect(url_for("admin.admin_settings"))
        st = c.get_settings(conn)
        topics = []
        for t in conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM questions q WHERE q.topic_id=t.id) AS n_q "
            "FROM topics t ORDER BY t.position, t.id"
        ).fetchall():
            want = diag_count_of(t, st)
            topics.append({**dict(t), "want": want, "real": diag_quota(want, t["n_q"], st)})
    finally:
        conn.close()
    groups = {}
    for key, (default, typ, label, grp) in c.SETTINGS.items():
        groups.setdefault(grp, []).append({"key": key, "label": label, "value": st[key], "default": default,
                                           "float": typ is float})
    diag_total = sum(t["real"] for t in topics if t["published"])
    return render_template("admin/settings.html", groups=groups, topics=topics, diag_total=diag_total, st=st)


# =====================================================================
#                   Matndan ommaviy import (eski format)
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
