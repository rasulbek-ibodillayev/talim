"""Sayt va bot uchun umumiy modul: sozlamalar, baza, kod algoritmi."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

from dotenv import load_dotenv

load_dotenv()

# ---------------- Sozlamalar ----------------
DB_PATH = os.getenv("DB_PATH", "data/app.db")
FLASK_SECRET = os.getenv("FLASK_SECRET", "")
CODE_SECRET = os.getenv("CODE_SECRET", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot").lstrip("@")
REQUIRE_PHONE_MATCH = os.getenv("REQUIRE_PHONE_MATCH", "0") == "1"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
PASS_PERCENT = int(os.getenv("PASS_PERCENT", "60"))   # mavzu testidan o'tish foizi
AVATAR_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "avatars")

CODE_TTL = 10 * 60        # 1-kod amal qilish muddati (soniya)
SIGNUP_TTL = 15 * 60      # tasdiqlangandan keyin ma'lumot kiritish muddati
MAX_VERIFY_ATTEMPTS = 5

REGIONS = [
    "Toshkent shahri", "Toshkent viloyati", "Andijon viloyati",
    "Buxoro viloyati", "Farg'ona viloyati", "Jizzax viloyati",
    "Xorazm viloyati", "Namangan viloyati", "Navoiy viloyati",
    "Qashqadaryo viloyati", "Qoraqalpog'iston Respublikasi",
    "Samarqand viloyati", "Sirdaryo viloyati", "Surxondaryo viloyati",
]

# O'xshash belgilar (0/O, 1/I) olib tashlangan, 32 ta belgi
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def require_secrets():
    if len(CODE_SECRET) < 16 or len(FLASK_SECRET) < 16:
        raise RuntimeError(
            "CODE_SECRET va FLASK_SECRET .env faylda kamida 16 belgidan iborat bo'lishi kerak."
        )


# ---------------- Baza ----------------
def get_db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL UNIQUE,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            region TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pending (
            phone TEXT PRIMARY KEY,
            code_a TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            tg_id INTEGER,
            state TEXT NOT NULL DEFAULT 'issued',
            verified INTEGER NOT NULL DEFAULT 0,
            signup_token TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pending_code ON pending(code_a);
        CREATE TABLE IF NOT EXISTS rate (
            key TEXT NOT NULL,
            ts INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rate_key ON rate(key, ts);

        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0,
            published INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'topic',
            text TEXT NOT NULL,
            o1 TEXT NOT NULL, o2 TEXT NOT NULL, o3 TEXT NOT NULL, o4 TEXT NOT NULL,
            correct INTEGER NOT NULL,
            explanation TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_q_topic ON questions(topic_id, kind);
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            topic_id INTEGER,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            finished_at INTEGER,
            score INTEGER,
            total INTEGER,
            result TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_attempts_user ON attempts(user_id, kind);
        CREATE TABLE IF NOT EXISTS reads (
            user_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, material_id)
        );
        CREATE TABLE IF NOT EXISTS progress (
            user_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            diag_percent INTEGER,
            best_percent INTEGER,
            passed INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, topic_id)
        );
        """
    )
    # Eski bazalar uchun: users jadvaliga yangi ustunlar qo'shish
    have = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    for col, ddl in (
        ("avatar", "TEXT"),
        ("bio", "TEXT NOT NULL DEFAULT ''"),
        ("birth_year", "INTEGER"),
        ("education", "TEXT NOT NULL DEFAULT ''"),
    ):
        if col not in have:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
    conn.commit()
    conn.close()


# ---------------- Rate limit ----------------
def too_many(conn, key, limit, window):
    now = int(time.time())
    conn.execute("DELETE FROM rate WHERE ts < ?", (now - 86400,))
    n = conn.execute(
        "SELECT COUNT(*) FROM rate WHERE key = ? AND ts > ?", (key, now - window)
    ).fetchone()[0]
    return n >= limit


def hit(conn, key):
    conn.execute("INSERT INTO rate(key, ts) VALUES (?, ?)", (key, int(time.time())))
    conn.commit()


# ---------------- Yordamchi funksiyalar ----------------
def normalize_phone(raw):
    """'90 123 45 67', '+998901234567' -> '+998901234567'. Noto'g'ri bo'lsa None."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return None


ADMIN_PHONES = {
    p for p in (normalize_phone(x) for x in os.getenv("ADMIN_PHONES", "").split(",")) if p
}


def normalize_code(raw):
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


def format_code(code):
    return f"{code[:4]}-{code[4:]}"


def generate_code_a():
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


def make_code_b(code_a, phone):
    """MAXSUS USUL: 1-kod + telefon raqamidan HMAC-SHA256 orqali 2-kod hosil qilinadi.
    Maxfiy kalit (CODE_SECRET) bo'lmasa, 2-kodni hisoblab bo'lmaydi.
    Usulni o'zgartirmoqchi bo'lsangiz, faqat shu funksiyani o'zgartiring."""
    digest = hmac.new(
        CODE_SECRET.encode(), f"{code_a}:{phone}".encode(), hashlib.sha256
    ).digest()
    return "".join(ALPHABET[b % 32] for b in digest[:8])


# ---------------- Bot mantiqi (Telegramdan mustaqil, test qilish oson) ----------------
def claim_code(conn, tg_id, raw_code, tg_phone=None):
    """Foydalanuvchi botga 1-kodni yuborganda chaqiriladi.

    Qaytaradi: (status, qiymat)
      ("ok", code_b)        - 2-kod tayyor
      ("need_contact", None) - telefon raqamini tasdiqlash kerak (REQUIRE_PHONE_MATCH)
      ("bad", None)         - kod topilmadi yoki muddati o'tgan
      ("other", None)       - kod boshqa Telegram akkauntga bog'langan
      ("phone_mismatch", None) - Telegram raqami saytda kiritilgan raqamga mos emas
      ("limit", None)       - juda ko'p urinish
    """
    key = f"bot:{tg_id}"
    if too_many(conn, key, 10, 600):
        return "limit", None
    code = normalize_code(raw_code)
    if len(code) != 8 or any(ch not in ALPHABET for ch in code):
        hit(conn, key)
        return "bad", None
    row = conn.execute(
        "SELECT * FROM pending WHERE code_a = ? AND expires_at > ?",
        (code, int(time.time())),
    ).fetchone()
    if row is None:
        hit(conn, key)
        return "bad", None
    if row["tg_id"] is not None and row["tg_id"] != tg_id:
        hit(conn, key)
        return "other", None
    if REQUIRE_PHONE_MATCH:
        if tg_phone is None:
            return "need_contact", None
        if normalize_phone(tg_phone) != row["phone"]:
            return "phone_mismatch", None
    conn.execute("UPDATE pending SET tg_id = ? WHERE phone = ?", (tg_id, row["phone"]))
    conn.commit()
    return "ok", make_code_b(code, row["phone"])
