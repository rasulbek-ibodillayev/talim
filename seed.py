"""Dastlabki ma'lumotlarni bazaga yozish. Faqat baza bo'sh bo'lganda, bir marta bajariladi.

Mavjud bazadagi mavzu va testlarni shu namunalar bilan almashtirish (serverni to'xtatib):

    python seed.py --replace

Bunda mavzular, testlar, o'quvchilarning natija va dars jarayoni o'chadi; foydalanuvchilar saqlanadi.
Eski bazaning nusxasi yoniga «.bak» qo'shimchasi bilan yoziladi.
"""
import random
import sys
import time

from seed_exams import EXAMS
from seed_topics import TOPICS


def parse_rows(text, n):
    """Har bir qator n ta «|» bilan ajratilgan qism bo'lishi shart."""
    out = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != n or not all(parts):
            raise ValueError(f"Savol qatori noto'g'ri: {line}")
        out.append(parts)
    return out


def shuffled(right, wrong):
    opts = [right, *wrong]
    random.shuffle(opts)
    return (*opts, opts.index(right) + 1)


def write_topics(conn):
    ids = []
    for pos, t in enumerate(TOPICS, 1):
        tid = conn.execute(
            "INSERT INTO topics(title, summary, position, published) VALUES (?, ?, ?, 1)",
            (t["title"], t["summary"], pos),
        ).lastrowid
        ids.append(tid)
        conn.executemany(
            "INSERT INTO materials(topic_id, title, body, url, position) VALUES (?, ?, ?, '', ?)",
            [(tid, title, text, n) for n, (title, text) in enumerate(t["materials"], 1)],
        )
        conn.executemany(
            "INSERT INTO questions(topic_id, text, o1, o2, o3, o4, correct) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(tid, text, *shuffled(right, wrong)) for text, right, *wrong in parse_rows(t["questions"], 5)],
        )
    return ids


def write_exams(conn):
    now = int(time.time())
    by_title = {r["title"]: r["id"] for r in conn.execute("SELECT id, title FROM topics")}
    for pos, e in enumerate(EXAMS, 1):
        eid = conn.execute(
            "INSERT INTO exams(kind, title, description, time_limit, shuffle, position, published, created_at, "
            "points_a, points_b) VALUES (?, ?, ?, ?, 0, ?, 1, ?, ?, ?)",
            (e["kind"], e["title"], e["description"], e["time_limit"], pos, now, e["points_a"], e["points_b"]),
        ).lastrowid
        n = 0
        for section in ("a", "b"):
            for num, text, right, *wrong in parse_rows(e.get(section, ""), 6):
                n += 1
                # Mavzu nomi bo'yicha topiladi: admin mavzuni o'chirgan bo'lsa, savol mavzusiz yoziladi
                topic_id = by_title.get(TOPICS[int(num) - 1]["title"]) if num != "0" else None
                conn.execute(
                    "INSERT INTO exam_questions(exam_id, topic_id, section, text, o1, o2, o3, o4, correct, position) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (eid, topic_id, section, text, *shuffled(right, wrong), n),
                )


def mark(conn, key):
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, str(int(time.time()))))


def seed_if_empty(conn):
    """Mavzular faqat bir marta yoziladi (admin o'chirsa qaytib kelmaydi)."""
    if (conn.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone()
            or conn.execute("SELECT 1 FROM topics LIMIT 1").fetchone()):
        return False
    write_topics(conn)
    mark(conn, "seeded")
    conn.commit()
    return True


def seed_exams_if_empty(conn):
    if (conn.execute("SELECT 1 FROM meta WHERE key='exams_seeded'").fetchone()
            or conn.execute("SELECT 1 FROM exams LIMIT 1").fetchone()):
        return False
    write_exams(conn)
    mark(conn, "exams_seeded")
    conn.commit()
    return True


def replace_all(conn):
    """Mavzu va testlarni namunalar bilan almashtiradi. Hammasi bitta tranzaksiyada. Eski fayl nomlarini qaytaradi."""
    files = [r[0] for r in conn.execute(
        "SELECT stored FROM topic_files UNION ALL SELECT image FROM materials WHERE image IS NOT NULL")]
    conn.execute("BEGIN IMMEDIATE")
    for table in ("attempts", "reads", "progress", "exam_questions", "exams", "topic_files", "materials", "questions",
                  "topics"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("UPDATE users SET diag_declined=0")
    write_topics(conn)
    write_exams(conn)
    mark(conn, "seeded")
    mark(conn, "exams_seeded")
    conn.commit()
    return files


def main():
    if sys.argv[1:] != ["--replace"]:
        sys.exit(__doc__)
    import sqlite3

    import bootstrap
    import common as c

    bootstrap.run()
    conn = c.get_db()
    backup = f"{c.DB_PATH}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    target = sqlite3.connect(backup)
    conn.backup(target)
    target.close()
    replace_all(conn)
    conn.close()
    print(f"Tayyor: {len(TOPICS)} ta mavzu, {len(EXAMS)} ta test. Eski baza: {backup}")


if __name__ == "__main__":
    main()
