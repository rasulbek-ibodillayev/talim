# Tarix Ustoz

Tarix fanidan tayyorgarlik sayti: Flask + SQLite. Baza `data/app.db` faylida.

## Ro'yxatdan o'tish va kirish

1. **Ro'yxatdan o'tish**: telefon raqam, ism, familiya, hudud, parol (2 marta) va mahfiy so'z.
2. **Kirish**: telefon raqam + parol.
3. **Parolni unutganda**: telefon raqam + mahfiy so'z. To'g'ri bo'lsa, 10 daqiqa ichida yangi parol qo'yiladi.
   Mahfiy so'zda katta-kichik harf farq qilmaydi. Uni profilda almashtirish mumkin.

Telefon raqam tasdiqlanmaydi, shuning uchun `ADMIN_PHONES` dagi raqamlar bilan saytdan ro'yxatdan o'tib va
parolni mahfiy so'z bilan tiklab bo'lmaydi. Admin hisobi serverda ochiladi (parol ham shu buyruq bilan almashtiriladi):

```bash
python create_admin.py
```

## Sozlash

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # FLASK_SECRET uchun
```

`.env` ichiga `FLASK_SECRET`, `ADMIN_PHONES` va (ixtiyoriy) `ADMIN_PASSWORD` ni yozing. `ADMIN_PASSWORD` berilsa, hisobi yo'q adminlar uchun hisob ishga tushganda ochiladi.

## Ishga tushirish

### A) Docker

```bash
docker compose up -d --build
docker compose exec web python create_admin.py
```

### B) Docker'siz

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python create_admin.py
gunicorn -w 2 -b 127.0.0.1:8000 app:app
```

## Serverni yangilash

```bash
bash ~/talim/yangilash.sh
```

Skript bazadan nusxa oladi (`~/zaxira/`), GitHub'dagi `main` ni o'rnatadi va `talim` xizmatini qayta yoqadi. Yangi
versiya ishga tushmasa, eski kod qaytariladi. Baza va `.env` ga tegmaydi.

## Productionga chiqarish (HTTPS)

Domen ulang va nginx/Caddy orqali HTTPS qiling. So'ng `.env`da:

```
COOKIE_SECURE=1
TRUST_PROXY=1
```

Nginx namunasi:

```nginx
server {
    server_name example.uz;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Xavfsizlik

- Parollar va mahfiy so'zlar `werkzeug` orqali xeshlanadi (scrypt/pbkdf2).
- Kirish, ro'yxatdan o'tish va parolni tiklash uchun tezlik chegarasi bor (tiklash: bir raqamga soatiga 5 ta urinish).
- Barcha POST so'rovlar faqat JSON qabul qiladi, cookie `HttpOnly` + `SameSite=Lax`.
- SQLite kichik/o'rta yuklama uchun yetarli. Katta yuklamada PostgreSQL'ga o'ting.
- `.env` va `data/` papkasini hech qachon ommaga chiqarmang.

---

# Fayllar

| Fayl | Vazifasi |
|---|---|
| `app.py` | Kirish, ro'yxatdan o'tish, parolni tiklash, xato sahifalari |
| `learn.py` | O'quvchi paneli |
| `admin.py` | Admin paneli |
| `common.py` | Sozlamalar, baza sxemasi |
| `bootstrap.py` | Ishga tushishda bazani tayyorlash |
| `seed.py`, `seed_topics.py`, `seed_exams.py` | Dastlabki ma'lumotlar: 10 ta mavzu (160 savol), olimpiada 30, sertifikat 35, DTM 10+30 |
| `create_admin.py` | Admin hisobini ochish yoki parolini almashtirish |
| `demo.py` | Lokal demo (serverda ishlatilmaydi) |
| `tests/` | Testlar: `python -m unittest` |

Dastlabki ma'lumotlar baza bo'sh bo'lganda bir marta yoziladi. Mavjud bazani ular bilan almashtirish:
`python seed.py --replace` (natijalar o'chadi, foydalanuvchilar saqlanadi, eski bazadan nusxa olinadi).
Kontentni darslik bilan solishtirib chiqing.

**Muhim:** baza va yuklangan fayllar `data/` papkasida. Serverda bu papka doimiy diskda bo'lishi shart
(masalan, Render'da Persistent Disk), aks holda har qayta joylashda ma'lumotlar yo'qoladi.

---

# Tarix Ustoz: o'quv jarayoni

## O'quvchi
- **Bosh sahifa** (`/dashboard`): birinchi kirishda diagnostika taklif qilinadi (`/welcome`). Bilish foizi yetarli mavzular chiqarib tashlanib, qolganlaridan dars reja tuziladi. Rad etilsa, dars reja barcha mavzulardan tuziladi. Diagnostika faqat bir marta ishlanadi. Yakunlanmagan testlar ham shu yerdan davom ettiriladi.
- **Dars**: materiallar (matn, rasm, havola, fayl), keyin mavzu testi. O'tish foizi to'planmasa, materiallar qaytadan o'qiladi va test yana topshiriladi. Keyingi dars oldingisidan o'tgach ochiladi.
- **Bitta savol bitta o'quvchiga faqat bir marta tushadi** (diagnostika va mavzu testlarida). Yangi savol qolmasa, test admin savol qo'shguncha yopiladi. Testlar bo'limida avval yangi savollar beriladi, yetmasa avvalgilari bilan to'ldiriladi.
- **Testlar**: Olimpiada, Milliy sertifikat, DTM (majburiy 10 + spes 30). Istalgan vaqtda ishlanadi.
- **Natijalarim** (`/results`): qatorni bosib natija va xatolar tahlili ochiladi.
- **Xatolarim** (`/mistakes`): mavzu testidan birinchi urinishda o'tilmagan mavzular; «Qayta o'zlashtirish» tugmasi mavzuni qaytadan boshlaydi.
- **Profil** (`/profile`).

## Admin
- **Mavzular** (`/admin`): yaratish, tartiblash, tahrirlash, o'chirish. Ichida: matn va rasmli materiallar (rasm 5 MB gacha), havolalar, Word/PDF fayllar (20 MB gacha), test savollari (bittalab, Excel yoki matndan), test vaqti va 1 savol balli.
- **Testlar** (`/admin/exams`): olimpiada, milliy sertifikat, DTM. Har bir testda ball va vaqt kiritiladi.
- **Test sozlamalari** (`/admin/settings`): savollar soni, o'tish foizi, diagnostikada qaysi mavzulardan nechta savol tushishi, bilish foizi.
- **Foydalanuvchilar** (`/admin/users`), **Profil** (`/admin/profile`).
- **Excel namunalari**: `/admin/template/topic.xlsx` va `/admin/template/exam.xlsx`.
- Admin va o'quvchi panellari alohida: admin o'quvchi sahifalariga, o'quvchi `/admin` ga kira olmaydi.

Testlarni ishga tushirish: `python -m unittest`. Standart qiymatlarni amaldagi qoidalar bilan tekshirib chiqing.
