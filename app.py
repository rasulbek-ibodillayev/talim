"""Sayt backend (Flask). Ishga tushirish: gunicorn app:app"""
import hashlib
import hmac
import sqlite3
import time

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import common as c
import bootstrap
from web_utils import body, client_ip, current_user, csrf_token, fail, home_url, is_admin, json_only, log_in, ok

c.require_secrets()
bootstrap.run()     # baza, namunaviy ma'lumot va admin hisobi (bir nechta jarayon bo'lsa ham bir marta)

app = Flask(__name__)
app.secret_key = c.FLASK_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=c.COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
    MAX_CONTENT_LENGTH=21 * 1024 * 1024,  # mavzu fayllari 20 MB gacha (rasm 2 MB, Excel 5 MB — kodda tekshiriladi)
)
if c.TRUST_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    if request.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.context_processor
def inject_globals():
    user = current_user()
    return {"user": user, "is_admin": is_admin(user), "csrf_token": csrf_token}


@app.errorhandler(413)
def too_large(_e):
    if request.path.startswith("/api"):
        return fail("Fayl hajmi juda katta.", 413)
    return render_template("error.html", code=413, message="Fayl hajmi juda katta."), 413


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="Bu sahifaga kirish huquqingiz yo'q."), 403


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api"):
        return fail("Topilmadi.", 404)
    return render_template("error.html", code=404, message="Sahifa topilmadi."), 404


@app.errorhandler(405)
def bad_method(_e):
    if request.path.startswith("/api"):
        return fail("Noto'g'ri so'rov.", 405)
    return render_template("error.html", code=405, message="Bu amalni bunday bajarib bo'lmaydi."), 405


@app.errorhandler(OverflowError)
def too_big_number(_e):
    """Manzildagi yoki formadagi son bazaga sig'maydi: bunday yozuv yo'q."""
    return not_found(_e)


@app.errorhandler(UnicodeError)
def bad_text(_e):
    return bad_request(_e)


@app.errorhandler(500)
def server_error(_e):
    if request.path.startswith("/api"):
        return fail("Serverda xatolik yuz berdi. Birozdan keyin qayta urinib ko'ring.", 500)
    return render_template("error.html", code=500, message="Serverda xatolik yuz berdi."), 500


@app.errorhandler(400)
def bad_request(_e):
    if request.path.startswith("/api"):
        return fail("Noto'g'ri so'rov.", 400)
    return render_template("error.html", code=400, message="Noto'g'ri so'rov. Sahifani yangilab qayta urinib ko'ring."), 400


# ---------------- Sahifalar ----------------
@app.get("/")
def index():
    if current_user():
        return redirect(home_url(current_user()))
    return render_template("index.html", regions=c.REGIONS, secret_min=c.SECRET_MIN)


@app.get("/healthz")
def healthz():
    conn = c.get_db()
    try:
        conn.execute("SELECT 1 FROM users LIMIT 1")
    finally:
        conn.close()
    return "ok"


@app.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.svg"), 301)


# ---------------- Ro'yxatdan o'tish ----------------
@app.post("/api/register")
@json_only
def register():
    data = body()
    phone = c.normalize_phone(str(data.get("phone", "")))
    first = " ".join(str(data.get("first_name", "")).split())
    last = " ".join(str(data.get("last_name", "")).split())
    region = str(data.get("region", ""))
    pw1 = str(data.get("password", ""))
    pw2 = str(data.get("password2", ""))
    secret = data.get("secret", "")

    if not phone:
        return fail("Telefon raqamni to'g'ri kiriting (masalan: 90 123 45 67).")
    if not (2 <= len(first) <= 50) or not (2 <= len(last) <= 50):
        return fail("Ism va familiya 2 dan 50 tagacha belgi bo'lishi kerak.")
    if region not in c.REGIONS:
        return fail("Hududni ro'yxatdan tanlang.")
    err = c.password_error(pw1, pw2) or c.secret_error(secret, pw1)
    if err:
        return fail(err)

    taken = "Bu telefon raqam allaqachon ro'yxatdan o'tgan. Kirish bo'limidan foydalaning."
    conn = c.get_db()
    try:
        key = f"reg:ip:{client_ip()}"
        if c.too_many(conn, key, 60, 3600):     # bitta sinf bitta internetdan ro'yxatdan o'tishi mumkin
            return fail("Juda ko'p urinish. Iltimos, birozdan keyin qayta urinib ko'ring.", 429)
        c.hit(conn, key)
        # Raqam tasdiqlanmaydi, shuning uchun admin raqamini bu yerdan egallab bo'lmaydi (create_admin.py)
        if phone in c.ADMIN_PHONES or conn.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
            return fail(taken, 409)
        try:
            cur = conn.execute(
                "INSERT INTO users (phone, first_name, last_name, region, password_hash, secret_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (phone, first, last, region, generate_password_hash(pw1),
                 generate_password_hash(c.normalize_secret(secret)), int(time.time())),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return fail(taken, 409)
        user = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()

    log_in(user)
    return ok(redirect=url_for("index"))


# ---------------- Parolni tiklash: telefon + mahfiy so'z -> yangi parol ----------------
def reset_mark(user):
    """Ruxsat faqat shu parol uchun amal qiladi: parol o'zgargach, qayta ishlatib bo'lmaydi."""
    return hashlib.sha256(f"{user['password_hash']}:{user['secret_hash']}".encode()).hexdigest()[:32]


@app.post("/api/recover/check")
@json_only
def recover_check():
    data = body()
    phone = c.normalize_phone(str(data.get("phone", "")))
    secret = c.normalize_secret(data.get("secret", ""))
    if not phone or not secret:
        return fail("Telefon raqam va mahfiy so'zni kiriting.")
    conn = c.get_db()
    try:
        ip_key, ph_key = f"rec:ip:{client_ip()}", f"rec:ph:{phone}"
        if (c.too_many(conn, ph_key, 5, 3600) or c.too_many(conn, ph_key, 15, 86400)
                or c.too_many(conn, ip_key, 30, 3600)):
            return fail("Juda ko'p urinish. Iltimos, keyinroq qayta urinib ko'ring.", 429)
        # Tekshirishdan oldin sanaladi: parallel so'rovlar chegarani aylanib o'tmasin
        c.hit(conn, ip_key)
        c.hit(conn, ph_key)
        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        usable = user is not None and bool(user["secret_hash"]) and not is_admin(user)
        valid = check_password_hash(user["secret_hash"] if usable else _DUMMY_HASH, secret[:200]) and usable
        if not valid:
            return fail("Telefon raqam yoki mahfiy so'z noto'g'ri.", 401)
        conn.execute("DELETE FROM rate WHERE key=?", (ph_key,))
        conn.commit()
    finally:
        conn.close()
    session.clear()
    session["reset"] = {"uid": user["id"], "until": int(time.time()) + c.RESET_TTL, "mark": reset_mark(user)}
    return ok(minutes=c.RESET_TTL // 60)


@app.post("/api/recover/reset")
@json_only
def recover_reset():
    grant = session.get("reset")
    if not grant or grant["until"] < int(time.time()):
        session.pop("reset", None)
        return fail("Vaqt tugadi. Telefon raqam va mahfiy so'zni qaytadan kiriting.", 401, restart=True)
    data = body()
    pw1, pw2 = str(data.get("password", "")), str(data.get("password2", ""))
    err = c.password_error(pw1, pw2)
    if err:
        return fail(err)
    conn = c.get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (grant["uid"],)).fetchone()
        if user is None or is_admin(user) or not hmac.compare_digest(reset_mark(user), grant["mark"]):
            session.pop("reset", None)
            return fail("Ruxsat eskirgan. Telefon raqam va mahfiy so'zni qaytadan kiriting.", 401, restart=True)
        if user["secret_hash"] and check_password_hash(user["secret_hash"], c.normalize_secret(pw1)):
            return fail("Parol mahfiy so'z bilan bir xil bo'lmasligi kerak.")
        conn.execute("UPDATE users SET password_hash=? WHERE id=? AND password_hash=?",
                     (generate_password_hash(pw1), user["id"], user["password_hash"]))
        conn.execute("DELETE FROM rate WHERE key=?", (f"login:ph:{user['phone']}",))
        conn.commit()
    finally:
        conn.close()
    session.clear()
    return ok(message="Parol yangilandi. Endi yangi parol bilan kiring.")


# ---------------- Kirish / chiqish ----------------
@app.post("/api/login")
@json_only
def login():
    data = body()
    phone = c.normalize_phone(data.get("phone"))
    password = str(data.get("password", ""))
    if not phone or not password:
        return fail("Telefon raqam va parolni kiriting.")

    conn = c.get_db()
    try:
        if c.too_many(conn, f"login:ip:{client_ip()}", 20, 900) or c.too_many(
            conn, f"login:ph:{phone}", 8, 900
        ):
            return fail("Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring.", 429)

        user = conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()
        # Foydalanuvchi bo'lmasa ham hash tekshiriladi (vaqt bo'yicha farqni yashirish uchun)
        hashed = user["password_hash"] if user else _DUMMY_HASH
        valid = check_password_hash(hashed, password) and user is not None
        if not valid:
            c.hit(conn, f"login:ip:{client_ip()}")
            c.hit(conn, f"login:ph:{phone}")
            return fail("Telefon raqam yoki parol noto'g'ri.", 401)
    finally:
        conn.close()

    log_in(user)
    return ok(redirect=url_for("index"))


_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


@app.post("/api/logout")
@json_only
def logout():
    session.clear()
    return ok(redirect=url_for("index"))



import admin  # noqa: E402  (admin paneli)
import learn  # noqa: E402  (o'quvchi paneli)

app.register_blueprint(learn.bp)
app.register_blueprint(admin.bp)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
