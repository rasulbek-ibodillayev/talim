# Telegram bot orqali tasdiqlanadigan ro'yxatdan o'tish tizimi

Sayt (Flask) + Telegram bot (aiogram) + SQLite. Ikkalasi bitta `data/app.db` faylidan foydalanadi.

## Ish tartibi

1. **Ro'yxatdan o'tish** → telefon raqam kiritiladi.
2. Sayt **1-kod** (8 belgi) va bot manzilini beradi (muddati 10 daqiqa).
3. Foydalanuvchi botga 1-kodni yuboradi (yoki "Botni ochish" tugmasini bosadi).
4. Bot **2-kod** beradi. U `HMAC-SHA256(CODE_SECRET, 1-kod + telefon)` asosida hisoblanadi.
5. Foydalanuvchi 2-kodni saytga kiritadi, sayt qayta hisoblab solishtiradi (5 ta urinish).
6. To'g'ri bo'lsa: ism, familiya, hudud, parol (2 marta) so'raladi va bazaga yoziladi.
7. **Kirish**: telefon raqam + parol.

2-kodni faqat `CODE_SECRET`ni biladigan bot hisoblay oladi, shuning uchun foydalanuvchi botdan o'tmasdan davom eta olmaydi.

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `app.py` | Sayt backend (Flask API + sahifalar) |
| `bot.py` | Telegram bot |
| `common.py` | Sozlamalar, baza, kod algoritmi (`make_code_b`) |
| `templates/`, `static/` | Frontend (HTML, CSS, JS) |
| `Dockerfile`, `docker-compose.yml` | Serverga joylash |

## Sozlash

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # FLASK_SECRET uchun
python -c "import secrets; print(secrets.token_hex(32))"   # CODE_SECRET uchun
```

`.env` ichiga `BOT_TOKEN` (BotFather'dan), `BOT_USERNAME`, `FLASK_SECRET`, `CODE_SECRET` ni yozing.

## Ishga tushirish

### A) Docker (tavsiya etiladi)

```bash
docker compose up -d --build
```

Sayt: `http://SERVER_IP:8000`

### B) Docker'siz

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

gunicorn -w 2 -b 127.0.0.1:8000 app:app      # 1-terminal (sayt)
python bot.py                                 # 2-terminal (bot)
```

Doimiy ishlashi uchun `systemd` yoki `supervisor` ishlating.

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

## Maxsus usulni o'zgartirish

2-kod `common.py` ichidagi `make_code_b(code_a, phone)` funksiyasida hisoblanadi. Boshqa formula
xohlasangiz, faqat shu funksiyani o'zgartiring, sayt ham, bot ham avtomatik yangisini ishlatadi.

## Qo'shimcha: telefon raqamni haqiqiy tasdiqlash

`.env`da `REQUIRE_PHONE_MATCH=1` qilsangiz, bot Telegram akkaunt raqamini so'raydi va u saytda
kiritilgan raqamga mos bo'lishi shart. Shunda birovning raqami bilan ro'yxatdan o'tib bo'lmaydi.
Oddiy rejimda (`0`) bot faqat kodni tekshiradi, raqam egaligi tasdiqlanmaydi.

## Xavfsizlik

- Parollar `werkzeug` orqali xeshlanadi (scrypt/pbkdf2).
- Kodlar bir martalik, 10 daqiqalik; noto'g'ri kiritish 5 martadan keyin bloklanadi.
- Kirish, kod olish va bot so'rovlari uchun tezlik chegarasi bor.
- Barcha POST so'rovlar faqat JSON qabul qiladi, cookie `HttpOnly` + `SameSite=Lax`.
- SQLite kichik/o'rta yuklama uchun yetarli. Katta yuklamada PostgreSQL'ga o'ting.
- `.env` va `data/` papkasini hech qachon ommaga chiqarmang.

---

# O'quv platformasi (Tarix fani)

Ro'yxatdan o'tgach foydalanuvchi shaxsiy kabinetga tushadi.

## Foydalanuvchi uchun

1. **Profil** (`/profile`): ism, familiya, hudud, tug'ilgan yil, o'qish joyi, o'zi haqida, **rasm** (JPG/PNG/WEBP, 2 MB gacha), parolni o'zgartirish. Login (telefon raqam) o'zgarmaydi.
2. **Diagnostik test** (`/diagnostic`): har bir mavzudan 3 tadan tasodifiy savol. Javob variantlari har safar aralashtiriladi.
3. **Natija**: mavzular bo'yicha foizlar. `PASS_PERCENT` (standart 60%) dan past mavzular **"o'rganish tavsiya etiladi"** deb belgilanadi va o'quv yo'lida birinchi turadi.
4. **Mavzu** (`/topic/<id>`): materiallar bilan tanishib, har birini "O'qib chiqdim" deb belgilaydi.
5. **Mavzu testi**: barcha materiallar o'qilgandan keyin ochiladi. Kamida `PASS_PERCENT` to'plansa mavzu "o'zlashtirilgan" bo'ladi, aks holda qayta urinish mumkin.
6. Har bir testdan keyin javoblar tahlili (to'g'ri javob va izoh) ko'rsatiladi.

## Admin uchun (`/admin`)

1. `.env` da `ADMIN_PHONES=+998901234567` yozing (o'zingizning raqamingiz).
2. Shu raqam bilan saytdan ro'yxatdan o'ting: yuqori menyuda **Admin** paydo bo'ladi.
3. Admin panelda: mavzu qo'shish/tahrirlash/yashirish/o'chirish, materiallar (matn + ixtiyoriy havola), savollar (alohida yoki **ommaviy import**), foydalanuvchilar ro'yxati.

Birinchi ishga tushirishda baza bo'sh bo'lsa, **5 ta namunaviy mavzu** (qadimgi davlatlar, islom davri allomalari, Temuriylar, xonliklar va Rossiya istilosi, mustaqillik) va 30 ta savol avtomatik yoziladi.
**Namunaviy kontentni darslik va dasturingiz bilan tekshirib, kerak bo'lsa admin paneldan tahrirlang.** Mavzu qo'shgan sari diagnostik test ham o'zi kengayadi.

### Ommaviy import formati

Har bir savol bo'sh qator bilan ajratiladi:

```
Amir Temur qachon tug'ilgan?
A) 1336-yilda
B) 1370-yilda
C) 1405-yilda
D) 1220-yilda
Javob: A
Izoh: Temur 1336-yilda Keshda tug'ilgan.
```

### Savol turlari
- **Diagnostik** savollar boshlang'ich testda ishlatiladi (har mavzudan 3 tagacha tasodifiy).
- **Mavzu** savollari mavzu testida ishlatiladi (8 tagacha tasodifiy). Har ikki turda ham kamida 3 tadan savol kiriting.

## Yangi fayllar

| Fayl | Vazifasi |
|---|---|
| `learn.py` | Profil, testlar, o'quv yo'li, admin panel |
| `seed.py` | Namunaviy tarix kontenti |
| `web_utils.py` | Umumiy yordamchilar (CSRF, ruxsatlar) |
| `templates/admin/` | Admin sahifalari |
| `static/learn.js` | Test, profil, material o'qish skriptlari |

Yuklangan rasmlar `data/avatars/` papkasida saqlanadi (Docker'da `./data` ulangan, shuning uchun saqlanib qoladi). Zaxira nusxa olishda `data/` papkasining hammasini (baza + rasmlar) saqlang.

## Mavjud bazani yangilash

Eski `data/app.db` ni o'chirish shart emas: ishga tushganda yangi jadvallar va ustunlar o'zi qo'shiladi, ro'yxatdan o'tgan foydalanuvchilar saqlanadi.
