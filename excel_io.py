"""Excel (.xlsx) orqali savollarni import qilish va namunaviy shablon yaratish."""
import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

MAX_ROWS = 2000

# Ustun kaliti -> sarlavhalar (birinchi qator shu nomlardan biri bo'lsa taniladi)
COLUMNS = {
    "text": ("savol", "savol matni", "question"),
    "a": ("a", "a variant", "a varianti"),
    "b": ("b", "b variant", "b varianti"),
    "c": ("c", "c variant", "c varianti"),
    "d": ("d", "d variant", "d varianti"),
    "answer": ("to'g'ri javob", "togri javob", "javob", "answer", "to‘g‘ri javob", "to’g’ri javob"),
    "explanation": ("izoh", "explanation"),
    "section": ("bo'lim", "blok", "bo‘lim", "bo’lim", "section"),
    "topic": ("mavzu", "topic"),
}

TOPIC_HEADERS = ["Savol", "A", "B", "C", "D", "To'g'ri javob", "Izoh"]
EXAM_HEADERS = ["Savol", "A", "B", "C", "D", "To'g'ri javob", "Izoh", "Bo'lim", "Mavzu"]


def _norm(v):
    return " ".join(str(v or "").replace("‘", "'").replace("’", "'").split()).strip().lower()


def build_template(kind, topics=()):
    """kind: 'topic' (mavzu savollari) yoki 'exam' (DTM/olimpiada/sertifikat)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Savollar"
    headers = TOPIC_HEADERS if kind == "topic" else EXAM_HEADERS
    ws.append(headers)
    if kind == "topic":
        ws.append(["Amir Temur qaysi yilda tug'ilgan?", "1336-yilda", "1370-yilda", "1405-yilda", "1220-yilda",
                   "A", "Amir Temur 1336-yilda Kesh yaqinida tug'ilgan."])
        ws.append(["«Boburnoma» asarining muallifi kim?", "Alisher Navoiy", "Zahiriddin Muhammad Bobur",
                   "Mirzo Ulug'bek", "Husayn Boyqaro", "B", ""])
    else:
        ws.append(["Qo'qon xonligi qachon tugatilgan?", "1867-yilda", "1876-yilda", "1873-yilda", "1920-yilda",
                   "B", "1876-yilda Farg'ona viloyati tuzildi.", "Majburiy",
                   topics[0] if topics else ""])
        ws.append(["Turkiston general-gubernatorligi qachon tashkil etilgan?", "1867-yilda", "1876-yilda",
                   "1853-yilda", "1920-yilda", "A", "", "Mutaxassislik", ""])

    head_fill = PatternFill("solid", fgColor="3B4CCA")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center")
    widths = [60, 24, 24, 24, 24, 14, 40, 16, 30]
    for i, w in enumerate(widths[: len(headers)]):
        ws.column_dimensions["ABCDEFGHI"[i]].width = w
    ws.freeze_panes = "A2"

    dv = DataValidation(type="list", formula1='"A,B,C,D"', allow_blank=False)
    dv.add(f"F2:F{MAX_ROWS}")
    ws.add_data_validation(dv)
    if kind != "topic":
        dv2 = DataValidation(type="list", formula1='"Majburiy,Mutaxassislik"', allow_blank=True)
        dv2.add(f"H2:H{MAX_ROWS}")
        ws.add_data_validation(dv2)

    info = wb.create_sheet("Yo'riqnoma")
    lines = [
        "Qanday to'ldiriladi:",
        "1. Har bir qator — bitta savol. Birinchi qator (sarlavhalar) o'zgartirilmasin.",
        "2. A, B, C, D — javob variantlari (to'rttasi ham majburiy, bir-biridan farq qilishi kerak).",
        "3. «To'g'ri javob» ustuniga A, B, C yoki D harfini yozing.",
        "4. «Izoh» ixtiyoriy: test yakunida xato qilgan o'quvchiga ko'rsatiladi.",
    ]
    if kind == "topic":
        lines.append("5. Savollar mavzu testida ham, diagnostikada ham ishlatiladi. Bitta savol o'quvchiga bir marta tushadi.")
    else:
        lines += [
            "5. «Bo'lim» faqat DTM uchun: «Majburiy» yoki «Mutaxassislik». Bo'sh bo'lsa — Majburiy.",
            "6. «Mavzu» ixtiyoriy: sayt dagi mavzu nomi (xatolar tahlilida ishlatiladi).",
        ]
        if topics:
            lines += ["", "Mavjud mavzular:"] + [f"  • {t}" for t in topics]
    for ln in lines:
        info.append([ln])
    info.column_dimensions["A"].width = 110
    info["A1"].font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_xlsx(data, kind, topic_titles=None):
    """Qaytaradi: (savollar ro'yxati, xatolar). Har bir savol — dict:
    text, opts[4], correct(1-4), explanation, section ('a'|'b'), topic_id."""
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        return [], ["Faylni o'qib bo'lmadi. Faqat .xlsx formatidagi Excel fayl yuklang."]
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        return [], ["Fayl bo'sh."]

    idx = {}
    for i, h in enumerate(header or ()):
        h = _norm(h)
        for key, names in COLUMNS.items():
            if h in names and key not in idx:
                idx[key] = i
    if not all(k in idx for k in ("text", "a", "b", "c", "d", "answer")):
        # Sarlavha tanilmadi: ustunlar shablondagi tartibda deb hisoblaymiz
        order = TOPIC_HEADERS if kind == "topic" else EXAM_HEADERS
        keys = ["text", "a", "b", "c", "d", "answer", "explanation", "section", "topic"]
        idx = {k: i for i, k in enumerate(keys[: len(order)])}
        rows = ws.iter_rows(values_only=True)   # birinchi qator ham savol bo'lishi mumkin
        if header and _norm(header[0]) in COLUMNS["text"]:
            next(rows)

    titles = {_norm(t): tid for tid, t in (topic_titles or {}).items()}

    def cell(row, key):
        i = idx.get(key)
        if i is None or i >= len(row) or row[i] is None:
            return ""
        v = row[i]
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        return " ".join(str(v).split())

    out, errors = [], []
    for n, row in enumerate(rows, start=2):
        if n > MAX_ROWS + 1:
            errors.append(f"Faylda {MAX_ROWS} tadan ortiq savol bor, qolganlari o'tkazib yuborildi.")
            break
        if not row or all(v is None or str(v).strip() == "" for v in row):
            continue
        text = cell(row, "text")[:1000]
        opts = [cell(row, k)[:300] for k in "abcd"]
        ans = cell(row, "answer").upper().strip().rstrip(")").strip()
        label = f"{n}-qator"
        if len(text) < 3:
            errors.append(f"{label}: savol matni yo'q.")
            continue
        if not all(opts):
            errors.append(f"{label}: A, B, C, D variantlari to'liq emas.")
            continue
        if len({o.lower() for o in opts}) < 4:
            errors.append(f"{label}: variantlar bir xil bo'lmasligi kerak.")
            continue
        if ans in ("1", "2", "3", "4"):
            correct = int(ans)
        elif ans in ("A", "B", "C", "D"):
            correct = "ABCD".index(ans) + 1
        else:
            match = [i for i, o in enumerate(opts) if o.lower() == cell(row, "answer").lower()]
            if not match:
                errors.append(f"{label}: «To'g'ri javob» ustuniga A, B, C yoki D yozing.")
                continue
            correct = match[0] + 1
        item = {"text": text, "opts": opts, "correct": correct, "explanation": cell(row, "explanation")[:1000],
                "section": "a", "topic_id": None}
        s = _norm(cell(row, "section"))
        if s.startswith(("mutax", "spes", "spets", "b")):
            item["section"] = "b"
        t = _norm(cell(row, "topic"))
        if t:
            item["topic_id"] = titles.get(t)
            if item["topic_id"] is None:
                errors.append(f"{label}: «{cell(row, 'topic')}» mavzusi topilmadi, savol mavzusiz qo'shildi.")
        out.append(item)
    wb.close()
    return out, errors


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def is_xlsx(data):
    return data[:4] == b"PK\x03\x04"
