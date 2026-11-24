"""Admin hisobini ochish yoki parolini almashtirish (faqat serverda ishga tushiriladi).

    python create_admin.py                              lokal
    docker compose exec web python create_admin.py      Docker

Raqam .env dagi ADMIN_PHONES ro'yxatida bo'lishi kerak. Saytdagi ro'yxatdan o'tish va mahfiy so'z bilan
tiklash admin raqamlari uchun yopiq: raqam tasdiqlanmagani uchun begona odam admin bo'lib qolmasin.
"""
import getpass
import sys
import time

from werkzeug.security import generate_password_hash

import bootstrap
import common as c


def save_admin(phone, password, first="Admin", last="Admin"):
    """Yangi hisob bo'lsa True, mavjud hisobning paroli almashgan bo'lsa False."""
    if phone not in c.ADMIN_PHONES:
        raise ValueError("Bu raqam .env dagi ADMIN_PHONES ro'yxatida yo'q.")
    err = c.password_error(password, password)
    if err:
        raise ValueError(err)
    bootstrap.run()
    conn = c.get_db()
    try:
        hashed = generate_password_hash(password)
        cur = conn.execute("UPDATE users SET password_hash=? WHERE phone=?", (hashed, phone))
        created = cur.rowcount == 0
        if created:
            conn.execute(
                "INSERT INTO users(phone, first_name, last_name, region, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)", (phone, first, last, c.REGIONS[0], hashed, int(time.time())),
            )
        conn.commit()
    finally:
        conn.close()
    return created


def main():
    phone = c.normalize_phone(input("Admin telefon raqami: "))
    if not phone or phone not in c.ADMIN_PHONES:
        sys.exit("Bu raqam .env dagi ADMIN_PHONES ro'yxatida yo'q.")
    first = input("Ism (yangi hisob uchun) [Admin]: ").strip() or "Admin"
    last = input("Familiya (yangi hisob uchun) [Admin]: ").strip() or "Admin"
    password = getpass.getpass("Parol (kamida 8 belgi): ")
    if password != getpass.getpass("Parolni tasdiqlang: "):
        sys.exit("Parollar bir xil emas.")
    try:
        created = save_admin(phone, password, first, last)
    except ValueError as e:
        sys.exit(str(e))
    print("Admin hisobi ochildi." if created else "Admin paroli almashtirildi.")


if __name__ == "__main__":
    main()
