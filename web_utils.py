"""Flask uchun umumiy yordamchilar: javoblar, foydalanuvchi, CSRF, ruxsatlar."""
import hashlib
import hmac
import re
import secrets
from functools import wraps

from flask import abort, g, jsonify, redirect, request, session, url_for

import common as c


def ok(**data):
    return jsonify(ok=True, **data)


def fail(msg, status=400, **data):
    return jsonify(ok=False, error=msg, **data), status


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def to_int(v, default=None, lo=None, hi=None):
    """Matndan butun son. Yaroqsiz yoki bazaga sig'maydigan qiymat bo'lsa, default."""
    s = str(v if v is not None else "").strip()
    if not re.fullmatch(r"[+-]?[0-9]{1,15}", s):
        return default
    n = int(s)
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def password_mark(user):
    """Sessiya shu parolga bog'lanadi: parol almashsa, boshqa qurilmalardagi sessiyalar yopiladi."""
    return hashlib.sha256(user["password_hash"].encode()).hexdigest()[:24]


def log_in(user):
    session.clear()
    session.permanent = True
    session["uid"] = user["id"]
    session["pm"] = password_mark(user)


def client_ip():
    return request.remote_addr or "?"


def json_only(fn):
    """Faqat JSON so'rovlarni qabul qiladi (cross-site formalardan himoya)."""

    @wraps(fn)
    def wrapper(*a, **kw):
        if not request.is_json:
            return fail("Noto'g'ri so'rov.", 415)
        if (request.content_length or 0) > 64 * 1024:
            return fail("So'rov hajmi juda katta.", 413)
        return fn(*a, **kw)

    return wrapper


def current_user():
    if "_user" in g:
        return g._user
    user = None
    uid = session.get("uid")
    if uid:
        conn = c.get_db()
        try:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        finally:
            conn.close()
        if user and not hmac.compare_digest(str(session.get("pm", "")), password_mark(user)):
            user = None
    g._user = user
    return user


def is_admin(user=None):
    user = user or current_user()
    return bool(user) and user["phone"] in c.ADMIN_PHONES


def home_url(user):
    """Har bir rolning o'z bosh sahifasi."""
    return url_for("admin.admin_index" if is_admin(user) else "learn.dashboard")


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            session.clear()
            return redirect(url_for("index"))
        return fn(*a, **kw)

    return wrapper


def api_login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user():
            return fail("Iltimos, tizimga kiring.", 401, redirect="/")
        return fn(*a, **kw)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user = current_user()
        if not user:
            session.clear()
            return redirect(url_for("index"))
        if not is_admin(user):
            abort(403)
        return fn(*a, **kw)

    return wrapper


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(16)
    return session["csrf"]


def check_csrf():
    """Forma yoki fayl yuklash so'rovlarida CSRF tokenni tekshiradi."""
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
    if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
        abort(400)
