"""Dastlabki imtihon testlari: olimpiada, milliy sertifikat, DTM (majburiy 10 + mutaxassislik 30).

Savol qatori:  mavzu raqami (1-10, 0 = mavzusiz) | savol | TO'G'RI javob | noto'g'ri | noto'g'ri | noto'g'ri
Mavzu raqami seed_topics.TOPICS dagi tartib. Kontentni amaldagi dastur bilan solishtirib chiqing.
"""

EXAMS = [
    {
        "kind": "olympiad", "title": "Olimpiada: saralash bosqichi", "time_limit": 90, "points_a": 1.0, "points_b": 0,
        "description": "Tarix fanidan olimpiadaga tayyorlanuvchilar uchun chuqurroq bilim talab qiladigan savollar.",
        "a": """
1|Ko'lbuloq manzilgohi qaysi viloyat hududida joylashgan?|Toshkent|Buxoro|Xorazm|Navoiy
1|Surxondaryodagi Jarqo'ton yodgorligi qaysi davrga oid?|Bronza|Paleolit|Mezolit|Neolit
2|Baqtriyaning bosh shahri Baqtra hozirgi qaysi shahar o'rnida bo'lgan?|Balx|Marv|Hirot|Termiz
2|Spitamen makedonlarni mag'lub etgan Politimet daryosi hozir qanday ataladi?|Zarafshon|Amudaryo|Sirdaryo|Qashqadaryo
2|Ahamoniylar shohi Doro I qaysi yillarda hukmronlik qilgan?|Mil. avv. 522–486-yillarda|Mil. avv. 558–530-yillarda|Mil. avv. 336–330-yillarda|Mil. avv. 486–465-yillarda
3|Kushon-baqtriya yozuvi qaysi alifbo asosida shakllangan?|Yunon|Arab|Hind (braxmi)|Xitoy
3|Antik davrga oid Qo'yqirilganqal'a yodgorligi qayerda joylashgan?|Xorazmda|Farg'onada|Surxondaryoda|Buxoroda
3|Musiqachilar tasviri tushirilgan Ayritom yodgorligi qaysi viloyatda?|Surxondaryo|Samarqand|Xorazm|Farg'ona
4|Buminning ukasi, turklarning g'arbiy yurishlariga boshchilik qilgan hukmdor kim?|Istami|Muqan|Peroz|Abruy
4|Narshaxiy «Buxoro tarixi»ni qaysi Somoniy hukmdorga bag'ishlagan?|Nuh ibn Nasr|Ismoil Somoniy|Mansur ibn Nuh|Nasr ibn Ahmad
4|751-yilgi Talas jangida arablar qaysi davlat qo'shinini yengan?|Xitoy (Tan) qo'shinini|Vizantiya qo'shinini|Eron qo'shinini|Hind qo'shinini
4|Abbosiylarning hokimiyatga kelishida hal qiluvchi rol o'ynagan Xurosonlik sarkarda kim?|Abu Muslim|Qutayba ibn Muslim|Nasr ibn Sayyor|Rofe ibn Lays
5|Tabariy tarixini fors tiliga tarjima qilgan Somoniylar vaziri kim?|Bal'amiy|Nizomulmulk|Jayhoniy|Juvayniy
5|«Ma'mun akademiyasi» qaysi shaharda faoliyat yuritgan?|Gurganjda (Urganchda)|Buxoroda|Samarqandda|G'aznada
5|«Siyosatnoma» asarining muallifi kim?|Nizomulmulk|Beruniy|Forobiy|Juvayniy
5|Ahmad al-Farg'oniy Yevropada qaysi nom bilan mashhur bo'lgan?|Alfraganus|Avitsenna|Algoritmus|Averroes
5|Abu Ali ibn Sino Yevropada qaysi nom bilan tanilgan?|Avitsenna|Alfraganus|Averroes|Algoritmus
6|Muhammad an-Nasaviy asarining nomi qaysi?|Siyrat as-sulton Jaloliddin Mankburni|Tarixi jahongushoy|Jome' ut-tavorix|Zafarnoma
6|«Tarixi jahongushoy» asarining muallifi kim?|Juvayniy|Rashididdin|Nasaviy|Ibn al-Asir
6|Soliq va majburiyatlardan ozod qiluvchi yorliq qanday atalgan?|Tarxon yorlig'i|Suyurg'ol yorlig'i|Vaqf yorlig'i|Iqto yorlig'i
7|Amir Temur topshirig'i bilan dastlabki «Zafarnoma»ni yozgan tarixchi kim?|Nizomiddin Shomiy|Sharafiddin Ali Yazdiy|Hofizi Abru|Ibn Arabshoh
7|«Matlai sa'dayn va majmai bahrayn» asarining muallifi kim?|Abdurazzoq Samarqandiy|Mirxond|Xondamir|Hofizi Abru
7|Mirzo Ulug'bekning tarixga oid asari qaysi?|To'rt ulus tarixi|Shajarayi turk|Boburnoma|Temur tuzuklari
7|Amir Temurning davlat boshqaruvi qoidalari bayon qilingan asar qaysi?|Temur tuzuklari|Siyosatnoma|Qutadg'u bilig|Yaso
8|«Abdullanoma» asarining muallifi kim?|Hofiz Tanish Buxoriy|Muhammad Solih|Kamoliddin Binoiy|Ogahiy
8|«Shayboniynoma» dostonini yozgan shoir kim?|Muhammad Solih|Hofiz Tanish Buxoriy|Ogahiy|Turdi Farog'iy
8|Xiva tarixiga oid «Firdavs ul-iqbol» asarini kim boshlab yozgan?|Munis|Ogahiy|Abulg'ozixon|Bayoniy
9|1906-yilda Toshkentda chiqqan «Taraqqiy» gazetasining muharriri kim?|Ismoil Obidiy|Munavvarqori|Abdulla Avloniy|Behbudiy
9|Xivada 1874-yilda toshbosma tashkil etgan xon kim?|Muhammad Rahimxon II (Feruz)|Olloqulixon|Muhammad Aminxon|Asfandiyorxon
0|1648-yilgi Vestfaliya sulhi qaysi urushga yakun yasagan?|O'ttiz yillik urushga|Yuz yillik urushga|Shimoliy urushga|Yetti yillik urushga
""",
    },
    {
        "kind": "certificate", "title": "Milliy sertifikat: namunaviy test", "time_limit": 120, "points_a": 1.0, "points_b": 0,
        "description": "Milliy sertifikat imtihoniga tayyorgarlik uchun 35 ta savol. Yakunda xatolaringiz tahlil qilinadi.",
        "a": """
1|A. P. Okladnikov Teshiktosh g'orini qachon tadqiq qilib, bola qoldiqlarini topgan?|1938-yilda|1912-yilda|1950-yilda|1966-yilda
1|«Eneolit» qaysi davrni anglatadi?|Mis-tosh davrini|Qadimgi tosh davrini|Temir davrini|O'rta tosh davrini
1|Xalqlarning turmush tarzi va urf-odatlarini qaysi fan o'rganadi?|Etnografiya|Numizmatika|Geraldika|Epigrafika
2|Malika To'maris qaysi qabilalarga yetakchilik qilgan?|Massagetlarga|Yuechjilarga|Eftallarga|Qarluqlarga
2|Zardushtiylik dinining asoschisi kim?|Zardusht|Moniy|Mazdak|Budda
2|Aleksandr Makedonskiyning ustozi bo'lgan faylasuf kim?|Aristotel|Platon|Suqrot|Demokrit
3|Kanishka qaysi davlat hukmdori bo'lgan?|Kushon podsholigi|Parfiya|Davan|Qang'
3|Parfiya davlatini qaysi sulola boshqargan?|Arshakiylar|Sosoniylar|Ahamoniylar|Salavkiylar
3|Buyuk ipak yo'li nomiga sabab bo'lgan asosiy tovar qayerdan olib kelingan?|Xitoydan|Hindistondan|Vizantiyadan|Misrdan
4|Eftallar davlati qaysi asrlarda hukm surgan?|V–VI asrlarda|II–III asrlarda|VIII–IX asrlarda|X–XI asrlarda
4|Islom dini qaysi asrda vujudga kelgan?|VII asrda|V asrda|VIII asrda|IX asrda
4|Hijriy yil hisobi milodiy qaysi yildan boshlanadi?|622-yildan|570-yildan|632-yildan|712-yildan
4|Varaxsha yodgorligi qaysi viloyatda joylashgan?|Buxoro|Samarqand|Surxondaryo|Xorazm
5|Qoraxoniylar davlatining poytaxtlaridan biri qaysi shahar bo'lgan?|Bolasog'un|G'azna|Nishopur|Hirot
5|Imom at-Termiziy qaysi ilm sohasida mashhur?|Hadis|Tibbiyot|Astronomiya|Matematika
5|«Qonuni Mas'udiy» asarining muallifi kim?|Abu Rayhon Beruniy|Ibn Sino|Forobiy|Muhammad al-Xorazmiy
5|Ismoil Somoniy maqbarasi qaysi shaharda joylashgan?|Buxoro|Samarqand|Termiz|Marv
5|Saljuqiylar davlatining birinchi sultoni kim?|To'g'rulbek|Sulton Sanjar|Alp Arslon|Malikshoh
6|Jo'ji ulusida tashkil topgan davlat qaysi?|Oltin O'rda|Chig'atoy ulusi|Xulokuylar davlati|Yuan davlati
6|Mo'g'ullar bostirib kirgan paytda Xorazmshoh kim edi?|Alouddin Muhammad|Takash|Jaloliddin|Otsiz
6|Jaloliddin Manguberdi qachon halok bo'lgan?|1231-yilda|1221-yilda|1238-yilda|1206-yilda
7|Amir Temur qaysi shaharni poytaxt qilgan?|Samarqandni|Keshni|Hirotni|Buxoroni
7|Amir Temur qurdirgan Oqsaroy qaysi shaharda joylashgan?|Shahrisabz|Samarqand|Buxoro|Turkiston
7|Alisher Navoiy qaysi shaharda tug'ilgan?|Hirot|Samarqand|Mashhad|Andijon
7|Mirzo Ulug'bek rasadxonasi qaysi shaharda qurilgan?|Samarqand|Hirot|Buxoro|Shahrisabz
7|«Boburnoma» asarining muallifi kim?|Zahiriddin Muhammad Bobur|Gulbadanbegim|Xondamir|Mirzo Haydar
8|Mang'itlar sulolasi hukmdorlari qanday unvon bilan atalgan?|Amir|Podsho|Sulton|Xoqon
8|XIX asr boshidan Xiva xonligini qaysi sulola boshqargan?|Qo'ng'irotlar|Mang'itlar|Minglar|Ashtarxoniylar
9|General Chernyayev 1865-yilda qaysi shaharni egallagan?|Toshkentni|Samarqandni|Qo'qonni|Xivani
9|Munavvarqori Abdurashidxonov yangi usul maktabini qaysi shaharda ochgan?|Toshkentda|Samarqandda|Qo'qonda|Buxoroda
9|Turkiston muxtoriyati qachon tugatilgan?|1918-yil fevralida|1917-yil noyabrida|1920-yil sentabrida|1924-yil oktabrida
10|Sharof Rashidov O'zbekistonga qaysi yillarda rahbarlik qilgan?|1959–1983-yillarda|1937–1950-yillarda|1983–1989-yillarda|1989–1991-yillarda
10|O'zbekiston Respublikasi Davlat madhiyasi qachon qabul qilingan?|1992-yil 10-dekabrda|1991-yil 18-noyabrda|1992-yil 2-iyulda|1992-yil 2-martda
10|2016-yil 4-dekabrda O'zbekiston Prezidenti etib kim saylangan?|Shavkat Mirziyoyev|Islom Karimov|Nig'matilla Yo'ldoshev|Abdulla Oripov
0|Yevropa Ittifoqini tashkil etgan 1992-yilgi shartnoma qaysi?|Maastrixt shartnomasi|Rim shartnomasi|Versal shartnomasi|Lissabon shartnomasi
""",
    },
    {
        "kind": "dtm", "title": "DTM namunaviy test №1", "time_limit": 80, "points_a": 1.1, "points_b": 3.1,
        "description": "Majburiy blok: O'zbekiston tarixidan 10 ta savol. Mutaxassislik bloki: O'zbekiston va jahon tarixidan 30 ta savol.",
        "a": """
1|«Neolit» atamasi qanday ma'noni bildiradi?|Yangi tosh davri|Qadimgi tosh davri|O'rta tosh davri|Temir davri
2|Zardushtiylikning axloqiy asosini tashkil etgan uchlik qaysi?|Ezgu fikr, ezgu so'z, ezgu amal|Sabr, shukr, qanoat|Ilm, mehnat, jasorat|Tinchlik, boylik, sog'liq
3|Kushon davri yodgorligi Fayoztepa qaysi shahar yaqinida joylashgan?|Termiz|Samarqand|Buxoro|Urganch
4|Muqanna qo'zg'oloni qaysi davlat hukmronligiga qarshi ko'tarilgan?|Arab xalifaligi|Turk xoqonligi|Eron Sosoniylari|Mo'g'ullar
5|Abu Rayhon Beruniy qaysi shaharda tug'ilgan?|Kat|Afshona|Farob|Kesh
6|Jaloliddin Manguberdi qaysi sulola vakili edi?|Xorazmshohlar|Qoraxoniylar|G'aznaviylar|Saljuqiylar
7|Mirzo Ulug'bek kimning o'g'li bo'lgan?|Shohruxning|Amir Temurning|Mironshohning|Umarshayxning
8|Tarixchi Abulg'ozixon qaysi davlat hukmdori bo'lgan?|Xiva xonligi|Buxoro xonligi|Qo'qon xonligi|Qozoq xonligi
9|Jadidlar ochgan maktablar qanday nom bilan mashhur?|Yangi usul maktablari|Rus-tuzem maktablari|Madrasa maktablari|Yakshanba maktablari
10|O'zbekiston Respublikasi Davlat gerbi qachon qabul qilingan?|1992-yil 2-iyulda|1991-yil 18-noyabrda|1992-yil 10-dekabrda|1992-yil 8-dekabrda
""",
        "b": """
1|Omonqo'ton g'or-manzilgohi qaysi viloyatda joylashgan?|Samarqand|Surxondaryo|Navoiy|Farg'ona
1|Bronza davriga oid Zamonbobo madaniyati qayerda tarqalgan?|Quyi Zarafshonda|Farg'ona vodiysida|Surxon vohasida|Ustyurtda
2|Zardushtiylarning olov ibodatxonasi qanday atalgan?|Otashkada|Masjid|Sinagoga|Stupa
2|Ahamoniylar davlatiga kim barham bergan?|Aleksandr Makedonskiy|Salavk I|Kanishka|Yuliy Sezar
3|Buyuk ipak yo'li Xitoyning qaysi qadimgi shahridan boshlangan?|Chan'an|Nankin|Pekin|Shanxay
3|Xitoy manbalarida «samoviy otlar» bilan mashhur bo'lgan davlat qaysi?|Davan|Parfiya|Kushon|Salavkiylar
4|Mug' tog'idan topilgan hujjatlar qaysi hokimning arxivi hisoblanadi?|Devashtichning|G'urakning|Varxumanning|Abruyning
4|Qadimgi turkiy bitiklar qanday nom bilan mashhur?|O'rxun-Enasoy bitiklari|Bahistun bitiklari|Rozetta bitiklari|Ashoka bitiklari
5|«Bayt ul-hikma» ilmiy markazi qaysi shaharda faoliyat yuritgan?|Bag'dodda|Damashqda|Qohirada|Buxoroda
5|«Al-Jome' as-sahih» hadislar to'plamining muallifi kim?|Imom al-Buxoriy|Imom at-Termiziy|Burhoniddin Marg'inoniy|Abu Mansur Moturidiy
5|Beruniyning «Hindiston» asari qaysi hukmdor davrida yozilgan?|G'aznaviylar davrida|Temuriylar davrida|Shayboniylar davrida|Ashtarxoniylar davrida
6|Xorazmshoh Alouddin Muhammad qayerda vafot etgan?|Kaspiy dengizidagi orolda|Urganchda|Sind bo'yida|O'trorda
6|Mo'g'ullar davrida Movarounnahrning dastlabki noibi kim bo'lgan?|Mahmud Yalavoch|Mas'udbek|Kebekxon|G'oyirxon
7|Amir Temur tug'ilgan qishloq qaysi?|Xo'ja Ilg'or|Afshona|Kat|Tarob
7|Amir Temur 1398-yilda qaysi mamlakatga yurish qilgan?|Hindistonga|Xitoyga|Misrga|Rossiyaga
7|Temuriylar davrida xizmat evaziga berilgan yer mulki qanday atalgan?|Suyurg'ol|Vaqf|Tanho|Xolisa
8|Muhammad Rahimbiy qaysi sulolaga asos solgan?|Mang'itlar|Minglar|Qo'ng'irotlar|Shayboniylar
8|Munis va Ogahiy qaysi xonlik tarixini yozgan?|Xiva|Buxoro|Qo'qon|Qozoq
9|1868-yilda Buxoro qo'shini mag'lubiyatga uchragan hal qiluvchi jang qaysi?|Zirabuloq jangi|Parvon jangi|Katvon jangi|Loy jangi
9|Turkiston muxtoriyati hukumatini Tinishboyevdan keyin kim boshqargan?|Mustafo Cho'qayev|Munavvarqori|Behbudiy|Fayzulla Xo'jayev
10|O'zbekiston Respublikasining birinchi Prezidenti kim?|Islom Karimov|Shavkat Mirziyoyev|Sharof Rashidov|Usmon Yusupov
0|Qadimgi Misr hukmdorlari qanday atalgan?|Fir'avn|Konsul|Imperator|Raja
0|G'arbiy Rim imperiyasi qachon qulagan?|476-yilda|395-yilda|313-yilda|1453-yilda
0|1215-yilda «Buyuk erkinlik xartiyasi» qaysi davlatda qabul qilingan?|Angliyada|Fransiyada|Ispaniyada|Germaniyada
0|Xristofor Kolumb Amerika qirg'oqlariga qachon yetib borgan?|1492-yilda|1453-yilda|1498-yilda|1519-yilda
0|Buyuk fransuz inqilobi qachon boshlangan?|1789-yilda|1776-yilda|1804-yilda|1848-yilda
0|AQSH Mustaqillik deklaratsiyasi qachon qabul qilingan?|1776-yil 4-iyulda|1783-yil 3-sentabrda|1787-yil 17-sentabrda|1861-yil 12-aprelda
0|Birinchi jahon urushi qaysi yillarda bo'lgan?|1914–1918-yillarda|1904–1905-yillarda|1939–1945-yillarda|1912–1913-yillarda
0|Ikkinchi jahon urushi qachon boshlangan?|1939-yil 1-sentabrda|1941-yil 22-iyunda|1938-yil 29-sentabrda|1940-yil 10-mayda
0|Birlashgan Millatlar Tashkiloti qachon tashkil etilgan?|1945-yilda|1919-yilda|1939-yilda|1949-yilda
""",
    },
]
