"""Telegram bot (aiogram 3). Ishga tushirish: python bot.py"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

import common as c

logging.basicConfig(level=logging.INFO)
c.require_secrets()
if not c.BOT_TOKEN:
    raise SystemExit("BOT_TOKEN .env faylda ko'rsatilmagan.")
c.init_db()

bot = Bot(c.BOT_TOKEN)
dp = Dispatcher()

# REQUIRE_PHONE_MATCH=1 bo'lganda: foydalanuvchi kodni yuborgach, telefon raqamini ulashishi kerak
waiting_contact: dict[int, str] = {}

CONTACT_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

MESSAGES = {
    "bad": "❌ Kod noto'g'ri yoki muddati tugagan.\nSaytdan olingan 8 belgili kodni tekshirib qayta yuboring.",
    "other": "⚠️ Bu kod boshqa Telegram akkauntga bog'langan.",
    "phone_mismatch": "⚠️ Telegram raqamingiz saytda kiritilgan raqamga mos kelmadi.",
    "limit": "⏳ Juda ko'p urinish. Bir necha daqiqadan keyin qayta urinib ko'ring.",
}


def result_text(code_b: str) -> str:
    return (
        "✅ Tayyor! Sizning yangi kodingiz:\n\n"
        f"<code>{c.format_code(code_b)}</code>\n\n"
        "Shu kodni saytdagi maydonga kiriting. Kod faqat sizning ro'yxatdan o'tishingiz uchun."
    )


def process(tg_id: int, text: str, phone: str | None = None):
    conn = c.get_db()
    try:
        return c.claim_code(conn, tg_id, text, phone)
    finally:
        conn.close()


async def answer_status(m: types.Message, status: str, value, code_raw: str):
    if status == "ok":
        waiting_contact.pop(m.from_user.id, None)
        await m.answer(result_text(value), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    elif status == "need_contact":
        waiting_contact[m.from_user.id] = code_raw
        await m.answer(
            "Xavfsizlik uchun telefon raqamingizni tasdiqlang. Pastdagi tugmani bosing 👇",
            reply_markup=CONTACT_KB,
        )
    else:
        await m.answer(MESSAGES[status], reply_markup=ReplyKeyboardRemove())


@dp.message(CommandStart())
async def start(m: types.Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) == 2:  # t.me/bot?start=KOD ssilkasi orqali kelgan
        status, value = await asyncio.to_thread(process, m.from_user.id, parts[1])
        return await answer_status(m, status, value, parts[1])
    await m.answer(
        "Assalomu alaykum! 👋\n\n"
        "Saytda ro'yxatdan o'tishda berilgan <b>8 belgili kodni</b> shu yerga yuboring, "
        "men sizga yangi kod beraman.",
        parse_mode="HTML",
    )


@dp.message(F.contact)
async def contact(m: types.Message):
    code_raw = waiting_contact.get(m.from_user.id)
    # Faqat o'zining kontaktini yuborgan bo'lsa qabul qilinadi
    if not code_raw or m.contact.user_id != m.from_user.id:
        return await m.answer("Avval saytdagi kodni yuboring, so'ng o'zingizning raqamingizni ulashing.")
    status, value = await asyncio.to_thread(process, m.from_user.id, code_raw, m.contact.phone_number)
    await answer_status(m, status, value, code_raw)


@dp.message(F.text)
async def handle_code(m: types.Message):
    status, value = await asyncio.to_thread(process, m.from_user.id, m.text)
    await answer_status(m, status, value, m.text)


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
