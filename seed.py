"""Namunaviy tarix kontenti (O'zbekiston tarixi). Faqat baza bo'sh bo'lganda bir marta yoziladi.

Muhim: bu namuna. Admin panel (/admin) orqali mavzu, material va savollarni tahrirlang,
o'chiring yoki o'z darsliklaringiz asosida yangilarini qo'shing.

Savol formati: (savol, TO'G'RI javob, noto'g'ri1, noto'g'ri2, noto'g'ri3, izoh)
"""
import random
import time

TOPICS = [
    {
        "title": "Qadimgi davlatlar va Buyuk ipak yo'li",
        "summary": "Baqtriya, So'g'diyona, Xorazm, Ahamoniylar, Iskandar yurishi, Kushon podsholigi va Buyuk ipak yo'li.",
        "materials": [
            (
                "Qadimgi davlatlar",
                "Hozirgi O'zbekiston hududida eng qadimgi davlatlar miloddan avvalgi I ming yillikda shakllangan. Ularning eng muhimlari Baqtriya, So'g'diyona va Xorazm edi. Bu o'lkalar dehqonchilik, hunarmandchilik va karvon savdosi bilan mashhur bo'lgan.\n\n"
                "Miloddan avvalgi VI asrda Kir II asos solgan Ahamoniylar davlati Markaziy Osiyoning katta qismini o'ziga bo'ysundirdi. Doro I davridagi Bahistun yozuvida Baqtriya, So'g'diyona va Xorazm Ahamoniylar tarkibidagi o'lkalar sifatida tilga olinadi.\n\n"
                "Markaziy Osiyoda zardushtiylik dini keng tarqalgan edi. Uning muqaddas kitobi — «Avesto».",
            ),
            (
                "Iskandar yurishi, Kushonlar va Buyuk ipak yo'li",
                "Miloddan avvalgi 329–327-yillarda Makedoniyalik Iskandar Markaziy Osiyoga bostirib kirdi. Unga qarshi kurashga so'g'diylar orasida Spitamen boshchilik qildi. Keyinchalik bu hududda Salavkiylar va Yunon-Baqtriya podsholigi hukm surdi.\n\n"
                "Miloddan avvalgi II asrda xitoylik elchi Chjan Szyan Farg'ona vodiysiga yetib keldi. Shundan keyin Sharq va G'arbni bog'lovchi Buyuk ipak yo'li rivojlandi. Samarqand va Buxoro kabi shaharlar bu yo'lda muhim savdo markazlari bo'lgan.\n\n"
                "Milodiy I–III asrlarda Kushon podsholigi gullab-yashnadi. Uning mashhur hukmdori Kanishka bo'lgan.",
            ),
        ],
        "diag": [
            ("«Avesto» qaysi dinning muqaddas kitobi?", "Zardushtiylik", "Islom", "Buddaviylik", "Xristianlik",
             "«Avesto» zardushtiylik dinining muqaddas kitobidir."),
            ("Makedoniyalik Iskandarga qarshi kurashga so'g'diylar orasida kim boshchilik qilgan?", "Spitamen", "Kir II", "Doro I", "Kanishka",
             "Iskandarga qarshi kurash (m.a. 329–327) so'g'diylar yo'lboshchisi Spitamen nomi bilan bog'liq."),
            ("Buyuk ipak yo'li nimani bog'lagan?", "Sharq va G'arbni", "Faqat Hindiston va Eronni", "Faqat Rossiya va Xitoyni", "Afrika va Amerikani",
             "Buyuk ipak yo'li Xitoydan O'rta yer dengizigacha bo'lgan savdo yo'llari tizimi bo'lib, Sharq va G'arbni bog'lagan."),
        ],
        "test": [
            ("Ahamoniylar davlatiga kim asos solgan?", "Kir II", "Doro I", "Spitamen", "Kanishka",
             "Ahamoniylar davlatiga miloddan avvalgi VI asrda Kir II asos solgan."),
            ("Kushon podsholigining mashhur hukmdori kim bo'lgan?", "Kanishka", "Spitamen", "Kir II", "Iskandar",
             "Kanishka Kushon podsholigining eng mashhur hukmdorlaridan biridir."),
            ("Iskandar Markaziy Osiyoga qaysi davrda yurish qilgan?", "Miloddan avvalgi 329–327-yillarda", "Miloddan avvalgi 550-yilda", "Milodiy 710-yilda", "Milodiy 1220-yilda",
             "Iskandarning Markaziy Osiyodagi yurishlari miloddan avvalgi 329–327-yillarga to'g'ri keladi."),
        ],
    },
    {
        "title": "Islom davri va Movarounnahr allomalari",
        "summary": "Arab istilosi, Somoniylar davlati hamda al-Xorazmiy, Beruniy, Ibn Sino, Imom al-Buxoriy.",
        "materials": [
            (
                "Arab istilosi va Somoniylar",
                "VII–VIII asrlarda arablar Movarounnahrni bosib oldi. VIII asr boshlarida Qutayba ibn Muslim yurishlari natijasida Buxoro, Samarqand va boshqa shaharlar xalifalik tarkibiga kirdi, islom dini asta-sekin keng tarqaldi.\n\n"
                "IX asrda mahalliy sulolalar kuchaydi. Somoniylar davlatining poytaxti Buxoro bo'ldi. Ismoil Somoniy davrida (892–907) davlat mustahkamlandi. Somoniylar davrida Buxoro ilm-fan va madaniyat markazlaridan biriga aylandi. Davlat 999-yilda tugatildi.",
            ),
            (
                "Buyuk allomalar",
                "Muhammad al-Xorazmiy (taxminan 780–850) — algebra fanining asoschisi. «Al-jabr» so'zi va «algoritm» atamasi uning nomi va asari bilan bog'liq.\n\n"
                "Abu Rayhon Beruniy (973–1048) — qomusiy olim, «Hindiston» hamda «Qadimgi xalqlardan qolgan yodgorliklar» asarlari muallifi.\n\n"
                "Abu Ali ibn Sino (980–1037) — buyuk tabib va faylasuf. Uning «Tib qonunlari» asari asrlar davomida tibbiyot darsligi bo'lgan.\n\n"
                "Imom al-Buxoriy (810–870) — hadis ilmining yirik allomasi, «Al-Jome' as-sahih» to'plami muallifi.",
            ),
        ],
        "diag": [
            ("«Tib qonunlari» asarining muallifi kim?", "Abu Ali ibn Sino", "Beruniy", "Al-Xorazmiy", "Mirzo Ulug'bek",
             "«Tib qonunlari» Abu Ali ibn Sino qalamiga mansub."),
            ("Algebra fanining asoschisi hisoblangan Xorazmlik olim kim?", "Muhammad al-Xorazmiy", "Beruniy", "Ibn Sino", "Alisher Navoiy",
             "Al-Xorazmiy algebra fanining asoschisi sanaladi."),
            ("Somoniylar davlatining poytaxti qaysi shahar edi?", "Buxoro", "Xiva", "Termiz", "Toshkent",
             "Somoniylar davlatining poytaxti Buxoro bo'lgan."),
        ],
        "test": [
            ("«Hindiston» asarining muallifi kim?", "Abu Rayhon Beruniy", "Ibn Sino", "Al-Xorazmiy", "Bobur",
             "«Hindiston» asari Abu Rayhon Beruniy tomonidan yozilgan."),
            ("«Al-Jome' as-sahih» to'plami kimga tegishli?", "Imom al-Buxoriy", "Beruniy", "Ibn Sino", "Amir Temur",
             "«Al-Jome' as-sahih» — Imom al-Buxoriyning mashhur hadislar to'plami."),
            ("Somoniylar davlati qaysi hukmdor davrida mustahkamlangan?", "Ismoil Somoniy", "Qutayba ibn Muslim", "Amir Temur", "Mirzo Ulug'bek",
             "Somoniylar davlati Ismoil Somoniy davrida (892–907) mustahkamlangan."),
        ],
    },
    {
        "title": "Amir Temur va Temuriylar davri",
        "summary": "Amir Temur davlati, Mirzo Ulug'bek, Alisher Navoiy va Zahiriddin Muhammad Bobur.",
        "materials": [
            (
                "Amir Temur davlati",
                "Amir Temur 1336-yilda Kesh (hozirgi Shahrisabz) yaqinida tug'ilgan. 1370-yilda Balxda amir deb e'lon qilindi va Samarqandni o'z davlatining poytaxti qildi.\n\n"
                "Temur Eron, Kavkaz, Hindiston va Old Osiyoga yurishlar qildi. 1402-yilda Ankara yaqinidagi jangda Usmonlilar sultoni Boyazid I ni mag'lub etdi. 1405-yilda Xitoyga yurish chog'ida Otrorda vafot etdi.\n\n"
                "Temur davrida Shahrisabzdagi Oqsaroy, Samarqanddagi Bibixonim masjidi, Go'ri Amir maqbarasi kabi muhtasham me'moriy obidalar bunyod etildi.",
            ),
            (
                "Temuriylar madaniyati",
                "Mirzo Ulug'bek (1394–1449) Samarqandda hukmronlik qildi. U buyuk astronom bo'lib, Samarqandda rasadxona qurdirdi va «Ziji jadidi Ko'ragoniy» asarini yaratdi. Registondagi Ulug'bek madrasasi 1417–1420-yillarda qurilgan.\n\n"
                "Alisher Navoiy (1441–1501) Hirotda yashab ijod etgan, o'zbek adabiy tilining buyuk namoyandasi, «Xamsa» muallifi.\n\n"
                "Zahiriddin Muhammad Bobur (1483–1530) Andijonda tug'ilgan. 1526-yilda Panipat jangida g'alaba qozonib Hindistonda Boburiylar davlatiga asos soldi. U «Boburnoma» asarining muallifi.",
            ),
        ],
        "diag": [
            ("Amir Temur qaysi yilda tug'ilgan?", "1336-yilda", "1370-yilda", "1394-yilda", "1405-yilda",
             "Amir Temur 1336-yilda Kesh yaqinida tug'ilgan."),
            ("Mirzo Ulug'bek qaysi sohada buyuk yutuqlarga erishgan?", "Astronomiya", "Tibbiyot", "Kimyo", "Dengizchilik",
             "Mirzo Ulug'bek buyuk astronom bo'lib, Samarqandda rasadxona qurdirgan."),
            ("«Boburnoma» asarining muallifi kim?", "Zahiriddin Muhammad Bobur", "Alisher Navoiy", "Mirzo Ulug'bek", "Beruniy",
             "«Boburnoma» Zahiriddin Muhammad Bobur asaridir."),
        ],
        "test": [
            ("Amir Temur o'z davlatining poytaxti qilib qaysi shaharni tanlagan?", "Samarqand", "Buxoro", "Xiva", "Hirot",
             "Temur Samarqandni poytaxt qilgan."),
            ("Alisher Navoiyning besh dostondan iborat to'plami qanday nomlanadi?", "Xamsa", "Boburnoma", "Avesto", "Devonu lug'otit turk",
             "Navoiyning besh dostonidan iborat to'plami «Xamsa» deb ataladi."),
            ("Bobur Hindistonda Boburiylar davlatiga qaysi jangdan so'ng asos solgan?", "Panipat jangi (1526)", "Ankara jangi", "Qatvon jangi", "Talas jangi",
             "Bobur 1526-yilgi Panipat jangidan so'ng Boburiylar davlatiga asos solgan."),
        ],
    },
    {
        "title": "Xonliklar davri va Rossiya istilosi",
        "summary": "Buxoro amirligi, Xiva va Qo'qon xonliklari, Rossiya istilosi va jadidlar harakati.",
        "materials": [
            (
                "Uch xonlik",
                "XVIII asrdan boshlab Movarounnahrda uchta yirik davlat mavjud edi: Buxoro amirligi (mang'itlar sulolasi), Xiva xonligi va Qo'qon xonligi. Qo'qon xonligiga 1709-yilda Shohruxbiy asos solgan.\n\n"
                "Xonliklar o'rtasidagi o'zaro urushlar, markaziy hokimiyatning zaiflashuvi va savdo yo'llarining o'zgarishi ularni zaiflashtirgan, bu esa tashqi bosqinni osonlashtirgan.",
            ),
            (
                "Rossiya istilosi va jadidlar",
                "XIX asr o'rtalarida Rossiya imperiyasi Markaziy Osiyoni bosib ola boshladi. 1865-yilda Toshkent bosib olindi. 1867-yilda Turkiston general-gubernatorligi tuzildi, uning birinchi general-gubernatori K. P. fon Kaufman bo'ldi.\n\n"
                "1868-yilda Buxoro amirligi, 1873-yilda Xiva xonligi Rossiyaga vassal qaramlikka tushdi. 1876-yilda Qo'qon xonligi tugatildi.\n\n"
                "XIX asr oxiri – XX asr boshlarida jadidlar harakati paydo bo'ldi. Mahmudxo'ja Behbudiy, Abdulla Avloniy, Munavvarqori Abdurashidxonov kabi ma'rifatparvarlar yangi usul maktablarini ochdilar.",
            ),
        ],
        "diag": [
            ("Toshkent Rossiya imperiyasi tomonidan qaysi yilda bosib olingan?", "1865-yilda", "1850-yilda", "1876-yilda", "1920-yilda",
             "Toshkent 1865-yilda bosib olingan."),
            ("Qo'qon xonligiga kim asos solgan?", "Shohruxbiy", "Amir Temur", "Ismoil Somoniy", "Kaufman",
             "Qo'qon xonligiga 1709-yilda Shohruxbiy asos solgan."),
            ("Turkiston general-gubernatorligining birinchi general-gubernatori kim bo'lgan?", "K. P. fon Kaufman", "Shohruxbiy", "Behbudiy", "Boyazid I",
             "Birinchi general-gubernator K. P. fon Kaufman bo'lgan (1867)."),
        ],
        "test": [
            ("Qo'qon xonligi qaysi yilda tugatilgan?", "1876-yilda", "1865-yilda", "1868-yilda", "1991-yilda",
             "Qo'qon xonligi 1876-yilda tugatilgan."),
            ("Jadidlar qanday maktablarni ochishgan?", "Yangi usul maktablarini", "Faqat harbiy maktablarni", "Faqat chet tilidagi maktablarni", "Maktablarni ochishga qarshi bo'lishgan",
             "Jadidlar yangi usul (usuli jadid) maktablarini ochgan."),
            ("Quyidagilardan qaysi biri jadid ma'rifatparvari?", "Mahmudxo'ja Behbudiy", "Spitamen", "Kanishka", "Ismoil Somoniy",
             "Mahmudxo'ja Behbudiy jadidchilik harakatining yirik namoyandasi."),
        ],
    },
    {
        "title": "Mustaqillik davri",
        "summary": "O'zbekiston mustaqilligi, Konstitutsiya, milliy valyuta va davlat ramzlari.",
        "materials": [
            (
                "Mustaqillikka erishish",
                "1991-yil 31-avgustda O'zbekiston Oliy Kengashi mustaqillik to'g'risida bayonot qabul qildi. 1-sentabr Mustaqillik kuni sifatida nishonlanadi. O'zbekistonning birinchi Prezidenti Islom Karimov bo'ldi.\n\n"
                "1992-yil 2-martda O'zbekiston Birlashgan Millatlar Tashkilotiga a'zo bo'ldi. 1992-yil 8-dekabrda yangi Konstitutsiya qabul qilindi (8-dekabr — Konstitutsiya kuni). Milliy valyuta — so'm 1994-yil 1-iyulda muomalaga kiritildi.",
            ),
            (
                "Davlat ramzlari",
                "Davlat bayrog'i 1991-yil 18-noyabrda, davlat gerbi esa 1992-yil 2-iyulda qabul qilingan. Davlat ramzlari mamlakatning mustaqilligi va suverenitetining ifodasidir.\n\n"
                "2016-yil dekabrida Shavkat Mirziyoyev O'zbekiston Respublikasi Prezidenti etib saylandi.",
            ),
        ],
        "diag": [
            ("O'zbekistonda Mustaqillik kuni qachon nishonlanadi?", "1-sentabrda", "8-dekabrda", "21-martda", "2-iyulda",
             "Mustaqillik kuni har yili 1-sentabrda nishonlanadi."),
            ("O'zbekistonning birinchi Prezidenti kim?", "Islom Karimov", "Shavkat Mirziyoyev", "Abdulla Oripov", "Mirzo Ulug'bek",
             "O'zbekistonning birinchi Prezidenti Islom Karimov."),
            ("Milliy valyuta — so'm qachon muomalaga kiritilgan?", "1994-yil 1-iyulda", "1991-yil 1-sentabrda", "1992-yil 8-dekabrda", "2016-yil 1-yanvarda",
             "So'm 1994-yil 1-iyulda muomalaga kiritilgan."),
        ],
        "test": [
            ("O'zbekiston Konstitutsiyasi qachon qabul qilingan?", "1992-yil 8-dekabrda", "1991-yil 31-avgustda", "1994-yil 1-iyulda", "2016-yil 4-dekabrda",
             "Konstitutsiya 1992-yil 8-dekabrda qabul qilingan."),
            ("Davlat bayrog'i qachon qabul qilingan?", "1991-yil 18-noyabrda", "1992-yil 2-iyulda", "1994-yil 1-iyulda", "2016-yil dekabrida",
             "Davlat bayrog'i 1991-yil 18-noyabrda qabul qilingan (gerb esa 1992-yil 2-iyulda)."),
            ("O'zbekiston BMTga qachon a'zo bo'lgan?", "1992-yil 2-martda", "1991-yil 1-sentabrda", "1994-yil 1-iyulda", "2001-yilda",
             "O'zbekiston 1992-yil 2-martda BMTga a'zo bo'lgan."),
        ],
    },
]


def _question_row(topic_id, kind, q):
    text, right, w1, w2, w3, expl = q
    opts = [right, w1, w2, w3]
    random.shuffle(opts)
    return (topic_id, kind, text, opts[0], opts[1], opts[2], opts[3], opts.index(right) + 1, expl)


def seed_if_empty(conn):
    done = conn.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone()
    has_topics = conn.execute("SELECT 1 FROM topics LIMIT 1").fetchone()
    if done or has_topics:
        return False
    for pos, t in enumerate(TOPICS, 1):
        cur = conn.execute(
            "INSERT INTO topics(title, summary, position, published) VALUES (?, ?, ?, 1)",
            (t["title"], t["summary"], pos),
        )
        tid = cur.lastrowid
        for mpos, (title, text) in enumerate(t["materials"], 1):
            conn.execute(
                "INSERT INTO materials(topic_id, title, body, url, position) VALUES (?, ?, ?, '', ?)",
                (tid, title, text, mpos),
            )
        for kind in ("diag", "test"):
            for q in t[kind]:
                row = _question_row(tid, "diagnostic" if kind == "diag" else "topic", q)
                conn.execute(
                    "INSERT INTO questions(topic_id, kind, text, o1, o2, o3, o4, correct, explanation) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('seeded', ?)", (str(int(time.time())),))
    conn.commit()
    return True
