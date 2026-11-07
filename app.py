"""Sayt backend (Flask). Ishga tushirish: gunicorn app:app"""
import hmac
import secrets
import time

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import common as c
from web_utils import body, client_ip, current_user, csrf_token, fail, is_admin, json_only, ok

c.require_secrets()
c.init_db()

import os
db_url = os.environ.get("DATABASE_URL", "sqlite:///data/app.db")

app = Flask(__name__)
app.secret_key = c.FLASK_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=c.COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
    MAX_CONTENT_LENGTH=3 * 1024 * 1024,   # rasm yuklash uchun (rasm limiti 2 MB)
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
        return fail("Fayl hajmi 2 MB dan oshmasligi kerak.", 413)
    return render_template("error.html", code=413, message="Fayl hajmi juda katta."), 413


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="Bu sahifaga kirish huquqingiz yo'q."), 403


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api"):
        return fail("Topilmadi.", 404)
    return render_template("error.html", code=404, message="Sahifa topilmadi."), 404


@app.errorhandler(400)
def bad_request(_e):
    if request.path.startswith("/api"):
        return fail("Noto'g'ri so'rov.", 400)
    return render_template("error.html", code=400, message="Noto'g'ri so'rov. Sahifani yangilab qayta urinib ko'ring."), 400


# ---------------- Sahifalar ----------------
@app.get("/")
def index():
    if current_user():
        return redirect(url_for("learn.dashboard"))
    return render_template("index.html", regions=c.REGIONS, bot_username=c.BOT_USERNAME)


@app.get("/healthz")
def healthz():
    return "ok"


# ---------------- Ro'yxatdan o'tish: 1-qadam (telefon -> 1-kod) ----------------
@app.post("/api/register/start")
@json_only
def register_start():
    phone = c.normalize_phone(body().get("phone"))
    if not phone:
        return fail("Telefon raqamni to'g'ri kiriting (masalan: 90 123 45 67).")

    conn = c.get_db()
    try:
        if conn.execute("SELECT 1 FROM users WHERE phone = ?", (phone,)).fetchone():
            return fail("Bu telefon raqam allaqachon ro'yxatdan o'tgan. Kirish bo'limidan foydalaning.")

        if c.too_many(conn, f"start:ip:{client_ip()}", 10, 3600) or c.too_many(
            conn, f"start:ph:{phone}", 5, 3600
        ):
            return fail("Juda ko'p urinish. Iltimos, birozdan keyin qayta urinib ko'ring.", 429)
        c.hit(conn, f"start:ip:{client_ip()}")
        c.hit(conn, f"start:ph:{phone}")

        while True:
            code_a = c.generate_code_a()
            if not conn.execute("SELECT 1 FROM pending WHERE code_a = ?", (code_a,)).fetchone():
                break
        now = int(time.time())
        conn.execute(
            """INSERT OR REPLACE INTO pending
               (phone, code_a, expires_at, attempts, tg_id, state, verified, signup_token, created_at)
               VALUES (?, ?, ?, 0, NULL, 'issued', 0, NULL, ?)""",
            (phone, code_a, now + c.CODE_TTL, now),
        )
        conn.commit()
    finally:
        conn.close()

    session.clear()
    session["signup_phone"] = phone
    return ok(
        code=c.format_code(code_a),
        raw_code=code_a,
        bot_username=c.BOT_USERNAME,
        bot_url=f"https://t.me/{c.BOT_USERNAME}?start={code_a}",
        expires_in=c.CODE_TTL,
        phone=phone,
    )


# ---------------- 2-qadam (bot bergan 2-kodni tekshirish) ----------------
@app.post("/api/register/verify")
@json_only
def register_verify():
    phone = session.get("signup_phone")
    if not phone:
        return fail("Seans tugagan. Iltimos, qaytadan boshlang.", 401, restart=True)
    submitted = c.normalize_code(body().get("code"))
    if len(submitted) != 8:
        return fail("Kod 8 ta belgidan iborat bo'lishi kerak.")

    conn = c.get_db()
    try:
        row = conn.execute("SELECT * FROM pending WHERE phone = ?", (phone,)).fetchone()
        if row is None or row["expires_at"] < int(time.time()):
            return fail("Kod muddati tugagan. Iltimos, qaytadan boshlang.", 410, restart=True)
        if row["attempts"] >= c.MAX_VERIFY_ATTEMPTS:
            conn.execute("DELETE FROM pending WHERE phone = ?", (phone,))
            conn.commit()
            return fail("Urinishlar soni tugadi. Iltimos, qaytadan boshlang.", 429, restart=True)
        if row["tg_id"] is None:
            return fail("Avval botga kirib, 1-kodni yuboring va 2-kodni oling.")

        expected = c.make_code_b(row["code_a"], phone)
        if not hmac.compare_digest(expected, submitted):
            conn.execute("UPDATE pending SET attempts = attempts + 1 WHERE phone = ?", (phone,))
            conn.commit()
            left = c.MAX_VERIFY_ATTEMPTS - row["attempts"] - 1
            return fail(f"Kod noto'g'ri. Qolgan urinishlar: {max(left, 0)}")

        token = secrets.token_urlsafe(24)
        conn.execute(
            "UPDATE pending SET verified = 1, signup_token = ?, expires_at = ? WHERE phone = ?",
            (token, int(time.time()) + c.SIGNUP_TTL, phone),
        )
        conn.commit()
    finally:
        conn.close()

    session["signup_token"] = token
    return ok()


# ---------------- 3-qadam (ma'lumotlar va parol) ----------------
@app.post("/api/register/complete")
@json_only
def register_complete():
    phone = session.get("signup_phone")
    token = session.get("signup_token")
    if not phone or not token:
        return fail("Seans tugagan. Iltimos, qaytadan boshlang.", 401, restart=True)

    data = body()
    first = " ".join(str(data.get("first_name", "")).split())
    last = " ".join(str(data.get("last_name", "")).split())
    region = str(data.get("region", ""))
    pw1 = str(data.get("password", ""))
    pw2 = str(data.get("password2", ""))

    if not (2 <= len(first) <= 50) or not (2 <= len(last) <= 50):
        return fail("Ism va familiya 2 dan 50 tagacha belgi bo'lishi kerak.")
    if region not in c.REGIONS:
        return fail("Hududni ro'yxatdan tanlang.")
    if len(pw1) < 8 or len(pw1) > 128:
        return fail("Parol kamida 8 ta belgidan iborat bo'lishi kerak.")
    if pw1 != pw2:
        return fail("Parollar bir xil emas.")

    conn = c.get_db()
    try:
        row = conn.execute("SELECT * FROM pending WHERE phone = ?", (phone,)).fetchone()
        if (
            row is None
            or not row["verified"]
            or not row["signup_token"]
            or not hmac.compare_digest(row["signup_token"], token)
            or row["expires_at"] < int(time.time())
        ):
            return fail("Tasdiqlash muddati tugagan. Iltimos, qaytadan boshlang.", 410, restart=True)

        try:
            cur = conn.execute(
                """INSERT INTO users (phone, first_name, last_name, region, password_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (phone, first, last, region, generate_password_hash(pw1), int(time.time())),
            )
        except Exception:
            conn.rollback()
            return fail("Bu telefon raqam allaqachon ro'yxatdan o'tgan.", 409, restart=True)
        conn.execute("DELETE FROM pending WHERE phone = ?", (phone,))
        conn.commit()
        uid = cur.lastrowid
    finally:
        conn.close()

    session.clear()
    session.permanent = True
    session["uid"] = uid
    return ok(redirect=url_for("learn.dashboard"))


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
        uid = user["id"]
    finally:
        conn.close()

    session.clear()
    session.permanent = True
    session["uid"] = uid
    return ok(redirect=url_for("learn.dashboard"))


_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


@app.post("/api/logout")
@json_only
def logout():
    session.clear()
    return ok(redirect=url_for("index"))



import learn  # noqa: E402  (o'quv qismi: profil, testlar, mavzular, admin)

app.register_blueprint(learn.bp)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
