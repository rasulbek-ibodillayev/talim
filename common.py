"""Umumiy modul: sozlamalar, baza, yordamchilar."""
import os
import re
import sqlite3
import time
import unicodedata

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---------------- Sozlamalar ----------------
# Nisbiy yo'l loyiha papkasidan hisoblanadi (qayerdan ishga tushirilgani muhim emas)
DB_PATH = os.path.join(BASE_DIR, os.getenv("DB_PATH") or "data/app.db")
FLASK_SECRET = os.getenv("FLASK_SECRET", "")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"
PASS_PERCENT = int(os.getenv("PASS_PERCENT", "60"))   # mavzu testidan o'tish foizi
AVATAR_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "avatars")
FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "files")   # mavzu fayllari (word, pdf)

# ---------------- Admin sozlamalari (Test sozlamalari bo'limida o'zgartiriladi) ----------------
# kalit: (standart qiymat, turi, nomi, guruh)
SETTINGS = {
    "topic_count": (5, int, "Mavzu testida beriladigan savollar soni", "Mavzu testi"),
    "pass_percent": (PASS_PERCENT, int, "O'tish foizi (kamida shuncha to'plasa, keyingi mavzu ochiladi)", "Mavzu testi"),
    "topic_time": (20, int, "Vaqt, daqiqa (yangi mavzular uchun standart)", "Mavzu testi"),
    "topic_points": (1.0, float, "1 savol balli (yangi mavzular uchun standart)", "Mavzu testi"),
    "high_percent": (80, int, "Bilish foizi (kamida shuncha to'plasa, mavzu dars rejaga kirmaydi)", "Diagnostika"),
    "diag_time": (0, int, "Diagnostika vaqti, daqiqa (0 = cheklanmagan)", "Diagnostika"),
    "diag_per_topic": (3, int, "Yangi mavzulardan beriladigan savollar soni (standart)", "Diagnostika"),
    "dtm_mandatory_count": (10, int, "DTM: majburiy blok savollari soni", "DTM"),
    "dtm_special_count": (30, int, "DTM: mutaxassislik (spes) blok savollari soni", "DTM"),
    "dtm_time": (80, int, "DTM: vaqt, daqiqa (yangi testlar uchun standart)", "DTM"),
    "dtm_points_mandatory": (1.1, float, "DTM: majburiy blok 1 savol balli (standart)", "DTM"),
    "dtm_points_special": (3.1, float, "DTM: mutaxassislik blok 1 savol balli (standart)", "DTM"),
    "olympiad_count": (30, int, "Olimpiada: savollar soni", "Olimpiada"),
    "olympiad_time": (90, int, "Olimpiada: vaqt, daqiqa (standart)", "Olimpiada"),
    "olympiad_points": (1.0, float, "Olimpiada: 1 savol balli (standart)", "Olimpiada"),
    "certificate_count": (35, int, "Milliy sertifikat: savollar soni", "Milliy sertifikat"),
    "certificate_time": (120, int, "Milliy sertifikat: vaqt, daqiqa (standart)", "Milliy sertifikat"),
    "certificate_points": (1.0, float, "Milliy sertifikat: 1 savol balli (standart)", "Milliy sertifikat"),
}


def get_settings(conn):
    vals = {k: v[0] for k, v in SETTINGS.items()}
    for r in conn.execute("SELECT key, value FROM meta WHERE key LIKE 'set:%'"):
        k = r["key"][4:]
        if k in SETTINGS:
            try:
                vals[k] = SETTINGS[k][1](r["value"])
            except (TypeError, ValueError):
                pass
    return vals


def save_settings(conn, values):
    for k, v in values.items():
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (f"set:{k}", str(v)))
    conn.commit()


RESET_TTL = 10 * 60       # mahfiy so'z to'g'ri topilgach yangi parol qo'yish muddati (soniya)
SECRET_MIN, SECRET_MAX = 4, 64

# Imtihon turlari: kalit -> (nomi, qisqa tavsif)
EXAM_KINDS = {
    "olympiad": ("Olimpiada", "Fan olimpiadalari uchun murakkab savollar"),
    "certificate": ("Milliy sertifikat", "Milliy sertifikat imtihoni formatidagi testlar"),
    "dtm": ("DTM testlari", "Majburiy va mutaxassislik (spes) bloklaridan iborat kirish testlari"),
}
# DTM bloklari: exam_questions.section qiymati -> nomi
DTM_SECTIONS = {"a": "Majburiy blok", "b": "Mutaxassislik (spes) blok"}

REGIONS = [
    "Toshkent shahri", "Toshkent viloyati", "Andijon viloyati",
    "Buxoro viloyati", "Farg'ona viloyati", "Jizzax viloyati",
    "Xorazm viloyati", "Namangan viloyati", "Navoiy viloyati",
    "Qashqadaryo viloyati", "Qoraqalpog'iston Respublikasi",
    "Samarqand viloyati", "Sirdaryo viloyati", "Surxondaryo viloyati",
]


def require_secrets():
    if len(FLASK_SECRET) < 16:
        raise RuntimeError("FLASK_SECRET .env faylda kamida 16 belgidan iborat bo'lishi kerak.")


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
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,                 -- dtm | olympiad | certificate
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            time_limit INTEGER NOT NULL DEFAULT 0,   -- daqiqa, 0 = cheklanmagan
            shuffle INTEGER NOT NULL DEFAULT 0,      -- savollar tartibini aralashtirish
            position INTEGER NOT NULL DEFAULT 0,
            published INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS exam_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
            topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
            text TEXT NOT NULL,
            o1 TEXT NOT NULL, o2 TEXT NOT NULL, o3 TEXT NOT NULL, o4 TEXT NOT NULL,
            correct INTEGER NOT NULL,
            explanation TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_eq_exam ON exam_questions(exam_id, position);
        """
    )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS topic_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            stored TEXT NOT NULL,
            size INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    # Eski bazalar uchun yangi ustunlar
    for table, cols in (
        ("attempts", (("exam_id", "INTEGER"), ("deadline", "INTEGER"), ("draft", "TEXT"),
                      ("paused", "INTEGER NOT NULL DEFAULT 0"), ("time_left", "INTEGER"),
                      ("points", "REAL"), ("max_points", "REAL"))),
        ("users", (("diag_declined", "INTEGER NOT NULL DEFAULT 0"), ("last_seen", "INTEGER"),
                   ("secret_hash", "TEXT"))),
        ("topics", (("diag_count", "INTEGER"), ("test_time", "INTEGER"), ("test_points", "REAL"))),
        ("exams", (("points_a", "REAL NOT NULL DEFAULT 1"), ("points_b", "REAL NOT NULL DEFAULT 0"))),
        ("exam_questions", (("section", "TEXT NOT NULL DEFAULT 'a'"),)),
        ("materials", (("image", "TEXT"),)),
        ("progress", (("first_failed", "INTEGER NOT NULL DEFAULT 0"),)),
    ):
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in cols:
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                if table == "exams" and col == "points_b":
                    # Avval ball tushunchasi yo'q edi: mavjud DTM testlariga standart ballar beriladi
                    conn.execute("UPDATE exams SET points_a=1.1, points_b=3.1 WHERE kind='dtm'")
                if col == "first_failed":
                    # Avvalgi urinishlardan: mavzu testining birinchi urinishida o'tolmaganlar
                    conn.execute(
                        "UPDATE progress SET first_failed=1 WHERE attempts > 0 AND ? > ("
                        "SELECT ROUND(100.0*a.score/a.total) FROM attempts a WHERE a.user_id=progress.user_id "
                        "AND a.topic_id=progress.topic_id AND a.kind='topic' AND a.finished_at IS NOT NULL "
                        "AND a.total > 0 ORDER BY a.id LIMIT 1)", (get_settings(conn)["pass_percent"],),
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
    digits = re.sub(r"[^0-9]", "", str(raw or ""))
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return None


ADMIN_PHONES = {
    p for p in (normalize_phone(x) for x in os.getenv("ADMIN_PHONES", "").split(",")) if p
}


def normalize_secret(raw):
    """Mahfiy so'z: katta-kichik harf, ortiqcha bo'shliq va apostrof turi farq qilmaydi."""
    t = unicodedata.normalize("NFKC", str(raw or ""))
    t = re.sub("[\u2018\u2019\u02bb\u02bc`\u00b4]", "'", t)
    return " ".join(t.split()).casefold()


def secret_error(raw, password=""):
    """Mahfiy so'z yaroqsiz bo'lsa, xato matni."""
    s = normalize_secret(raw)
    if not SECRET_MIN <= len(s) <= SECRET_MAX:
        return f"Mahfiy so'z {SECRET_MIN} tadan {SECRET_MAX} tagacha belgi bo'lishi kerak."
    if password and s == normalize_secret(password):
        return "Mahfiy so'z parol bilan bir xil bo'lmasligi kerak."
    return None


def password_error(pw1, pw2):
    if len(pw1) < 8 or len(pw1) > 128:
        return "Parol kamida 8 ta belgidan iborat bo'lishi kerak."
    if pw1 != pw2:
        return "Parollar bir xil emas."
    return None
